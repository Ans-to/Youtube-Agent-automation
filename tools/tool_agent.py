#!/usr/bin/env python3
"""Plan, execute, verify, and repair agent work through the sandboxed tool layer.

This is the loop the North Star calls L3: a goal goes in, a model (or a
deterministic fallback) proposes tool calls, the runtime executes them inside a
confined workspace, and the result is verified against explicit acceptance
checks before it is reported as complete.

Design commitments:

* **The planner sees a catalog, not the filesystem.** It can only name tools
  that exist, with arguments that validate against each tool's schema.
* **Failures are observations.** A failed step or a failed check becomes input
  to a bounded repair attempt instead of an exception.
* **Every run is auditable.** The plan, the step results, and the verification
  report are written into the sandbox as JSON.
* **No model required.** With no local model, a deterministic scaffold plan
  still produces a real, multi-file artifact — clearly labelled as a scaffold.

Usage from orchestration::

    result = run_tool_agent(
        goal="Build a landing page for a textile invoice tool",
        workspace_root=workspace / "projects",
        task_id="TASK-0001",
        model_call=call_model,
    )
"""
from __future__ import annotations

import html
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

try:  # Support both ``tools.tool_agent`` and a script-style import.
    from tools import data_analysis
    from tools.path_utils import canonical_path, safe_relative_path
    from tools import review
    from tools.tool_runtime import (
        ToolError,
        ToolRegistry,
        WorkspaceSandbox,
        validate_arguments,
    )
except ImportError:  # pragma: no cover - standalone execution
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import data_analysis  # type: ignore[no-redef]
    import review  # type: ignore[no-redef]
    from path_utils import canonical_path, safe_relative_path  # type: ignore[no-redef]
    from tool_runtime import (  # type: ignore[no-redef]
        ToolError,
        ToolRegistry,
        WorkspaceSandbox,
        validate_arguments,
    )

MAX_STEPS = 24
#: What the loop is allowed to be asked for. Each kind has a fixed deterministic
#: scaffold, a fixed set of acceptance checks, and an artifact contract the
#: orchestrator verifies independently. Adding a kind is a product decision.
DELIVERABLES = ("web", "document", "cli", "data")
MAX_REPAIRS = 2
MAX_GOAL_CHARS = 4_000
MAX_VERIFY_ITEMS = 12
MAX_STEP_LOG_ENTRIES = 200
DEFAULT_PLAN_TOKENS = 3_000
MAX_PLAN_PROMPT_CHARS = 16_000

# ``model_call(prompt, max_tokens) -> str``. Injected so this module never
# imports an agent module or opens a socket itself.
ModelCall = Callable[[str, int], str]


class PlanError(ValueError):
    """The planner produced something that cannot be executed safely."""


@dataclass(frozen=True)
class PlanStep:
    tool: str
    args: Mapping[str, Any] = field(default_factory=dict)
    why: str = ""


@dataclass(frozen=True)
class VerificationItem:
    path: str
    contains: str = ""

    def as_dict(self) -> dict:
        return {"path": self.path, "contains": self.contains}


@dataclass
class ToolPlan:
    goal: str
    mode: str
    deliverable: str = "web"
    steps: list[PlanStep] = field(default_factory=list)
    verify: list[VerificationItem] = field(default_factory=list)
    notes: str = ""

    def as_dict(self) -> dict:
        return {
            "goal": self.goal,
            "mode": self.mode,
            "deliverable": self.deliverable,
            "steps": [{"tool": step.tool, "args": dict(step.args), "why": step.why} for step in self.steps],
            "verify": [item.as_dict() for item in self.verify],
            "notes": self.notes,
        }


def normalise_deliverable(value: str | None) -> str:
    """Validate a requested deliverable kind, or raise."""
    kind = str(value or "web").strip().lower()
    if kind not in DELIVERABLES:
        raise ValueError(f"unknown deliverable '{kind}'; expected one of: {', '.join(DELIVERABLES)}")
    return kind


#: The files (and the text they must contain) each kind owes its consumer. The
#: orchestrator checks the real files on disk against this contract after the
#: run; keeping the contract here means a plan cannot quietly redefine it.
DELIVERABLE_CONTRACT = {
    "web": (("index.html", "<!doctype html"), ("README.md", "#")),
    "document": (("deliverable.md", "#"), ("deliverable.json", "\"ai_generated\"")),
    "cli": (("tool.py", "argparse"), ("README.md", "#")),
    "data": (("summary.json", '"schema"'), ("analysis.md", "# "), ("chart.svg", "<svg")),
}


# ---------------------------------------------------------------------------
# Planning prompt
# ---------------------------------------------------------------------------

PLANNER_SYSTEM = (
    "You are the planning head of a local automation system. You choose tools and "
    "write their inputs; you do not perform work yourself. Rules: return only valid "
    "JSON in the requested shape; use only tools in the catalog; never invent files "
    "that already exist; never claim an action you did not plan; keep artifacts "
    "self-contained and runnable offline with no external network, no API keys, and "
    "no paid services. Prefer a small number of complete files over many fragments. "
    "Write real, working content — never placeholders such as TODO, lorem ipsum, or "
    "'your code here'. Every file must be finished at the size you submit."
)


DELIVERABLE_BRIEF = {
    "web": (
        "DELIVERABLE: a working offline web page or small web app.",
        "index.html must be a complete document with a no-network Content-Security-Policy "
        "(connect-src 'none'), no external URLs, no external assets, and no build step. "
        "Include a README.md that says how to open it and what it does not do."
    ),
    "document": (
        "DELIVERABLE: one structured Markdown document plus machine-readable metadata.",
        "deliverable.md must start with a level-1 heading and carry real, specific content: "
        "purpose, scope, the decisions or steps, and acceptance criteria. "
        "deliverable.json must be a JSON object with keys schema (1), title, deliverable "
        "(\"document\"), generated_by, ai_generated (false), sections (array of strings), "
        "acceptance_criteria (array of strings), human_review_required (true). "
        "Write no fact you cannot support from the goal."
    ),
    "data": (
        "DELIVERABLE: a measured profile of one dataset, not an interpretation of it.",
        "summary.json must be the output of real column profiling: schema (1), rows, "
        "columns, numeric_columns, text_columns, columns_detail, complete_percent. "
        "analysis.md must start with a level-1 heading and contain '## Findings' and "
        "'## Limits'. chart.svg must be a self-contained SVG (no scripts, no external "
        "references) drawn from measured values. Never state a trend, correlation, or "
        "causal claim: none is computed."
    ),
    "cli": (
        "DELIVERABLE: a working command-line tool in the Python standard library.",
        "tool.py must run with `python tool.py`, parse arguments with argparse, expose "
        "--self-test, and exit non-zero on failure. README.md must show the exact commands. "
        "No third-party imports, no network, no file writes outside the workspace."
    ),
}


def build_plan_prompt(goal: str, catalog_json: str, *, allow_exec: bool,
                      deliverable: str = "web", feedback: str = "") -> str:
    """Compose the single planning prompt. Kept deterministic for testability."""
    kind = normalise_deliverable(deliverable)
    primary = DELIVERABLE_CONTRACT[kind][0][0]
    rules = [
        "Return JSON only, with this shape:",
        '{"steps":[{"tool":"write_file","args":{"path":"' + primary + '","content":"..."},"why":"one clause"}],'
        '"verify":[{"path":"' + primary + '","contains":"..."}]}',
        "Each step must name one catalog tool and pass exactly its declared arguments.",
        "Paths are relative to the workspace; absolute paths and '..' are rejected.",
        f"At most {MAX_STEPS} steps. At most {MAX_VERIFY_ITEMS} verify checks.",
        "verify must contain at least one check that proves the main deliverable exists.",
        "Use write_file for every file you create. Do not describe files you did not write.",
        "Keep each file under the write limit; split large work across steps.",
    ]
    rules.extend(DELIVERABLE_BRIEF[kind])
    if allow_exec:
        rules.append(
            "run_command is available: program must be python, python3, or node; args is a list of strings; "
            "no shell syntax. Use it only to run a check you wrote, never to fetch or install anything."
        )
    else:
        rules.append("run_command is not available in this workspace; do not plan it.")
    sections = [
        PLANNER_SYSTEM,
        "AUTOMATION RULES\n- " + "\n- ".join(rules),
        "DELIVERABLE KIND: " + kind,
        "TOOL CATALOG (JSON)\n" + catalog_json,
        "GOAL\n" + goal.strip(),
    ]
    if feedback.strip():
        sections.append("PREVIOUS ATTEMPT FAILED — FIX THESE OBSERVATIONS\n" + feedback.strip()[:4_000])
    return "\n\n".join(sections)[:MAX_PLAN_PROMPT_CHARS]


# ---------------------------------------------------------------------------
# Plan parsing and validation
# ---------------------------------------------------------------------------

def _extract_json_object(text: str) -> dict | None:
    """Return the first JSON object that decodes, tolerating prose around it."""
    if not isinstance(text, str):
        return None
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            parsed, _ = decoder.raw_decode(text[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def parse_plan(text: str, registry: ToolRegistry, *, goal: str = "", mode: str = "model") -> ToolPlan:
    """Validate a planner response into an executable plan.

    Invalid steps are dropped rather than trusted; if nothing survives, the
    caller gets a ``PlanError`` so it can fall back deterministically.
    """
    payload = _extract_json_object(text)
    if payload is None:
        raise PlanError("planner response contained no JSON object")

    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise PlanError("planner response has no steps array")

    by_name = {spec.name: spec for spec in registry.specs()}
    steps: list[PlanStep] = []
    rejected: list[str] = []
    for index, item in enumerate(raw_steps):
        if len(steps) >= MAX_STEPS:
            rejected.append(f"step {index}: exceeds the {MAX_STEPS}-step budget")
            break
        if not isinstance(item, dict):
            rejected.append(f"step {index}: must be an object")
            continue
        name = str(item.get("tool", "")).strip()
        spec = by_name.get(name)
        if spec is None:
            rejected.append(f"step {index}: unknown tool '{name[:40]}'")
            continue
        raw_args = item.get("args") if "args" in item else item.get("arguments")
        try:
            args = validate_arguments(raw_args if raw_args is not None else {}, spec.schema)
            # Reject escaping paths at plan time, not halfway through a run.
            if "path" in spec.schema.get("properties", {}) and isinstance(args.get("path"), str):
                registry.sandbox.resolve(args["path"])
        except ToolError as exc:
            rejected.append(f"step {index} ({name}): {exc}")
            continue
        steps.append(PlanStep(tool=name, args=args, why=str(item.get("why", ""))[:200]))

    if not steps:
        raise PlanError("no valid steps survived validation: " + "; ".join(rejected[:4]) or "empty plan")

    verify: list[VerificationItem] = []
    raw_verify = payload.get("verify")
    if isinstance(raw_verify, list):
        for item in raw_verify:
            if len(verify) >= MAX_VERIFY_ITEMS:
                break
            if not isinstance(item, dict):
                continue
            path = str(item.get("path", "")).strip()
            if not path:
                continue
            verify.append(VerificationItem(path=path[:400], contains=str(item.get("contains", ""))[:400]))
    if not verify:
        # Derive a floor from the writes so a lazy plan cannot claim success.
        for step in steps:
            if step.tool == "write_file":
                verify.append(VerificationItem(path=str(step.args["path"])))
                if len(verify) >= MAX_VERIFY_ITEMS:
                    break
        if not verify:
            raise PlanError("plan has no verification checks and writes no files")

    return ToolPlan(
        goal=goal,
        mode=mode,
        steps=steps,
        verify=verify,
        notes=("; ".join(rejected[:5]) if rejected else ""),
    )


# ---------------------------------------------------------------------------
# Deterministic fallback plan (no model required)
# ---------------------------------------------------------------------------

GENERIC_PAGE_NOUNS = (
    "landing page", "website", "web app", "webapp", "site", "page",
    "dashboard", "app", "product", "tool",
)


def _site_title(goal: str) -> str:
    """Derive a human title without letting the goal's verb become the headline."""
    text = re.sub(r"\s+", " ", goal).strip()
    text = re.sub(
        r"(?i)^(?:please\s+)?(?:build|create|make|generate|develop|implement|launch|design"
        r"|write|draft|compose|produce|prepare|assemble|render|export)\s+"
        r"(?:(?:me|a|an|the|my)\s+)?(?:(?:simple|small|local|offline|responsive|basic|functional|custom|tiny|working|modern|personal|professional)\s+){0,3}",
        "",
        text,
    )
    text = re.sub(r"(?i)^(?:a|an|the|my)\s+", "", text).strip()

    head, _, tail = text.partition(" for ")
    if not _ and not tail:
        head, _, tail = text.partition(" about ")
    if tail and head.strip().lower() in GENERIC_PAGE_NOUNS:
        # "a landing page for X" is about X; the word "page" is not the subject.
        text = re.sub(r"(?i)^(?:a|an|the)\s+", "", tail.strip()).title()
    else:
        text = head if tail else text
    if text.strip().lower() not in GENERIC_PAGE_NOUNS and text.strip().lower() not in {"portfolio"}:
        text = re.split(r"(?i)\s+(?:with|that|which|using)\s+", text, maxsplit=1)[0]
    text = text.strip(" .,:;!?-")[:70] or "Local Project"
    return text[:1].upper() + text[1:]


def _slug(value: str, limit: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:limit] or "project"


def deterministic_site_files(goal: str) -> dict[str, str]:
    """A complete, dependency-free starter site used when no model is available."""
    title = _site_title(goal)
    safe_title = html.escape(title)
    summary = html.escape(re.sub(r"\s+", " ", goal).strip()[:280] or title)
    return {
        "index.html": f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'none'; base-uri 'none'; form-action 'none'">
<title>{safe_title}</title>
<link rel="stylesheet" href="styles.css">
</head>
<body>
<header class="site-header">
  <p class="eyebrow">Offline project scaffold</p>
  <h1>{safe_title}</h1>
  <p class="lede">{summary}</p>
</header>
<main>
  <section aria-labelledby="work">
    <h2 id="work">Plan</h2>
    <ul class="steps">
      <li>Define the single job this page must do.</li>
      <li>Replace this scaffold with product-specific content and copy.</li>
      <li>Add real acceptance checks before publishing.</li>
    </ul>
  </section>
  <section aria-labelledby="demo">
    <h2 id="demo">Local checklist</h2>
    <p>Everything below runs in this browser tab. Nothing is uploaded anywhere.</p>
    <form id="item-form" autocomplete="off">
      <label for="item">Add an item</label>
      <div class="row">
        <input id="item" name="item" maxlength="120" required>
        <button type="submit">Add</button>
      </div>
    </form>
    <ul id="items" class="items"></ul>
    <button id="clear" type="button" class="secondary">Clear saved items</button>
    <p id="status" class="status" role="status" aria-live="polite"></p>
  </section>
</main>
<footer><p>Generated offline by Agent HQ. This is a deterministic scaffold, not AI-written product copy.</p></footer>
<script src="app.js"></script>
</body>
</html>
""",
        "styles.css": """:root{color-scheme:dark;--bg:#0b0b0f;--panel:#17171f;--text:#f4f2ec;--muted:#a7a7b3;--accent:#c8ff3d;--line:#353541}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.6 system-ui,-apple-system,Segoe UI,sans-serif}
.site-header,main,footer{max-width:900px;margin:0 auto;padding:0 20px}
.site-header{padding-top:56px;padding-bottom:8px}
.eyebrow{margin:0 0 8px;color:var(--accent);font-size:12px;letter-spacing:.14em;text-transform:uppercase}
h1{font-size:clamp(30px,5vw,52px);line-height:1.1;margin:0 0 12px}
h2{font-size:clamp(20px,3vw,28px);margin:0 0 12px}
.lede{color:var(--muted);max-width:62ch;margin:0}
section{margin:36px 0;padding:22px;background:var(--panel);border:1px solid var(--line);border-radius:16px}
.steps{padding-left:20px;color:var(--muted)}
.row{display:flex;gap:10px;margin-top:8px}
input{flex:1;padding:12px;border-radius:10px;border:1px solid #454552;background:#0d0d13;color:var(--text);font:inherit}
button{border:0;border-radius:10px;background:var(--accent);color:#101010;font-weight:700;padding:12px 16px;cursor:pointer}
button.secondary{background:transparent;color:var(--muted);border:1px solid var(--line);margin-top:14px}
.items{list-style:none;padding:0;margin:16px 0 0}
.items li{display:flex;justify-content:space-between;gap:12px;padding:10px 0;border-bottom:1px solid var(--line)}
.items button{background:transparent;color:var(--muted);padding:4px 8px;border:1px solid var(--line)}
.status{color:var(--muted);font-size:14px;min-height:1.4em;margin:10px 0 0}
footer{color:var(--muted);font-size:13px;padding-bottom:48px}
@media (max-width:520px){.row{flex-direction:column}button{width:100%}}
""",
        "app.js": """(function () {
  "use strict";
  var STORAGE_KEY = "offline-project-items";
  var form = document.getElementById("item-form");
  var input = document.getElementById("item");
  var list = document.getElementById("items");
  var status = document.getElementById("status");
  var clear = document.getElementById("clear");

  function read() {
    try {
      var parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
      return Array.isArray(parsed) ? parsed.filter(function (item) { return typeof item === "string"; }) : [];
    } catch (error) {
      return [];
    }
  }

  function save(items) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
    } catch (error) {
      status.textContent = "Storage is unavailable; items will not persist.";
    }
  }

  function render() {
    var items = read();
    list.textContent = "";
    items.forEach(function (text, index) {
      var row = document.createElement("li");
      var label = document.createElement("span");
      label.textContent = text;
      var remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "Remove";
      remove.addEventListener("click", function () {
        var next = read();
        next.splice(index, 1);
        save(next);
        render();
      });
      row.appendChild(label);
      row.appendChild(remove);
      list.appendChild(row);
    });
    status.textContent = items.length ? items.length + " item(s) saved locally." : "No items yet.";
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var value = input.value.trim();
    if (!value) { return; }
    var items = read();
    items.push(value);
    save(items);
    input.value = "";
    render();
  });

  clear.addEventListener("click", function () {
    save([]);
    render();
  });

  render();
})();
""",
        "README.md": f"""# {title}

Deterministic offline scaffold generated without a language model.

## What works

- `index.html` — semantic page with a strict Content-Security-Policy and no external requests
- `styles.css` — responsive layout, 16:9 and narrow-screen safe
- `app.js` — local checklist with `localStorage` persistence and no network calls

## Run it

Open `index.html` directly, or serve the folder locally:

```sh
python -m http.server 8080
```

## Honest status

This is a starting point, not a finished product. Replace the copy, add the real
workflow, and write acceptance tests before publishing. No AI-generated content
was used.
""",
    }


DOCUMENT_SECTIONS = (
    "Purpose",
    "Scope",
    "What is decided",
    "Acceptance criteria",
    "Open questions",
    "Next actions",
)


def _one_line(value: str, limit: int = 300) -> str:
    return re.sub(r"\s+", " ", value).strip().rstrip(".")[:limit] or "the stated goal"


def deterministic_document_files(goal: str) -> dict[str, str]:
    """A structured document with real acceptance criteria and no invented facts.

    The honest limit is written into the file itself: this is structure, not
    research. A document that pretends to summarise sources it never read would be
    worse than no document, so the scaffold states what it does not contain.
    """
    title = _site_title(goal)
    summary = _one_line(goal)
    criteria = [
        "Every section in this document contains at least one specific sentence, not a placeholder.",
        "The document names a single owner and a review date before it is circulated.",
        "Each factual claim is either sourced or removed; nothing is asserted from memory.",
        "Anything still open is listed under Open questions, not implied to be settled.",
    ]
    body = [
        f"# {title}",
        "",
        "> Deterministic scaffold generated offline by Agent HQ. It provides structure,",
        "> headings, and acceptance criteria only. No language model wrote it, no",
        "> research was performed for it, and no claim in it has been verified.",
        "> Replace the bracketed text before anyone relies on this document.",
        "",
        f"**Goal as given:** {summary}",
        "",
        "## Purpose",
        "",
        "State in one paragraph why this document exists and what decision or action",
        "it should enable. If it enables neither, delete the document.",
        "",
        "## Scope",
        "",
        "- In scope: [the work, decision, or system this covers]",
        "- Out of scope: [what a reader might reasonably expect but will not find here]",
        "- Owner: [one named person]",
        "- Review date: [YYYY-MM-DD]",
        "",
        "## What is decided",
        "",
        "| Decision | Rationale | Reversible? |",
        "| --- | --- | --- |",
        "| [decision] | [why] | [yes/no] |",
        "",
        "## Acceptance criteria",
        "",
    ]
    body.extend(f"{index}. {item}" for index, item in enumerate(criteria, start=1))
    body.extend([
        "",
        "## Open questions",
        "",
        "- [question that must be answered before the next step]",
        "",
        "## Next actions",
        "",
        "- [ ] [action] — [owner] — [date]",
        "",
    ])
    metadata = {
        "schema": 1,
        "title": title,
        "goal": summary,
        "deliverable": "document",
        "generated_by": "deterministic_scaffold",
        "ai_generated": False,
        "research_performed": False,
        "sections": list(DOCUMENT_SECTIONS),
        "acceptance_criteria": criteria,
        "human_review_required": True,
    }
    return {
        "deliverable.md": "\n".join(body),
        "deliverable.json": json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
    }


CLI_TEMPLATE = '''#!/usr/bin/env python3
"""{name} — a small standard-library records tool.

Deterministic scaffold generated offline by Agent HQ. The argument parsing,
reading, de-duplication, and self-test below are real and runnable; `clean()`
is the one function to replace with the rule this task actually needs.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def clean(record: str) -> str:
    """Normalise one record. Replace this with the task's real rule."""
    return " ".join(record.split())


def dedupe(records: list[str]) -> list[str]:
    """Drop repeats while keeping the original order."""
    seen: set[str] = set()
    kept: list[str] = []
    for item in records:
        if item not in seen:
            seen.add(item)
            kept.append(item)
    return kept


def load(paths: list[str]) -> list[str]:
    records: list[str] = []
    for path in paths:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        records.extend(clean(line) for line in text.splitlines() if line.strip())
    return records


def run(args: argparse.Namespace) -> int:
    records = load(args.files) if args.files else [
        clean(line) for line in sys.stdin if line.strip()
    ]
    if args.unique:
        records = dedupe(records)
    if args.json:
        print(json.dumps({"count": len(records), "records": records}, indent=2))
    else:
        for item in records:
            print(item)
    return 0


def self_test() -> int:
    """Prove the plumbing works, without a test framework."""
    assert clean("  a   b  ") == "a b"
    assert clean("") == ""
    assert dedupe(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]
    assert dedupe([]) == []
    print("self-test: ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="{name}: clean and de-duplicate text records.")
    parser.add_argument("files", nargs="*", help="UTF-8 text files; reads stdin when empty")
    parser.add_argument("--unique", action="store_true", help="drop repeated records")
    parser.add_argument("--json", action="store_true", help="print a JSON object instead of lines")
    parser.add_argument("--self-test", action="store_true", help="run the built-in checks and exit")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
'''


def deterministic_cli_files(goal: str, name: str = "") -> dict[str, str]:
    """A runnable command-line tool whose plumbing is finished and tested."""
    if not name:
        # "Build a CLI called photo-dedupe" names the tool; otherwise derive one.
        named = re.search(r"(?i)\b(?:called|named|titled)\s+[`'\"]?([a-z][a-z0-9_-]{1,40})", goal)
        name = named.group(1) if named else ""
    candidate = re.sub(r"[^a-z0-9_-]+", "-", (name or _slug(_site_title(goal), 32)).lower()).strip("-")
    tool_name = candidate if re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", candidate or "") else "records-tool"
    readme = f"""# {tool_name}

A small command-line tool in the Python standard library, generated offline by
Agent HQ as a deterministic scaffold.

## What is real

- `tool.py` parses arguments, reads files or stdin, cleans records, optionally
  de-duplicates them, and prints text or JSON.
- `python tool.py --self-test` runs the built-in checks; they exit non-zero on
  failure, so the tool can be verified without a test framework.
- No third-party imports, no network access, no writes outside the workspace.

## What is not

`clean()` in `tool.py` only normalises whitespace. It is a placeholder for the
rule this task needs. Until that rule is written and tested, this tool cleans and
de-duplicates text — it does not do the job the goal describes, and nothing here
should be read as claiming that it does.

## Usage

```sh
python tool.py --self-test
python tool.py records.txt --unique
cat records.txt | python tool.py --json
```
"""
    return {"tool.py": CLI_TEMPLATE.replace("{name}", tool_name), "README.md": readme}


def deterministic_data_files(goal: str, *, data_text: str = "", data_name: str = "",
                             title: str = "", reason: str = "") -> dict[str, str]:
    """A real profile of the supplied dataset, plus a runner that reproduces it.

    When no dataset is available the same four files are produced with an explicit
    "nothing was measured" record rather than invented numbers, so a consumer can
    never mistake the scaffold for analysis.
    """
    report_title = (title or "").strip()
    # `data_text == ""` means no file was read; whitespace means a file was read and
    # is unusable, which must be reported as such rather than as "no dataset".
    if data_text:
        try:
            summary = data_analysis.summarize(data_text, source_name=data_name, title=report_title)
        except data_analysis.DataError as exc:
            summary = data_analysis.empty_summary(
                report_title or _site_title(goal),
                reason=f"The supplied dataset could not be read: {exc}")
    else:
        summary = data_analysis.empty_summary(
            report_title or _site_title(goal),
            reason=reason or "No CSV was supplied with this request, so there is nothing to measure.")
    return {
        "summary.json": json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        "analysis.md": data_analysis.render_markdown(summary),
        "chart.svg": data_analysis.render_svg(summary),
        "analyze.py": data_analysis.ANALYZE_SCRIPT,
    }


def deterministic_plan(goal: str, *, allow_exec: bool = False,
                       deliverable: str = "web", deliverable_name: str = "",
                       data_text: str = "", data_name: str = "",
                       data_reason: str = "") -> ToolPlan:
    """A fixed, safe plan that still produces a genuine artifact offline."""
    kind = normalise_deliverable(deliverable)
    if kind == "document":
        return _scaffold_plan(goal, deterministic_document_files(goal), kind, allow_exec=allow_exec,
                              notes="No local model was available; this is a labelled document scaffold.")
    if kind == "cli":
        return _scaffold_plan(goal, deterministic_cli_files(goal, name=deliverable_name), kind,
                              allow_exec=allow_exec,
                              notes="No local model was available; this is a labelled CLI scaffold.")
    if kind == "data":
        files = deterministic_data_files(goal, data_text=data_text, data_name=data_name,
                                         title=deliverable_name, reason=data_reason)
        notes = ("No local model was available; the numbers are measured from the supplied "
                 "file, and no interpretation was applied.")
        if not data_text.strip():
            notes = ("No dataset was supplied, so nothing was measured; the artifact "
                     "records that explicitly.")
        return _scaffold_plan(goal, files, kind, allow_exec=allow_exec, notes=notes)
    files = deterministic_site_files(goal)
    steps = [
        PlanStep(tool="write_file", args={"path": name, "content": content},
                 why="deterministic scaffold file")
        for name, content in files.items()
    ]
    verify = [
        VerificationItem(path="index.html", contains="<!doctype html>"),
        VerificationItem(path="index.html", contains="styles.css"),
        VerificationItem(path="app.js", contains="localStorage"),
        VerificationItem(path="README.md", contains="offline scaffold"),
    ]
    if allow_exec and _exec_available():
        # A no-network syntax check of the generated JavaScript, when Node exists.
        steps.append(PlanStep(tool="run_command", args={"program": "node", "args": ["--check", "app.js"]},
                              why="verify generated JavaScript parses"))
    return ToolPlan(goal=goal, mode="deterministic", deliverable=kind, steps=steps, verify=verify,
                    notes="No local model was available; this is a labelled scaffold.")


def _scaffold_plan(goal: str, files: dict[str, str], kind: str, *,
                   allow_exec: bool = False, notes: str = "") -> ToolPlan:
    """Turn a deterministic file set into a verified plan for one deliverable kind."""
    steps = [
        PlanStep(tool="write_file", args={"path": name, "content": content},
                 why="deterministic scaffold file")
        for name, content in files.items()
    ]
    verify = [VerificationItem(path=name, contains=needle)
              for name, needle in DELIVERABLE_CONTRACT[kind]]
    interpreter = _python_program() if allow_exec and kind == "cli" else ""
    if interpreter:
        # The tool ships its own checks; run them rather than trusting the text.
        steps.append(PlanStep(tool="run_command",
                              args={"program": interpreter, "args": ["tool.py", "--self-test"]},
                              why="run the generated tool's self-test"))
    return ToolPlan(goal=goal, mode="deterministic", deliverable=kind,
                    steps=steps, verify=verify, notes=notes)


def _python_program() -> str:
    """An allowlisted Python interpreter that exists on this machine.

    Windows installs ``python`` and not ``python3``; planning a command that the
    runtime would refuse is worse than planning none, because the failure looks
    like a broken artifact instead of a missing launcher.
    """
    import shutil

    for name in ("python3", "python"):
        if shutil.which(name):
            return name
    return ""


def _exec_available() -> bool:
    import shutil

    return bool(shutil.which("node"))


# ---------------------------------------------------------------------------
# Execution and verification
# ---------------------------------------------------------------------------

def execute_plan(registry: ToolRegistry, plan: ToolPlan,
                 baseline: dict[str, str | None] | None = None) -> list[dict]:
    """Run every step in order, stopping only when the step budget is exhausted.

    When ``baseline`` is given, the content of each file is captured before the
    first step that writes it, so the run can later show a diff rather than a
    dump. The first capture wins: a repair attempt rewriting the same file must
    still be compared with what the run found, not with the failed attempt.
    """
    results: list[dict] = []
    for index, step in enumerate(plan.steps[:MAX_STEPS], start=1):
        if baseline is not None and step.tool == "write_file":
            path = step.args.get("path")
            if isinstance(path, str) and path not in baseline:
                try:
                    baseline[path] = review.read_text_file(registry.sandbox.resolve(path))
                except ToolError:
                    pass
        result = registry.execute(step.tool, dict(step.args))
        result["step"] = index
        result["why"] = step.why
        if step.tool == "write_file":
            # Do not echo file bodies into logs or manifests.
            result.pop("content", None)
        results.append(result)
        if len(results) >= MAX_STEP_LOG_ENTRIES:
            break
    return results


def verify_plan(registry: ToolRegistry, plan: ToolPlan) -> list[dict]:
    """Check the acceptance criteria against what is actually on disk."""
    checks: list[dict] = []
    for item in plan.verify[:MAX_VERIFY_ITEMS]:
        check = {"path": item.path, "contains": item.contains}
        try:
            target = registry.sandbox.resolve(item.path)
        except ToolError as exc:
            checks.append({**check, "status": "failed", "error": str(exc)})
            continue
        if not target.is_file():
            checks.append({**check, "status": "failed", "error": "file does not exist"})
            continue
        size = target.stat().st_size
        if size <= 0:
            checks.append({**check, "status": "failed", "error": "file is empty"})
            continue
        if item.contains:
            try:
                text = target.read_text(encoding="utf-8", errors="replace")
            except OSError:
                checks.append({**check, "status": "failed", "error": "file could not be read"})
                continue
            if item.contains not in text:
                checks.append({**check, "status": "failed", "error": "required text is missing"})
                continue
        checks.append({**check, "status": "passed", "bytes": size})
    return checks


def _failure_feedback(step_results: list[dict], checks: list[dict]) -> str:
    lines: list[str] = []
    for result in step_results:
        if result.get("status") != "ok":
            detail = result.get("error") or ""
            lines.append(f"- {result.get('tool')} failed: {detail[:300]}")
        elif result.get("tool") == "run_command" and result.get("exit_code") not in (0, None):
            lines.append(f"- command exited {result['exit_code']}: {(result.get('stderr') or '')[:300]}")
    for check in checks:
        if check.get("status") != "passed":
            lines.append(f"- verification failed for {check['path']}: {check.get('error', 'unknown')}")
    return "\n".join(lines[:20])


def _artifacts(step_results: list[dict]) -> list[str]:
    seen: list[str] = []
    for result in step_results:
        path = result.get("path")
        if result.get("tool") == "write_file" and isinstance(path, str) and path not in seen:
            seen.append(path)
    return seen


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_tool_agent(
    goal: str,
    workspace_root: str | Path,
    task_id: str,
    *,
    model_call: ModelCall | None = None,
    allow_exec: bool = False,
    deliverable: str = "web",
    deliverable_name: str = "",
    data_text: str = "",
    data_name: str = "",
    data_reason: str = "",
    max_repairs: int = MAX_REPAIRS,
    max_seconds: int = 900,
    timeout_seconds: int = 120,
) -> dict:
    """Plan → execute → verify → repair, inside one confined task sandbox.

    ``deliverable`` selects the artifact contract: a web page or app, a
    structured document, or a command-line tool. It changes the deterministic
    scaffold, the instructions the model receives, and the acceptance checks the
    orchestrator applies afterwards — never the sandbox, the tool set, or the
    repair budget.

    Returns a manifest-safe dict. The status is ``completed`` only when every
    acceptance check passes; otherwise it is ``failed`` with the observations
    that explain why.
    """
    if not isinstance(goal, str) or not goal.strip():
        raise ValueError("goal must be a non-empty string")
    goal = goal.strip()[:MAX_GOAL_CHARS]
    deliverable = normalise_deliverable(deliverable)
    max_repairs = max(0, min(int(max_repairs), MAX_REPAIRS))
    started = time.monotonic()

    try:
        sandbox = WorkspaceSandbox(
            Path(workspace_root) / "projects" / _slug(task_id),
            allow_exec=allow_exec,
            timeout_seconds=timeout_seconds,
        )
    except (ToolError, OSError) as exc:
        return {"tool": "tool_agent", "status": "failed", "error": f"sandbox could not be created: {exc}"}

    registry = ToolRegistry(sandbox)
    catalog = registry.catalog_json(max_chars=6_000)
    attempts: list[dict] = []
    baseline: dict[str, str | None] = {}
    feedback = ""
    plan: ToolPlan | None = None
    executed_plan: ToolPlan | None = None
    step_results: list[dict] = []
    checks: list[dict] = []

    for attempt_index in range(max_repairs + 1):
        remaining = max_seconds - (time.monotonic() - started)
        if remaining <= 1:
            feedback = "time budget exhausted"
            break

        plan_error = ""
        if model_call is not None:
            prompt = build_plan_prompt(goal, catalog, allow_exec=allow_exec,
                                       deliverable=deliverable, feedback=feedback)
            try:
                response = model_call(prompt, DEFAULT_PLAN_TOKENS)
                plan = parse_plan(response, registry, goal=goal, mode="model")
            except PlanError as exc:
                plan_error = str(exc)
                plan = None
            except (OSError, RuntimeError, ValueError) as exc:
                plan_error = f"model call failed: {type(exc).__name__}"
                plan = None
        if model_call is None or plan is None:
            if attempt_index == 0 or model_call is None:
                plan = deterministic_plan(goal, allow_exec=allow_exec, deliverable=deliverable,
                                          deliverable_name=deliverable_name,
                                          data_text=data_text, data_name=data_name,
                                          data_reason=data_reason)
                if plan_error:
                    plan.notes = (plan.notes + " | planner error: " + plan_error)[:500]
            else:
                feedback = (feedback + "\n- " + plan_error).strip()
                break

        executed_plan = plan
        # The requested kind is the caller's decision; a plan describes how to
        # meet it, not what was asked for.
        plan.deliverable = deliverable
        step_results = execute_plan(registry, plan, baseline=baseline)
        checks = verify_plan(registry, plan)
        attempts.append({
            "attempt": attempt_index + 1,
            "mode": plan.mode,
            "steps": len(plan.steps),
            "failed_steps": sum(1 for item in step_results if item.get("status") != "ok"),
            "failed_checks": sum(1 for item in checks if item.get("status") != "passed"),
        })
        if all(check.get("status") == "passed" for check in checks) and all(
            item.get("status") == "ok" for item in step_results
        ):
            break
        feedback = _failure_feedback(step_results, checks)
        if model_call is None:
            break

    passed = bool(checks) and all(check.get("status") == "passed" for check in checks) and all(
        item.get("status") == "ok" for item in step_results
    )
    mode = executed_plan.mode if executed_plan else "none"
    if passed:
        # A deterministic scaffold is verified, but it is not model-authored work.
        status = "completed" if mode == "model" else "partial"
    else:
        status = "failed"

    changes = review.build_changes(sandbox.root, baseline, title=goal)
    review.write(sandbox.root, changes, title="Changes: " + goal[:120])
    artifacts = _artifacts(step_results)
    try:
        artifact_dir = safe_relative_path(sandbox.root, canonical_path(workspace_root)).as_posix()
    except (ValueError, OSError):
        artifact_dir = "projects/" + _slug(task_id)
    manifest = {
        "tool": "tool_agent",
        "status": status,
        "mode": mode,
        "deliverable": deliverable,
        "goal": goal,
        "attempts": attempts,
        "step_count": len(step_results),
        "steps": [
            {key: value for key, value in result.items() if key not in {"stdout", "stderr"}}
            for result in step_results
        ],
        "verification": checks,
        "artifacts": artifacts,
        "changes": review.manifest_entry(changes),
        "sandbox": artifact_dir,
        "artifact_dir": artifact_dir,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "exec_enabled": allow_exec,
        "human_review_required": True,
        "note": (
            "Verified artifact: every acceptance check passed."
            if passed
            else "Not verified: acceptance checks failed; the workspace is preserved for inspection."
        ),
    }
    if executed_plan is not None:
        _write_json(sandbox.root / "tool-plan.json", executed_plan.as_dict())
    _write_json(sandbox.root / "tool-runs.json", {
        "goal": goal,
        "status": status,
        "steps": manifest["steps"],
        "verification": checks,
    })
    _write_json(sandbox.root / "tool-summary.json", {
        key: manifest[key] for key in (
            "status", "mode", "deliverable", "attempts", "artifact_dir", "artifacts",
            "elapsed_seconds", "human_review_required", "note",
        )
    })
    manifest["files"] = [
        name for name in ("tool-plan.json", "tool-runs.json", "tool-summary.json",
                          "changes.json", "changes.md")
        if (sandbox.root / name).is_file()
    ]
    return manifest


def main() -> int:
    """Run the loop from the command line, for inspection and debugging."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("goal", help="what the agent should produce")
    parser.add_argument("--workspace", default="workspace/projects", help="sandbox parent directory")
    parser.add_argument("--task-id", default="cli", help="sandbox name")
    parser.add_argument("--allow-exec", action="store_true", help="permit the allowlisted command tool")
    args = parser.parse_args()
    import os
    import sys

    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    model_call = None
    try:
        from agents import dispatch  # noqa: F401  (import guarded: optional)
        from app_config import load_config

        cfg = load_config()
        if cfg.get("model", {}).get("enabled"):
            model = cfg["model"]

            def model_call(prompt: str, max_tokens: int) -> str:
                body = {
                    "model": model.get("model", "local-model"),
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": max_tokens,
                }
                data = dispatch.post_local_model(model.get("base_url", ""), body, int(model.get("timeout_seconds", 240)))
                return data["choices"][0]["message"]["content"]
    except (ImportError, KeyError, TypeError, ValueError, OSError) as exc:
        print(f"note: local model unavailable ({type(exc).__name__}); using the deterministic planner", flush=True)
        model_call = None
    result = run_tool_agent(
        args.goal,
        args.workspace,
        args.task_id,
        model_call=model_call,
        allow_exec=args.allow_exec or os.environ.get("AGENT_HQ_ALLOW_EXEC", "").strip().lower() in {"1", "true", "yes", "on"},
    )
    print(json.dumps({key: result[key] for key in ("status", "mode", "artifact_dir", "verification", "note")}, indent=2))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
