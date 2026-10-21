#!/usr/bin/env python3
"""Enforce the project's non-negotiable rules from docs/NORTH_STAR.md.

This is a policy check, not a general linter. It fails when first-party code
starts depending on a billable service, when a credential-shaped literal is
committed, when the shipped model endpoint is not loopback, or when a safety
mechanism named by the North Star is removed.

Run directly, from CI, or from tools/run_quality_gate.py:

    python tools/check_invariants.py
    python tools/check_invariants.py --json
"""
from __future__ import annotations

import argparse
import ast
import ipaddress
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]

# Rules are mapped to the invariant ID they enforce. The document must contain
# every ID below, so a new rule cannot be added without documenting it.
RULE_TO_INVARIANT: dict[str, str] = {
    "NO_PAID_SDK": "P1",
    "NO_BILLABLE_ENDPOINT": "P1",
    "NO_SECRET_LITERAL": "P1",
    "LOOPBACK_MODEL_ONLY": "P2",
    "HONEST_DEGRADATION": "P4",
    "TOOL_SANDBOX_PRESENT": "P5",
    "SAFE_SUBPROCESS": "P8",
}

# Files that intentionally contain provider names or credential-shaped strings
# as detection fixtures. Exemptions are listed in the report so they stay visible.
PATH_EXEMPTIONS: dict[str, str] = {
    "tools/check_invariants.py": "defines the blocked-provider policy itself",
    "tests/test_invariants.py": "contains synthetic violations to test this checker",
}

SKIP_DIRECTORIES = {
    ".git", "node_modules", "__pycache__", ".venv", ".venv-piper-urdu",
    "venv", "dist", "build", "outputs", "workspace", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "htmlcov", "coverage",
}

BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".mp4", ".mov", ".wav",
    ".mp3", ".onnx", ".zip", ".gz", ".tar", ".pdf", ".woff", ".woff2", ".ttf",
    ".otf", ".pyc", ".so", ".dll", ".exe", ".bin",
}

TEXT_SUFFIXES = {
    ".py", ".js", ".mjs", ".ts", ".json", ".md", ".txt", ".yml", ".yaml",
    ".html", ".css", ".ps1", ".bat", ".sh", ".toml", ".cfg", ".ini", "",
}

# Scan for endpoint literals in executable or machine-read files, not in prose.
URL_SCAN_SUFFIXES = {".py", ".js", ".mjs", ".json", ".yml", ".yaml", ".html", ".ps1", ".sh", ".bat"}

MAX_SCAN_BYTES = 2 * 1024 * 1024

BLOCKED_MODULES = {
    "openai", "anthropic", "cohere", "mistralai", "replicate", "together",
    "elevenlabs", "deepgram", "assemblyai", "stability_sdk", "vertexai",
    "groq", "fireworks", "portkey_ai",
}
BLOCKED_MODULE_PREFIXES = ("azure.ai", "google.generativeai", "google.cloud.aiplatform")

# Distinctive substrings that identify hosted-AI packages whose names do not
# normalize to a module name (for example "@anthropic-ai/sdk" -> "anthropic-ai").
BLOCKED_PACKAGE_HINTS = (
    "anthropic", "openai", "generative-ai", "google-genai", "vertexai",
    "elevenlabs", "deepgram", "assemblyai", "replicate", "stability-sdk",
    "mistral", "cohere", "groq", "fireworks-ai", "together-ai",
)

BLOCKED_HOSTS = {
    "api.openai.com", "openai.azure.com", "api.anthropic.com",
    "generativelanguage.googleapis.com", "aiplatform.googleapis.com",
    "api.cohere.ai", "api.cohere.com", "api.mistral.ai", "api.replicate.com",
    "api.elevenlabs.io", "api.deepgram.com", "api.assemblyai.com",
    "api.stability.ai", "api.together.xyz", "api.groq.com", "api.fireworks.ai",
    "api.perplexity.ai", "api.tavily.com", "api-inference.huggingface.co",
    "api.heygean.com", "api.heygen.com", "api.synthesia.io", "api.d-id.com",
    "api.runwayml.com", "api.lumalabs.ai", "fal.run", "api.fal.ai",
}

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai_key", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}")),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghs|ghr)_[A-Za-z0-9]{30,}")),
    ("github_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("huggingface_token", re.compile(r"\bhf_[A-Za-z0-9]{30,}")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
)

PRAGMA_PATTERN = re.compile(r"invariant-allow:\s*([A-Z_]+)")

SHELL_EXECUTION_PATTERNS = (
    re.compile(r"\bshell\s*=\s*True\b"),
    re.compile(r"\bos\.system\s*\("),
    re.compile(r"\bos\.popen\s*\("),
)

HONEST_DEGRADATION_MARKERS: dict[str, tuple[str, ...]] = {
    "agents/orchestrate.py": ("generation_mode", "deterministic_template", "explicit_template_demo"),
    "video_studio/production.py": ("--render-template", "No local model is enabled"),
}

MINIMUM_SANDBOX_MARKERS = ("safe_relative_path", "is_within", "allow_exec")


@dataclass(frozen=True)
class Finding:
    """One failed rule at one location."""

    rule: str
    path: str
    line: int
    message: str

    def as_dict(self) -> dict:
        return {
            "rule": self.rule,
            "invariant": RULE_TO_INVARIANT.get(self.rule, ""),
            "path": self.path,
            "line": self.line,
            "message": self.message,
        }


def _iter_files(root: Path) -> list[Path]:
    """List repository files, preferring git so ignored trees are never scanned."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            capture_output=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        result = None
    names: list[str] = []
    if result is not None and result.returncode == 0 and result.stdout:
        names = [name for name in result.stdout.decode("utf-8", "replace").split("\0") if name]
    if not names:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in SKIP_DIRECTORIES for part in path.relative_to(root).parts):
                continue
            names.append(path.relative_to(root).as_posix())
    files = []
    for name in names:
        candidate = root / name
        if not candidate.is_file():
            continue
        if any(part in SKIP_DIRECTORIES for part in Path(name).parts):
            continue
        if candidate.suffix.lower() in BINARY_SUFFIXES:
            continue
        try:
            if candidate.stat().st_size > MAX_SCAN_BYTES:
                continue
        except OSError:
            continue
        files.append(candidate)
    return sorted(set(files))


def _read_lines(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return text.splitlines()


def _suppressed(line: str, rule: str) -> bool:
    return any(match == rule for match in PRAGMA_PATTERN.findall(line))


def check_imports(path: Path, relative: str) -> list[Finding]:
    """Parse Python imports with the AST so prose and strings cannot trigger it."""
    findings: list[Finding] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=relative)
    except (OSError, SyntaxError, ValueError) as exc:
        return [Finding("NO_PAID_SDK", relative, 1, f"cannot parse module to verify imports: {type(exc).__name__}")]
    for node in ast.walk(tree):
        modules: list[tuple[str, int]] = []
        if isinstance(node, ast.Import):
            modules = [(alias.name, node.lineno) for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules = [(node.module, node.lineno)]
        for module, line in modules:
            lowered = module.lower()
            root_module = lowered.split(".")[0]
            blocked = root_module in BLOCKED_MODULES or any(
                lowered == prefix or lowered.startswith(prefix + ".") for prefix in BLOCKED_MODULE_PREFIXES
            )
            if blocked:
                findings.append(Finding(
                    "NO_PAID_SDK", relative, line,
                    f"imports hosted-AI SDK '{module}'; the project must run without paid services (P1)",
                ))
    return findings


def check_requirements(path: Path, relative: str) -> list[Finding]:
    """Detect hosted-AI packages in requirement files and package.json."""
    findings: list[Finding] = []
    if path.name == "package.json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return findings
        if isinstance(data, dict):
            for section in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
                entries = data.get(section)
                if not isinstance(entries, dict):
                    continue
                for name in entries:
                    normalized = name.lower().removeprefix("@").split("/")[0]
                    blocked = (
                        normalized in BLOCKED_MODULES
                        or any(normalized.startswith(module + "-") for module in BLOCKED_MODULES)
                        or any(module in normalized for module in BLOCKED_MODULE_PREFIXES)
                        or any(hint in normalized for hint in BLOCKED_PACKAGE_HINTS)
                    )
                    if blocked:
                        findings.append(Finding(
                            "NO_PAID_SDK", relative, 0,
                            f"declares hosted-AI package '{name}' (P1)",
                        ))
        return findings
    for index, line in enumerate(_read_lines(path), start=1):
        stripped = line.split("#", 1)[0].strip()
        if not stripped or stripped.startswith("-"):
            continue
        name = re.split(r"[<>=!~;\[\s]", stripped, maxsplit=1)[0].strip().lower()
        if not name:
            continue
        if name in BLOCKED_MODULES or any(name == p or name.startswith(p + ".") for p in BLOCKED_MODULE_PREFIXES):
            findings.append(Finding("NO_PAID_SDK", relative, index, f"requires hosted-AI package '{name}' (P1)"))
    return findings


def check_endpoints(path: Path, relative: str) -> list[Finding]:
    """Block literal billable AI/TTS/vision endpoints in executable or config files."""
    findings: list[Finding] = []
    if path.suffix.lower() not in URL_SCAN_SUFFIXES:
        return findings
    for index, line in enumerate(_read_lines(path), start=1):
        if _suppressed(line, "NO_BILLABLE_ENDPOINT"):
            continue
        lowered = line.lower()
        for host in BLOCKED_HOSTS:
            if host in lowered:
                findings.append(Finding(
                    "NO_BILLABLE_ENDPOINT", relative, index,
                    f"references billable endpoint '{host}'; only the four documented boundaries are allowed (P1/P7)",
                ))
                break
    return findings


def redact(value: str) -> str:
    """Keep enough context to locate a leak without reproducing it."""
    if len(value) <= 10:
        return value[:2] + "***"
    return value[:4] + "…" + value[-2:]


def check_secrets(path: Path, relative: str) -> list[Finding]:
    """Detect high-confidence credential literals in any text file."""
    findings: list[Finding] = []
    for index, line in enumerate(_read_lines(path), start=1):
        if _suppressed(line, "NO_SECRET_LITERAL"):
            continue
        for label, pattern in SECRET_PATTERNS:
            match = pattern.search(line)
            if match:
                findings.append(Finding(
                    "NO_SECRET_LITERAL", relative, index,
                    f"credential-shaped literal ({label}: {redact(match.group(0))}); remove it and rotate the credential (P1)",
                ))
                break
    return findings


def check_loopback_config(root: Path) -> list[Finding]:
    """The shipped example must keep the model disabled and its endpoint loopback."""
    findings: list[Finding] = []
    relative = "config.example.json"
    path = root / relative
    if not path.is_file():
        return [Finding("LOOPBACK_MODEL_ONLY", relative, 0, "config.example.json is missing")]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [Finding("LOOPBACK_MODEL_ONLY", relative, 0, f"config.example.json is not valid JSON: {type(exc).__name__}")]
    model = data.get("model") if isinstance(data, dict) else None
    if not isinstance(model, dict):
        return [Finding("LOOPBACK_MODEL_ONLY", relative, 0, "config.example.json has no model section")]
    if model.get("enabled") is not False:
        findings.append(Finding(
            "LOOPBACK_MODEL_ONLY", relative, 0,
            "example config must ship with model.enabled = false so a fresh checkout never calls anything (P2/P4)",
        ))
    endpoint = model.get("base_url")
    if isinstance(endpoint, str) and endpoint:
        try:
            parts = urlsplit(endpoint)
            address = ipaddress.ip_address(parts.hostname or "")
        except ValueError:
            findings.append(Finding(
                "LOOPBACK_MODEL_ONLY", relative, 0,
                f"model.base_url '{endpoint}' is not a literal IP endpoint",
            ))
        else:
            if (
                parts.scheme != "http"
                or not address.is_loopback
                or parts.port is None
                or parts.username
                or parts.password
                or parts.query
                or parts.fragment
            ):
                findings.append(Finding(
                    "LOOPBACK_MODEL_ONLY", relative, 0,
                    f"model.base_url '{endpoint}' is not plain HTTP on a literal loopback IP with an explicit port (P2)",
                ))
    return findings


def check_markers(root: Path) -> list[Finding]:
    """Verify that safety and honesty mechanisms named by the North Star still exist."""
    findings: list[Finding] = []
    for relative, markers in HONEST_DEGRADATION_MARKERS.items():
        path = root / relative
        text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        for marker in markers:
            if marker not in text:
                findings.append(Finding(
                    "HONEST_DEGRADATION", relative, 0,
                    f"offline-labelling marker '{marker}' is missing; degraded output could be presented as generated work (P4)",
                ))
    runtime = root / "tools" / "tool_runtime.py"
    if not runtime.is_file():
        findings.append(Finding(
            "TOOL_SANDBOX_PRESENT", "tools/tool_runtime.py", 0,
            "the sandboxed tool runtime is missing; agents must not gain file access without confinement (P5)",
        ))
    else:
        text = runtime.read_text(encoding="utf-8", errors="replace")
        for marker in MINIMUM_SANDBOX_MARKERS:
            if marker not in text:
                findings.append(Finding(
                    "TOOL_SANDBOX_PRESENT", "tools/tool_runtime.py", 0,
                    f"confinement marker '{marker}' is missing from the tool runtime (P5/P8)",
                ))
    return findings


def check_shell_execution(path: Path, relative: str) -> list[Finding]:
    """Reject shell-string subprocess execution in first-party modules."""
    findings: list[Finding] = []
    for index, line in enumerate(_read_lines(path), start=1):
        if _suppressed(line, "SAFE_SUBPROCESS"):
            continue
        for pattern in SHELL_EXECUTION_PATTERNS:
            if pattern.search(line):
                findings.append(Finding(
                    "SAFE_SUBPROCESS", relative, index,
                    "uses shell-string execution; pass an argument list and keep the program allowlist (P8)",
                ))
                break
    return findings


def check_documented_rules(root: Path) -> list[Finding]:
    """Fail when a rule exists without a documented invariant, or vice versa."""
    findings: list[Finding] = []
    relative = "docs/NORTH_STAR.md"
    path = root / relative
    if not path.is_file():
        return [Finding("INVARIANT_REGISTRY", relative, 0, "docs/NORTH_STAR.md is missing (P1-P8 have no contract)")]
    text = path.read_text(encoding="utf-8", errors="replace")
    for required in sorted(set(RULE_TO_INVARIANT.values())):
        if required not in text:
            findings.append(Finding(
                "INVARIANT_REGISTRY", relative, 0,
                f"rule set references invariant {required}, but the document does not define it",
            ))
    for rule in sorted(RULE_TO_INVARIANT):
        if rule not in text:
            findings.append(Finding(
                "INVARIANT_REGISTRY", relative, 0,
                f"rule {rule} is enforced by this checker but is not named in the document",
            ))
    return findings


def run_checks(root: Path = ROOT) -> list[Finding]:
    """Run every rule against the repository."""
    findings: list[Finding] = []
    for path in _iter_files(root):
        relative = path.relative_to(root).as_posix()
        if relative in PATH_EXEMPTIONS:
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if path.suffix == ".py":
            findings.extend(check_imports(path, relative))
            findings.extend(check_shell_execution(path, relative))
        if ("requirements" in path.name and path.suffix.lower() == ".txt") or path.name == "package.json":
            findings.extend(check_requirements(path, relative))
        findings.extend(check_endpoints(path, relative))
        findings.extend(check_secrets(path, relative))
    findings.extend(check_loopback_config(root))
    findings.extend(check_markers(root))
    findings.extend(check_documented_rules(root))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT), help="repository root to check")
    parser.add_argument("--json", action="store_true", help="emit a machine-readable report")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2
    findings = run_checks(root)
    report = {
        "schema_version": 1,
        "root": str(root),
        "status": "FAIL" if findings else "PASS",
        "rules": sorted(RULE_TO_INVARIANT),
        "exemptions": PATH_EXEMPTIONS,
        "violations": [finding.as_dict() for finding in findings],
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for finding in findings:
            location = finding.path + (f":{finding.line}" if finding.line else "")
            print(f"FAIL [{finding.rule}] {location}: {finding.message}")
        print(f"\nInvariant check: {len(findings)} violation(s)")
        for path, reason in PATH_EXEMPTIONS.items():
            print(f"  exempt: {path} ({reason})")
        print("PASS" if not findings else "FAIL")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
