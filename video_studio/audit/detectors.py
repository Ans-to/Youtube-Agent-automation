"""Pure detectors: signals in, findings out.

Nothing here touches the filesystem, the network, or a model. Each detector is a
deterministic function over :class:`~audit.signals.MediaSignals`, so the
thresholds can be unit-tested with synthetic numbers and reviewed by a human.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import vision
from .rules import rule_by_id
from .signals import best_lag, format_timestamp, normalize, resample

MAX_FINDINGS_PER_RULE = 20


@dataclass
class Finding:
    """One flagged span, in the shape the operator asked for."""

    rule_id: str
    start: float
    end: float
    description: str
    confidence: float
    evidence: dict = field(default_factory=dict)

    @property
    def category(self) -> str:
        return rule_by_id(self.rule_id).category

    @property
    def rule_name(self) -> str:
        return rule_by_id(self.rule_id).name

    def as_dict(self) -> dict:
        return {
            "timestamp": {"start": round(max(0.0, self.start), 3), "end": round(max(self.start, self.end), 3)},
            "timestamp_display": f"[{format_timestamp(self.start)} - {format_timestamp(self.end)}]",
            "category": self.category,
            "rule_id": self.rule_id,
            "rule": self.rule_name,
            "description": self.description,
            "confidence": round(max(0.0, min(100.0, self.confidence)), 1),
            "evidence": self.evidence,
        }


# ---------------------------------------------------------------------------
# Technical detectors
# ---------------------------------------------------------------------------

def detect_black(luminance: list[tuple[float, float]], *, threshold: float = 0.10,
                 min_seconds: float = 0.5, step: float | None = None) -> list[Finding]:
    """Report spans where mean frame luminance stays below ``threshold``."""
    if len(luminance) < 2:
        return []
    step = step or _median_step(luminance)
    runs: list[list[float]] = []
    current: list[float] | None = None
    for time, value in luminance:
        if value <= threshold:
            current = current or [time, time]
            current[1] = time + step
        elif current is not None:
            runs.append(current)
            current = None
    if current is not None:
        runs.append(current)

    findings = []
    for start, end in runs:
        if end - start + 1e-9 < min_seconds:
            continue
        findings.append(Finding(
            rule_id="TQ-BLACK", start=start, end=end,
            description=(
                f"Picture is effectively black for {end - start:.1f} s "
                f"(mean luminance at or below {threshold:.0%})."
            ),
            confidence=99.0,
            evidence={"threshold": threshold, "min_seconds": min_seconds},
        ))
    return findings[:MAX_FINDINGS_PER_RULE]


def detect_dead_air(rms: list[tuple[float, float]], *, window: float = 0.1,
                    floor: float = 0.01, min_seconds: float = 2.0) -> list[Finding]:
    """Report spans of near-silence in the audio track."""
    if len(rms) < 2:
        return []
    window = window or _median_step(rms)
    runs: list[list[float]] = []
    current: list[float] | None = None
    for time, value in rms:
        if value <= floor:
            current = current or [time, time]
            current[1] = time + window
        elif current is not None:
            runs.append(current)
            current = None
    if current is not None:
        runs.append(current)

    findings = []
    for start, end in runs:
        if end - start + 1e-9 < min_seconds:
            continue
        findings.append(Finding(
            rule_id="TQ-DEAD-AIR", start=start, end=end,
            description=(
                f"No usable audio for {end - start:.1f} s "
                f"(RMS at or below {floor}). Check for a dropped audio stream."
            ),
            confidence=97.0,
            evidence={"floor": floor, "min_seconds": min_seconds},
        ))
    return findings[:MAX_FINDINGS_PER_RULE]


def detect_freeze(motion: list[tuple[float, float]], *, threshold: float = 0.002,
                  min_seconds: float = 3.0) -> list[Finding]:
    """Report spans where the picture stops changing."""
    if len(motion) < 2:
        return []
    step = _median_step(motion)
    runs: list[list[float]] = []
    current: list[float] | None = None
    for time, value in motion:
        if value <= threshold:
            current = current or [time, time]
            current[1] = time + step
        elif current is not None:
            runs.append(current)
            current = None
    if current is not None:
        runs.append(current)

    findings = []
    for start, end in runs:
        if end - start + 1e-9 < min_seconds:
            continue
        findings.append(Finding(
            rule_id="TQ-FREEZE", start=start, end=end,
            description=(
                f"Frame content is static for {end - start:.1f} s. Confirm this is an "
                "intentional hold rather than a stalled render or dropped signal."
            ),
            confidence=92.0,
            evidence={"threshold": threshold, "min_seconds": min_seconds},
        ))
    return findings[:MAX_FINDINGS_PER_RULE]


def detect_strobe(luminance: list[tuple[float, float]], red: list[tuple[float, float]] | None = None,
                  *, delta: float = 0.10, window: float = 1.0, max_flashes: int = 3) -> list[Finding]:
    """Flag rapid brightness or saturated-red flashing (photosensitivity risk).

    A flash is a transition of at least ``delta`` of the full range. Three or more
    transitions inside one second means a flash rate above 3 Hz, which is where
    guidance for photosensitive viewers starts to bite.
    """
    if len(luminance) < 3:
        return []
    step = _median_step(luminance)
    ordered = sorted(luminance)
    transitions = [
        time for index, (time, value) in enumerate(ordered)
        if index and abs(value - ordered[index - 1][1]) >= delta
    ]
    findings: list[Finding] = []
    for start, end, count in _dense_windows(transitions, window, max_flashes):
        rate = count / max(window, 1e-6)
        findings.append(Finding(
            rule_id="TQ-STROBE", start=max(0.0, start - step), end=end,
            description=(
                f"{count} luminance transitions of at least {delta:.0%} within "
                f"{window:.1f} s (approximately {rate:.1f} flashes per second)."
            ),
            confidence=min(95.0, 60.0 + count * 8.0),
            evidence={"transitions": count, "flash_rate_hz": round(rate, 2)},
        ))

    if red and len(red) >= 3:
        ordered_red = sorted(red)
        red_transitions = [
            time for index, (time, value) in enumerate(ordered_red)
            if index and abs(value - ordered_red[index - 1][1]) >= 0.20 and value >= 0.45
        ]
        for start, end, count in _dense_windows(red_transitions, window, max_flashes):
            findings.append(Finding(
                rule_id="TQ-STROBE", start=max(0.0, start - step), end=end,
                description=(
                    f"{count} saturated red flashes within {window:.1f} s. Red flashes are "
                    "more provocative for photosensitive viewers than white flashes."
                ),
                confidence=min(95.0, 62.0 + count * 8.0),
                evidence={"red_transitions": count},
            ))
    return findings[:MAX_FINDINGS_PER_RULE]


def detect_av_sync(rms: list[tuple[float, float]], motion: list[tuple[float, float]],
                   *, step: float = 0.1, tolerance: float = 0.15,
                   min_correlation: float = 0.35) -> list[Finding]:
    """Report a persistent offset between the audio and visual envelopes."""
    if len(rms) < 10 or len(motion) < 10:
        return []
    duration = max(rms[-1][0], motion[-1][0]) + step
    audio = normalize(resample(rms, step, duration))
    visual = normalize(resample(motion, step, duration))
    lag, score = best_lag(audio, visual, step)
    if abs(lag) <= tolerance or score < min_correlation:
        return []
    direction = "picture lags sound" if lag > 0 else "picture leads sound"
    return [Finding(
        rule_id="TQ-AVSYNC", start=0.0, end=duration,
        description=(
            f"Best audio/visual alignment is {lag:+.2f} s ({direction}), beyond the "
            f"{tolerance:.2f} s tolerance. Envelope correlation {score:.2f}."
        ),
        confidence=min(80.0, 40.0 + score * 60.0),
        evidence={"lag_seconds": round(lag, 3), "correlation": round(score, 3)},
    )]


# ---------------------------------------------------------------------------
# Text detectors
# ---------------------------------------------------------------------------

_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})


def normalize_text(text: str) -> str:
    """Lowercase, fold leetspeak, and drop separator characters used to evade matching."""
    lowered = text.lower().translate(_LEET)
    lowered = re.sub(r"[*\-_.|/\\]+", "", lowered)
    return re.sub(r"\s+", " ", lowered)


def _word_pattern(term: str) -> re.Pattern[str]:
    """Word-bounded match that also accepts common inflectional suffixes."""
    escaped = re.escape(term)
    return re.compile(rf"(?<![a-z0-9]){escaped}(s|es|ed|ing|er|ers)?(?![a-z0-9])")


def _scan_cues(text: str, terms: dict[str, tuple[str, ...]]) -> list[tuple[str, str, str]]:
    """Return (term, category, matched_phrase) for every hit, first occurrence order."""
    normalized = normalize_text(text)
    hits: list[tuple[str, str, str]] = []
    for term, meta in terms.items():
        if _word_pattern(term).search(normalized):
            hits.append((term, meta[0], meta[1]))
    return hits


def detect_profanity(text: str, *, start: float = 0.0, duration: float = 0.0,
                     max_per_minute: float = 2.0) -> list[Finding]:
    """Count profanity and flag when the rate exceeds a brand-safety threshold."""
    hits = _scan_cues(text, PROFANITY)
    if not hits:
        return []
    minutes = max(duration / 60.0, 1 / 60.0) if duration else 1.0
    rate = len(hits) / minutes
    if rate <= max_per_minute:
        return []
    words = sorted({hit[0] for hit in hits})
    return [Finding(
        rule_id="BS-PROFANITY", start=start, end=max(start, start + duration),
        description=(
            f"{len(hits)} profanity hit(s) across {minutes:.1f} min "
            f"({rate:.1f} per minute, limit {max_per_minute:.1f}). Matched: {', '.join(words[:8])}."
        ),
        confidence=88.0,
        evidence={"hits": len(hits), "per_minute": round(rate, 2), "terms": words[:8]},
    )]


def detect_competitors(text: str, terms: list[str], *, start: float = 0.0, duration: float = 0.0) -> list[Finding]:
    """Flag operator-supplied competitor names in speech or on-screen text."""
    findings: list[Finding] = []
    normalized = normalize_text(text)
    for term in terms:
        cleaned = term.strip()
        if not cleaned:
            continue
        if _word_pattern(cleaned.lower()).search(normalized):
            findings.append(Finding(
                rule_id="BS-COMPETITOR", start=start, end=max(start, start + duration),
                description=(
                    f"Configured competitor '{cleaned}' appears in the audio transcript or "
                    "on-screen text. Confirm the placement and any contractual restrictions."
                ),
                confidence=85.0,
                evidence={"competitor": cleaned},
            ))
    return findings[:MAX_FINDINGS_PER_RULE]


def detect_content_terms(transcript_cues, ocr_blocks) -> list[Finding]:
    """Low-confidence term cues for violence, weapons, self-harm, and drugs.

    These are explicitly *cues*, not verdicts. The chef-with-a-knife case is why:
    a weapon word in a cooking context is not violence. Co-occurring benign
    context terms lower the confidence and say so in the description, and every
    finding states that temporal context must be reviewed.
    """
    findings: list[Finding] = []
    entries = [(cue.start, cue.end, cue.text, "transcript") for cue in transcript_cues]
    entries += [(block.start, block.end, block.text, "on-screen text") for block in ocr_blocks]
    for start, end, text, origin in entries:
        hits = _scan_cues(text, CONTENT_TERMS)
        for term, rule_id, category in hits:
            window_text = _context_window(transcript_cues, ocr_blocks, start, end)
            benign = sorted({hit[0] for hit in _scan_cues(window_text, BENIGN_CONTEXT)})
            confidence = 18.0 if benign else 42.0
            context_note = (
                f" Co-occurring benign context ({', '.join(benign[:4])}) suggests this may be a "
                "safe depiction, such as a cooking or sports scene."
                if benign else " No benign context terms were found in the surrounding window."
            )
            findings.append(Finding(
                rule_id=rule_id, start=start, end=end,
                description=(
                    f"Term cue '{term}' from {origin}. Text alone cannot distinguish depiction "
                    f"from endorsement; temporal context must be reviewed.{context_note}"
                ),
                confidence=confidence,
                evidence={"term": term, "origin": origin, "benign_context": benign,
                          "category_hint": category},
            ))
    return findings[:MAX_FINDINGS_PER_RULE]


def detect_controversy(text: str, *, start: float = 0.0, duration: float = 0.0) -> list[Finding]:
    hits = _scan_cues(text, CONTROVERSY)
    if not hits:
        return []
    themes = sorted({hit[2] for hit in hits})
    return [Finding(
        rule_id="BS-CONTROVERSY", start=start, end=max(start, start + duration),
        description=(
            "Sensitive-theme keywords detected: " + ", ".join(themes[:6])
            + ". Keywords flag topics for review; they do not establish that the treatment is controversial."
        ),
        confidence=45.0,
        evidence={"themes": themes[:6]},
    )]


def detect_disclosures(ocr_blocks, required: list[str], *, duration: float,
                       min_height_ratio: float = 0.015, min_display_seconds: float = 1.5) -> list[Finding]:
    """Verify required legal text is present, readable, and on screen long enough."""
    findings: list[Finding] = []
    for phrase in required:
        pattern = _word_pattern(phrase.lower())
        matches = [block for block in ocr_blocks if pattern.search(normalize_text(block.text))]
        if not matches:
            findings.append(Finding(
                rule_id="LE-DISCLOSURE", start=0.0, end=duration,
                description=(
                    f"Required disclosure '{phrase}' was not found in on-screen text. "
                    "If it appears only in the description or voice-over, statically verify it."
                ),
                confidence=90.0,
                evidence={"required": phrase, "found": False},
            ))
            continue
        total = sum(block.end - block.start for block in matches)
        readable = [block for block in matches if block.height_ratio >= min_height_ratio]
        if not readable:
            smallest = min(block.height_ratio for block in matches)
            findings.append(Finding(
                rule_id="LE-DISCLOSURE", start=matches[0].start, end=matches[-1].end,
                description=(
                    f"Disclosure '{phrase}' is on screen but may be illegible: the text is "
                    f"{smallest:.1%} of frame height (minimum {min_height_ratio:.1%})."
                ),
                confidence=72.0,
                evidence={"required": phrase, "height_ratio": round(smallest, 4)},
            ))
        elif total < min_display_seconds:
            findings.append(Finding(
                rule_id="LE-DISCLOSURE", start=matches[0].start, end=matches[-1].end,
                description=(
                    f"Disclosure '{phrase}' is displayed for {total:.1f} s, below the "
                    f"{min_display_seconds:.1f} s review threshold."
                ),
                confidence=70.0,
                evidence={"required": phrase, "display_seconds": round(total, 2)},
            ))
    return findings[:MAX_FINDINGS_PER_RULE]


def detect_children_context(text: str, *, start: float = 0.0, duration: float = 0.0) -> list[Finding]:
    """Flag child-directed content combined with data-collection calls to action."""
    child = sorted({hit[0] for hit in _scan_cues(text, CHILD_CUES)})
    data = sorted({hit[0] for hit in _scan_cues(text, DATA_CUES)})
    if not child or not data:
        return []
    return [Finding(
        rule_id="LE-CHILDREN", start=start, end=max(start, start + duration),
        description=(
            f"Child-directed cues ({', '.join(child[:4])}) co-occur with data-collection cues "
            f"({', '.join(data[:4])}). Review against children's privacy requirements; this is a "
            "screening heuristic, not a legal determination."
        ),
        confidence=38.0,
        evidence={"child_cues": child[:4], "data_cues": data[:4]},
    )]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _median_step(series: list[tuple[float, float]]) -> float:
    if len(series) < 2:
        return 0.0
    differences = sorted(
        series[index + 1][0] - series[index][0] for index in range(len(series) - 1)
    )
    return max(1e-3, differences[len(differences) // 2])


def _dense_windows(times: list[float], window: float, minimum: int) -> list[tuple[float, float, int]]:
    """Group event times into windows containing at least ``minimum`` events."""
    ordered = sorted(times)
    windows: list[tuple[float, float, int]] = []
    index = 0
    while index < len(ordered):
        end = ordered[index] + window
        count = 0
        cursor = index
        while cursor < len(ordered) and ordered[cursor] <= end:
            count += 1
            cursor += 1
        if count >= minimum:
            windows.append((ordered[index], ordered[cursor - 1], count))
            index = cursor
        else:
            index += 1
    return windows


def _context_window(transcript, ocr, start: float, end: float, radius: float = 8.0) -> str:
    """Text from +/-``radius`` seconds, used to judge safe versus unsafe context."""
    low, high = start - radius, end + radius
    parts = [cue.text for cue in transcript if cue.end >= low and cue.start <= high]
    parts += [block.text for block in ocr if block.end >= low and block.start <= high]
    return " ".join(parts)


# Term dictionaries: term -> (rule id, category hint)
PROFANITY: dict[str, tuple[str, str]] = {
    word: ("BS-PROFANITY", "profanity")
    for word in (
        "fuck", "shit", "bitch", "asshole", "bastard", "damn", "crap", "dick",
        "piss", "whore", "slut", "bullshit", "motherfucker", "cunt",
    )
}

CONTENT_TERMS: dict[str, tuple[str, str]] = {
    **{word: ("CS-VIOLENCE", "violence") for word in (
        "blood", "gore", "gory", "murder", "murdered", "massacre", "corpse", "stabbed",
        "beaten", "brutal", "decapitate", "dismember", "assault", "violence",
    )},
    **{word: ("CS-WEAPONS", "weapons") for word in (
        "gun", "rifle", "pistol", "shotgun", "handgun", "knife", "blade", "sword",
        "weapon", "grenade", "explosive", "ammunition",
    )},
    **{word: ("CS-SELFHARM", "self-harm") for word in (
        "suicide", "suicidal", "self-harm", "self harm", "cutting myself",
        "anorexia", "bulimia", "kill myself",
    )},
    **{word: ("CS-CONTRABAND", "contraband") for word in (
        "cocaine", "heroin", "methamphetamine", "meth", "fentanyl", "illegal drugs",
        "get high", "snorting",
    )},
}

BENIGN_CONTEXT: dict[str, tuple[str, str]] = {
    word: ("BENIGN", "safe context")
    for word in (
        "chef", "kitchen", "recipe", "cook", "cooking", "bake", "baking", "restaurant",
        "food", "meal", "sport", "game", "practice", "training", "studio", "workshop",
        "tutorial", "safety", "prop", "costume", "toy", "museum", "documentary",
    )
}

CONTROVERSY: dict[str, tuple[str, str]] = {
    **{word: ("BS-CONTROVERSY", "politics") for word in (
        "election", "politician", "parliament", "senate", "government", "protest",
        "referendum", "campaign trail",
    )},
    **{word: ("BS-CONTROVERSY", "disaster") for word in (
        "earthquake", "flood", "hurricane", "wildfire", "tsunami", "pandemic",
        "famine", "disaster", "catastrophe",
    )},
    **{word: ("BS-CONTROVERSY", "tragedy") for word in (
        "terrorist", "terrorism", "genocide", "shooting", "casualties", "mass grave",
        "war crime", "fatalities",
    )},
    **{word: ("BS-CONTROVERSY", "sensitive social") for word in (
        "abortion", "immigration", "vaccine", "religion", "euthanasia",
    )},
}

CHILD_CUES: dict[str, tuple[str, str]] = {
    word: ("LE-CHILDREN", "child-directed")
    for word in ("kids", "children", "toddler", "nursery", "cartoon", "playtime", "toys", "for kids")
}

DATA_CUES: dict[str, tuple[str, str]] = {
    word: ("LE-CHILDREN", "data collection")
    for word in ("enter your email", "download the app", "giveaway", "subscribe now",
                 "visit our website", "sign up", "link in the description", "free trial")
}


# ---------------------------------------------------------------------------
# Audio-profile detectors
# ---------------------------------------------------------------------------

def detect_clipping(profile, *, min_ratio: float = 0.001, min_seconds: float = 0.1) -> list[Finding]:
    """Report spans of clipped samples (a distorted master)."""
    spans = profile.spans(lambda frame: frame.clipped_ratio > min_ratio)
    findings = []
    for start, end in spans:
        if end - start + 1e-9 < min_seconds:
            continue
        peak_ratio = max(
            (frame.clipped_ratio for frame in profile.frames if start <= frame.time <= end),
            default=0.0,
        )
        findings.append(Finding(
            rule_id="TQ-CLIPPING", start=start, end=end,
            description=(
                f"Audio is clipped for {end - start:.1f} s; up to {peak_ratio:.1%} of samples in a "
                "window sit at full scale. Clipping cannot be repaired by normalizing."
            ),
            confidence=96.0,
            evidence={"max_clipped_ratio": round(peak_ratio, 4)},
        ))
    return findings[:MAX_FINDINGS_PER_RULE]


def detect_loudness(profile, *, quiet_dbfs: float = -45.0, hot_dbfs: float = -6.0,
                    min_seconds: float = 2.0) -> list[Finding]:
    """Report sustained too-quiet or too-hot audio."""
    findings: list[Finding] = []
    for start, end in profile.spans(lambda frame: frame.rms_db < quiet_dbfs):
        if end - start + 1e-9 < min_seconds:
            continue
        findings.append(Finding(
            rule_id="TQ-LOUDNESS", start=start, end=end,
            description=(
                f"Program audio sits below {quiet_dbfs:.0f} dBFS for {end - start:.1f} s "
                "(integrated " + f"{profile.integrated_db:.1f} dBFS). Viewers will reach for the volume."
            ),
            confidence=85.0,
            evidence={"integrated_dbfs": round(profile.integrated_db, 2)},
        ))
    for start, end in profile.spans(lambda frame: frame.rms_db >= hot_dbfs):
        if end - start + 1e-9 < min_seconds:
            continue
        findings.append(Finding(
            rule_id="TQ-LOUDNESS", start=start, end=end,
            description=(
                f"Program audio reaches {hot_dbfs:.0f} dBFS or above for {end - start:.1f} s; "
                "platform loudness normalization will pull it down and may expose distortion."
            ),
            confidence=80.0,
            evidence={"peak_dbfs": round(profile.peak_db, 2)},
        ))
    return findings[:MAX_FINDINGS_PER_RULE]


def detect_lipsync(mouth: list[tuple[float, float]], rms: list[tuple[float, float]],
                   *, step: float = 0.1, tolerance: float = 0.12,
                   min_correlation: float = 0.30) -> list[Finding]:
    """Compare mouth-region motion with the speech envelope."""
    if len(mouth) < 10 or len(rms) < 10:
        return []
    duration = max(mouth[-1][0], rms[-1][0]) + step
    visual = normalize(resample(mouth, step, duration))
    audio = normalize(resample(rms, step, duration))
    if not any(audio):
        # No speech energy means there is nothing for a mouth to match.
        return []
    lag, score = best_lag(audio, visual, step)
    if score >= min_correlation and abs(lag) <= tolerance:
        return []
    if score < min_correlation:
        description = (
            f"Mouth-region motion and the speech envelope do not correspond "
            f"(correlation {score:.2f}, below {min_correlation:.2f}). Check for detached narration "
            "or a speaker who is not on camera."
        )
        confidence = 45.0
    else:
        direction = "mouth movement lags the speech" if lag > 0 else "mouth movement leads the speech"
        description = (
            f"{direction.capitalize()} by {abs(lag):.2f} s, beyond the {tolerance:.2f} s tolerance "
            f"(correlation {score:.2f})."
        )
        confidence = min(80.0, 45.0 + score * 45.0)
    return [Finding(
        rule_id="TQ-LIPSYNC", start=0.0, end=duration,
        description=description,
        confidence=confidence,
        evidence={"lag_seconds": round(lag, 3), "correlation": round(score, 3)},
    )]


# ---------------------------------------------------------------------------
# Visual observation detectors (temporal)
# ---------------------------------------------------------------------------

def _visual_confidence(base: float, event, *, benign: bool) -> float:
    """Scale confidence by detector confidence, dwell time, and scene context."""
    duration_factor = min(1.0, 0.55 + event.duration / 3.0)
    value = base * event.confidence * duration_factor
    if benign:
        value *= 0.35
    return round(max(5.0, min(96.0, value)), 1)


def _is_benign_tool_use(event, events) -> bool:
    """A knife in a kitchen while chopping is not violence."""
    if event.kind != "object" or event.label not in vision.WEAPON_LABELS:
        return False
    contexts = set(event.scenes) | vision.scene_context(events, event.start, event.end)
    if contexts & vision.BENIGN_SCENES:
        return True
    return any(
        other.kind == "action" and other.label in vision.SAFE_TOOL_ACTIONS
        and other.start < event.end and other.end > event.start
        for other in events
    )


def detect_visual_content(observations) -> list[Finding]:
    """Temporal, context-aware findings from local vision observations."""
    events = vision.build_events(observations)
    findings: list[Finding] = []
    for event in events:
        if event.kind not in {"object", "action"}:
            continue
        label = event.label
        benign = _is_benign_tool_use(event, events)
        context_note = (
            f" Scene context: {', '.join(event.scenes)}." if event.scenes else " No scene context was supplied."
        )
        if label in vision.VIOLENCE_ACTIONS:
            findings.append(Finding(
                rule_id="CS-VIOLENCE", start=event.start, end=event.end,
                description=(
                    f"Action '{label}' detected for {event.duration:.1f} s "
                    f"(detector confidence {event.confidence:.0%}).{context_note}"
                ),
                confidence=_visual_confidence(85.0, event, benign=benign),
                evidence=event.as_dict(),
            ))
        elif label in vision.GORE_LABELS:
            findings.append(Finding(
                rule_id="CS-VIOLENCE", start=event.start, end=event.end,
                description=(
                    f"Gore-related label '{label}' visible for {event.duration:.1f} s.{context_note}"
                ),
                confidence=_visual_confidence(80.0, event, benign=benign),
                evidence=event.as_dict(),
            ))
        elif label in vision.WEAPON_LABELS:
            description = (
                f"Weapon '{label}' visible for {event.duration:.1f} s "
                f"(detector confidence {event.confidence:.0%}).{context_note}"
            )
            if benign:
                description += (
                    " A benign scene or food-preparation action overlaps this span, so this is "
                    "most likely a tool or prop rather than a threat."
                )
            findings.append(Finding(
                rule_id="CS-WEAPONS", start=event.start, end=event.end,
                description=description,
                confidence=_visual_confidence(75.0, event, benign=benign),
                evidence=event.as_dict(),
            ))
        elif label in vision.ADULT_LABELS:
            findings.append(Finding(
                rule_id="CS-ADULT", start=event.start, end=event.end,
                description=(
                    f"Adult-content label '{label}' detected for {event.duration:.1f} s "
                    f"(detector confidence {event.confidence:.0%})."
                ),
                confidence=_visual_confidence(88.0, event, benign=False),
                evidence=event.as_dict(),
            ))
        elif label in vision.CONTRABAND_LABELS:
            findings.append(Finding(
                rule_id="CS-CONTRABAND", start=event.start, end=event.end,
                description=(
                    f"Contraband-related label '{label}' detected for {event.duration:.1f} s.{context_note}"
                ),
                confidence=_visual_confidence(60.0, event, benign=benign),
                evidence=event.as_dict(),
            ))
    return findings[:MAX_FINDINGS_PER_RULE]


def detect_visual_competitors(observations, competitor_terms: list[str]) -> list[Finding]:
    """Match competitor names against logo and on-screen text observations."""
    findings: list[Finding] = []
    display_terms = {term.strip().lower(): term.strip() for term in competitor_terms if term.strip()}
    if not display_terms:
        return findings
    for event in vision.build_events(observations):
        if event.kind not in {"logo", "text"}:
            continue
        label = normalize_text(event.label)
        for key in sorted(display_terms):
            term = display_terms[key]
            if _word_pattern(key).search(label):
                findings.append(Finding(
                    rule_id="BS-COMPETITOR", start=event.start, end=event.end,
                    description=(
                        f"Competitor '{term}' appears as a {event.kind} for {event.duration:.1f} s "
                        f"(detector confidence {event.confidence:.0%})."
                    ),
                    confidence=round(min(95.0, 60.0 + event.confidence * 35.0), 1),
                    evidence=event.as_dict(),
                ))
    return findings[:MAX_FINDINGS_PER_RULE]
