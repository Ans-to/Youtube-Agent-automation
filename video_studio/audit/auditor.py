"""Audit orchestration and report rendering.

The auditor evaluates every rule in the catalog and records one of five states:

===============  ==========================================================
``flagged``      A detector ran and produced at least one finding.
``passed``       A detector ran and produced none.
``unverified``   The evidence this rule needs was not collected.
``manual``       No offline method can establish this (licensing, provenance).
``not_applicable`` The rule needs operator input that was not supplied.
===============  ==========================================================

A clean report is only issued when **every** rule passed. That is the whole
point: a machine without ASR or OCR must not be able to print a clean bill of
health.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import detectors, media
from .rules import NOT_DETECTABLE, RULES, Rule, rule_by_id
from .signals import MediaSignals, format_timestamp

PASSED = "PASSED"
FLAGGED = "FLAGGED"
INCOMPLETE = "INCOMPLETE"

STATUS_FLAGGED = "flagged"
STATUS_PASSED = "passed"
STATUS_UNVERIFIED = "unverified"
STATUS_MANUAL = "manual"
STATUS_NOT_APPLICABLE = "not_applicable"
STATUS_ATTESTED = "attested"


def audit_video(path: str | Path, *, subtitle_path: str | Path | None = None,
                whisper_model: str | None = "base", ocr: bool = True,
                competitor_terms: list[str] | None = None,
                required_disclosures: list[str] | None = None,
                hate_lexicon: list[str] | None = None,
                max_profanity_per_minute: float = 2.0,
                sample_fps: float = 10.0,
                attested: list[str] | tuple[str, ...] = (),
                attested_by: str = "") -> dict:
    """Audit a media file end to end.

    Optional models are attempted only when the caller asks for them, and every
    unavailable capability is reported rather than assumed.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    signals = media.collect(
        path,
        sample_fps=sample_fps,
        subtitle_path=subtitle_path,
        whisper_model=whisper_model,
        ocr=ocr,
        competitor_terms=competitor_terms,
    )
    return audit_signals(
        signals,
        video_name=path.name,
        required_disclosures=required_disclosures,
        hate_lexicon=hate_lexicon,
        max_profanity_per_minute=max_profanity_per_minute,
        attested=attested,
        attested_by=attested_by,
    )


def audit_signals(signals: MediaSignals, *, video_name: str = "video",
                  required_disclosures: list[str] | None = None,
                  hate_lexicon: list[str] | None = None,
                  max_profanity_per_minute: float = 2.0,
                  capabilities: dict | None = None,
                  attested: list[str] | tuple[str, ...] = (),
                  attested_by: str = "") -> dict:
    """Evaluate every rule against the collected signals.

    ``attested`` lists rule IDs a human has already checked. Attestation is how a
    rule that no offline detector can decide still reaches a defensible verdict —
    the report records who vouched for it and when, rather than silently passing.
    """
    attested_ids = {rule_id.strip().upper() for rule_id in attested if rule_id.strip()}
    unknown = sorted(attested_ids - {rule.id for rule in RULES})
    if unknown:
        raise ValueError("unknown rule id(s) in attested list: " + ", ".join(unknown))
    if attested_ids and not attested_by.strip():
        raise ValueError("attested_by is required when attesting rules")
    duration = float(signals.duration or 0.0)
    findings: list[detectors.Finding] = []
    results: list[dict] = []

    def maybe_attested(rule: Rule, fallback: str) -> None:
        """Attestation is only accepted where the machine genuinely cannot decide.

        A detector that ran and flagged can never be overridden this way.
        """
        if rule.id in attested_ids:
            results.append(_result(rule, STATUS_ATTESTED, "Attested by " + attested_by.strip() + "."))
        else:
            results.append(_result(rule, STATUS_UNVERIFIED, fallback))

    def record(rule: Rule, detector: object = None, *, requires: tuple[str, ...] | None = None) -> None:
        if rule.feasibility == NOT_DETECTABLE:
            if rule.id in attested_ids:
                results.append(_result(rule, STATUS_ATTESTED, "Attested by " + attested_by.strip() + "."))
            else:
                results.append(_result(rule, STATUS_MANUAL, rule.limitation or "No offline method."))
            return
        missing = signals.missing(rule.requires if requires is None else requires)
        if missing:
            maybe_attested(rule, "Missing evidence: " + ", ".join(missing)
                           + ". Install or supply it to verify this rule.")
            return
        if detector is None:
            maybe_attested(rule, "No detector is available for this rule.")
            return
        produced = [finding for finding in detector() if finding.rule_id == rule.id]
        findings.extend(produced)
        if produced:
            results.append(_result(rule, STATUS_FLAGGED, f"{len(produced)} finding(s)."))
        else:
            results.append(_result(rule, STATUS_PASSED, "Evaluated; no finding."))

    record(rule_by_id("TQ-BLACK"), lambda: detectors.detect_black(signals.luminance))
    record(rule_by_id("TQ-DEAD-AIR"), lambda: detectors.detect_dead_air(
        signals.audio_rms, window=signals.audio_window))
    record(rule_by_id("TQ-FREEZE"), lambda: detectors.detect_freeze(signals.motion))
    record(rule_by_id("TQ-STROBE"), lambda: detectors.detect_strobe(
        signals.luminance, signals.red_level))
    record(rule_by_id("TQ-AVSYNC"), lambda: detectors.detect_av_sync(
        signals.audio_rms, signals.motion))

    record(rule_by_id("BS-PROFANITY"), lambda: detectors.detect_profanity(
        signals.transcript_text(), start=0.0, duration=duration,
        max_per_minute=max_profanity_per_minute))

    if signals.competitor_terms:
        competitor_text = signals.transcript_text() + " " + signals.ocr_text()
        record(rule_by_id("BS-COMPETITOR"), lambda: detectors.detect_competitors(
            competitor_text, signals.competitor_terms, start=0.0, duration=duration))
    else:
        results.append(_result(
            rule_by_id("BS-COMPETITOR"), STATUS_NOT_APPLICABLE,
            "No competitor list supplied; pass --competitor to enable this check.",
        ))

    record(rule_by_id("BS-CONTROVERSY"), lambda: detectors.detect_controversy(
        signals.transcript_text() + " " + signals.ocr_text(), start=0.0, duration=duration))

    content_text_present = signals.has("transcript") or signals.has("ocr")
    for rule_id in ("CS-VIOLENCE", "CS-WEAPONS", "CS-SELFHARM", "CS-CONTRABAND"):
        rule = rule_by_id(rule_id)
        if not content_text_present:
            maybe_attested(rule, "Missing evidence: transcript, ocr. Text cues cannot run.")
            continue
        record(rule, lambda: detectors.detect_content_terms(signals.transcript, signals.ocr))

    # Rules with no offline detector: attested, or honestly unverified.
    rule = rule_by_id("CS-HATE-SPEECH")
    if rule.id in attested_ids:
        results.append(_result(rule, STATUS_ATTESTED, "Attested by " + attested_by.strip() + "."))
    elif hate_lexicon and signals.has("transcript"):
        custom = {term.lower(): ("CS-HATE-SPEECH", "hate") for term in hate_lexicon if term.strip()}
        hits = detectors._scan_cues(signals.transcript_text(), custom)  # noqa: SLF001 - shared scanner
        if hits:
            findings.append(detectors.Finding(
                rule_id="CS-HATE-SPEECH", start=0.0, end=duration,
                description=(
                    "Operator lexicon matched: " + ", ".join(sorted({hit[0] for hit in hits})[:8])
                    + ". Review the surrounding transcript before acting."
                ),
                confidence=70.0,
                evidence={"terms": sorted({hit[0] for hit in hits})[:8]},
            ))
            results.append(_result(rule, STATUS_FLAGGED, f"{len(hits)} lexicon hit(s)."))
        else:
            results.append(_result(rule, STATUS_PASSED, "Operator lexicon matched nothing."))
    else:
        results.append(_result(
            rule, STATUS_UNVERIFIED,
            "Requires a local language model or an operator-supplied --hate-lexicon.",
        ))

    for rule_id in ("CS-ADULT", "BS-SENTIMENT"):
        rule = rule_by_id(rule_id)
        maybe_attested(rule, "Requires a local visual or language classifier, which is not installed.")

    if required_disclosures:
        record(rule_by_id("LE-DISCLOSURE"), lambda: detectors.detect_disclosures(
            signals.ocr, required_disclosures, duration=duration))
    else:
        results.append(_result(
            rule_by_id("LE-DISCLOSURE"), STATUS_NOT_APPLICABLE,
            "No disclosure requirement supplied; pass --require-disclosure to enable this check.",
        ))

    record(rule_by_id("LE-CHILDREN"), lambda: detectors.detect_children_context(
        signals.transcript_text() + " " + signals.ocr_text(), start=0.0, duration=duration))

    for rule_id in ("LE-MUSIC", "LE-CLIPS"):
        rule = rule_by_id(rule_id)
        if rule_id == "LE-MUSIC" and signals.music_detected is True and rule.id not in attested_ids:
            findings.append(detectors.Finding(
                rule_id=rule_id, start=0.0, end=duration,
                description=(
                    "Music is present in the mix. The auditor cannot determine ownership or "
                    "licensing offline; confirm every track against its licence document."
                ),
                confidence=95.0,
                evidence={"music_detected": True},
            ))
            results.append(_result(rule, STATUS_FLAGGED, "Music present; rights cannot be verified offline."))
        elif rule.id in attested_ids:
            results.append(_result(rule, STATUS_ATTESTED, "Attested by " + attested_by.strip() + "."))
        else:
            results.append(_result(rule, STATUS_MANUAL, rule.limitation or "No offline method."))

    findings.sort(key=lambda item: (item.start, item.rule_id))
    status = _overall_status(results, findings)
    unverified = [item["id"] for item in results if item["status"] in {STATUS_UNVERIFIED, STATUS_MANUAL}]
    attested_rules = [item for item in results if item["status"] == STATUS_ATTESTED]

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "video": video_name,
        "duration_seconds": round(duration, 3),
        "status": status,
        "summary": {
            "findings": len(findings),
            "rules_total": len(RULES),
            "passed": sum(1 for item in results if item["status"] == STATUS_PASSED),
            "flagged": sum(1 for item in results if item["status"] == STATUS_FLAGGED),
            "unverified": sum(1 for item in results if item["status"] == STATUS_UNVERIFIED),
            "manual": sum(1 for item in results if item["status"] == STATUS_MANUAL),
            "not_applicable": sum(1 for item in results if item["status"] == STATUS_NOT_APPLICABLE),
            "attested": len(attested_rules),
        },
        "findings": [finding.as_dict() for finding in findings],
        "rules": results,
        "unverified_rule_ids": unverified,
        "capabilities": capabilities or {},
        "attestation": {
            "attested_by": attested_by.strip(),
            "rule_ids": sorted(item["id"] for item in attested_rules),
        },
        "signal_sources": dict(signals.sources),
        "notes": list(signals.notes),
        "statement": _statement(status, findings, unverified),
    }


def _result(rule: Rule, status: str, reason: str) -> dict:
    return {
        "id": rule.id,
        "category": rule.category,
        "name": rule.name,
        "severity": rule.severity,
        "feasibility": rule.feasibility,
        "status": status,
        "reason": reason,
    }


def _overall_status(results: list[dict], findings: list[detectors.Finding]) -> str:
    if findings:
        return FLAGGED
    if any(item["status"] in {STATUS_UNVERIFIED, STATUS_MANUAL} for item in results):
        return INCOMPLETE
    return PASSED


def _statement(status: str, findings: list[detectors.Finding], unverified: list[str]) -> str:
    if status == PASSED:
        return "AUDIT STATUS: PASSED - No violations detected."
    if status == FLAGGED:
        return f"AUDIT STATUS: FLAGGED - {len(findings)} violation(s) detected."
    return (
        f"AUDIT STATUS: INCOMPLETE - No violations detected, but {len(unverified)} rule(s) could not "
        "be verified: " + ", ".join(unverified) + "."
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_markdown(report: dict) -> str:
    """Render the required structured summary."""
    lines = [
        "# Video audit",
        "",
        f"**File:** `{report['video']}`  ",
        f"**Duration:** {format_timestamp(report['duration_seconds'])}  ",
        f"**Generated:** {report['generated_at']}",
        "",
        "## Result",
        "",
        report["statement"],
        "",
    ]
    summary = report["summary"]
    lines += [
        f"- Rules evaluated: {summary['passed']} passed, {summary['flagged']} flagged",
        f"- Not verifiable on this machine: {summary['unverified']} unverified, {summary['manual']} manual",
        f"- Not applicable: {summary['not_applicable']}",
        "",
    ]

    if report["findings"]:
        lines += ["## Violations", ""]
        for index, finding in enumerate(report["findings"], start=1):
            lines += [
                f"### {index}. {finding['category']} — {finding['rule']}",
                "",
                f"- **Timestamp:** [{format_timestamp(finding['timestamp']['start'])} - "
                f"{format_timestamp(finding['timestamp']['end'])}]",
                f"- **Violation Category:** {finding['category']}",
                f"- **Rule Broken:** {finding['rule']} (`{finding['rule_id']}`)",
                f"- **Description:** {finding['description']}",
                f"- **Confidence Score:** {finding['confidence']:.0f}%",
                "",
            ]

    unverified = [item for item in report["rules"] if item["status"] in {STATUS_UNVERIFIED, STATUS_MANUAL}]
    if unverified:
        lines += ["## Not verified", "", "These rules were **not** checked. A clean result above does not cover them.", ""]
        for item in unverified:
            lines.append(f"- `{item['id']}` **{item['name']}** — {item['reason']}")
        lines.append("")

    attested_rules = [item for item in report["rules"] if item["status"] == STATUS_ATTESTED]
    if attested_rules:
        attestation = report.get("attestation", {})
        lines += [
            "## Human attestation",
            "",
            f"Attested by **{attestation.get('attested_by') or 'unnamed operator'}**. "
            "These rules were not machine-verified.",
            "",
        ]
        for item in attested_rules:
            lines.append(f"- `{item['id']}` **{item['name']}**")
        lines.append("")

    not_applicable = [item for item in report["rules"] if item["status"] == STATUS_NOT_APPLICABLE]
    if not_applicable:
        lines += ["## Not applicable (no input supplied)", ""]
        for item in not_applicable:
            lines.append(f"- `{item['id']}` **{item['name']}** — {item['reason']}")
        lines.append("")

    if report["signal_sources"]:
        lines += ["## Evidence used", ""]
        for name, source in sorted(report["signal_sources"].items()):
            lines.append(f"- `{name}` — {source}")
        lines.append("")

    capabilities = report.get("capabilities") or {}
    if capabilities:
        unavailable = [name for name, ready in capabilities.items() if not ready]
        if unavailable:
            lines += [
                "## Capability gaps",
                "",
                "Unavailable on this machine: " + ", ".join(sorted(unavailable)) + ".",
                "Install them or supply equivalent inputs to verify the rules listed above.",
                "",
            ]
    return "\n".join(lines).rstrip() + "\n"


def render_json(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2)
