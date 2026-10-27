# Nokia financial-line audio repair — draft evidence

**Not a released mix or an approved narration.** The previous full-length
review video mispronounces the amounts in shot `s10-03`: its old phrase splitter
removed both decimal points before synthesis. That MP4 has not been patched.

[`51-s10-03.wav`](51-s10-03.wav) is a replacement generated with the corrected
splitter, the same Kokoro `bm_george` voice, calm profile, and 0.95 rate. The
model phonemizer supplied “five point four four” and “seven point two”; an
approximate forced aligner also placed the “point” words in the new clip. These
are supporting indicators, not a listening review. A person must listen to the
replacement and its final encoded mix before approval.

- Replacement: mono 48 kHz PCM WAV, 10.7335 seconds; SHA-256
  `97a28bb09189f13685eaaf83ca1b2764edbf5505e3f0a5d167b1d0d33d8b9b6d`.
- `shots.json` and `voice-timing.json` are the rebuilt proposed 72-shot clock,
  ending at 934.986 seconds. They refer to this replacement and 71 old clips;
  **only the replacement is included in this folder**. Rebuild or supply those
  other recordings before producing a new mix.
- `phrase-timing.json` records phrase resynthesis matching the sample counts of
  all 72 recordings, with their individual WAV hashes. It does not verify spoken
  words, word-level times or a final picture. Do not apply it to changed clips.
- `music-plan.json` lays out the five moods on the revised clock.
- `repaired-audio-measurements.json` contains preliminary measurements from a
  local scratch WAV mix/stems, not bundled or hash-bound here. It is **not**
  evidence of an encoded video, semantic alignment or perceptual balance.

The picture still needs to be corrected and rendered on this clock. The proposed
short script is not author-approved; listen, fact-check, watch, audit the exact
encoded file and obtain human approval before considering release. See the
[release workflow](../nokia-release-audit.md).
