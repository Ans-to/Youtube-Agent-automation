# Script-first motion-graphics proofs — DRAFT / not approved

These are three small, unrelated fixture scripts, not final films. Each uses a manually authored visual plan, the procedural house-style drawing renderer and English Kokoro speech; the final render reused the previously synthesized clips. There are **no still photos or generated-image backplates**. They demonstrate parts of the new path, but do **not** test an actual running local-model director. They do not demonstrate real Urdu speech. No independent topical research was performed.

| Draft | Illustrates | Length | Frames | Encoded master | Speech-active voice / sample peak / music |
|---|---|---:|---:|---|---|
| [Systems](systems/video.mp4) | A server sends a message; the reverse transfer does **not** occur | 7.467 s | 224 | −14.3 LUFS, −3.3 dBTP | −15.84 / −3.67 / −29.23 dBFS |
| [Nature](nature/video.mp4) | Sunlight and a leaf, then a drawn seed growing into a plant | 4.833 s | 145 | −14.9 LUFS, −2.1 dBTP | −16.75 / −3.30 / −26.80 dBFS |
| [Numbers](numbers/video.mp4) | A narrated decrease from 20 to 10 liters | 3.967 s | 119 | −15.2 LUFS, −3.5 dBTP | −17.05 / −3.30 / −27.51 dBFS |

All are 1920×1080, 30 fps, H.264 with 48 kHz AAC stereo, without captions. The encoded QA recorded no threshold-exceeding black, freeze or silence events, and the longest sampled held pictures were 0.6 s, 0.7 s and 0.7 s respectively. Frame counts and timestamps were checked against their render plans. The voice and music levels are measured on the included, aligned mono stems in speech-active 50 ms windows; they are not listener evaluations. No effects stem is used. The stated audio ranges are recommendations and the per-file audit reports any deviations.

Every [audit](systems/script.audit.json) ([nature](nature/script.audit.json), [numbers](numbers/script.audit.json)) is **INCOMPLETE**: speech, word-level sync, meaning, pacing, mix, captions, ending and factual review are not verified by a named human. The technical checks do not prove any of these. Watch and listen before judging quality; neither the clips nor this report approves the Nokia full film.

Each folder includes its exact source, plan, frame/voice clocks, QA, blank review and measurable voice/music stems. An auditor with the dependencies described in the [workflow guide](../../script-first-motion.md) can reproduce the automated checks:

```bash
python video_studio/script_audit.py --package docs/media/script-motion-proofs/systems
# Exit 2 / INCOMPLETE is expected until a named reviewer completes the checks.
```

`video.qc.json` records the original local render path for provenance; the hash binds the copied video. The audit uses hashes and can run on this copy. `script-review.json` is intentionally blank and must not be represented as an approval.

Video SHA-256:

- Systems: `77071784cb71173d516cb7a265e82127fdbcae47e8402a755b7baed75969273e`
- Nature: `9a644047e9ab8dec8925c66ad094d2175de04c28a231f91e2e27d28fb7578f41`
- Numbers: `8ca6fe5150ad378201809c147a10d5ef7ef9f7563138bfe280ef12b7018825ca`
