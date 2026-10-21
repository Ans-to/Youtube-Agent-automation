# Video audit

**File:** `film-1080p.mp4`  
**Duration:** 00:00:31  
**Generated:** 2026-10-21T19:59:20+00:00

## Result

AUDIT STATUS: INCOMPLETE - No violations detected, but 13 rule(s) could not be verified: TQ-LIPSYNC, BS-PROFANITY, BS-CONTROVERSY, CS-VIOLENCE, CS-WEAPONS, CS-SELFHARM, CS-CONTRABAND, CS-HATE-SPEECH, CS-ADULT, BS-SENTIMENT, LE-CHILDREN, LE-MUSIC, LE-CLIPS.

- Rules evaluated: 7 passed, 0 flagged
- Not verifiable on this machine: 12 unverified, 1 manual
- Not applicable: 2

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

- `audio_profile` — local DSP: -24.5 dBFS integrated, music heuristics: no bed (60% confidence)
- `audio_rms` — ffmpeg PCM, 0.1 s windows
- `luminance` — ffmpeg frames at 10 fps

## Capability gaps

Unavailable on this machine: asr, local_model, ocr, ocr_engine.
Install them or supply equivalent inputs to verify the rules listed above.
