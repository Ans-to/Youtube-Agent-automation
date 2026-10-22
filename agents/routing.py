#!/usr/bin/env python3
"""Choose which local pipeline runs a task, and record why.

Before this module, `agents/orchestrate.py` decided what work to do with a pile of
regular expressions next to the code that ran it: `video_requested`,
`web_requested`, `product_requested`. That works for the phrasings it was tuned
on and fails silently on everything else — there is no way for a goal the
patterns do not match to reach a builder, and no record of why a builder did or
did not run.

This module turns that decision into a named step:

* **A pipeline catalog.** Five pipelines exist, each with an id, a summary, a
  deliverable kind, the arguments it accepts, and the phrasings it must never
  claim. The catalog is what the model sees; it is also what validation checks
  against, so the two cannot drift.
* **A model router.** With a local model enabled, the model chooses from that
  catalog (an empty choice is valid and often correct) and returns validated
  arguments. It is choosing among existing code paths — it cannot name a new
  pipeline, cannot pass shell text, and cannot widen an argument's bounds.
* **A deterministic router.** With no model, the same catalog is selected with
  explicit patterns. This is the previous behaviour, moved, not improved, so
  that enabling the router is not a silent behaviour change on existing tasks.
* **Vetoes that apply to both.** A veto is a *policy* rule, not a preference:
  "describe how to build a website" is not a build request, and a YouTube
  automation *studio* is software, not a video to render. A model choice that
  contradicts a veto is dropped with the reason recorded, so the router can add
  coverage but cannot remove a guard.

Nothing here executes a pipeline. It returns a `Route`; the caller decides how to
run each request and remains responsible for its own execution-time guards
(no render without a model, no publish without approval).

Usage::

    route = routing.route_task(task, cfg, model_call=routing_model_call(cfg))
    for request in route.requests:
        ...  # request.pipeline, request.args, request.why
    manifest["routing"] = route.as_dict()
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

MAX_GOAL_CHARS = 6_000
MAX_REQUESTS = 3
MAX_PROMPT_CHARS = 12_000
DEFAULT_ROUTE_TOKENS = 700

#: ``call(prompt, max_tokens) -> str``. Injected, never opened here.
ModelCall = Callable[[str, int], str]

# Pipelines that write files through the confined tool loop. One run per task:
# two of them would produce two unrelated workspaces and two competing claims
# about what the deliverable is.
TOOL_LOOP_PIPELINES = ("web_build", "document_deliverable", "cli_tool")

BUILD_VERB_WORDS = (
    "build|create|make|generate|produce|develop|implement|write|draft|compose"
    "|design|code|render|export|assemble|scaffold|prototype"
)
BUILD_VERBS = r"\b(?:" + BUILD_VERB_WORDS + r")\b"

# A request for analysis, explanation, or advice. Construction pipelines must not
# claim it: an offline scaffold cannot summarise a document or answer a question,
# and returning one as though it had would be a false completion.
ADVISORY_OPENING = re.compile(
    r"(?i)^\s*(?:how\s+(?:do|can|would|should|to)\b|what\s+(?:is|are|would|should)\b"
    r"|why\b|explain\b|compare\b|tell\s+me\b|should\s+i\b|could\s+i\b|can\s+i\b"
    r"|is\s+it\b|are\s+there\b|recommend\b|suggest\b|review\b|critique\b"
    r"|summari[sz]e\b|analyse\b|analyze\b|describe\b|list\b|brainstorm\b|ideas?\b)"
)

# ...unless the same sentence also asks, in the first person, for something to be
# produced. "Explain how to build a website" is a question; "explain the options
# and build me a website" is a request.
PRODUCE_MARKER = re.compile(
    r"(?i)\b(?:" + BUILD_VERB_WORDS + r")\s+(?:me|us)\b"
    r"|\b(?:i\s+need|i\s+want|i'?d\s+like|please\s+(?:build|create|make|write))\b"
)


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PipelineSpec:
    """One existing code path the router may select, and the rules it obeys."""

    id: str
    summary: str
    deliverable: str
    executor: str
    examples: tuple[str, ...] = ()
    arguments: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    vetoes: tuple[tuple[str, str], ...] = ()
    policy: tuple[str, ...] = ()
    requires: str = ""

    def catalog_entry(self) -> dict:
        entry = {
            "id": self.id,
            "summary": self.summary,
            "deliverable": self.deliverable,
            "examples": list(self.examples),
            "args": {name: {key: value for key, value in schema.items() if key != "default"}
                     for name, schema in self.arguments.items()},
        }
        if self.requires:
            entry["requires"] = self.requires
        if self.policy:
            entry["policy"] = list(self.policy)
        return entry


PIPELINES: tuple[PipelineSpec, ...] = (
    PipelineSpec(
        id="video_production",
        summary="Build a YouTube package: research, script, storyboard, scenes, metadata, and QA.",
        deliverable="video_package",
        executor="video_studio",
        examples=(
            "Create a 6-minute YouTube video about solar maintenance in Sindh",
            "Make a short-form video explaining invoice matching",
        ),
        arguments={
            "topic": {"type": "string", "maxLength": 500},
            "format": {"type": "string", "enum": ["long", "shorts"], "default": "long"},
            "language": {"type": "string", "enum": ["", "en", "ur-en"], "default": ""},
            "target_minutes": {"type": "number", "minimum": 0.5, "maximum": 60},
            "render": {"type": "boolean", "default": False},
        },
        vetoes=(
            (r"(?i)\b(?:youtube|content)\s+automation\s+(?:agent\s+)?(?:studio|software|system|platform|pipeline)\b",
             "the goal asks for an automation studio or software system, not a video to produce"),
        ),
        policy=(
            "Rendering to MP4 requires a local model and a compatible voice backend; "
            "the package is still produced without one.",
        ),
        requires="nothing to build the package; a local model plus a verified voice for MP4",
    ),
    PipelineSpec(
        id="web_build",
        summary="Write a complete offline web page or small web app inside the confined tool loop.",
        deliverable="web",
        executor="tool_agent",
        examples=(
            "Build a landing page for a textile invoice tool",
            "Create a small web app that matches supplier invoices",
        ),
        arguments={"title": {"type": "string", "maxLength": 100}},
        vetoes=(),
        policy=("One web build per task; it must pass its own acceptance checks to count.",),
    ),
    PipelineSpec(
        id="document_deliverable",
        summary="Write a structured Markdown document plus machine-readable metadata.",
        deliverable="document",
        executor="tool_agent",
        examples=(
            "Write a changelog for the v2 release",
            "Draft a one-page project brief for the invoice tool",
        ),
        arguments={"title": {"type": "string", "maxLength": 100}},
        vetoes=(),
        policy=(
            "The offline scaffold produces structure and acceptance criteria, not "
            "researched prose; it is labelled as such.",
        ),
    ),
    PipelineSpec(
        id="cli_tool",
        summary="Write a small standard-library Python command-line tool with a self-test.",
        deliverable="cli",
        executor="tool_agent",
        examples=(
            "Build a CLI that deduplicates photo files by hash",
            "Create a command-line tool that reconciles two CSV files",
        ),
        arguments={"name": {"type": "string", "maxLength": 60,
                            "pattern": r"^[a-z][a-z0-9_-]*$"}},
        vetoes=(),
        policy=("Python standard library only; no package installation, no network.",),
    ),
    PipelineSpec(
        id="product_prototype",
        summary="Package a digital-product prototype with a README, status file, and archive.",
        deliverable="product_prototype",
        executor="product_studio",
        examples=(
            "Build a digital product prototype for invoice reconciliation",
            "Create a small offline tool product I could sell",
        ),
        arguments={
            "title": {"type": "string", "maxLength": 100},
            "idea": {"type": "string", "maxLength": 1000},
        },
        vetoes=(),
        policy=("The prototype is always marked draft and never publishable without human review.",),
    ),
)

PIPELINES_BY_ID: dict[str, PipelineSpec] = {spec.id: spec for spec in PIPELINES}


def pipeline_catalog(max_chars: int = 8_000) -> str:
    """Compact JSON catalog for a routing prompt."""
    payload = [spec.catalog_entry() for spec in PIPELINES]
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))[:max_chars]


def tool_catalog(max_chars: int = 4_000) -> str:
    """Describe the tools a chosen pipeline would be able to use.

    The router never calls these tools; the model reads them so it can tell a
    deliverable that needs file writes from one that does not.
    """
    try:
        from tools.tool_runtime import default_tool_catalog
    except ImportError:  # standalone execution from agents/
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from tools.tool_runtime import default_tool_catalog  # type: ignore[no-redef]

    return json.dumps(default_tool_catalog(allow_exec=False), ensure_ascii=False,
                      separators=(",", ":"))[:max_chars]


# ---------------------------------------------------------------------------
# Route value
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RouteRequest:
    pipeline: str
    args: Mapping[str, Any] = field(default_factory=dict)
    why: str = ""

    def as_dict(self) -> dict:
        return {"pipeline": self.pipeline, "args": dict(self.args), "why": self.why}


@dataclass
class Route:
    """What should run, what was rejected, and how the decision was made."""

    mode: str
    requests: list[RouteRequest] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    vetoed: list[str] = field(default_factory=list)
    notes: str = ""
    advisory: bool = False
    #: What the deterministic router would have chosen, kept for comparison.
    heuristic: list[str] = field(default_factory=list)

    @property
    def pipelines(self) -> list[str]:
        return [request.pipeline for request in self.requests]

    @property
    def agreement(self) -> str:
        """How the model's choice compares with the deterministic one."""
        if self.mode not in {"model", "model_rejected_plan"}:
            return "not_applicable"
        if sorted(self.pipelines) == sorted(self.heuristic):
            return "match"
        if not self.pipelines and self.heuristic:
            return "model_chose_nothing"
        if self.pipelines and not self.heuristic:
            return "model_only"
        return "differs"

    def as_dict(self) -> dict:
        return {
            "mode": self.mode,
            "pipelines": self.pipelines,
            "requests": [request.as_dict() for request in self.requests],
            "heuristic_pipelines": list(self.heuristic),
            "agreement": self.agreement,
            "advisory": self.advisory,
            "vetoed": list(self.vetoed),
            "rejected": list(self.rejected),
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Intent text
# ---------------------------------------------------------------------------

def extract_intent(task: str) -> str:
    """The user's own words, without the intake wrapper when one is present."""
    text = str(task or "").strip()
    match = re.search(r"(?is)USER REQUEST:\s*(.+?)(?:\n\nREQUIRED OUTCOME:|$)", text)
    return (match.group(1).strip() if match else text)[:MAX_GOAL_CHARS]


def requested_narration_language(text: str):
    """Return an explicit narration/subtitle language override, or None.

    Avoid switching because a topic merely mentions English or Urdu. Match language words
    only when tied to narration, voice-over, subtitles/captions, or an explicit in-language
    instruction.
    """
    value = str(text or "")
    language_token = r"(english|en|urdu(?:\s*[-+&]\s*english)?|ur(?:\s*[-+&]\s*en)?)"
    patterns = (
        r"(?i)\b(?:narration|voice(?:[\s-]?over)?|subtitles?|captions?)\s+(?:language\s*[:=]\s*|in\s+)" + language_token + r"\b",
        r"(?i)\blanguage\s*[:=]\s*" + language_token + r"\b",
        r"(?i)\b" + language_token + r"\s+(?:narration|voice[\s-]?over|subtitles?|captions?)\b",
        r"(?i)\b(?:speak|narrate|read|use)\s+(?:it\s+)?in\s+" + language_token + r"\b",
    )
    selected = None
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            selected = match.group(1)
            break
    if not selected:
        return None
    return "en" if selected.strip().lower() in {"english", "en"} else "ur-en"


def is_advisory(intent_text: str) -> bool:
    """True when the request asks for an answer rather than an artifact."""
    text = str(intent_text or "").strip()
    return bool(ADVISORY_OPENING.match(text)) and not PRODUCE_MARKER.search(text)


# ---------------------------------------------------------------------------
# Deterministic routing (no model)
# ---------------------------------------------------------------------------

def video_instructions(intent_text: str) -> dict:
    """Read explicit instructions out of the request itself.

    Whether to render, whether narration was asked for, the target length, the
    frame format, and the narration language are properties of what the user
    wrote — not routing preferences. They are parsed here so both routers agree,
    and so the executor can fall back to them when a model omits a field: a model
    forgetting ``render`` must not turn "create and render this to MP4" into a
    silent package build.
    """
    lower = str(intent_text or "").lower()
    output: dict[str, Any] = {
        "render": bool(re.search(r"\b(render|mp4|export video|final video)\b", lower)),
        "with_voice": bool(re.search(r"\b(with voice|with local narration|piper narration)\b", lower)),
        "format": "shorts" if re.search(r"\b(shorts|short-form|vertical)\b", lower) else "long",
        "language": requested_narration_language(intent_text) or "",
    }
    duration = re.search(r"(?i)target[_ ]minutes\s*[:=]\s*(\d+(?:\.\d+)?)", str(intent_text or ""))
    if duration:
        try:
            minutes = float(duration.group(1))
        except ValueError:
            minutes = 0.0
        if 0.5 <= minutes <= 60:
            output["target_minutes"] = minutes
    return output


def heuristic_route(task: str, cfg: Mapping[str, Any] | None = None) -> Route:
    """Select pipelines with explicit patterns — the pre-router behaviour.

    Deliberately unchanged in outcome: every pipeline this returns is one the old
    inline classifier would have run for the same task. It is kept as the
    no-model path *and* as the recorded comparison for model decisions.
    """
    text = str(task or "")
    intent = extract_intent(text)
    intent_lower = intent.lower()
    requests: list[RouteRequest] = []

    video_intent = re.search(
        r"\b(video|shorts|short-form|storyboard|motion graphics|video production|youtube script|video script|youtube content package|faceless channel video)\b",
        intent_lower,
    )
    video_requested = bool(video_intent and re.search(BUILD_VERBS, intent_lower))
    product_requested = bool(re.search(
        r"\b(?:build|create|make|develop|implement)\s+(?:(?:me|a|an|the)\s+)?(?:(?:simple|small|local|offline|responsive|basic|functional|custom|tiny|working|digital)\s+){0,3}(?:product|app|website|web app|software tool|tool|utility|prototype|calculator|dashboard)\b",
        intent_lower,
    ) or re.search(r"\bproduct idea for (?:a )?tool\b", intent_lower))
    web_requested = bool(re.search(
        r"\b(?:build|create|make|develop|implement|launch|design|code)\s+"
        r"(?:(?:me|a|an|the|my)\s+)?"
        r"(?:(?:simple|small|local|offline|responsive|basic|functional|custom|tiny|working|modern|"
        r"personal|professional|static|single[- ]page)\s+){0,3}"
        r"(?:website|web\s?app|webapp|landing\s+page|static\s+site|web\s+site|site|portfolio)\b",
        intent_lower,
    ))
    cli_requested = bool(re.search(
        r"(?:\b(?:build|create|make|write|develop|implement|code)\b[^\n]{0,80}?"
        r"\b(?:cli|command[- ]line\s+(?:tool|utility|app|program)|console\s+(?:tool|app)"
        r"|terminal\s+(?:tool|utility)|shell\s+(?:tool|utility|script)))\b",
        intent_lower,
    ))
    document_requested = bool(re.search(
        r"\b(?:write|draft|compose|produce|create|prepare)\s+"
        r"(?:(?:me|us)\s+)?(?:(?:a|an|the|my)\s+)?"
        r"(?:(?:short|one[- ]page|single[- ]page|brief|simple)\s+)?"
        r"(?:(?:project|release|product|technical|policy|audit)\s+)?"
        r"(?:changelog|release\s+notes|readme|brief|report|memo|document|white\s?paper"
        r"|spec(?:ification)?|guide|checklist|outline|proposal|policy\s+document)\b",
        intent_lower,
    ))
    if web_requested or cli_requested or document_requested:
        # A concrete artifact is the more specific deliverable; the product
        # packager is the fallback for everything else.
        product_requested = False

    if video_requested:
        instructions = video_instructions(intent)
        topic_match = re.search(r"(?i)\b(?:about|on|topic\s*[:=])\s+(.+?)(?:[.;\n]|,\s*(?:include|with|and also)\b|$)", intent)
        topic = (topic_match.group(1).strip() if topic_match else intent[:220]).strip(" \t\r\n.,;:")
        args: dict[str, Any] = {
            "topic": (topic[:500] or "Technology explainer"),
            "format": instructions["format"],
            "language": instructions["language"],
            "render": instructions["render"],
        }
        if "target_minutes" in instructions:
            args["target_minutes"] = instructions["target_minutes"]
        requests.append(RouteRequest(
            pipeline="video_production", args=args,
            why="video nouns plus a production verb"
            + (" and an explicit render request" if instructions["render"] else ""),
        ))

    if web_requested:
        requests.append(RouteRequest(
            pipeline="web_build", args={}, why="a page or app is named with a build verb",
        ))

    if cli_requested:
        name_match = re.search(r"(?i)\b(?:called|named|titled)\s+[`'\"]?([a-z][a-z0-9_-]{1,40})", intent)
        requests.append(RouteRequest(
            pipeline="cli_tool",
            args={"name": name_match.group(1)} if name_match else {},
            why="a command-line tool is named with a build verb",
        ))

    if document_requested:
        title_match = re.search(
            r"(?i)\b(?:called|named|titled)\s+[`'\"]?([^.;\n]{1,80})", intent)
        requests.append(RouteRequest(
            pipeline="document_deliverable",
            args={"title": title_match.group(1).strip()} if title_match else {},
            why="a written document is named with a writing verb",
        ))

    if product_requested:
        title_match = re.search(r"(?i)\b(?:product|prototype|app|tool|website)\s*(?:called|named|titled|:)\s*([^.;\n]{1,100})", intent)
        idea_match = re.search(r"(?is)user problem and product idea:\s*(.+?)(?:\.\s*research the user need|$)", intent)
        args = {
            "title": (title_match.group(1).strip() if title_match else "")[:100],
            "idea": (idea_match.group(1).strip() if idea_match else intent[:1000])[:1000],
        }
        requests.append(RouteRequest(
            pipeline="product_prototype", args=args, why="a sellable product artifact is named with a build verb",
        ))

    return Route(
        mode="heuristic",
        requests=requests,
        notes="" if requests else "no pipeline matched this goal",
        heuristic=[request.pipeline for request in requests],
    )


# ---------------------------------------------------------------------------
# Model routing
# ---------------------------------------------------------------------------

ROUTER_SYSTEM = (
    "You are the routing head of a local automation system. You do not do the work. "
    "You choose at most one or two existing pipelines that will, or you choose none."
)


def build_route_prompt(goal: str, *, allow_model_language: bool = True) -> str:
    """Compose the routing prompt. Deterministic so it can be tested exactly."""
    rules = [
        'Return JSON only: {"pipelines":[{"id":"web_build","args":{},"why":"one clause"}],"notes":"optional"}',
        "Use only ids that appear in PIPELINE CATALOG. An empty list is valid and often correct.",
        "Choose a pipeline only when the user asked for that artifact to be produced now.",
        "Never choose a pipeline for a question, comparison, review, or plan request; return [] instead.",
        "Pass only the argument keys declared for that pipeline. Copy short values from the task; invent nothing.",
        "At most one of " + ", ".join(TOOL_LOOP_PIPELINES) + " per task.",
        f"At most {MAX_REQUESTS} pipelines. Do not repeat an id.",
        "If the task needs something no pipeline can do, return an empty list and say so in notes.",
    ]
    if not allow_model_language:
        rules.append('A pipeline cannot invent facts: leave fields that need research empty.')
    sections = [
        ROUTER_SYSTEM,
        "ROUTING RULES\n- " + "\n- ".join(rules),
        "PIPELINE CATALOG (JSON)\n" + pipeline_catalog(),
        "TOOLS THE TOOL-LOOP PIPELINES MAY USE (JSON)\n" + tool_catalog(),
        "TASK\n" + extract_intent(goal).strip(),
    ]
    return "\n\n".join(sections)[:MAX_PROMPT_CHARS]


def _extract_json_object(text: str) -> dict | None:
    """The first JSON object that decodes, tolerating prose around it."""
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


def _coerce_argument(value: Any, schema: Mapping[str, Any]) -> Any:
    """Validate one argument against the small schema subset the catalog uses."""
    expected = schema.get("type", "string")
    if expected == "string":
        if not isinstance(value, str):
            raise ValueError("must be a string")
        value = value.strip()
        limit = int(schema.get("maxLength", 500))
        if len(value) > limit:
            raise ValueError(f"must be at most {limit} characters")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and value and not re.search(pattern, value):
            raise ValueError("has an invalid format")
        return value
    if expected == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("must be a number")
        low, high = schema.get("minimum"), schema.get("maximum")
        if isinstance(low, (int, float)) and value < low:
            raise ValueError(f"must be at least {low}")
        if isinstance(high, (int, float)) and value > high:
            raise ValueError(f"must be at most {high}")
        return value
    if expected == "boolean":
        if not isinstance(value, bool):
            raise ValueError("must be true or false")
        return value
    return value


def parse_route_response(text: str) -> Route:
    """Validate a router response into a Route.

    Unknown ids, malformed arguments, and duplicates are dropped with a recorded
    reason rather than raising: a bad routing answer must not stop the pipeline,
    it must degrade to the deterministic path with the rejection visible.
    """
    payload = _extract_json_object(text)
    if payload is None:
        return Route(mode="model_rejected_plan", rejected=["router response contained no JSON object"],
                     notes="router response was not JSON")

    raw = payload.get("pipelines")
    if raw is None and isinstance(payload.get("pipeline"), str):
        raw = [{"id": payload.get("pipeline"), "args": payload.get("args") or {}}]
    if not isinstance(raw, list):
        return Route(mode="model_rejected_plan", rejected=["'pipelines' must be an array"],
                     notes="router response shape was invalid")

    requests: list[RouteRequest] = []
    rejected: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if len(requests) >= MAX_REQUESTS:
            rejected.append(f"entry {index}: exceeds the {MAX_REQUESTS}-pipeline limit")
            break
        if not isinstance(item, dict):
            rejected.append(f"entry {index}: must be an object")
            continue
        pipeline_id = str(item.get("id", "")).strip()
        spec = PIPELINES_BY_ID.get(pipeline_id)
        if spec is None:
            rejected.append(f"entry {index}: unknown pipeline '{pipeline_id[:40]}'")
            continue
        if pipeline_id in seen:
            rejected.append(f"entry {index}: duplicate pipeline '{pipeline_id}'")
            continue
        if pipeline_id in TOOL_LOOP_PIPELINES and any(
            request.pipeline in TOOL_LOOP_PIPELINES for request in requests
        ):
            rejected.append(f"entry {index}: a tool-loop pipeline is already selected")
            continue
        raw_args = item.get("args") if isinstance(item.get("args"), dict) else {}
        args: dict[str, Any] = {}
        for key, value in raw_args.items():
            schema = spec.arguments.get(key)
            if schema is None:
                rejected.append(f"entry {index} ({pipeline_id}): unknown argument '{key[:40]}'")
                continue
            try:
                args[key] = _coerce_argument(value, schema)
            except ValueError as exc:
                rejected.append(f"entry {index} ({pipeline_id}): argument '{key}' {exc}")
        seen.add(pipeline_id)
        requests.append(RouteRequest(pipeline=pipeline_id, args=args,
                                     why=str(item.get("why", ""))[:200]))

    return Route(
        mode="model",
        requests=requests,
        rejected=rejected,
        notes=str(payload.get("notes", ""))[:400],
    )


# ---------------------------------------------------------------------------
# Policy applied to every route, whoever proposed it
# ---------------------------------------------------------------------------

def apply_policy(route: Route, intent_text: str) -> Route:
    """Drop requests that a deterministic rule disqualifies. Mutates `route`.

    These are guard rails, not preferences: they encode failures that already
    happened (a "YouTube automation studio" being routed to the video renderer),
    so they run against model choices too.
    """
    kept: list[RouteRequest] = []
    for request in route.requests:
        spec = PIPELINES_BY_ID[request.pipeline]
        veto_reason = next((reason for pattern, reason in spec.vetoes
                            if re.search(pattern, intent_text)), "")
        if veto_reason:
            route.vetoed.append(f"{request.pipeline}: {veto_reason}")
            continue
        kept.append(request)
    route.requests = kept

    if route.requests and is_advisory(intent_text):
        route.advisory = True
        for request in route.requests:
            route.vetoed.append(
                f"{request.pipeline}: the request asks for analysis or advice, "
                "not for an artifact this pipeline can produce")
        route.requests = []

    if route.requests and not re.search(BUILD_VERBS, intent_text.lower()):
        for request in route.requests:
            route.vetoed.append(f"{request.pipeline}: the request names no build verb")
        route.requests = []
    return route


def route_task(
    task: str,
    cfg: Mapping[str, Any] | None = None,
    *,
    model_call: ModelCall | None = None,
    max_tokens: int = DEFAULT_ROUTE_TOKENS,
) -> Route:
    """Decide which pipelines should run. Never raises; never executes anything."""
    text = str(task or "")
    heuristic = heuristic_route(text, cfg)
    apply_policy(heuristic, extract_intent(text))
    comparison = list(heuristic.pipelines)

    if model_call is None:
        heuristic.heuristic = comparison
        return heuristic

    prompt = build_route_prompt(text)
    try:
        response = model_call(prompt, max_tokens)
    except Exception as exc:  # noqa: BLE001 - a router failure must never stop the pipeline
        # urllib raises OSError subclasses, but a malformed HTTP response surfaces
        # as http.client.HTTPException, which is neither OSError nor ValueError.
        # Whatever the transport does, routing degrades to the deterministic path.
        route = heuristic_route(text, cfg)
        route.mode = "heuristic_after_model_error"
        route.notes = (route.notes + " | router model call failed: " + type(exc).__name__).strip(" |")
        apply_policy(route, extract_intent(text))
        route.heuristic = comparison
        return route

    route = parse_route_response(response)
    apply_policy(route, extract_intent(text))
    route.heuristic = comparison
    if route.mode == "model_rejected_plan":
        # A response that could not be parsed is not a routing decision. Fall
        # back, keep the parser's complaint, and say which path ran.
        fallback = heuristic_route(text, cfg)
        fallback.rejected = list(route.rejected)
        fallback.notes = (fallback.notes + " | router response rejected; deterministic routing used").strip(" |")
        apply_policy(fallback, extract_intent(text))
        fallback.mode = "heuristic_after_rejected_plan"
        fallback.heuristic = comparison
        return fallback
    return route
