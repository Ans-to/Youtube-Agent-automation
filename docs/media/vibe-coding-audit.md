# Video audit

**File:** `film-1080p.mp4`  
**Duration:** 00:11:29  
**Generated:** 2026-10-22T21:48:34+00:00

## Result

AUDIT STATUS: FLAGGED - 5 violation(s) detected.

- Rules evaluated: 6 passed, 1 flagged
- Not verifiable on this machine: 12 unverified, 1 manual
- Not applicable: 2

## Violations

### 1. Technical QA — Freeze and stalled motion

- **Timestamp:** [00:03:34 - 00:03:37]
- **Violation Category:** Technical QA
- **Rule Broken:** Freeze and stalled motion (`TQ-FREEZE`)
- **Description:** Frame content is static for 3.2 s. Confirm this is an intentional hold rather than a stalled render or dropped signal.
- **Confidence Score:** 92%

### 2. Technical QA — Freeze and stalled motion

- **Timestamp:** [00:03:50 - 00:03:53]
- **Violation Category:** Technical QA
- **Rule Broken:** Freeze and stalled motion (`TQ-FREEZE`)
- **Description:** Frame content is static for 3.2 s. Confirm this is an intentional hold rather than a stalled render or dropped signal.
- **Confidence Score:** 92%

### 3. Technical QA — Freeze and stalled motion

- **Timestamp:** [00:07:24 - 00:07:27]
- **Violation Category:** Technical QA
- **Rule Broken:** Freeze and stalled motion (`TQ-FREEZE`)
- **Description:** Frame content is static for 3.0 s. Confirm this is an intentional hold rather than a stalled render or dropped signal.
- **Confidence Score:** 92%

### 4. Technical QA — Freeze and stalled motion

- **Timestamp:** [00:07:27 - 00:07:31]
- **Violation Category:** Technical QA
- **Rule Broken:** Freeze and stalled motion (`TQ-FREEZE`)
- **Description:** Frame content is static for 3.4 s. Confirm this is an intentional hold rather than a stalled render or dropped signal.
- **Confidence Score:** 92%

### 5. Technical QA — Freeze and stalled motion

- **Timestamp:** [00:08:54 - 00:08:57]
- **Violation Category:** Technical QA
- **Rule Broken:** Freeze and stalled motion (`TQ-FREEZE`)
- **Description:** Frame content is static for 3.1 s. Confirm this is an intentional hold rather than a stalled render or dropped signal.
- **Confidence Score:** 92%

## Not verified

These rules were **not** checked. A clean result above does not cover them.

- `TQ-LIPSYNC` **Lip-sync alignment** — Missing evidence: faces, mouth_motion. Install or supply it to verify this rule.
- `BS-PROFANITY` **Profanity frequency** — Missing evidence: transcript. Install or supply it to verify this rule.
- `BS-CONTROVERSY` **Controversial themes** — Missing evidence: transcript, ocr. Install or supply it to verify this rule.
- `CS-VIOLENCE` **Violence and gore** — Missing evidence: transcript, ocr, vision. No content signal is available.
- `CS-WEAPONS` **Weapons on screen** — Missing evidence: transcript, ocr, vision. No content signal is available.
- `CS-SELFHARM` **Self-harm** — Missing evidence: transcript, ocr, vision. No content signal is available.
- `CS-CONTRABAND` **Contraband and illegal substances** — Missing evidence: transcript, ocr, vision. No content signal is available.
- `CS-HATE-SPEECH` **Hate speech and harassment in speech** — Requires a local language model or an operator-supplied --hate-lexicon.
- `CS-ADULT` **Adult content and nudity** — Requires local vision observations from an NSFW classifier.
- `BS-SENTIMENT` **Aggressive tone and negative sentiment** — Requires a local language model, which is not configured.
- `LE-CHILDREN` **Children's privacy and audience** — Missing evidence: transcript, ocr. Install or supply it to verify this rule.
- `LE-MUSIC` **Copyrighted background music** — The music heuristic was not confident enough to clear this rule (60% < 75%). Confirm the soundtrack licence directly.
- `LE-CLIPS` **Unlicensed visual clips** — Requires a reference corpus or a licensed content-ID service.

## Not applicable (no input supplied)

- `BS-COMPETITOR` **Competitor presence** — No competitor list supplied; pass --competitor to enable this check.
- `LE-DISCLOSURE` **Mandatory disclosures and watermarks** — No disclosure requirement supplied; pass --require-disclosure to enable this check.

## Evidence used

- `audio_profile` — local DSP: -23.4 dBFS integrated, music heuristics: no bed (60% confidence)
- `audio_rms` — ffmpeg PCM, 0.1 s windows
- `luminance` — ffmpeg frames at 10 fps

## Capability gaps

Unavailable on this machine: asr, ffprobe, local_model, ocr, ocr_engine.
Install them or supply equivalent inputs to verify the rules listed above.
