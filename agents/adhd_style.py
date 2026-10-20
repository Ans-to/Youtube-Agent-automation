"""Compact runtime integration for the upstream i-have-adhd skill.

The full upstream skill is retained under skills/i-have-adhd/SKILL.md. These
instructions are intentionally compact for CPU-local models with small context.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = ROOT / "skills" / "i-have-adhd" / "SKILL.md"

_RUNTIME_INSTRUCTIONS = """ADHD-FRIENDLY OUTPUT STYLE (formatting only; safety and task requirements take priority)
- Lead with the answer or the next concrete action; no introductory filler.
- Number multi-step procedures. Keep each step bounded and actionable.
- Restate current step/progress when continuing multi-turn work; show completed outcomes clearly.
- Give concrete time estimates when useful; avoid vague estimates.
- Keep tangents out of the main answer; group lists into at most five visible items when completeness permits.
- State errors plainly with location/cause/fix. Never claim tests, research, or external actions succeeded unless verified.
- End with one specific next action when work remains. Avoid recap/closing pleasantries.
- Preserve the requested artifact's format: do not force these response rules onto code, data, scripts, or creative deliverables where they would damage correctness.
- Explain fully when asked; ask one short question for real ambiguity; confirm before destructive actions; after three failed fixes, reassess the assumption.
"""

def runtime_instructions():
    """Return compact rules for model prompts without loading the full skill each run."""
    return _RUNTIME_INSTRUCTIONS.strip()


def canonical_skill_exists():
    """Small health check used by tests and diagnostics."""
    return SKILL_PATH.is_file()
