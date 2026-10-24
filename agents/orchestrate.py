#!/usr/bin/env python3
"""Run a sequential, local-model specialist pipeline with a persistent audit trail."""
import argparse
import ast
import hashlib
import json
import os
import re
import sys
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
sys.path.insert(0, str(ROOT / "tools"))
from path_utils import canonical_path, is_within, safe_relative_path
import memory
import resources
import review
import test_fix
import tool_agent
WORKSPACE = canonical_path(ROOT / "workspace")
sys.path.insert(0, str(BASE))
import dispatch
import routing

DEFAULT_PIPELINE = [
    "AGENT-02", "AGENT-09", "AGENT-51", "AGENT-31",
    "AGENT-26", "AGENT-08", "AGENT-37",
]


def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:48] or "project"


# Language selection is part of routing: a pipeline's arguments are validated
# against what the narration profile allows, whether a model or a pattern chose
# the pipeline. Re-exported here because existing callers import it from this
# module.
requested_narration_language = routing.requested_narration_language


def configured_narration_language_instruction(config):
    """Describe the configured narration profile for the CEO prompt without guessing."""
    video_config = config.get("video_studio", {}) if isinstance(config, dict) else {}
    if not isinstance(video_config, dict):
        return "The configured narration-language section is invalid; report the configuration error instead of guessing."
    value = str(video_config.get("narration_language", "ur-en")).strip().lower().replace("_", "-")
    if value in {"en", "english", "en-us", "en-gb"}:
        return "The configured default narration language is English. Use English narration and subtitles unless the user explicitly asks for another supported profile."
    if value in {"ur", "urdu", "ur-en", "urdu-english", "urdu-with-english-technical-terms", "ur-pk"}:
        return "The configured default narration language is Pakistani Urdu written in Urdu/Arabic script, with common English technical terms preserved. Use that profile unless the user explicitly requests English."
    return "The configured narration_language value " + repr(value) + " is unsupported. Report this configuration error and do not silently guess or substitute a language."


def extract_quality_gate(text):
    """Accept a quality verdict only when exactly one explicit gate line is present."""
    matches = re.findall(
        r"(?im)^[ \t]*OVERALL QUALITY GATE:[ \t]*(PASS|PARTIAL|FAIL)[ \t]*[.!]?[ \t]*$",
        str(text or ""),
    )
    return matches[0].lower() if len(matches) == 1 else "unconfirmed"


def is_retryable_error(error):
    """Return true only for failures plausibly fixed by one bounded repeat."""
    if isinstance(error, (TimeoutError, ConnectionError)):
        return True
    message = str(error or "").strip().lower()
    if isinstance(error, ValueError) and message == "specialist returned an empty result.":
        # A model may transiently return an empty completion; the retry prompt can recover.
        return True
    transient_markers = (
        "timed out", "temporarily unavailable", "temporary failure",
        "connection reset", "connection aborted", "connection refused",
        "remote disconnected", "rate limit", "too many requests",
        "http 429", "http 500", "http 502", "http 503", "http 504",
        "status 429", "status 500", "status 502", "status 503", "status 504",
        "server busy", "try again later",
    )
    return any(marker in message for marker in transient_markers)


def run_role_with_retry(role, instruction, context, cfg, runner=None):
    """Retry one plausibly transient failure; never repeat deterministic errors unchanged."""
    execute = runner or dispatch.run_role
    try:
        result = execute(role, instruction, context, cfg)
        if not isinstance(result, str) or not result.strip():
            raise ValueError("Specialist returned an empty result.")
        return result, 0
    except Exception as first_error:
        if not is_retryable_error(first_error):
            # Preserve the original exception type while recording that no retry ran.
            try:
                first_error.retry_count = 0
            except Exception:
                pass
            raise
        retry_instruction = (
            instruction
            + "\n\nAUTOMATIC RECOVERY ATTEMPT 2/2. The previous attempt failed with "
            + type(first_error).__name__ + ": " + str(first_error)[:700]
            + ". Re-read the task and supplied evidence, correct the cause, and return the complete deliverable. "
              "Do not claim work succeeded unless you actually produce it. This is the final automatic retry."
        )
        try:
            result = execute(role, retry_instruction, context, cfg)
        except Exception as retry_error:
            # The second exception is still surfaced unchanged for existing callers.
            try:
                retry_error.retry_count = 1
            except Exception:
                pass
            raise
        if not isinstance(result, str) or not result.strip():
            retry_error = ValueError("Specialist returned an empty result on automatic retry.")
            retry_error.retry_count = 1
            raise retry_error
        return result, 1


def read_context(path):
    if not path:
        return ""
    source = Path(path).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() not in {".txt", ".md", ".json"}:
        raise ValueError("Context must be an existing .txt, .md, or .json file.")
    if source.stat().st_size > 2_000_000:
        raise ValueError("Context file must not exceed 2 MB.")
    return source.read_text(encoding="utf-8", errors="replace")[:50000]



def heuristic_assignments(task):
    """Transparent no-model routing: parent roles are assigned, and each parent directs its children.

    Ten parents own the deliverables; the sub-agents under them own one craft
    each and receive their brief from the parent, not from this function. Keeping
    the assignment list this short is the point: the fallback used to name eleven
    roles directly and could not say why any of them was there.
    """
    text = task.lower()
    explicit_video = bool(re.search(r"\b(video|shorts|short-form|storyboard|motion graphics|video production|youtube script|video script|youtube content package|faceless channel video)\b", text))
    # Creative screenplay/fight requests often do not say "video" or "YouTube".
    # Route them to script/storyboard/motion roles without misclassifying code scripts.
    creative_scene_request = bool(
        re.search(r"\b(fight|battle|screenplay|superhero|anime|animation|animated sequence|scene[- ]by[- ]scene)\b", text)
        and re.search(r"\b(script|screenplay|scene|sequence|storyboard|create|write|draft)\b", text)
    )
    video = explicit_video or creative_scene_request
    assignments = [{"agent_id": "AGENT-02", "task": "Research the task requirements, authoritative sources, current constraints, and viable approaches. Return source-linked evidence and uncertainties."}]
    if video:
        assignments.extend([
            {"agent_id": "AGENT-09", "task": "Own the words: the narrative arc, the hook, the outline and the retention pass, directing its sub-agents and returning the narration-ready script."},
            {"agent_id": "AGENT-51", "task": "Own the picture: art direction, shot rhythm, and the timing, kinetic typography, transitions, palette and diagrams its sub-agents produce."},
            {"agent_id": "AGENT-31", "task": "Own the file: the local render and encode, with its animator, validator and visual QA sub-agents reporting against it."},
            {"agent_id": "AGENT-26", "task": "Prepare accessibility captions aligned to the narration and timing information available."},
        ])
        # Language is an explicit production profile; do not silently replace Urdu-English with English.
        # Country/topic mentions must never silently switch a video into another language.
    else:
        # A request to build software is software. routing.py sends it to the tool
        # pipelines, which write the files themselves; no specialist's prose
        # changes that outcome, so the fallback no longer invents a software team.
        assignments.extend([
            {"agent_id": "AGENT-03", "task": "Audit the evidence, source quality, dates, and whether citations support the key claims."},
            {"agent_id": "AGENT-12", "task": "Synthesize the research into the requested practical deliverable, clearly separating facts from assumptions."},
        ])
    # Keep the fallback small and append a quality gate after role-specific work.
    unique = []
    seen = set()
    for item in assignments:
        if item["agent_id"] not in seen and item["agent_id"] not in {"AGENT-01", "AGENT-50"}:
            seen.add(item["agent_id"])
            unique.append(item)
    unique = unique[:7]
    if "AGENT-08" not in {item["agent_id"] for item in unique}:
        unique.append({"agent_id": "AGENT-08", "task": "Fact-check the draft and its claims against the supplied research report; flag unsupported statements and unresolved risks."})
    return unique[:8], "heuristic_no_model"


def parse_ceo_assignments(text, roles_by_id):
    """Parse and validate CEO-produced JSON delegation without executing arbitrary content."""
    candidates = []
    for match in re.finditer(r"\{", text):
        try:
            parsed, _ = json.JSONDecoder().raw_decode(text[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            candidates = parsed.get("assignments", parsed.get("agents", []))
            break
    if not isinstance(candidates, list):
        return []
    result, seen = [], set()
    for item in candidates:
        if isinstance(item, str):
            agent_id, subtask = item.strip().upper(), ""
        elif isinstance(item, dict):
            agent_id = str(item.get("agent_id", item.get("id", ""))).strip().upper()
            subtask = str(item.get("task", item.get("responsibility", ""))).strip()
        else:
            continue
        if agent_id in {"AGENT-01", "AGENT-50"} or agent_id not in roles_by_id or agent_id in seen:
            continue
        if len(result) >= 7:
            break
        if len(subtask) > 2500:
            subtask = subtask[:2500]
        result.append({"agent_id": agent_id, "task": subtask})
        seen.add(agent_id)
    if not result:
        return []
    for item in result:
        if not item["task"]:
            item["task"] = "Complete the assigned specialist contribution to this overall goal: " + str(item["agent_id"])
    reviewer = next((item for item in result if item["agent_id"] == "AGENT-08"), None)
    result = [item for item in result if item["agent_id"] != "AGENT-08"]
    if reviewer is None:
        reviewer = {"agent_id": "AGENT-08", "task": "Review the combined work for factual support, contradictions, omissions, and unresolved risks. Use the supplied research report and cite source URLs."}
    reviewer["task"] = "FINAL QUALITY GATE: " + reviewer["task"]
    result.append(reviewer)
    return result[:8]


def plan_delegation(task, context, cfg, roles_by_id):
    """Let the CEO choose specialist roles; use deterministic routing only when no valid model plan exists."""
    model_enabled = bool(cfg.get("model", {}).get("enabled"))
    ceo_error = False
    if model_enabled:
        skill_profiles = {
            profile.get("agent_id"): profile
            for profile in dispatch.load_json(dispatch.SKILLBOOK, {}).get("profiles", [])
        }
        roster = []
        for role in roles_by_id.values():
            agent_id = role.get("id")
            if agent_id in {"AGENT-01", "AGENT-50"}:
                continue
            skill = skill_profiles.get(agent_id, {})
            roster.append({
                "id": agent_id,
                "name": role.get("name"),
                "division": role.get("division"),
                "parent": role.get("parent"),
                "directs": [str(child.get("id")) + " " + str(child.get("name")) for child in dispatch.children_of(agent_id)],
                "mission": str(role.get("mission", ""))[:180],
                "expertise": str(skill.get("expertise", ""))[:140],
                "deliverable": str(skill.get("deliverable_contract", ""))[:120],
            })
        ceo_task = (
            "Act as the CEO of Agent HQ and the single point of task intake. The user supplies the goal; you alone decide which specialists receive work, their distinct responsibilities, dependencies, and execution order. Never require the user to choose agent IDs, and do not treat user-suggested agent IDs as binding routing instructions. "
            "The specialists form a tree: a role with a null parent owns a deliverable and directs the sub-agents listed in its directs field; a role with a parent owns one craft inside that parent's deliverable. Assign work to parent roles. Name a sub-agent directly only when the task needs that one craft and nothing else, and never assign a sub-agent to direct other sub-agents. "
            "Delegate to the smallest sufficient set of specialists. Choose 1-7 specialist assignments, in dependency order; one specialist plus the required reviewer is valid for a narrow task. Include one factual quality-review role "
            "(prefer AGENT-08) unless inappropriate. Never select AGENT-01 or AGENT-50 as a worker. "
            "Give each role a concrete, distinct subtask with an observable deliverable. Do not select roles merely to fill a quota. "
            "VIDEO LANGUAGE RULE: preserve the explicit language requested by the user. "
            "Voice-over narration and subtitles must follow the explicit request or configured default; never silently substitute English or Urdu. "
            "Never delegate translation/localization as a standalone task. "
            + configured_narration_language_instruction(cfg) + " "
            "The renderer must reject a missing/incompatible voice backend rather than claim that narration was synthesized. "
            "Return ONLY valid JSON in this exact shape: "
            '{"assignments":[{"agent_id":"AGENT-02","task":"Specific work and deliverable"}]}\n\n'
            "USER GOAL:\n" + task + "\n\nAVAILABLE SPECIALISTS:\n"
            + json.dumps(roster, ensure_ascii=False)[:18000]
        )
        try:
            # Delegation is a lightweight planning call. Specialist stages perform
            # their own task-specific research; searching before the CEO can route work
            # adds latency and can time out CPU-only local models.
            raw = dispatch.run_role(
                roles_by_id["AGENT-01"], ceo_task, context[:6000], cfg,
                perform_research=False,
            )
            assignments = parse_ceo_assignments(raw, roles_by_id)
            if assignments:
                return assignments, "ceo_model_delegation"
        except Exception:
            ceo_error = True
    assignments, _ = heuristic_assignments(task)
    if model_enabled:
        return assignments, "heuristic_fallback_after_ceo_error" if ceo_error else "heuristic_fallback_invalid_ceo_plan"
    return assignments, "heuristic_no_model"


def tool_model_call(cfg):
    """Adapter that lets the tool planner use the configured loopback model.

    Returns ``None`` when no model is enabled so the planner falls back to its
    deterministic scaffold instead of pretending to plan.
    """
    model = cfg.get("model", {}) if isinstance(cfg, dict) else {}
    if not model.get("enabled"):
        return None
    url = model.get("base_url", "")
    # The device tier decides how long one generation may block and how long an
    # answer may be. Without this a 2-core box waits four minutes per call and
    # asks for a 4,000-token answer it cannot produce, which reads to the user as
    # a freeze rather than a slow machine. Both numbers are recorded in the
    # manifest under "resources", so a shorter answer is never a silent surprise.
    limits = resources.limits_from(cfg)
    timeout = max(60, min(int(model.get("timeout_seconds", 240)),
                          limits["model_timeout_seconds"]))
    token_cap = limits["model_max_tokens"]

    def call(prompt, max_tokens):
        body = {
            "model": model.get("model", "local-model"),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": max(256, min(int(max_tokens), token_cap)),
        }
        data = dispatch.post_local_model(url, body, timeout)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("Local model response did not contain choices[0].message.content.") from exc

    return call


def routing_model_call(cfg):
    """Adapter that lets the routing head use the configured loopback model.

    The router answers with a small JSON object, so it gets a small budget and the
    same loopback endpoint the tool planner uses. ``None`` when no model is
    enabled, which is what makes the deterministic path the default rather than a
    fallback that only triggers on failure.
    """
    base = tool_model_call(cfg)
    if base is None:
        return None

    def call(prompt, max_tokens):
        return base(prompt, max(256, min(int(max_tokens), 900)))

    return call


def run_builtin_tools(task, destination, cfg, source_context="", route_sink=None):
    """Run the fixed, repository-owned builders the router selected.

    Selection is delegated to ``agents/routing.py``; this function owns execution
    and the guards that must hold no matter who selected the pipeline — no render
    without a local model, no voice backend silently substituted, no fixed builder
    replaced by generated text. ``route_sink``, when given, receives the route so
    the caller can record the decision and its evidence in the manifest.
    """
    results = []
    intent_text = routing.extract_intent(task)
    intent_lower = intent_text.lower()
    model_enabled = bool(cfg.get("model", {}).get("enabled"))
    route = routing.route_task(task, cfg, model_call=routing_model_call(cfg))
    if route_sink is not None:
        route_sink["route"] = route
    template_demo = bool(re.search(r"\b(template demo|demo render)\b", intent_lower)) and not model_enabled
    kinds = {request.pipeline for request in route.requests}
    source_path = None
    if source_context.strip() and kinds:
        source_path = destination / "source-notes.md"
        source_path.write_text(source_context[:50000], encoding="utf-8")

    video_plan = routing.video_instructions(intent_text) if "video_production" in kinds else {}
    for request in route.requests:
        if request.pipeline == "video_production":
            results.extend(_run_video_pipeline(request, destination, model_enabled,
                                               template_demo, source_path, video_plan, cfg))
        elif request.pipeline in {"web_build", "document_deliverable", "cli_tool", "data_deliverable"}:
            results.append(_run_tool_loop(request, intent_text, destination, cfg))
        elif request.pipeline == "test_fix":
            results.append(_run_test_fix(request, destination, cfg))
        elif request.pipeline == "product_prototype":
            results.append(_run_product_pipeline(request, destination, model_enabled, source_path))
    return results


def _resolved_narration_language(request, instructions, cfg):
    """One answer to "which language is this film in", read in the same order the tool reads it.

    The orchestrator used to pass nothing when neither the route nor the intent
    named a language, so production.py fell back to config and the two could
    disagree without either knowing.
    """
    explicit = request.args.get("language") or instructions.get("language")
    if explicit:
        value = str(explicit).strip().lower()
        return "en" if value in {"en", "english"} else "ur-en"
    video = (cfg or {}).get("video_studio") if isinstance(cfg, dict) else None
    value = str((video or {}).get("narration_language", "ur-en") or "ur-en").strip().lower()
    return "en" if value in {"en", "english"} else "ur-en"


def _run_video_pipeline(request, destination, model_enabled, template_demo, source_path,
                        instructions, cfg=None):
    """Build a video package, and only render when the guards allow it.

    Creative arguments come from the route; execution instructions (render,
    narration, format, length, language) are parsed from the request and win over
    an empty route argument. A model that forgets to pass ``render`` therefore
    cannot quietly downgrade an explicit MP4 request to a package build.
    """
    render_requested = bool(request.args.get("render")) or bool(instructions.get("render"))
    topic = str(request.args.get("topic") or "").strip() or "Technology explainer"
    output = destination / "video-production"
    relative_out = safe_relative_path(output, ROOT).as_posix()
    command = [sys.executable, str(ROOT / "video_studio" / "production.py"),
               "--topic", topic[:500],
               "--format", "shorts" if (request.args.get("format") or instructions.get("format")) == "shorts" else "long",
               "--out", relative_out]
    language = _resolved_narration_language(request, instructions, cfg)
    if not model_enabled and language == "ur-en":
        # A policy refusal is not a crash. Without the local model this build
        # cannot produce Urdu-English narration, and substituting an English
        # scaffold would be the silent substitution the project forbids. Report it
        # as blocked, with the way forward, and let the rest of the run stand.
        return [{
            "tool": "video_studio", "status": "blocked", "artifact_dir": relative_out,
            "language": language, "selected_by": "video_production",
            "reason": (
                "Urdu-English narration requires the configured local language model, which is "
                "disabled, so no video package was built and no English scaffold was substituted "
                "for it. Enable the model, or ask for the film in English "
                "(narration language: English), to get a labelled English template without a model."
            ),
        }]
    command.extend(["--language", language])
    if source_path is not None:
        command.extend(["--source-file", str(source_path)])
    else:
        command.append("--research")
    minutes = request.args.get("target_minutes") or instructions.get("target_minutes")
    if minutes:
        command.extend(["--target-minutes", str(minutes)])
    blocked = None
    if render_requested and model_enabled:
        command.append("--render")
        if instructions.get("with_voice"):
            command.append("--with-voice")
    elif render_requested and template_demo:
        # Only an explicitly labelled English CI/demo request should override the
        # configured language. Otherwise production.py uses config and fails closed
        # when the selected profile has no compatible voice backend.
        command.extend(["--render", "--render-template"])
    elif render_requested:
        # Keep the package build, refuse the render, and say why.
        blocked = {
            "tool": "video_render", "status": "blocked",
            "artifact_dir": relative_out,
            "reason": "Full-length MP4 rendering is blocked because no local model is enabled. A separate deterministic template package will be generated and clearly labelled; it is not a substitute for the requested final video.",
        }
    tool_result = _run_fixed_tool("video_studio", command, destination, relative_out, timeout=14400)
    tool_result["generation_mode"] = ("local_model" if model_enabled else
                                      ("explicit_template_demo" if template_demo and render_requested
                                       else "deterministic_template"))
    tool_result["render_requested"] = render_requested
    tool_result["render_expected"] = bool(render_requested and (model_enabled or template_demo))
    if not model_enabled:
        tool_result["note"] = "No local model is enabled: script and storyboard are deterministic scaffolding, not a researched or AI-written final video."
    tool_result["selected_by"] = "video_production"
    # The render refusal is reported as its own result: the artifact exists and
    # the requested render does not, and collapsing the two would hide one.
    return ([blocked] if blocked is not None else []) + [tool_result]


#: A dataset is read only from inside the project and only up to this size. The
#: cap exists because the analysis runs on a phone: a 500 MB CSV would fail as a
#: memory error halfway through a task instead of as a clear refusal.
MAX_DATASET_BYTES = 2_000_000
DATASET_SUFFIXES = (".csv", ".tsv")


def _read_dataset(reference, project_root=None, max_bytes=None):
    """Read one dataset named by a task. Returns (text, name, error).

    Confinement matters here: this is the first pipeline that reads a file the
    user named, so it must not become a way to read arbitrary disk content. The
    path is resolved, confined to the project root, restricted to table suffixes,
    and size-capped before a byte is read.
    """
    reference = str(reference or "").strip()
    if not reference:
        return "", "", "no dataset file was named in the request"
    root = canonical_path(project_root or ROOT)
    parts = reference.replace("\\", "/").split("/")
    if reference.startswith(("/", "\\")) or ":" in reference or ".." in parts:
        return "", "", "dataset path must be a relative path inside the project"
    if any(part.startswith(".") for part in parts):
        # A named dataset is input data, not a way to reach .git, .env or tooling
        # directories. Dot-paths are refused rather than resolved and checked.
        return "", "", "dataset path must not contain hidden or dot-directories"
    candidate = root / reference
    try:
        target = canonical_path(candidate)
    except (OSError, RuntimeError, ValueError):
        return "", "", "dataset path could not be resolved"
    if not is_within(target, root, allow_equal=False):
        return "", "", "dataset path resolves outside the project"
    if target.suffix.lower() not in DATASET_SUFFIXES:
        return "", "", "only .csv and .tsv files are read"
    if not target.is_file():
        return "", "", "dataset file was not found"
    # The default cap is the balanced-tier one; a smaller machine passes its own,
    # smaller limit so it refuses early instead of being killed mid-analysis.
    limit_bytes = int(max_bytes or MAX_DATASET_BYTES)
    try:
        if target.stat().st_size > limit_bytes:
            return "", "", f"dataset is larger than the {limit_bytes:,}-byte limit"
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "", "", "dataset file could not be read"
    return text, target.name, ""


def _resolve_project(reference, project_root=None):
    """Resolve a project the user named. Returns (path or None, error).

    The repair loop writes into this directory, so the same confinement rules as
    dataset reads apply, plus one: the target must be a directory (or a test file
    whose project directory can be derived), never a bare file path.
    """
    reference = str(reference or "").strip()
    if not reference:
        return None, "no project directory was named in the request"
    root = canonical_path(project_root or ROOT)
    parts = reference.replace("\\", "/").split("/")
    if reference.startswith(("/", "\\")) or ":" in reference or ".." in parts:
        return None, "project path must be a relative path inside the project"
    if any(part.startswith(".") for part in parts):
        return None, "project path must not contain hidden or dot-directories"
    try:
        target = canonical_path(root / reference)
    except (OSError, RuntimeError, ValueError):
        return None, "project path could not be resolved"
    if not is_within(target, root, allow_equal=False):
        return None, "project path resolves outside the project"
    if target.is_file():
        # "fix the tests in tests/test_api.py" names a file but means its project.
        target = target.parent
        if target.name.lower() in {"tests", "test", "__tests__"}:
            target = target.parent
    if not target.is_dir():
        return None, "project directory was not found"
    return target, ""


def _run_test_fix(request, destination, cfg):
    """Run a project's suite, diagnose it, and keep a repair only if it verifies."""
    allow_exec = os.environ.get("AGENT_HQ_ALLOW_EXEC", "").strip().lower() in {"1", "true", "yes", "on"}
    artifact_dir = destination / "projects" / (destination.name + "-fix")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    relative_out = safe_relative_path(artifact_dir, ROOT).as_posix()
    project_dir, problem = _resolve_project(request.args.get("project"))
    propose = None
    if project_dir is not None and allow_exec:
        call = tool_model_call(cfg)
        if call is not None:
            propose = test_fix.model_proposer(call, project_dir)
    report = test_fix.diagnose(
        project_dir if project_dir is not None else artifact_dir,
        allow_exec=allow_exec and project_dir is not None,
        title=str(request.args.get("title") or "") or (
            f"Test report: {project_dir.name}" if project_dir is not None
            else f"Test report: {destination.name}"),
        propose=propose,
        timeout=resources.limits_from(cfg)["test_timeout_seconds"],
        max_attempts=resources.limits_from(cfg)["test_max_attempts"],
    )
    if problem:
        report["no_run_reason"] = problem
        report["green"] = False
        report["verified_fix"] = False
    test_fix.write_report(report, artifact_dir)
    if report.get("verified_fix"):
        status = "completed"
    elif report.get("no_run_reason") or report.get("runs"):
        status = "partial"
    else:
        status = "failed"
    return {
        "tool": "test_fix",
        "status": status,
        "deliverable": "fix",
        "project": report.get("project", ""),
        "command": report.get("command_text", ""),
        "runs": len(report.get("runs") or []),
        "tests_ran": report.get("tests_ran", 0),
        "failures": len(report.get("failures") or []),
        "repairs": len(report.get("repairs") or []),
        "verified_fix": bool(report.get("verified_fix")),
        "test_files_modified": bool(report.get("test_files_modified")),
        "no_run_reason": report.get("no_run_reason", ""),
        "artifact_dir": relative_out,
        "artifacts": ["test-report.json", "fix-plan.md"],
        "selected_by": request.pipeline,
        "generation_mode": "local_model_test_repair" if propose else "deterministic_test_doctor",
        "human_review_required": True,
        "summary": (
            "Suite passing after a verified repair." if report.get("verified_fix")
            else report.get("no_run_reason") or "Suite still failing; diagnosis recorded."
        )[:400],
    }


def _run_tool_loop(request, intent_text, destination, cfg):
    """Execute a web, document, CLI, or data deliverable in the confined tool loop."""
    deliverable = routing.PIPELINES_BY_ID[request.pipeline].deliverable
    suffix = {"web": "-web", "document": "-document", "cli": "-cli", "data": "-data"}[deliverable]
    allow_exec = os.environ.get("AGENT_HQ_ALLOW_EXEC", "").strip().lower() in {"1", "true", "yes", "on"}
    data_text, data_name, data_error = "", "", ""
    if deliverable == "data":
        data_text, data_name, data_error = _read_dataset(
            request.args.get("source"), max_bytes=resources.limits_from(cfg)["dataset_max_bytes"])
    result = tool_agent.run_tool_agent(
        goal=intent_text,
        workspace_root=destination,
        task_id=destination.name + suffix,
        model_call=tool_model_call(cfg),
        allow_exec=allow_exec,
        deliverable=deliverable,
        # A name the router read from the goal ("called photo-dedupe") is used
        # verbatim; the scaffold re-derives one when this is empty.
        deliverable_name=str(request.args.get("name") or request.args.get("title") or ""),
        data_text=data_text,
        data_name=data_name,
        data_reason=data_error,
        max_repairs=resources.limits_from(cfg)["tool_max_repairs"],
        max_seconds=max(1, min(resources.limits_from(cfg)["tool_loop_max_seconds"],
                               cfg.get("_build_seconds") or resources.limits_from(cfg)["tool_loop_max_seconds"])),
        timeout_seconds=resources.limits_from(cfg)["tool_loop_timeout_seconds"],
    )
    result["resource_tier"] = (cfg.get("_resources") or {}).get("tier", "unknown")
    result["tool"] = "tool_agent"
    result["selected_by"] = request.pipeline
    artifact_dir = result.get("artifact_dir")
    if artifact_dir:
        result["artifact_dir"] = safe_relative_path(destination / artifact_dir, ROOT).as_posix()
    result["generation_mode"] = "local_model_tool_loop" if result.get("mode") == "model" else "deterministic_scaffold"
    result["human_review_required"] = True
    return result


def _run_product_pipeline(request, destination, model_enabled, source_path):
    """Package a product prototype with the existing fixed builder."""
    intent_text = str(request.args.get("idea", ""))
    title = str(request.args.get("title", "")).strip()
    if not title:
        title_seed = re.sub(r"(?i)^\s*(?:please\s+)?(?:build|create|make|generate|develop|implement)\s+(?:a|an|the)?\s*", "", intent_text).strip()
        title = re.sub(r"[-_]+", " ", slug(title_seed[:70])).title()
    idea = (intent_text or "A small offline product prototype")[:1000]
    output = destination / "product-prototype"
    relative_out = safe_relative_path(output, ROOT).as_posix()
    command = [sys.executable, str(ROOT / "product_studio" / "build_product.py"),
               "--title", title[:100], "--idea", idea, "--out", relative_out]
    if source_path is not None:
        command.extend(["--source-file", str(source_path)])
    tool_result = _run_fixed_tool("product_studio", command, destination, relative_out, timeout=900)
    tool_result["generation_mode"] = "local_model" if model_enabled else "deterministic_template"
    if not model_enabled:
        tool_result["note"] = "Local model disabled: this is a generic starter template, not a product-specific AI implementation."
    return tool_result


def _run_fixed_tool(name, command, destination, relative_out, timeout):
    """Execute a fixed in-repository builder and persist bounded diagnostics."""
    log_path = destination / (name.replace("_", "-") + "-tool.log")
    try:
        result = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True,
                                timeout=timeout, check=False)
        output = (result.stdout or "")[-12000:]
        errors = (result.stderr or "")[-12000:]
        log_path.write_text("STDOUT\n" + output + "\nSTDERR\n" + errors + "\n", encoding="utf-8")
        return {
            "tool": name, "status": "completed" if result.returncode == 0 else "failed",
            "exit_code": result.returncode, "artifact_dir": relative_out,
            "log_file": safe_relative_path(log_path, ROOT).as_posix(),
            "summary": output[-2000:] if output else errors[-2000:],
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        log_path.write_text(type(exc).__name__ + ": " + str(exc)[:1000] + "\n", encoding="utf-8")
        return {
            "tool": name, "status": "failed", "artifact_dir": relative_out,
            "log_file": safe_relative_path(log_path, ROOT).as_posix(),
            "error": type(exc).__name__ + ": " + str(exc)[:500],
        }



def verify_artifact_tool_runs(tool_runs, project_root=None):
    """Independently verify files emitted by the built-in video and product builders.

    A zero exit code is necessary but not sufficient: missing, malformed, or
    unsafe artifacts convert a nominally successful builder run to a failure.
    All artifact paths must remain beneath this project's workspace directory.
    """
    root = canonical_path(project_root or ROOT)
    workspace_root = canonical_path(root / "workspace")
    checks = []

    def nonempty_file(path):
        return path.is_file() and path.stat().st_size > 0

    def require_file(directory, name, errors):
        path = directory / name
        if not nonempty_file(path):
            errors.append("Missing or empty artifact: " + name)
        return path

    for result in tool_runs or []:
        tool = str(result.get("tool", ""))
        if tool not in {"video_studio", "product_studio", "tool_agent", "test_fix"}:
            continue

        check = {
            "tool": tool,
            "artifact_dir": str(result.get("artifact_dir", "")),
            "status": "skipped",
            "checks": [],
            "errors": [],
        }
        if tool in {"tool_agent", "test_fix"}:
            # Both report "partial" when the artifact is honest but the work is not
            # fully done: a scaffold for the tool loop, an unrepaired suite here.
            if result.get("status") not in {"completed", "partial"}:
                check["reason"] = "Tool loop did not report a verified result; its failure is preserved."
                checks.append(check)
                continue
        elif result.get("status") != "completed":
            check["reason"] = "Builder did not report success; its failure or blocked status is preserved."
            checks.append(check)
            continue

        artifact_value = str(result.get("artifact_dir", "")).strip()
        target = (root / artifact_value).resolve() if artifact_value else root
        errors = check["errors"]

        if target == workspace_root or workspace_root not in target.parents:
            errors.append("Artifact path is missing or escapes the project workspace.")
        elif not target.is_dir():
            errors.append("Artifact output directory does not exist.")
        elif tool == "video_studio":
            script = require_file(target, "script.md", errors)
            storyboard_path = require_file(target, "storyboard.json", errors)
            status_path = require_file(target, "package-status.json", errors)

            if nonempty_file(script) and not script.read_text(encoding="utf-8", errors="replace").strip():
                errors.append("Video script contains no usable text.")

            storyboard = None
            if nonempty_file(storyboard_path):
                try:
                    storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
                    if not isinstance(storyboard, dict):
                        raise ValueError("Storyboard must be a JSON object.")
                    width, height, fps = storyboard.get("width"), storyboard.get("height"), storyboard.get("fps")
                    if not isinstance(storyboard.get("scenes"), list) or not 1 <= len(storyboard["scenes"]) <= 100:
                        errors.append("Storyboard must contain 1–100 scenes.")
                    if not isinstance(width, int) or isinstance(width, bool) or not 320 <= width <= 3840:
                        errors.append("Storyboard width is missing or outside renderer limits.")
                    if not isinstance(height, int) or isinstance(height, bool) or not 180 <= height <= 2160:
                        errors.append("Storyboard height is missing or outside renderer limits.")
                    if not isinstance(fps, int) or isinstance(fps, bool) or not 1 <= fps <= 60:
                        errors.append("Storyboard frame rate is missing or outside renderer limits.")
                except (json.JSONDecodeError, OSError, ValueError, AttributeError) as exc:
                    errors.append("Storyboard JSON could not be validated: " + str(exc)[:250])

            package_status = None
            if nonempty_file(status_path):
                try:
                    package_status = json.loads(status_path.read_text(encoding="utf-8"))
                    if not isinstance(package_status, dict):
                        raise ValueError("Package status must be a JSON object.")
                    if package_status.get("publishable") is not False:
                        errors.append("Video package must remain non-publishable pending human approval.")
                    if package_status.get("published") is not False:
                        errors.append("Video package must not claim that it has been published.")
                    if package_status.get("human_review_required") is not True:
                        errors.append("Video package must explicitly require human review.")
                except (json.JSONDecodeError, OSError, ValueError, AttributeError) as exc:
                    errors.append("Package-status JSON could not be validated: " + str(exc)[:250])

            check["checks"].append("script_storyboard_package_status")
            traceable_source_ids = set()
            if package_status and package_status.get("web_research_performed") is True:
                research_md = require_file(target, "research.md", errors)
                research_json_path = require_file(target, "research.json", errors)
                if nonempty_file(research_md) and not research_md.read_text(encoding="utf-8", errors="replace").strip():
                    errors.append("Research report is empty.")
                if nonempty_file(research_json_path):
                    try:
                        research_data = json.loads(research_json_path.read_text(encoding="utf-8"))
                        if not isinstance(research_data, dict):
                            raise ValueError("Research report must be a JSON object.")
                        research_metadata = research_data.get("metadata")
                        research_results = research_data.get("results")
                        if not isinstance(research_metadata, dict) or not isinstance(research_results, list):
                            raise ValueError("Research metadata/results have invalid types.")
                        if research_metadata.get("source_provenance_schema") != 1:
                            errors.append("Research report lacks the required source-provenance schema.")
                        if research_metadata.get("verified") is not False:
                            errors.append("Research metadata must not overclaim independent verification.")
                        fetched_count = 0
                        fetched_domains = set()
                        fetched_hashes = set()
                        seen_fetched_source_ids = set()
                        for source in research_results:
                            if not isinstance(source, dict):
                                errors.append("Research results must contain only JSON objects.")
                                continue
                            # Publication dates are untrusted page metadata. Validate their shape
                            # without treating them as proof that a claim is current or true.
                            for date_key in ("published_date", "published_date_source", "modified_date"):
                                date_value = source.get(date_key)
                                if date_value is not None and (
                                    not isinstance(date_value, str) or not date_value.strip() or len(date_value) > 100
                                ):
                                    errors.append("Research source has invalid " + date_key + " metadata.")
                            if source.get("fetch_status") != "fetched":
                                continue
                            page_text = source.get("page_text")
                            digest_value = source.get("page_text_sha256")
                            domain = source.get("final_domain")
                            if not isinstance(page_text, str) or not page_text.strip():
                                continue
                            if (not isinstance(digest_value, str) or len(digest_value) != 64
                                    or any(char not in "0123456789abcdef" for char in digest_value.lower())):
                                errors.append("Fetched research source is missing a valid extracted-text SHA-256.")
                                continue
                            actual_text_hash = hashlib.sha256(page_text.encode("utf-8")).hexdigest()
                            if actual_text_hash != digest_value:
                                errors.append("Research extracted-text SHA-256 does not match the saved page text.")
                                continue
                            if not isinstance(domain, str) or not domain.strip():
                                errors.append("Fetched research source is missing its final domain.")
                                continue
                            source_id = source.get("source_id")
                            if not isinstance(source_id, str) or not re.fullmatch(r"S[1-9][0-9]*", source_id):
                                errors.append("Fetched research source is missing a valid stable source ID.")
                                continue
                            if source_id in seen_fetched_source_ids:
                                errors.append("Research report contains duplicate fetched source ID: " + source_id)
                                continue
                            seen_fetched_source_ids.add(source_id)
                            fetched_count += 1
                            fetched_domains.add(domain.lower().rstrip("."))
                            fetched_hashes.add(digest_value)
                            traceable_source_ids.add(source_id)
                        if research_metadata.get("pages_fetched") != fetched_count:
                            errors.append("Research metadata fetched-page count does not match traceable fetched sources.")
                        if fetched_count < 1:
                            errors.append("Research was marked complete without any fetched, traceable source-page text.")
                        summary = package_status.get("research_evidence")
                        if not isinstance(summary, dict):
                            errors.append("Package status is missing the research evidence summary.")
                        else:
                            if summary.get("fetched_page_count") != fetched_count:
                                errors.append("Package research evidence page count does not match research.json.")
                            if summary.get("independent_domain_count") != len(fetched_domains):
                                errors.append("Package research domain count does not match research.json.")
                            if summary.get("domains") != sorted(fetched_domains):
                                errors.append("Package research domain list does not match research.json.")
                            if summary.get("page_text_sha256") != sorted(fetched_hashes):
                                errors.append("Package research text-digest list does not match research.json.")
                            expected_research_status = "multiple_domains_fetched" if len(fetched_domains) > 1 else "single_domain_only"
                            if summary.get("status") != expected_research_status:
                                errors.append("Package research evidence status does not match the fetched domains.")
                            if summary.get("independently_verified") is not False:
                                errors.append("Package research summary must not claim independent verification.")
                    except (json.JSONDecodeError, OSError, ValueError, AttributeError) as exc:
                        errors.append("Research JSON could not be validated: " + str(exc)[:250])
                check["checks"].append("research_source_text_provenance_and_manifest_parity")
            if package_status and package_status.get("generated_by") == "local_model_multi_pass" and isinstance(storyboard, dict):
                for scene_index, scene in enumerate(storyboard.get("scenes", []), start=1):
                    if not isinstance(scene, dict):
                        errors.append("Scene " + str(scene_index) + " must be an object before evidence can be validated.")
                        continue
                    refs = scene.get("source_refs")
                    if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs):
                        errors.append("Scene " + str(scene_index) + " must contain a source_refs array.")
                        continue
                    unknown_refs = [ref for ref in refs if ref not in traceable_source_ids]
                    if unknown_refs:
                        errors.append("Scene " + str(scene_index) + " cites unavailable or unfetched source IDs: " + ", ".join(unknown_refs))
                    evidence_status = scene.get("evidence_status")
                    unresolved = scene.get("unresolved_notes")
                    if refs and evidence_status != "source_linked_requires_review":
                        errors.append("Scene " + str(scene_index) + " has source references but lacks the correct review status.")
                    if not refs and evidence_status != "needs_human_verification":
                        errors.append("Scene " + str(scene_index) + " without source references must be marked for human verification.")
                    if not refs and (not isinstance(unresolved, list) or not unresolved):
                        errors.append("Scene " + str(scene_index) + " without source references must record unresolved verification notes.")
                check["checks"].append("scene_level_source_reference_validation")
            if result.get("render_expected") is True:
                video = require_file(target, "video.mp4", errors)
                srt = require_file(target, "video.srt", errors)
                vtt = require_file(target, "video.vtt", errors)
                qc_path = require_file(target, "video.qc.json", errors)
                if nonempty_file(video) and video.stat().st_size < 1024:
                    errors.append("Rendered MP4 is too small to be a valid release candidate.")
                if package_status and package_status.get("quality_audit_passed") is not True:
                    errors.append("Rendered video does not have a passing strict technical quality audit.")
                if package_status and package_status.get("status") != "technical_qa_passed_waiting_for_human_review":
                    errors.append("Rendered video package is not in the expected post-QA review state.")
                if nonempty_file(qc_path):
                    try:
                        qc_report = json.loads(qc_path.read_text(encoding="utf-8"))
                        if not isinstance(qc_report, dict):
                            raise ValueError("Quality report must be a JSON object.")
                        if qc_report.get("strict") is not True or qc_report.get("passed") is not True:
                            errors.append("Technical QA report is not a strict passing report.")
                        if nonempty_file(video):
                            digest = hashlib.sha256()
                            with video.open("rb") as video_stream:
                                for chunk in iter(lambda: video_stream.read(1024 * 1024), b""):
                                    digest.update(chunk)
                            actual_hash = digest.hexdigest()
                            if qc_report.get("video_sha256") != actual_hash:
                                errors.append("Technical QA report hash does not match the rendered MP4.")
                            if package_status and package_status.get("quality_report_video_sha256") != actual_hash:
                                errors.append("Package status hash does not match the rendered MP4.")
                    except (json.JSONDecodeError, OSError, ValueError, AttributeError) as exc:
                        errors.append("Technical QA JSON could not be validated: " + str(exc)[:250])
                if nonempty_file(srt) and not srt.read_text(encoding="utf-8", errors="replace").strip():
                    errors.append("SRT subtitle file is empty.")
                if nonempty_file(vtt) and not vtt.read_text(encoding="utf-8", errors="replace").strip():
                    errors.append("WebVTT subtitle file is empty.")
                check["checks"].append("mp4_subtitles_strict_qc_and_hash")
            check["checks"].append("release_safety_flags")
        elif tool == "tool_agent":
            deliverable = str(result.get("deliverable") or "web")
            if deliverable not in tool_agent.DELIVERABLES:
                errors.append("Tool run declares an unknown deliverable kind: " + deliverable[:40])
                deliverable = "web"
            summary_path = require_file(target, "tool-summary.json", errors)
            plan_path = require_file(target, "tool-plan.json", errors)
            verification_errors = []
            if nonempty_file(summary_path):
                try:
                    summary = json.loads(summary_path.read_text(encoding="utf-8"))
                    if not isinstance(summary, dict):
                        raise ValueError("Tool summary must be a JSON object.")
                    if summary.get("status") not in {"completed", "partial"}:
                        errors.append("Tool summary does not record a verified run.")
                    if summary.get("human_review_required") is not True:
                        errors.append("Tool summary must require human review.")
                    if summary.get("deliverable") != deliverable:
                        errors.append("Tool summary deliverable does not match the run.")
                except (json.JSONDecodeError, OSError, ValueError, AttributeError) as exc:
                    errors.append("Tool summary JSON could not be validated: " + str(exc)[:250])
            declared_checks = result.get("verification")
            if not isinstance(declared_checks, list) or not declared_checks:
                verification_errors.append("Tool run recorded no acceptance checks.")
            else:
                failed_checks = [item for item in declared_checks if not isinstance(item, dict) or item.get("status") != "passed"]
                if failed_checks:
                    verification_errors.append(f"{len(failed_checks)} acceptance check(s) did not pass.")
            if verification_errors:
                errors.extend(verification_errors)

            changes_path = require_file(target, "changes.json", errors)
            require_file(target, "changes.md", errors)
            if nonempty_file(changes_path):
                try:
                    changes = json.loads(changes_path.read_text(encoding="utf-8"))
                    if not isinstance(changes, dict):
                        raise ValueError("Change report must be a JSON object.")
                    if changes.get("schema") != 1:
                        errors.append("Change report does not declare schema 1.")
                    files = changes.get("files")
                    if not isinstance(files, list):
                        errors.append("Change report has no file list.")
                        files = []
                    summary = changes.get("summary") or {}
                    if isinstance(summary, dict) and summary.get("files_changed") != len(files):
                        errors.append("Change report summary does not match its file list.")
                    for item in files:
                        if not isinstance(item, dict):
                            errors.append("Change report contains a malformed entry.")
                            break
                        name = str(item.get("path", ""))
                        if not name or name.startswith(("/", "\\")) or ":" in name \
                                or ".." in name.replace("\\", "/").split("/"):
                            errors.append("Change report names a path outside the artifact: "
                                          + (name[:80] or "<empty>"))
                            break
                        # A claimed change must carry its lines, unless it is binary.
                        if item.get("kind") in {"created", "modified"} and not item.get("diff") \
                                and not item.get("binary"):
                            errors.append("Change report records a change with no diff: " + name[:80])
                            break
                except (json.JSONDecodeError, OSError, ValueError, AttributeError) as exc:
                    errors.append("Change report could not be validated: " + str(exc)[:250])
            check["checks"].append("change_report_matches_the_writes")
            if deliverable == "web":
                index_path = require_file(target, "index.html", errors)
                if nonempty_file(index_path):
                    html_text = index_path.read_text(encoding="utf-8", errors="replace")
                    lowered = html_text.lower()
                    if "<!doctype html" not in lowered or "<html" not in lowered:
                        errors.append("Web artifact is not a complete HTML document.")
                    if "connect-src 'none'" not in lowered:
                        errors.append("Web artifact does not declare a no-network Content-Security-Policy.")
                    if "http://" in lowered or "https://" in lowered.replace("http://www.w3.org", ""):
                        # Any external asset would break the offline guarantee.
                        external = [url for url in re.findall(r"https?://[^\s\"'<>]+", html_text) if "www.w3.org" not in url]
                        if external:
                            errors.append("Web artifact references external URLs: " + ", ".join(sorted(set(external))[:5]))
                check["checks"].append("web_offline_csp_tool_summary_and_acceptance_checks")
            elif deliverable == "document":
                document_path = require_file(target, "deliverable.md", errors)
                metadata_path = require_file(target, "deliverable.json", errors)
                if nonempty_file(document_path):
                    text = document_path.read_text(encoding="utf-8", errors="replace")
                    if not text.lstrip().startswith("# "):
                        errors.append("Document does not open with a level-1 heading.")
                    if "## Acceptance criteria" not in text:
                        errors.append("Document has no acceptance-criteria section.")
                if nonempty_file(metadata_path):
                    try:
                        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                        if not isinstance(metadata, dict):
                            raise ValueError("Document metadata must be a JSON object.")
                        if metadata.get("deliverable") != "document":
                            errors.append("Document metadata does not declare the document deliverable.")
                        if metadata.get("ai_generated") is not False:
                            errors.append("Document metadata must not claim AI authorship it cannot support.")
                        if metadata.get("human_review_required") is not True:
                            errors.append("Document metadata must require human review.")
                        criteria = metadata.get("acceptance_criteria")
                        if not isinstance(criteria, list) or not criteria:
                            errors.append("Document metadata carries no acceptance criteria.")
                    except (json.JSONDecodeError, OSError, ValueError, AttributeError) as exc:
                        errors.append("Document metadata could not be validated: " + str(exc)[:250])
                check["checks"].append("document_structure_metadata_and_acceptance_criteria")
            elif deliverable == "data":
                summary_path = require_file(target, "summary.json", errors)
                report_path = require_file(target, "analysis.md", errors)
                chart_path = require_file(target, "chart.svg", errors)
                script_path = require_file(target, "analyze.py", errors)
                if nonempty_file(summary_path):
                    try:
                        summary = json.loads(summary_path.read_text(encoding="utf-8"))
                        if not isinstance(summary, dict):
                            raise ValueError("Dataset summary must be a JSON object.")
                        if summary.get("schema") != 1:
                            errors.append("Dataset summary does not declare schema 1.")
                        if not isinstance(summary.get("columns"), list):
                            errors.append("Dataset summary has no column list.")
                        if not isinstance(summary.get("columns_detail"), dict):
                            errors.append("Dataset summary has no per-column profile.")
                        rows = summary.get("rows")
                        if not isinstance(rows, int) or isinstance(rows, bool) or rows < 0:
                            errors.append("Dataset summary reports an invalid row count.")
                        if summary.get("ai_generated") is not False:
                            errors.append("Dataset summary must not claim AI authorship.")
                        if summary.get("interpretation_performed") is not False:
                            errors.append("Dataset summary must not claim interpretation.")
                        if summary.get("human_review_required") is not True:
                            errors.append("Dataset summary must require human review.")
                        # A summary with rows but no profile (or the reverse) is a
                        # claim that was never measured.
                        if rows and not summary.get("columns_detail"):
                            errors.append("Dataset summary reports rows but profiles no columns.")
                        if not rows and not summary.get("no_data_reason"):
                            errors.append("Empty dataset summary does not explain why nothing was measured.")
                    except (json.JSONDecodeError, OSError, ValueError, AttributeError) as exc:
                        errors.append("Dataset summary could not be validated: " + str(exc)[:250])
                if nonempty_file(report_path):
                    report = report_path.read_text(encoding="utf-8", errors="replace")
                    if not report.lstrip().startswith("# "):
                        errors.append("Analysis report does not open with a level-1 heading.")
                    for section in ("## Findings", "## Limits"):
                        if section not in report:
                            errors.append("Analysis report is missing the " + section + " section.")
                if nonempty_file(chart_path):
                    chart = chart_path.read_text(encoding="utf-8", errors="replace")
                    if "<svg" not in chart or "</svg>" not in chart:
                        errors.append("Chart is not a complete SVG document.")
                    if "<script" in chart.lower():
                        errors.append("Chart contains a script element; charts must be inert.")
                    external = [url for url in re.findall(r"https?://[^\s\"'<>]+", chart)
                                if "www.w3.org/2000/svg" not in url]
                    if external:
                        errors.append("Chart references external resources: " + ", ".join(sorted(set(external))[:3]))
                if nonempty_file(script_path):
                    try:
                        ast.parse(script_path.read_text(encoding="utf-8", errors="replace"))
                    except (SyntaxError, ValueError) as exc:
                        errors.append("Analyzer script is not valid Python: " + str(exc)[:200])
                check["checks"].append("data_summary_report_chart_and_analyzer")
            elif deliverable == "cli":
                cli_path = require_file(target, "tool.py", errors)
                require_file(target, "README.md", errors)
                if nonempty_file(cli_path):
                    source = cli_path.read_text(encoding="utf-8", errors="replace")
                    try:
                        ast.parse(source)
                    except (SyntaxError, ValueError) as exc:
                        errors.append("CLI tool is not valid Python: " + str(exc)[:200])
                    if "--self-test" not in source:
                        errors.append("CLI tool does not expose a --self-test check.")
                check["checks"].append("cli_parses_self_test_and_readme")
            if not nonempty_file(plan_path):
                errors.append("Missing or empty artifact: tool-plan.json")
        elif tool == "test_fix":
            report_path = require_file(target, "test-report.json", errors)
            plan_path = require_file(target, "fix-plan.md", errors)
            if nonempty_file(report_path):
                try:
                    report = json.loads(report_path.read_text(encoding="utf-8"))
                    if not isinstance(report, dict):
                        raise ValueError("Test report must be a JSON object.")
                    if report.get("schema") != 1:
                        errors.append("Test report does not declare schema 1.")
                    if report.get("human_review_required") is not True:
                        errors.append("Test report must require human review.")
                    if report.get("ai_generated") is not False:
                        errors.append("Test report must not claim AI authorship.")
                    if not str(report.get("project", "")).strip():
                        errors.append("Test report names no project.")
                    runs = report.get("runs")
                    if not isinstance(runs, list):
                        errors.append("Test report has no run history.")
                        runs = []
                    if not runs and not report.get("no_run_reason"):
                        errors.append("Test report records no run and does not explain why.")
                    if report.get("test_files_modified"):
                        errors.append("A test file was modified; that is not a repair.")
                    if report.get("verified_fix"):
                        # A claimed fix must be backed by a green run and a repair
                        # that the run itself confirmed.
                        last = runs[-1] if runs else {}
                        if last.get("exit_code") != 0 or last.get("green") is not True:
                            errors.append("Test report claims a verified fix without a passing run.")
                        verified_repairs = [item for item in report.get("repairs") or []
                                            if isinstance(item, dict) and item.get("verified")]
                        if not verified_repairs:
                            errors.append("Test report claims a verified fix with no verified repair.")
                    for repair in report.get("repairs") or []:
                        if not isinstance(repair, dict):
                            errors.append("Test report contains a malformed repair record.")
                            break
                        if repair.get("kind") == "model_patch" and not repair.get("diff"):
                            errors.append("A repair record has no diff; a change must be shown, not described.")
                            break
                        if repair.get("verified") and repair.get("reverted"):
                            errors.append("A repair is recorded as both verified and reverted.")
                            break
                    for failure in report.get("failures") or []:
                        if isinstance(failure, dict) and not str(failure.get("test", "")).strip():
                            errors.append("Test report contains a failure with no test name.")
                            break
                except (json.JSONDecodeError, OSError, ValueError, AttributeError) as exc:
                    errors.append("Test report JSON could not be validated: " + str(exc)[:250])
            if nonempty_file(plan_path):
                plan = plan_path.read_text(encoding="utf-8", errors="replace")
                if not plan.lstrip().startswith("# "):
                    errors.append("Fix plan does not open with a level-1 heading.")
                if "## Limits" not in plan:
                    errors.append("Fix plan is missing the ## Limits section.")
            check["checks"].append("test_report_diagnosis_and_verified_repair")
        elif tool == "product_studio":
            candidates = sorted(
                child for child in target.iterdir()
                if child.is_dir() and (child / "product-status.json").is_file()
            )
            if len(candidates) != 1:
                errors.append("Expected exactly one generated product directory with product-status.json.")
            else:
                product_dir = candidates[0]
                index_path = require_file(product_dir, "index.html", errors)
                readme_path = require_file(product_dir, "README.md", errors)
                status_path = require_file(product_dir, "product-status.json", errors)
                if nonempty_file(index_path):
                    html_text = index_path.read_text(encoding="utf-8", errors="replace")
                    if "<html" not in html_text.lower() or "<head" not in html_text.lower():
                        errors.append("Product prototype is not a complete HTML document.")
                if nonempty_file(status_path):
                    try:
                        package_status = json.loads(status_path.read_text(encoding="utf-8"))
                        if not isinstance(package_status, dict):
                            raise ValueError("Product status must be a JSON object.")
                        if package_status.get("status") != "draft":
                            errors.append("Product prototype must be marked as a draft.")
                        if package_status.get("published") is not False:
                            errors.append("Product prototype must not claim publication.")
                        if package_status.get("human_review_required") is not True:
                            errors.append("Product prototype must explicitly require human review.")
                        risks = package_status.get("external_patterns_found")
                        if not isinstance(risks, list) or risks:
                            errors.append("Product prototype static safety scan did not pass cleanly.")
                    except (json.JSONDecodeError, OSError, ValueError, AttributeError) as exc:
                        errors.append("Product-status JSON could not be validated: " + str(exc)[:250])
                archive_path = target / (product_dir.name + ".zip")
                require_file(target, archive_path.name, errors)
                if nonempty_file(archive_path):
                    try:
                        with zipfile.ZipFile(archive_path) as archive:
                            if archive.testzip() is not None:
                                errors.append("Product ZIP archive failed its CRC integrity check.")
                            if not any(name.endswith("/index.html") for name in archive.namelist()):
                                errors.append("Product ZIP archive does not contain index.html.")
                    except (OSError, zipfile.BadZipFile) as exc:
                        errors.append("Product ZIP archive could not be validated: " + str(exc)[:250])
                if nonempty_file(readme_path) and not readme_path.read_text(encoding="utf-8", errors="replace").strip():
                    errors.append("Product README is empty.")
                check["checks"].append("html_readme_product_status_and_archive")
                check["product_directory"] = safe_relative_path(product_dir, root).as_posix()

        if errors:
            check["status"] = "failed"
            result["status"] = "failed"
            result["artifact_validation_errors"] = list(errors)
            result["error"] = "Post-build artifact validation failed: " + "; ".join(errors[:8])
        else:
            check["status"] = "passed"
        checks.append(check)
    return checks

def run_pipeline(task, context="", agent_ids=None, output_dir=None, config=None, note="",
                 resume=False, budget_minutes=None):
    if not isinstance(task, str) or not task.strip() or len(task) > 20000:
        raise ValueError("Task must be 1–20,000 characters.")
    roles = dispatch.load_json(dispatch.ROSTER, {}).get("agents", [])
    roles_by_id = {role.get("id"): role for role in roles}
    cfg = dict(config) if isinstance(config, dict) else dispatch.load_json(ROOT / "config.json", {})
    # One resource plan per run, decided once and read by every stage. The tier
    # comes from measured hardware unless AGENT_HQ_PROFILE (or config
    # "resources": {"profile": ...}) names one, which is how a user on a shared or
    # borrowed machine says "treat this as small" without editing hardware.
    requested_profile = (
        os.environ.get("AGENT_HQ_PROFILE", "").strip()
        or str((cfg.get("resources") or {}).get("profile", "") if isinstance(cfg.get("resources"), dict) else "")
        or "auto"
    )
    resource_plan = resources.plan(requested_profile, base_path=str(ROOT))
    cfg["_resources"] = resource_plan
    # One clock for the whole run. Every stage asks it whether there is still
    # time to be worth starting, and the answer is written down at the end.
    limits = resources.limits_from(cfg)
    budget_seconds = limits["run_budget_seconds"]
    if budget_minutes is not None:
        try:
            budget_seconds = max(60, min(int(float(budget_minutes) * 60), 12 * 3600))
        except (TypeError, ValueError):
            raise ValueError("budget_minutes must be a number of minutes.")
    run_budget = resources.RunBudget(budget_seconds)
    destination = canonical_path(output_dir) if output_dir else canonical_path(WORKSPACE / "orchestration" / slug(task[:80]))
    workspace_root = canonical_path(WORKSPACE)
    if destination == workspace_root or not is_within(destination, workspace_root, allow_equal=False):
        raise ValueError("Pipeline output must remain inside the project workspace.")
    destination.mkdir(parents=True, exist_ok=True)
    progress_path = destination / "pipeline-progress.json"

    # Phase 3 memory: what earlier runs in this workspace actually did. The block is
    # explicitly history to verify, not instructions, and it is bounded.
    memory_enabled = os.environ.get("AGENT_HQ_NO_MEMORY", "").strip().lower() not in {"1", "true", "yes", "on"}
    store = memory.MemoryStore(destination.parent / "memory")
    prior_runs = store.search(task, limit=memory.DEFAULT_LIMIT) if memory_enabled else []
    prior_block = store.render_context(prior_runs) if prior_runs else ""
    if prior_block:
        context = prior_block + "\n\n" + context

    # What a --resume run would be continuing. Read before this run rewrites the
    # delegation file, so the comparison is against the previous run, not this one.
    previous_delegation = None
    try:
        previous_delegation = json.loads(
            (destination / "00-ceo-delegation.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous_delegation = None

    def save_progress(status, phase, message, completed_stages=0, total_stages=0, agent_id=None, role_name=None):
        snapshot = {
            "status": status, "phase": phase, "message": message,
            "completed_stages": completed_stages, "total_stages": total_stages,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if agent_id:
            snapshot["agent_id"] = agent_id
        if role_name:
            snapshot["role"] = role_name
        temporary = progress_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(progress_path)

    save_progress("running", "CEO delegation", "CEO is planning the task and selecting specialist responsibilities.")
    ceo_research_dir = ROOT / "workspace" / "research" / "agent-runs"
    ceo_reports_before = set(ceo_research_dir.glob("agent-01-*.md")) if ceo_research_dir.is_dir() else set()
    if agent_ids is None:
        assignments, delegation_mode = plan_delegation(task.strip(), context, cfg, roles_by_id)
    else:
        selected = [str(agent_id).strip().upper() for agent_id in agent_ids]
        if not selected or len(selected) > 50 or len(set(selected)) != len(selected):
            raise ValueError("Choose 1–50 unique worker IDs; AGENT-01 is the CEO and AGENT-50 is reserved for human approval.")
        if any(agent_id not in roles_by_id for agent_id in selected):
            raise ValueError("Unknown specialist ID in pipeline.")
        if "AGENT-50" in selected or "AGENT-01" in selected:
            raise ValueError("CEO and human approval roles cannot be run as ordinary specialist stages.")
        assignments = [{"agent_id": agent_id, "task": "Complete your specialist contribution to this overall goal: " + task.strip()} for agent_id in selected]
        assignments = [item for item in assignments if item["agent_id"] != "AGENT-08"]
        assignments.append({
            "agent_id": "AGENT-08",
            "task": "FINAL QUALITY GATE: Review the combined deliverables, research evidence, factual claims, contradictions, omissions, and unresolved risks. Cite source URLs and end with OVERALL QUALITY GATE: PASS, PARTIAL, or FAIL.",
        })
        delegation_mode = "user_selected_roles"
    ceo_reports_after = set(ceo_research_dir.glob("agent-01-*.md")) if ceo_research_dir.is_dir() else set()
    ceo_research_reports = sorted(safe_relative_path(path, ROOT).as_posix() for path in ceo_reports_after - ceo_reports_before)
    selected = [item["agent_id"] for item in assignments]
    resume_plan = _resume_decision(resume, previous_delegation, task, assignments)
    save_progress("running", "Specialist work", "CEO assigned " + str(len(assignments)) + " stages; starting specialist execution.", 0, len(assignments))
    combined_context = context[:20000]
    (destination / "00-ceo-delegation.json").write_text(
        json.dumps({"task": task.strip(), "delegation_mode": delegation_mode,
                    "assignments": assignments, "human_approval_role": "AGENT-50"},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    records = []
    for index, assignment in enumerate(assignments, start=1):
        agent_id = assignment["agent_id"]
        role = roles_by_id[agent_id]
        specialist_task = assignment.get("task") or ("Complete your specialist contribution to: " + task.strip())
        filename = str(index).zfill(2) + "-" + slug(agent_id + "-" + role["name"]) + ".md"
        reused = _reusable_stage_text(destination, filename) if resume_plan["enabled"] else None
        if reused is not None:
            # A finished stage is read back, not re-run: the model is not called,
            # no research is repeated, and the file is not rewritten.
            resume_plan["stages_reused"] += 1
            quality_gate = extract_quality_gate(reused) if agent_id == "AGENT-08" else None
            records.append({
                "sequence": index, "agent_id": agent_id, "role": role["name"],
                "assigned_task": specialist_task, "output_file": filename,
                "status": "reused_from_previous_run", "retry_count": 0,
                "research_status": "not_rerun", "research_reports": [],
                "research_pages_attempted": 0, "research_pages_fetched": 0,
                "quality_gate": quality_gate if agent_id == "AGENT-08" else None,
                "mode": "local_model" if cfg.get("model", {}).get("enabled") else "template_fallback",
                "resumed": True,
            })
            save_progress("running", "Resuming stage " + str(index) + "/" + str(len(assignments)),
                          agent_id + " / " + role["name"] + " was already finished; its saved output is reused.",
                          index, len(assignments), agent_id, role["name"])
            combined_context = (combined_context + "\n\n--- " + role["name"] + " output (unverified) ---\n" + reused)[-24000:]
            continue
        reviewer_waiting = any(
            item.get("agent_id") == "AGENT-08" for item in assignments[index:]
        )
        stage_seconds = limits["min_stage_seconds"]
        tail_reserve = run_budget.reserve_for(reviewer_waiting=reviewer_waiting,
                                              min_stage_seconds=stage_seconds)
        is_reviewer = agent_id == "AGENT-08"
        # The reviewer runs while any time at all is left: stopping with output
        # that was never checked is worse than stopping before starting.
        if not is_reviewer and not run_budget.can_start(stage_seconds, tail_reserve):
            reason = ("the run budget of " + str(int(run_budget.total // 60)) + " minutes was "
                      + "exhausted with " + str(int(run_budget.remaining() // 60)) + " minutes left")
            run_budget.note_stage(agent_id, 0, skipped_reason=reason)
            records.append({
                "sequence": index, "agent_id": agent_id, "role": role["name"],
                "assigned_task": specialist_task, "output_file": "",
                "status": "skipped_out_of_time", "retry_count": 0,
                "research_status": "not_attempted", "research_reports": [],
                "research_pages_attempted": 0, "research_pages_fetched": 0,
                "quality_gate": None,
                "mode": "local_model" if cfg.get("model", {}).get("enabled") else "template_fallback",
                "reason": reason,
            })
            save_progress("running", "Stage skipped " + str(index) + "/" + str(len(assignments)),
                          agent_id + " was not started: " + reason + ".",
                          index, len(assignments), agent_id, role["name"])
            continue
        resume_plan["stages_run"] += 1
        stage_started = run_budget.timestamp()
        save_progress("running", "Specialist stage " + str(index) + "/" + str(len(assignments)), agent_id + " / " + role["name"] + " is researching and producing its assigned deliverable.", index - 1, len(assignments), agent_id, role["name"])
        instruction = (
            "OVERALL USER GOAL:\n" + task.strip()
            + "\n\nYOUR CEO-ASSIGNED SUBTASK:\n" + specialist_task
            + "\n\nPipeline stage " + str(index) + " of " + str(len(assignments)) + ". "
            + "Work on your assigned responsibility, not the entire task in parallel. "
            + "Use prior-stage notes as unverified working context. Correct errors when evidence permits. "
            + "This stage automatically attempts free web research. Prioritize primary sources, use the retrieved page text, compare independent sources for important claims, cite URLs, distinguish sourced facts from assumptions, and disclose search failures. Do not claim page verification unless page content was supplied. Do not claim external actions. "
            + "Return your concrete deliverable, validation status, and explicit unresolved issues."
        )
        if agent_id == "AGENT-08":
            instruction += (
                "\n\nMACHINE-READABLE FINAL GATE: End your deliverable with exactly one line in this format: "
                "OVERALL QUALITY GATE: PASS, PARTIAL, or FAIL. Use PASS only when critical claims are supported; "
                "PARTIAL when material evidence is missing; FAIL when material claims are unsupported, contradictory, or unsafe. "
                "Do not mark PASS merely because the draft is well formatted."
            )
        research_dir = ROOT / "workspace" / "research" / "agent-runs"
        reports_before = set(research_dir.glob(agent_id.lower() + "-*.md")) if research_dir.is_dir() else set()
        retry_count = 0
        try:
            result, retry_count = run_role_with_retry(role, instruction, combined_context, cfg)
        except Exception as exc:
            failed_retry_count = int(getattr(exc, "retry_count", 0))
            # Preserve research files created before a model timeout, then continue to
            # downstream specialists and the final quality gate.
            reports_after_failure = set(research_dir.glob(agent_id.lower() + "-*.md")) if research_dir.is_dir() else set()
            failed_stage_reports = sorted(reports_after_failure - reports_before)
            failed_stage_report_names = [safe_relative_path(path, ROOT).as_posix() for path in failed_stage_reports]
            research_pages_attempted = 0
            research_pages_fetched = 0
            evidence_sections = []
            for report_path in failed_stage_reports:
                structured_path = report_path.with_suffix(".json")
                try:
                    report_data = json.loads(structured_path.read_text(encoding="utf-8"))
                    metadata = report_data.get("metadata", {})
                    research_pages_attempted += int(metadata.get("pages_attempted", 0))
                    research_pages_fetched += int(metadata.get("pages_fetched", 0))
                except (OSError, ValueError, TypeError):
                    pass
                try:
                    evidence_sections.append(
                        "\n\n## Research saved before specialist failure — "
                        + safe_relative_path(report_path, ROOT).as_posix() + "\n"
                        + report_path.read_text(encoding="utf-8", errors="replace")[:5000]
                    )
                except OSError:
                    pass
            if research_pages_fetched:
                failure_research_status = "pages_fetched"
            elif research_pages_attempted:
                failure_research_status = "search_leads_only"
            elif failed_stage_reports:
                failure_research_status = "failure_disclosed"
            else:
                failure_research_status = "not_recorded"

            failure_filename = str(index).zfill(2) + "-" + slug(agent_id + "-" + role["name"] + "-failure") + ".md"
            report_listing = "\n".join("- " + item for item in failed_stage_report_names) or "- None recorded"
            failure_text = (
                "# Specialist stage failed: " + role["name"] + "\n\n"
                + "- Agent: " + agent_id + "\n"
                + "- Stage: " + str(index) + " of " + str(len(assignments)) + "\n"
                + "- Error type: " + type(exc).__name__ + "\n"
                + "- Error: " + str(exc)[:1000] + "\n"
                + "- Retry attempts used: " + str(failed_retry_count) + "\n"
                + "- Research status before failure: " + failure_research_status + "\n"
                + "- Research pages fetched before failure: " + str(research_pages_fetched) + "\n"
                + "- Research reports: \n" + report_listing + "\n\n"
                + "No specialist deliverable was confirmed. Any saved research below is source evidence to assess, "
                  "not proof of the final claims. Downstream stages may continue, but missing work remains unresolved.\n"
                + "".join(evidence_sections)
            )
            (destination / failure_filename).write_text(failure_text, encoding="utf-8")
            failure = {
                "sequence": index, "agent_id": agent_id, "role": role["name"],
                "assigned_task": specialist_task, "output_file": failure_filename, "status": "failed",
                "retry_count": failed_retry_count,
                "research_status": failure_research_status,
                "research_reports": failed_stage_report_names,
                "research_pages_attempted": research_pages_attempted,
                "research_pages_fetched": research_pages_fetched,
                "error_type": type(exc).__name__, "error": str(exc)[:500],
                "mode": "local_model" if cfg.get("model", {}).get("enabled") else "template_fallback",
                "seconds": round(run_budget.timestamp() - stage_started, 1),
            }
            records.append(failure)
            run_budget.note_stage(agent_id, run_budget.timestamp() - stage_started)
            save_progress("running", "Recovering from specialist failure", agent_id + " failed; the failure and available research were saved, and later stages will continue.", index, len(assignments), agent_id, role["name"])
            combined_context = (
                combined_context + "\n\n--- " + role["name"] + " stage failure and preserved research ---\n"
                + failure_text
            )[-24000:]
            continue
        (destination / filename).write_text(result.rstrip() + "\n", encoding="utf-8")
        quality_gate = extract_quality_gate(result) if agent_id == "AGENT-08" else None
        reports_after = set(research_dir.glob(agent_id.lower() + "-*.md")) if research_dir.is_dir() else set()
        new_report_paths = reports_after - reports_before
        research_reports = sorted(safe_relative_path(path, ROOT).as_posix() for path in new_report_paths)
        pages_attempted = 0
        pages_fetched = 0
        for report_path in new_report_paths:
            structured_path = report_path.with_suffix(".json")
            try:
                report_data = json.loads(structured_path.read_text(encoding="utf-8"))
                metadata = report_data.get("metadata", {})
                pages_attempted += int(metadata.get("pages_attempted", 0))
                pages_fetched += int(metadata.get("pages_fetched", 0))
            except (OSError, ValueError, TypeError):
                continue
        if pages_fetched:
            research_status = "pages_fetched"
        elif pages_attempted:
            research_status = "search_leads_only"
        elif research_reports:
            research_status = "failure_disclosed"
        else:
            result_lower = result.lower()
            research_status = "failure_disclosed" if ("web research attempt failed" in result_lower or "web research module unavailable" in result_lower) else "not_confirmed"
        records.append({
            "sequence": index, "agent_id": agent_id, "role": role["name"],
            "assigned_task": specialist_task, "output_file": filename, "status": "draft_generated",
            "retry_count": retry_count,
            "research_status": research_status, "research_reports": research_reports,
            "research_pages_attempted": pages_attempted, "research_pages_fetched": pages_fetched,
            "quality_gate": quality_gate if agent_id == "AGENT-08" else None,
            "mode": "local_model" if cfg.get("model", {}).get("enabled") else "template_fallback",
            "seconds": round(run_budget.timestamp() - stage_started, 1),
        })
        run_budget.note_stage(agent_id, run_budget.timestamp() - stage_started)
        combined_context = (combined_context + "\n\n--- " + role["name"] + " output (unverified) ---\n" + result)[-24000:]
    repair_attempt = {"attempted": False, "status": "not_needed", "reason": ""}
    reviewer_record = next((item for item in records if item.get("agent_id") == "AGENT-08"), {})
    if reviewer_record and reviewer_record.get("quality_gate", "unconfirmed") in {"partial", "fail", "unconfirmed"}:
        if not cfg.get("model", {}).get("enabled"):
            repair_attempt = {
                "attempted": False, "status": "blocked",
                "reason": "Local model is disabled; automatic semantic repair cannot be performed in template mode.",
                "trigger_gate": reviewer_record.get("quality_gate"),
            }
        else:
            task_lower = task.lower()
            preferred = (
                ["AGENT-52", "AGENT-51", "AGENT-20", "AGENT-09"]
                if re.search(r"\b(video|youtube|shorts|motion graphics|storyboard|animation)\b", task_lower)
                else ["AGENT-12", "AGENT-09", "AGENT-03"]
            )
            repair_assignment = next(
                (item for agent_id in preferred for item in assignments
                 if item.get("agent_id") == agent_id and agent_id != "AGENT-08"),
                next((item for item in reversed(assignments) if item.get("agent_id") != "AGENT-08"), None),
            )
            reviewer_file = destination / str(reviewer_record.get("output_file", ""))
            reviewer_feedback = reviewer_file.read_text(encoding="utf-8", errors="replace")[:10000] if reviewer_file.is_file() else "Reviewer feedback file missing."
            if not repair_assignment:
                repair_attempt = {
                    "attempted": False, "status": "blocked",
                    "reason": "No eligible specialist was available for a bounded repair attempt.",
                    "trigger_gate": reviewer_record.get("quality_gate"),
                }
            else:
                repair_id = repair_assignment["agent_id"]
                repair_role = roles_by_id.get(repair_id)
                repair_task = (
                    "AUTOMATIC QUALITY REPAIR ATTEMPT 1/1. Overall user goal: " + task.strip()
                    + "\nYour original assignment: " + str(repair_assignment.get("task", ""))[:2000]
                    + "\nThe independent reviewer returned " + str(reviewer_record.get("quality_gate", "unconfirmed")).upper()
                    + ". Address the concrete defects below, preserve supported facts, and explicitly label any issue you cannot resolve. "
                    "Return a corrected, complete deliverable; do not merely describe recommendations.\n\nREVIEWER FEEDBACK:\n"
                    + reviewer_feedback
                )
                repair_path = destination / ("99-repair-" + slug(repair_id + "-" + repair_role.get("name", "specialist")) + ".md")
                try:
                    repaired_output, repair_retries = run_role_with_retry(
                        repair_role, repair_task, (combined_context + "\n\nREVIEWER FEEDBACK:\n" + reviewer_feedback)[-24000:], cfg
                    )
                    repair_path.write_text(repaired_output.rstrip() + "\n", encoding="utf-8")
                    final_review_instruction = (
                        "FINAL QUALITY RE-REVIEW after one bounded repair attempt. Overall user goal: " + task.strip()
                        + "\nReview the repaired deliverable against the original goal, previous evidence, and initial review feedback. "
                        "Do not assume the repair succeeded. State remaining defects and evidence. End with exactly one line: "
                        "OVERALL QUALITY GATE: PASS, PARTIAL, or FAIL. PASS only if critical requirements are demonstrably met."
                        + "\n\nINITIAL REVIEW:\n" + reviewer_feedback
                        + "\n\nREPAIRED DELIVERABLE:\n" + repaired_output[:14000]
                    )
                    final_review, review_retries = run_role_with_retry(
                        roles_by_id["AGENT-08"], final_review_instruction,
                        (combined_context + "\n\nREPAIRED DELIVERABLE:\n" + repaired_output)[-30000:], cfg
                    )
                    final_review_path = destination / "99-final-quality-review.md"
                    final_review_path.write_text(final_review.rstrip() + "\n", encoding="utf-8")
                    final_gate = extract_quality_gate(final_review)
                    reviewer_record["initial_quality_gate"] = reviewer_record.get("quality_gate")
                    reviewer_record["quality_gate"] = final_gate
                    reviewer_record["final_review_file"] = str(final_review_path.name)
                    repair_attempt = {
                        "attempted": True, "status": "completed" if final_gate == "pass" else "unresolved",
                        "repair_agent_id": repair_id, "repair_file": repair_path.name,
                        "repair_retry_count": repair_retries, "final_review_file": final_review_path.name,
                        "final_review_retry_count": review_retries,
                        "initial_gate": reviewer_record.get("initial_quality_gate"),
                        "final_gate": final_gate,
                    }
                    combined_context = (combined_context + "\n\n--- Bounded repair output ---\n" + repaired_output
                                        + "\n\n--- Final quality re-review ---\n" + final_review)[-30000:]
                except Exception as exc:
                    repair_attempt = {
                        "attempted": True, "status": "failed",
                        "repair_agent_id": repair_id, "error_type": type(exc).__name__,
                        "error": str(exc)[:700], "failed_call_retry_count": int(getattr(exc, "retry_count", 0)),
                        "trigger_gate": reviewer_record.get("quality_gate"),
                    }
                    (destination / "99-repair-failure.md").write_text(
                        "# Automatic repair failed\n\n"
                        + "- Repair specialist: " + repair_id + "\n"
                        + "- Error: " + type(exc).__name__ + ": " + str(exc)[:1000] + "\n"
                        + "The initial reviewer result remains authoritative; no repair success is claimed.\n",
                        encoding="utf-8",
                    )

    save_progress("running", "Specialist stage complete", "All specialist stages have returned; assembling research evidence and preparing artifact tools.", len(assignments), len(assignments))
    research_sections = []
    research_budget = 18000
    research_root = canonical_path(ROOT / "workspace" / "research" / "agent-runs")
    for record in records:
        for report in record.get("research_reports", []):
            if research_budget <= 0:
                break
            report_path = canonical_path(ROOT / report)
            if not is_within(report_path, research_root, allow_equal=False) or report_path.suffix.lower() != ".md" or not report_path.is_file():
                continue
            try:
                report_text = report_path.read_text(encoding="utf-8", errors="replace")[:min(5000, research_budget)]
            except OSError:
                continue
            research_sections.append("\n\n## Source-linked research report — " + str(record.get("role", record.get("agent_id", "specialist"))) + "\n" + report_text)
            research_budget -= len(report_text)
        if research_budget <= 0:
            break
    tool_context = (
        (context or "")[:10000]
        + "\n\n## Retrieved specialist research reports (unverified until reviewed)\n"
        + "".join(research_sections)
        + "\n\n## CEO specialist deliverables (unverified until reviewed)\n"
        + combined_context[-10000:]
    )[:40000]
    save_progress("running", "Artifact generation", "Specialist stages finished; building selected artifacts and preparing the final quality status.", len(assignments), len(assignments))
    route_sink = {}
    # The builder gets the smaller of its own ceiling and what is left, so a long
    # build cannot consume the reviewer's reserved time or push the run past the
    # budget the user chose.
    build_seconds = run_budget.slice_for(limits["tool_loop_max_seconds"])
    # Kept beside the plan rather than written into it: the plan says what this
    # machine may do, this says what was actually left when the builder started.
    cfg["_build_seconds"] = build_seconds
    tool_runs = run_builtin_tools(task, destination, cfg, source_context=tool_context,
                                  route_sink=route_sink)
    route = route_sink.get("route")
    routing_record = route.as_dict() if route is not None else {}
    if routing_record:
        # The decision, the deterministic comparison, and every veto belong with
        # the run: "why did nothing build?" must be answerable from the manifest.
        (destination / "routing.json").write_text(
            json.dumps(routing_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    save_progress("running", "Post-build artifact validation", "Verifying generated files, media, strict QA reports, and release-safety metadata.")
    artifact_checks = verify_artifact_tool_runs(tool_runs, project_root=ROOT)
    change_review = _write_change_review(task, destination, tool_runs)
    required_tool_failed = any(item.get("status") == "failed" for item in tool_runs)
    required_tool_blocked = any(item.get("status") == "blocked" for item in tool_runs)
    reviewer_record = next((item for item in records if item.get("agent_id") == "AGENT-08"), {})
    reviewer_gate = reviewer_record.get("quality_gate", "unconfirmed")
    specialist_failed = any(item.get("status") == "failed" for item in records)
    stages_skipped = [item for item in records if item.get("status") == "skipped_out_of_time"]
    final_status = "failed" if required_tool_failed else (
        "blocked" if required_tool_blocked else (
            "review_failed" if reviewer_gate == "fail" else (
                "partial" if specialist_failed or stages_skipped or reviewer_gate in {"partial", "unconfirmed"} else "draft"
            )
        )
    )
    manifest = build_manifest(task, records, cfg, status=final_status, delegation_mode=delegation_mode, assignments=assignments, tool_runs=tool_runs, ceo_research_reports=ceo_research_reports, artifact_checks=artifact_checks, routing=routing_record)
    budget_record = run_budget.as_dict()
    budget_record["stage_budget_seconds"] = limits["min_stage_seconds"]
    budget_record["build_seconds_allowed"] = build_seconds
    if isinstance(manifest.get("resources"), dict):
        manifest["resources"]["budget"] = budget_record
    manifest["repair_attempt"] = repair_attempt
    manifest["resume"] = dict(resume_plan)
    manifest["change_review"] = change_review
    manifest["memory"] = _record_run_memory(store, memory_enabled, task, manifest, note, prior_runs, tool_runs)
    (destination / "budget.json").write_text(
        json.dumps(budget_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (destination / "pipeline-status.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    progress_status = "completed" if final_status == "draft" else ("failed" if final_status == "failed" else "needs_human_action")
    save_progress(progress_status, "Pipeline complete", "Pipeline ended with status: " + final_status + "; final quality gate: " + str(manifest.get("quality_gate", "unconfirmed")) + ".", len(assignments), len(assignments))
    return destination, manifest


def _write_change_review(task, destination, tool_runs):
    """Index every builder's writes into one review page for the run.

    The diffs themselves stay beside each builder's output; this page says which
    builder wrote what, and where to read the lines. Nothing here restates file
    content, so a manifest stays small.
    """
    entries = []
    for item in tool_runs or []:
        if not isinstance(item, dict):
            continue
        changes = item.get("changes")
        if not isinstance(changes, dict):
            continue
        entries.append({
            "tool": str(item.get("tool", "builder"))[:40],
            "artifact_dir": str(item.get("artifact_dir", ""))[:200],
            "files": [str(name)[:200] for name in (changes.get("files") or [])][:review.MAX_FILES],
            "summary": changes.get("summary") or {},
            "review": str(changes.get("review", "changes.md"))[:40],
        })
    # Kept in its own folder: the run directory's top level belongs to the stage
    # notes, and a review page must not be mistaken for one of them.
    review_dir = destination / "review"
    try:
        review_dir.mkdir(parents=True, exist_ok=True)
        (review_dir / "changes.md").write_text(
            review.render_aggregate(entries, title="Changes: " + str(task).strip()[:120]),
            encoding="utf-8")
    except OSError:
        return {"path": "", "builders": len(entries), "files_changed": 0,
                "error": "the change review could not be written"}
    files_changed = sum(int((item.get("summary") or {}).get("files_changed", 0)) for item in entries)
    try:
        path = safe_relative_path(canonical_path(review_dir / "changes.md"), ROOT).as_posix()
    except ValueError:
        path = "review/changes.md"
    return {
        "path": path,
        "builders": len(entries),
        "files_changed": files_changed,
    }


def _resume_decision(enabled, previous_delegation, task, assignments):
    """Decide whether this run continues the previous one in the same directory.

    Resuming is only safe when the previous run in this output directory was the
    same task with the same stages. Anything else would mix two jobs' outputs into
    one manifest that claims to describe a single run.
    """
    plan = {"enabled": False, "requested": bool(enabled), "reason": "",
            "stages_reused": 0, "stages_run": 0}
    if not enabled:
        plan["reason"] = "resume was not requested"
        return plan
    if not isinstance(previous_delegation, dict):
        plan["reason"] = "no previous run was found in this output directory"
        return plan
    previous_task = str(previous_delegation.get("task", "")).strip()
    if previous_task != str(task).strip():
        plan["reason"] = "the previous run in this directory was a different task"
        return plan
    previous_stages = [str(item.get("agent_id", "")) for item in previous_delegation.get("assignments") or []
                       if isinstance(item, dict)]
    current_stages = [str(item.get("agent_id", "")) for item in assignments]
    if previous_stages != current_stages:
        plan["reason"] = "the previous run assigned different stages"
        return plan
    plan["enabled"] = True
    plan["reason"] = "continuing the unfinished run in this output directory"
    return plan


def _reusable_stage_text(destination, filename):
    """A finished stage's saved output, or None when it is missing or empty."""
    path = destination / filename
    try:
        if not path.is_file() or path.stat().st_size == 0:
            return None
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    return text or None


def _record_run_memory(store, enabled, task, manifest, note, prior_runs, tool_runs):
    """Append this run to the workspace memory, and say what was read and written.

    A memory failure must never fail a run: it is a convenience record, not part of
    the deliverable, so an unreadable or unwritable store is reported, not raised.
    """
    if not enabled:
        return {"enabled": False, "reason": "disabled by AGENT_HQ_NO_MEMORY", "used": []}
    artifacts = sorted({
        str(item.get("artifact_dir", ""))
        for item in tool_runs or []
        if isinstance(item, dict) and item.get("artifact_dir")
    })[:memory.MAX_ARTIFACTS]
    entry = memory.entry_from_manifest(task, manifest, note=note, artifacts=artifacts)
    record = {
        "enabled": True,
        "used": [item.get("id", "") for item in prior_runs or []],
        "recorded": "",
        "store": "",
    }
    try:
        record["store"] = safe_relative_path(store.path, ROOT).as_posix()
    except ValueError:
        record["store"] = store.path.name
    try:
        record["recorded"] = store.record(entry)["id"]
    except (OSError, ValueError) as exc:
        record["error"] = type(exc).__name__ + ": this run was not recorded"
    return record


def format_duration(seconds):
    """Seconds as a short human string: 42s, 3m 05s, 1h 12m."""
    try:
        total = max(0, int(round(float(seconds))))
    except (TypeError, ValueError):
        return "unknown"
    if total < 60:
        return str(total) + "s"
    minutes, rest = divmod(total, 60)
    if minutes < 60:
        return str(minutes) + "m " + str(rest).zfill(2) + "s"
    hours, minutes = divmod(minutes, 60)
    return str(hours) + "h " + str(minutes).zfill(2) + "m"


def build_manifest(task, records, cfg, status, delegation_mode="unspecified", assignments=None, tool_runs=None, ceo_research_reports=None, artifact_checks=None, routing=None):
    return {
        "resources": dict(cfg.get("_resources") or {}),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "task": task.strip(),
        "pipeline": records,
        "delegation_mode": delegation_mode,
        "routing": routing or {},
        "ceo_assignments": assignments or [],
        "ceo_research_reports": ceo_research_reports or [],
        "tool_runs": tool_runs or [],
        "artifact_checks": artifact_checks or [],
        "quality_gate": next((item.get("quality_gate") or "unconfirmed" for item in records if item.get("agent_id") == "AGENT-08"), "unconfirmed"),
        "status": status,
        "model_enabled": bool(cfg.get("model", {}).get("enabled")),
        "research_performed": "attempted_for_each_specialist_stage",
        "research_method": "DuckDuckGo HTML search plus bounded public webpage text extraction; retrieved content is evidence to assess, not automatic verification",
        "research_pages_independently_verified": False,
        "external_actions_performed": False,
        "human_review_required": True,
        "note": "Sequential specialist pipeline; each specialist run attempts fresh web research and receives search leads. Search availability can fail, snippets are not independent verification, and outputs require quality review.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True)
    parser.add_argument("--context-file")
    parser.add_argument("--out", default="workspace/orchestration/run")
    parser.add_argument("--note", default="",
                        help="a human note to store with this run in the workspace memory")
    parser.add_argument("--no-memory", action="store_true",
                        help="do not read or write the workspace run memory")
    parser.add_argument("--resume", action="store_true",
                        help="reuse stages already finished in this output directory")
    parser.add_argument("--budget-minutes", type=float, default=None,
                        help="total wall-clock budget for the run (default: from the device tier)")
    parser.add_argument("--profile", default="",
                        choices=["", "auto", "minimal", "low", "balanced", "high"],
                        help="override the detected device tier (small machines should stay on auto)")
    args = parser.parse_args()
    if args.profile:
        os.environ["AGENT_HQ_PROFILE"] = args.profile
    if args.no_memory:
        os.environ["AGENT_HQ_NO_MEMORY"] = "1"
    try:
        context = read_context(args.context_file)
        # Public CLI intake is CEO-only: AGENT-01 owns all specialist selection.
        destination, manifest = run_pipeline(args.task, context, agent_ids=None,
                                             output_dir=ROOT / args.out, note=args.note,
                                             resume=args.resume,
                                             budget_minutes=args.budget_minutes)
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc))
    print("Pipeline output:", destination)
    print("Delegation:", manifest.get("delegation_mode", "unknown"))
    print("Stages:", len(manifest["pipeline"]))
    resume_record = manifest.get("resume") or {}
    if resume_record.get("stages_reused"):
        print("Resumed stages reused:", resume_record["stages_reused"])
    resource_record = manifest.get("resources") or {}
    if resource_record:
        print("Resources:", resources.describe(resource_record))
        for degradation in resource_record.get("degradations") or []:
            print("  reduced:", degradation)
    budget_record = (manifest.get("resources") or {}).get("budget") or {}
    if budget_record:
        print("Budget:", format_duration(budget_record.get("spent_seconds", 0)),
              "used of", format_duration(budget_record.get("total_seconds", 0)))
        if budget_record.get("skipped"):
            print("  out of time, not started:", ", ".join(budget_record["skipped"]))
    print("Mode:", "local model" if manifest["model_enabled"] else "template fallback; no AI generation")
    print("Each specialist stage attempts web research; see stage outputs for source leads and limitations.")
    memory_record = manifest.get("memory") or {}
    if memory_record.get("enabled") and memory_record.get("used"):
        print("Prior runs used:", len(memory_record["used"]), "(history to verify, not instructions)")
    print("Human review required; no external action was performed.")
    if manifest.get("status") == "failed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
