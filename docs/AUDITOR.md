# Video auditor

An offline auditor for finished videos covering content safety, brand safety,
legal compliance, and technical QA. It runs on the operator's machine with no
account, no key, and no upload.

```bash
python video_studio/audit_video.py workspace/generated/video.mp4 \
  --competitor "Acme" --require-disclosure "paid partnership" \
  --report workspace/generated/audit.md
```

## The one rule that shapes everything

**A check that did not run is not a pass.**

A typical "AI moderation" tool returns *clean* when its model is not installed.
This one cannot. Every rule declares the evidence it needs, and the report has
five states:

| State | Meaning |
| --- | --- |
| `flagged` | A detector ran and found something |
| `passed` | A detector ran and found nothing |
| `unverified` | The evidence was never collected (no ASR, no OCR, no model) |
| `manual` | No offline method can decide this (licensing, provenance) |
| `not_applicable` | The rule needs operator input that was not supplied |
| `attested` | A named human reviewed it; recorded with their name |

`AUDIT STATUS: PASSED - No violations detected.` is printed **only** when every
rule is `passed`, `not_applicable`, or `attested`. Otherwise the auditor prints
`FLAGGED` or `INCOMPLETE` and lists exactly which rules it could not check.

## Rule catalog

### Content Safety

| ID | Rule | Feasibility |
| --- | --- | --- |
| `CS-VIOLENCE` | Violence and gore | Term cues automatic; visual needs a local classifier |
| `CS-WEAPONS` | Weapons on screen | Term cues automatic; objects need a detector |
| `CS-SELFHARM` | Self-harm | Term cues automatic; imagery needs a model |
| `CS-HATE-SPEECH` | Slurs and harassment | Operator lexicon or a local model |
| `CS-ADULT` | Nudity and sexual content | Local NSFW classifier only |
| `CS-CONTRABAND` | Drugs and illegal substances | Term cues; visual needs a detector |

### Brand Safety

| ID | Rule | Feasibility |
| --- | --- | --- |
| `BS-COMPETITOR` | Rival brands | Automatic from `--competitor` in speech and on-screen text |
| `BS-PROFANITY` | Curse-word rate | Automatic, obfuscation-tolerant, per-minute threshold |
| `BS-SENTIMENT` | Aggressive or negative tone | Local language model |
| `BS-CONTROVERSY` | Politics, disasters, tragedies | Automatic keyword screening for review |

### Legal

| ID | Rule | Feasibility |
| --- | --- | --- |
| `LE-MUSIC` | Copyrighted music | **Not detectable offline.** No fingerprint database exists locally |
| `LE-CLIPS` | Unlicensed footage | **Not detectable offline.** Requires a reference corpus |
| `LE-DISCLOSURE` | Mandatory legal text | OCR + presence, legibility (text height), and dwell time |
| `LE-CHILDREN` | Children's privacy | Screening heuristic: child cues + data-collection cues |

### Technical QA

| ID | Rule | Feasibility |
| --- | --- | --- |
| `TQ-BLACK` | Black screens, dropped signal | Automatic |
| `TQ-DEAD-AIR` | Prolonged silence | Automatic |
| `TQ-FREEZE` | Stalled picture | Automatic |
| `TQ-STROBE` | Photosensitive flashing | Automatic (>3 transitions/s at ≥10% luminance step) |
| `TQ-AVSYNC` | Audio/video drift | Automatic envelope correlation, ±0.5 s |

## What it can and cannot prove

Be precise about this before acting on a result.

| Claim | Does the auditor support it? |
| --- | --- |
| "No black frames, dead air, freezes, or strobing were detected." | **Yes**, deterministic measurement |
| "Audio and picture agree within ~0.15 s." | **Yes**, as an envelope correlation — not phoneme/viseme alignment |
| "No required disclosure is missing or illegible." | **Yes, if OCR ran** |
| "The transcript contains no profanity above the threshold." | **Yes, if a transcript exists** |
| "No weapons or violence appear." | **No.** Text cues only; silent footage is invisible to it |
| "The music is licensed." | **No.** Impossible offline |
| "The footage is original or licensed." | **No.** Impossible offline |
| "The video is suitable for children." | **No.** A heuristic, not a legal determination |

## Context aware: the chef with a knife

The requirement to distinguish *a chef holding a knife* from *violence* is why
text-term detection is scored rather than decided. Each cue is evaluated with a
±8 second context window:

- weapon term **with** benign context (`chef`, `kitchen`, `recipe`, `prop`,
  `tutorial`, `safety`) → confidence drops to ~18% and the description says a
  safe depiction is likely;
- weapon term **without** benign context → confidence ~42%, still explicitly
  "requires contextual review".

Nothing produced by term matching is treated as a verdict. That is the honest
ceiling of a text-only method, and the report says so.

## Installation tiers

| Tier | What it enables | Install |
| --- | --- | --- |
| 0 (default) | All technical QA, profanity, controversy, competitor text, children heuristic | Nothing — FFmpeg only |
| 1 (OCR) | Disclosure verification: presence, size, dwell | `pip install pytesseract pillow` + Tesseract binary |
| 2 (ASR) | Speech-based rules without subtitles | `pip install faster-whisper` (downloads a model once) |
| 3 (models) | Visual content rules | A local object/NSFW classifier (roadmap) |

Everything stays local. `faster-whisper` runs on the CPU and never phones home.

## Attestation

Some rules cannot be automated. Instead of silently passing them, a named human
can attest them:

```bash
python video_studio/audit_video.py video.mp4 \
  --attest CS-ADULT --attest LE-MUSIC --attested-by "Sana K."
```

The report states who attested what, and these appear under **Human attestation**
as *not machine-verified*. Attestation can never silence a detector that actually
ran and flagged something — it only fills a gap where no evidence exists.

## Output

```markdown
### 1. Technical QA — Strobing and photosensitivity

- **Timestamp:** [00:00:14 - 00:00:15]
- **Violation Category:** Technical QA
- **Rule Broken:** Strobing and photosensitivity (`TQ-STROBE`)
- **Description:** 4 luminance transitions of at least 10% within 1.0 s (approximately 4.0 flashes per second).
- **Confidence Score:** 92%
```

JSON output (`--json`) carries the same fields plus `evidence`, per-rule states,
signal sources, and capability gaps.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Passed — every rule verified |
| `1` | Violations found |
| `2` | No violations, but rules could not be verified |
| `3` | Audit could not run |

`--allow-incomplete` maps `2` to `0` for CI stages that only gate on violations.
Use it deliberately: an incomplete audit is not a clean bill of health.

## Pipeline integration

`video_studio/production.py` can run the auditor after rendering:

```bash
python video_studio/production.py --topic "..." --render --audit \
  --require-disclosure "paid partnership" --competitor "Acme"
```

This writes `audit.json` and `audit.md` into the package and adds
`content_audit_status`, `content_audit_findings`, and
`content_audit_unverified_rules` to `package-status.json`. The audit never
publishes and never overrides the human approval gate.

## Design notes

- Detectors are pure functions over signals (`video_studio/audit/detectors.py`),
  so thresholds are unit-tested with synthetic numbers and can be reviewed.
- Signal extraction is isolated in `media.py`; without FFmpeg the audit still
  runs and reports everything as unverified.
- No network access is used anywhere in the package, and
  `tools/check_invariants.py` enforces that no billable endpoint can creep in.
- The strobing threshold (≥10% luminance change, >3 per second) is a screening
  rule, not a certified Harding analysis. Treat a flag as "review this", and a
  pass as "nothing measurable at this sampling rate".
