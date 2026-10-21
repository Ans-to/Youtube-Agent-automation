"""Offline video auditor: content safety, brand safety, legal, and technical QA.

The auditor is built around one rule that matters more than any detector:
**a check that did not run is not a pass.** Every rule declares the evidence it
needs, and the report separates *flagged*, *passed*, and *unverified* so a
limited installation cannot produce a falsely clean result.

Public surface::

    from audit import audit_video, render_markdown
    report = audit_video("video.mp4")
    print(render_markdown(report))
"""
from __future__ import annotations

from .auditor import audit_signals, audit_video, render_json, render_markdown
from .rules import CATEGORIES, RULES, Rule, rule_by_id
from .signals import MediaSignals, TextBlock, TranscriptCue

__all__ = [
    "CATEGORIES",
    "RULES",
    "MediaSignals",
    "Rule",
    "TextBlock",
    "TranscriptCue",
    "audit_signals",
    "audit_video",
    "render_json",
    "render_markdown",
    "rule_by_id",
]
