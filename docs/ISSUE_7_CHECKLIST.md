# Issue #7 — checklist status (2026-10-22)

Recorded here because the token available to the automation session can read the
issue but cannot write to it (`403 Resource not accessible by integration` on
issue comments, Dependabot alerts and code-scanning alerts alike). Evidence and
commands: [`AUDIT_2026-10-22.md`](AUDIT_2026-10-22.md).

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | Audit runtime, orchestration, agents, skillbooks, builder, renderer, voice, QA, recovery | **Done** | `AUDIT_2026-10-22.md`; each layer executed, not read |
| 2 | Research with a source ledger; never claim failed research succeeded | **Mechanism verified / blocked** | Research attempted, failed with disclosed TLS error; 0 pages fetched, 0 citations invented |
| 3 | Improve specialist code/skills | **Verified** | 52/52 roster↔skillbook parity, all fields present, enforced by `tests/test_skillbooks.py` |
| 4 | Layered 2D rig + documented animation system | **Done** | `node video_studio/character/selfcheck.mjs` → 22/22 |
| 5 | Audio-driven viseme timing + stated limitations | **Done** | Mouth↔envelope correlation 0.969; limits documented below |
| 6 | Natural adult-male Urdu narration; fail closed rather than eSpeak/silence | **Fail-closed done / naturalness blocked** | Both guards executed at runtime; transcripts below |
| 7 | Fix defects, add regression tests, rerun failed stages then full pipeline | **Defects fixed; full rerun blocked** | 2 defects fixed, +23 tests, 685 passing |
| 8 | Run through the CEO intake/orchestrator | **Done** | `python agent.py --once --task-id AUDIT-CEO-E2E` |
| 9 | MP4 from the integrated pipeline + QA report | **Blocked** | No reachable English Piper voice model |

## Fail-closed, verified by running it

```
--language ur-en
→ "Urdu-English production render is blocked pending human voice approval for the
   current voice profile. ... set urdu_voice_human_approved=true and
   urdu_voice_approved_profile_sha256 to this exact SHA-256:
   9198ede5911dbabdec7850abbd56836b78c3302b85b837307a6b4e77b18ecbcb."

--language en
→ "English narration requires Piper and PIPER_MODEL pointing to a verified
   English voice model; silent output is not an acceptable fallback."
```

## Defects found by the recheck

1. **`requirements-kani-tts.txt` could never install.** It pinned
   `transformers==4.57.1` while `nemo_toolkit[tts]==2.4.0` requires
   `transformers<=4.52.0,>=4.51.0`. `pip install -r` failed with
   `ResolutionImpossible`, so the documented Kani backend never worked.
2. **Fixing it the obvious way installs a vulnerable stack.** Ten advisories
   apply to transformers 4.57.1. NeMo 3.0 drops the cap, so the pair now moves
   together to 3.0.0 / 5.x and all ten clear.

Both are now guarded by `tests/test_kani_requirements_security.py`.

## Why item 9 is blocked

`piper-tts` installs from PyPI, but the voice model does not exist anywhere
reachable:

- `en_US-lessac-medium` is published on HuggingFace — unreachable from this
  sandbox.
- The `rhasspy/piper` GitHub **release asset** redirects to
  `release-assets.githubusercontent.com` — also unreachable.
- Every GitHub repo mirror of the file is a 133-byte Git LFS pointer.

So the pipeline cannot render an integrated MP4 here, and the guard in item 6 is
what stops a silent or eSpeak video from being passed off as the deliverable.

## Still open

- **Item 9** — blocked on the voice model above.
- **Item 2** — research *quality* is unassessable with outbound web access
  restricted to a small allowlist. The failure path is honest; the success path
  is unproven.
- **Items 5/6** — mouth timing is driven by measured audio energy and spectral
  brightness, not forced phoneme alignment. It is real audio-driven sync but it
  is not phoneme-accurate, and it is not labelled as such.
- **6 advisories remain** in the optional Kani/NeMo set (`hydra-core`,
  `lightning`, `fsspec`), capped below their fixed releases by NeMo 3.0's own
  constraints. No requirements file clears them while NeMo is used; the only
  route to zero is dropping that backend, which is a product decision.
