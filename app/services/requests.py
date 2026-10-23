"""Turn a submitted form into a task request.

These rules used to live inside the HTTP handler: forty lines per route mixing
field parsing, validation, filesystem checks and English error messages. That
made them untestable without a socket, invisible to any other entry point, and
easy to get subtly different from each other - the video route and the pipeline
route each had their own copy of the "must be a file inside workspace" check.

Each builder is pure. It takes a ``{field: [values]}`` mapping (the shape
:func:`urllib.parse.parse_qs` returns), and either returns a
:class:`TaskRequest` or raises :class:`TaskInputError` with a message written for
a person.

The workspace check itself lives in ``ui.dashboard.security`` because it is
about untrusted input. It is injected here as ``resolve_file`` so this module
stays free of the presentation layer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from app.errors import TaskInputError
from app.services.tasks import MAX_INPUT_CHARS, MAX_TITLE_CHARS

ResolveFile = Callable[[str], "object | None"]

VIDEO_FORMATS = frozenset({"long", "shorts"})
VIDEO_MODES = frozenset({"draft", "render", "template"})
MIN_TARGET_MINUTES = 0.25
MAX_TARGET_MINUTES = 16


@dataclass(frozen=True)
class TaskRequest:
    """One validated unit of work, ready for the queue."""

    title: str
    kind: str
    text: str
    context_file: str = ""


def _field(form: Mapping[str, list[str]], name: str, default: str = "") -> str:
    values = form.get(name) or [default]
    first = values[0] if isinstance(values, list) else values
    return str(first or default).strip()


def build_video_request(
    form: Mapping[str, list[str]],
    *,
    resolve_file: ResolveFile,
    model_enabled: bool,
) -> TaskRequest:
    """Validate the video form and describe the work for the CEO."""
    topic = _field(form, "topic")
    fmt = _field(form, "format", "long").lower()
    mode = _field(form, "render_mode", "draft").lower()
    source_file = _field(form, "source_file")
    with_voice = _field(form, "with_voice") == "yes"
    if not topic or len(topic) > 500 or fmt not in VIDEO_FORMATS or mode not in VIDEO_MODES:
        raise TaskInputError("Invalid video request. Check topic, format, and output mode.")

    target_minutes = None
    raw_target = _field(form, "target_minutes")
    if raw_target:
        try:
            target_minutes = float(raw_target)
        except ValueError:
            raise TaskInputError("Target minutes must be a number between 0.25 and 16.") from None
        if not MIN_TARGET_MINUTES <= target_minutes <= MAX_TARGET_MINUTES:
            raise TaskInputError("Target minutes must be between 0.25 and 16.")

    if with_voice and mode != "render":
        raise TaskInputError("Local narration can only be selected with the full render mode.")
    if mode == "render" and not model_enabled:
        raise TaskInputError(
            "A local model is disabled. Enable a compatible local model to render a "
            "full-length video, or choose the explicit template-demo mode."
        )
    if mode == "template" and source_file:
        # Voice was already refused above for every non-render mode, so only a
        # source file can still reach this branch.
        raise TaskInputError("Template demo mode cannot be combined with source files or voice.")

    context_file = ""
    if source_file:
        if len(source_file) > 500:
            raise TaskInputError("Source notes must be a .txt, .md, or .json file inside workspace.")
        resolved = resolve_file(source_file)
        if resolved is None:
            raise TaskInputError("Source notes must be an existing file inside workspace.")
        context_file = str(resolved)

    parts = [
        "Create a faceless YouTube video package about " + topic + ".",
        "Format: " + fmt + ".",
        ("target_minutes: " + str(target_minutes)) if target_minutes is not None else "",
        "Requested mode: " + mode + ".",
        "Collect current web research and create the actual script and storyboard deliverables.",
    ]
    if mode == "render":
        parts.append("Render the final video to MP4.")
    if mode == "template":
        parts.append("Explicitly authorized: template demo render, not a full AI-generated video.")
    if with_voice:
        parts.append("Add local Piper narration with voice.")
    return TaskRequest(
        title=("Video: " + topic)[:MAX_TITLE_CHARS],
        kind="youtube_package",
        text=" ".join(part for part in parts if part),
        context_file=context_file,
    )


def build_product_request(form: Mapping[str, list[str]]) -> TaskRequest:
    """Validate the digital-product form."""
    title = _field(form, "product_title")
    idea = _field(form, "product_idea")
    if not title or len(title) > 100 or not idea or len(idea) > 1000:
        raise TaskInputError(
            "Product title must be 1-100 characters and product idea 1-1000 characters."
        )
    text = (
        "Build a digital product prototype called " + title + ". "
        "User problem and product idea: " + idea + ". "
        "Research the user need and similar solutions, produce a usable local HTML/ZIP prototype, "
        "document its limitations, and do not claim market validation without evidence."
    )
    return TaskRequest(title="Digital product: " + title, kind="draft", text=text)


def build_plain_request(form: Mapping[str, list[str]]) -> TaskRequest:
    """The generic "add a task" form."""
    title = _field(form, "title")[:MAX_TITLE_CHARS]
    kind = _field(form, "kind", "plan")
    text = _field(form, "input")
    if not title or not text:
        raise TaskInputError("Task instructions must contain 1-16,000 characters and use a supported workflow.")
    return TaskRequest(title=title, kind=kind, text=text)


@dataclass(frozen=True)
class PipelineRequest:
    """A direct CEO pipeline run: the operator supplies the whole goal."""

    task: str
    context_file: str = ""


def build_pipeline_request(
    form: Mapping[str, list[str]], *, resolve_file: ResolveFile
) -> PipelineRequest:
    """Validate the pipeline form. Manual specialist overrides are refused."""
    if _field(form, "agents"):
        raise TaskInputError(
            "Manual specialist selection is disabled. Submit the goal to the CEO; "
            "AGENT-01 chooses the team."
        )
    task = _field(form, "task")
    if not task or len(task) > MAX_INPUT_CHARS:
        raise TaskInputError("CEO task must contain 1-16,000 characters.")
    context = _field(form, "context_file")
    context_file = ""
    if context:
        if len(context) > 500:
            raise TaskInputError("Context path must point to a .txt, .md, or .json file.")
        resolved = resolve_file(context)
        if resolved is None:
            raise TaskInputError(
                "Context file must be an existing .txt, .md, or .json file inside the local workspace."
            )
        context_file = str(resolved)
    return PipelineRequest(task=task, context_file=context_file)


__all__ = [
    "TaskRequest",
    "PipelineRequest",
    "build_video_request",
    "build_product_request",
    "build_plain_request",
    "build_pipeline_request",
    "VIDEO_FORMATS",
    "VIDEO_MODES",
]
