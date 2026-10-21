"""The audit rule catalog.

Every rule states what evidence it needs. That declaration is what allows the
auditor to be honest: when the evidence is missing, the rule is reported as
**unverified**, never as passed.

Feasibility values:

* ``automatic`` — computable from pixels, audio levels, subtitles, or metadata
  with no model download.
* ``model_required`` — needs a local model (ASR, OCR, object/action classifier,
  or a local language model). Free, but a one-time download and CPU cost.
* ``not_detectable_offline`` — cannot be established on a personal machine
  without a reference database or a licensed service. Reported as a manual
  verification item instead of pretending to check it.
"""
from __future__ import annotations

from dataclasses import dataclass

CATEGORIES = ("Content Safety", "Brand Safety", "Legal", "Technical QA")

AUTOMATIC = "automatic"
MODEL_REQUIRED = "model_required"
NOT_DETECTABLE = "not_detectable_offline"

# Signal keys a detector may request. Missing keys mark a rule unverified.
SIGNALS = (
    "luminance",       # per-sample brightness (0..1) with timestamps
    "motion",          # per-sample frame-to-frame change (0..1)
    "red_level",       # per-sample mean red channel (0..1)
    "audio_rms",       # per-window loudness (0..1)
    "silence",         # silence intervals from FFmpeg silencedetect
    "transcript",      # speech text with timestamps (ASR or supplied subtitles)
    "ocr",             # on-screen text with timestamps and size
    "disclosure_text",  # on-screen text retained for legal checks
    "competitor_terms",  # operator-supplied brand list
    "music",           # music presence (not ownership)
)


@dataclass(frozen=True)
class Rule:
    """One auditable requirement."""

    id: str
    category: str
    name: str
    intent: str
    severity: str
    feasibility: str
    requires: tuple[str, ...]
    detection: str
    limitation: str = ""

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "name": self.name,
            "intent": self.intent,
            "severity": self.severity,
            "feasibility": self.feasibility,
            "requires": list(self.requires),
            "detection": self.detection,
            "limitation": self.limitation,
        }


RULES: tuple[Rule, ...] = (
    # ---------------------------------------------------------------- content
    Rule(
        id="CS-VIOLENCE",
        category="Content Safety",
        name="Violence and gore",
        intent="Flag physical altercations, blood, injury, and graphic harm.",
        severity="high",
        feasibility=MODEL_REQUIRED,
        requires=("transcript", "ocr"),
        detection="Transcript and on-screen text are scanned for violence and gore terms.",
        limitation=(
            "Visual violence detection needs a local action/gore classifier. Text cues miss "
            "silent footage entirely, so a clean text result is not proof the video is safe."
        ),
    ),
    Rule(
        id="CS-WEAPONS",
        category="Content Safety",
        name="Weapons on screen",
        intent="Flag firearms, blades, and other weapons shown as objects.",
        severity="high",
        feasibility=MODEL_REQUIRED,
        requires=("transcript", "ocr"),
        detection="Text cues only until an object-detection model is installed.",
        limitation="Recording a weapon requires an object detector; text cannot see a prop.",
    ),
    Rule(
        id="CS-SELFHARM",
        category="Content Safety",
        name="Self-harm",
        intent="Flag references to self-harm, suicide, or eating disorders.",
        severity="high",
        feasibility=MODEL_REQUIRED,
        requires=("transcript", "ocr"),
        detection="Transcript and on-screen text are scanned for self-harm terms.",
        limitation="Semantic implication and imagery need a model; literal term matching only.",
    ),
    Rule(
        id="CS-HATE-SPEECH",
        category="Content Safety",
        name="Hate speech and harassment in speech",
        intent="Flag slurs, bullying, and discriminatory language in the transcript.",
        severity="high",
        feasibility=MODEL_REQUIRED,
        requires=("transcript",),
        detection=(
            "A maintained term list supplied with --lexicon, or a local language model for "
            "semantic judgement. No slur list is bundled: hard-coded lists age badly, miss "
            "obfuscation, and cause false positives on reclaimed language."
        ),
        limitation="Requires a human-maintained lexicon or a local model; absent that, unverified.",
    ),
    Rule(
        id="CS-ADULT",
        category="Content Safety",
        name="Adult content and nudity",
        intent="Flag explicit nudity, sexual behaviour, and restricted substances.",
        severity="high",
        feasibility=MODEL_REQUIRED,
        requires=("transcript",),
        detection="Text cues; visual detection needs a local NSFW classifier.",
        limitation="A skin-ratio heuristic is not shipped because its error rate is unacceptable for this decision.",
    ),
    Rule(
        id="CS-CONTRABAND",
        category="Content Safety",
        name="Contraband and illegal substances",
        intent="Flag depiction or promotion of drugs and illegal substances.",
        severity="high",
        feasibility=MODEL_REQUIRED,
        requires=("transcript", "ocr"),
        detection="Text cues only until an object detector is installed.",
        limitation="Visual substance identification requires a trained detector.",
    ),
    # ------------------------------------------------------------ brand safety
    Rule(
        id="BS-COMPETITOR",
        category="Brand Safety",
        name="Competitor presence",
        intent="Flag rival brand names, logos, or distinct competitor products.",
        severity="medium",
        feasibility=AUTOMATIC,
        requires=("competitor_terms", "transcript", "ocr"),
        detection=(
            "Operator-supplied brand names are matched against the transcript and on-screen "
            "text. Logo and product-image matching needs reference images plus a model."
        ),
        limitation="Only runs when --competitor is supplied; text matching cannot see an unlabelled logo.",
    ),
    Rule(
        id="BS-PROFANITY",
        category="Brand Safety",
        name="Profanity frequency",
        intent="Track curse words and their rate per minute.",
        severity="medium",
        feasibility=AUTOMATIC,
        requires=("transcript",),
        detection="Bundled profanity lexicon with obfuscation-tolerant matching, reported with frequency.",
    ),
    Rule(
        id="BS-SENTIMENT",
        category="Brand Safety",
        name="Aggressive tone and negative sentiment",
        intent="Flag persistently hostile or highly negative tone.",
        severity="medium",
        feasibility=MODEL_REQUIRED,
        requires=("transcript",),
        detection="Keyword tone cues; reliable sentiment needs a local language model.",
        limitation="Lexicon sentiment is crude and context-blind; treat scores as a weak signal.",
    ),
    Rule(
        id="BS-CONTROVERSY",
        category="Brand Safety",
        name="Controversial themes",
        intent="Flag sensitive political topics, disasters, and tragedies.",
        severity="medium",
        feasibility=MODEL_REQUIRED,
        requires=("transcript", "ocr"),
        detection="Keyword cues for a documented default theme list, overridable with --theme.",
        limitation="Topical sensitivity is contextual; keyword hits are leads, not verdicts.",
    ),
    # ------------------------------------------------------------------ legal
    Rule(
        id="LE-MUSIC",
        category="Legal",
        name="Copyrighted background music",
        intent="Detect unauthorised copyrighted music in the audio track.",
        severity="high",
        feasibility=NOT_DETECTABLE,
        requires=("music",),
        detection=(
            "Impossible offline without a licensed audio fingerprint database. The auditor can "
            "only report whether music is likely present and require manual rights confirmation."
        ),
        limitation="Ownership and licensing cannot be established on a personal machine.",
    ),
    Rule(
        id="LE-CLIPS",
        category="Legal",
        name="Unlicensed visual clips",
        intent="Detect third-party footage used without a licence.",
        severity="high",
        feasibility=NOT_DETECTABLE,
        requires=(),
        detection="No offline method can establish provenance or licensing of arbitrary footage.",
        limitation="Requires a reference corpus or a licensed content-ID service.",
    ),
    Rule(
        id="LE-DISCLOSURE",
        category="Legal",
        name="Mandatory disclosures and watermarks",
        intent="Verify required legal text is present, legible, and on screen long enough.",
        severity="high",
        feasibility=MODEL_REQUIRED,
        requires=("disclosure_text",),
        detection=(
            "On-screen text is read with OCR and matched against requested disclosure patterns; "
            "readability is checked via text height as a fraction of frame height and dwell time."
        ),
        limitation="Needs a local OCR engine (Tesseract). Without it, disclosure presence is unverified.",
    ),
    Rule(
        id="LE-CHILDREN",
        category="Legal",
        name="Children's privacy and audience",
        intent="Flag content that appears child-directed but includes inappropriate themes or data collection.",
        severity="high",
        feasibility=MODEL_REQUIRED,
        requires=("transcript", "ocr"),
        detection=(
            "Child-directed cue words combined with data-collection cues (giveaway, enter your "
            "email, download the app) produce a low-confidence flag for human review."
        ),
        limitation="Audience is a judgement; this is a screening heuristic, not a legal determination.",
    ),
    # ----------------------------------------------------------- technical QA
    Rule(
        id="TQ-BLACK",
        category="Technical QA",
        name="Black screens and dropped signal",
        intent="Flag frames that are effectively black for longer than the tolerance.",
        severity="medium",
        feasibility=AUTOMATIC,
        requires=("luminance",),
        detection="Per-frame mean luminance; contiguous intervals below threshold are reported.",
    ),
    Rule(
        id="TQ-DEAD-AIR",
        category="Technical QA",
        name="Dead air",
        intent="Flag prolonged silence in a track that should carry narration.",
        severity="medium",
        feasibility=AUTOMATIC,
        requires=("audio_rms",),
        detection="Per-window RMS; consecutive windows below the floor are grouped into intervals.",
    ),
    Rule(
        id="TQ-FREEZE",
        category="Technical QA",
        name="Freeze and stalled motion",
        intent="Flag a picture that stops updating.",
        severity="medium",
        feasibility=AUTOMATIC,
        requires=("motion",),
        detection="Per-frame change ratio; near-zero change for longer than the tolerance is reported.",
    ),
    Rule(
        id="TQ-STROBE",
        category="Technical QA",
        name="Strobing and photosensitivity",
        intent="Flag rapid flashing that could trigger photosensitive seizures.",
        severity="high",
        feasibility=AUTOMATIC,
        requires=("luminance", "red_level"),
        detection=(
            "Counts luminance transitions of at least 10% of range inside one-second windows; "
            "three or more transitions flash at over 3 Hz. Saturated red flashes are counted separately."
        ),
    ),
    Rule(
        id="TQ-AVSYNC",
        category="Technical QA",
        name="Audio-video sync",
        intent="Detect drift between speech and picture.",
        severity="medium",
        feasibility=AUTOMATIC,
        requires=("audio_rms", "motion"),
        detection=(
            "Cross-correlates the audio-onset envelope with the visual-motion envelope across "
            "lags of +/-0.5 s and reports the best offset."
        ),
        limitation=(
            "This correlates sound energy with picture change. It is not phoneme-to-viseme "
            "alignment and cannot verify lip-sync on a static speaker."
        ),
    ),
)

RULES_BY_ID = {rule.id: rule for rule in RULES}


def rule_by_id(rule_id: str) -> Rule:
    try:
        return RULES_BY_ID[rule_id]
    except KeyError as exc:
        raise KeyError(f"unknown audit rule: {rule_id}") from exc


def rules_for(category: str | None = None) -> tuple[Rule, ...]:
    if category is None:
        return RULES
    if category not in CATEGORIES:
        raise ValueError(f"category must be one of: {', '.join(CATEGORIES)}")
    return tuple(rule for rule in RULES if rule.category == category)
