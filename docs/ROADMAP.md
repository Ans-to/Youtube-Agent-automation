# Roadmap — from working pipeline to general automation

This is the honest gap list between the current system and the three promises in
[`NORTH_STAR.md`](NORTH_STAR.md): free, sovereign, and *actually doing the work*.

Each phase has an **acceptance test**. A phase is not done because the code
exists; it is done when the test passes on a real task and the evidence is
committed.

---

## Where the system is today

| Capability | State | Evidence |
| --- | --- | --- |
| Offline operation, no key | **Done** | 328 tests, quality gate 41/41, invariant check |
| Rules enforced in CI | **Done** | `tools/check_invariants.py`, 7 rules |
| Video pipeline (script → MP4) | **Done** | `video_studio/production.py`, technical QA |
| Confined tool execution | **Done** | `tools/tool_runtime.py`, 4 tools |
| Plan → act → verify → repair | **Done for web builds** | `tools/tool_agent.py`, `agents/orchestrate.py` |
| Professional motion design (L4) | **Gap** | 10 visual types, 7 transitions, 5 camera moves, box-figure rig |
| General task automation (L3) | **Partial** | Web builds only; no long-horizon memory |
| Code quality of local models | **Gap** | Small models route well but write weak code |

---

## Phase 1 — Renderer primitives (professional motion)

**Why first.** This is the most visible promise and the least dependent on model
quality. It is engineering, not prompting.

Work:

1. **Compositing:** offscreen layer canvases, `globalCompositeOperation` blend
   modes, mask/clip paths, per-layer parallax at fixed depths.
2. **Finish:** deterministic motion blur (frame accumulation), bloom, vignette,
   film grain, and a depth-of-field substitute — all seeded, all reproducible.
3. **Motion library:** spring solver, bezier keyframes, anticipation/overshoot,
   stagger, and a shared easing registry used by every scene type.
4. **Assets:** SVG path import and a Lottie subset (layers + transforms) so
   artwork stops being hand-coded shapes.
5. **Typography:** variable-font weight animation, optical tracking, text on
   path, and measured reflow with collision detection.
6. **Character:** skeletal 2D rig (bones, IK targets, viseme timeline) rendered
   to RGBA frames and composited in FFmpeg — the pipeline described in
   `video_studio/skills/CHARACTER_VOICE_LIPSYNC.md`.

**Acceptance test:** three reference storyboards (30 s each: explainer, product,
kinetic type) render at 1080p30 and pass a written review against named
commercial references, with a defect log and regression fixtures added to
`video_studio/storyboard.*.json`.

**Do not** raise the L4 claim in `NORTH_STAR.md` before that review exists.

## Phase 2 — General task routing

Work:

1. Replace the regex intent classifier in `run_builtin_tools` with a **task
   routing layer**: the model sees the tool catalog *and* the available
   pipelines, and returns a pipeline or tool plan.
2. Extend the tool loop beyond web builds: document/data deliverables
   (Markdown, CSV, JSON, charts), script/CLI projects, and test-and-fix tasks.
3. Add tools with new side effects behind explicit policy:
   `delete_file` (trash-only), `http_fetch` (allowlisted, SSRF-hardened reuse),
   `package_install` (never), `serve_preview` (loopback, read-only).
4. Multi-artifact plans: one goal, several deliverables, one manifest.

**Acceptance test:** ten held-out goals across four domains ("write a
changelog", "analyze this CSV and chart it", "build a CLI that dedupes photos",
"debug this failing test") each produce verified artifacts with no manual step,
and each failure is reported as a failure rather than a draft.

## Phase 3 — Long-horizon memory and repair

Work:

1. Persist plan state across runs so a long task can pause and resume.
2. Feed human review notes back as lessons (`workspace/training/feedback` is
   already wired for specialists).
3. Budget-aware repair: token, wall-clock, and disk ceilings per task.
4. A diff-based review step: every write is shown as a change, not a dump.

**Acceptance test:** a task interrupted mid-run resumes and completes without
duplicating artifacts. A deliberately broken plan recovers in ≤2 repairs.

## Phase 4 — Motion as an agent capability

Work:

1. Give AGENT-51/52 the renderer's *actual* primitive list, not prose.
2. Have them emit storyboard JSON that validates against `render.js` on the
   first try (schema-first, not prose-first).
3. Automated visual QA: extract frames, measure contrast, safe-area overflow,
   text collision, blank frames, and freeze duration; fail the render.

**Acceptance test:** a storyboard authored purely by the agents renders without
manual repair, and automated visual QA catches a deliberately seeded layout bug.

## Phase 5 — Operating it

Work:

1. A single `start` command that verifies prerequisites, runs the capability
   probe, and prints what is possible on this machine.
2. Model presets: 3B (routing only), 8B (drafting), 14–32B (code) with honest
   capability labels.
3. Per-task cost report: wall-clock, tokens, disk — the "free" claim measured.

---

## Deliberately out of scope

- **A4 autonomy** (unbounded self-directed operation). Conflicts with the
  approval gate in P6 and cannot be made safe on a personal machine.
- **Paid or hosted inference**, ever (P1).
- **Arbitrary code execution without a sandbox** (P8).
- **Publishing, payments, deletion, or messaging without human approval** (P6).

## Known limits that code cannot fix

| Limit | Consequence |
| --- | --- |
| Local model size vs hardware | 3B models route; they do not write production code. 14B+ needs ~16–24 GB RAM. |
| CPU-only rendering | 1080p motion graphics are minutes per minute of video; 4K is impractical. |
| No forced aligner on CPU | Lip-sync stays approximate unless a phoneme aligner is added. |
| Review is human | "Professional" is a judgement; the system can only make it measurable. |

## Order of work

1. Phase 2 routing (highest capability gain per unit of work).
2. Phase 1 renderer primitives (highest visible quality gain).
3. Phase 3 memory (makes long tasks viable).
4. Phase 4 + 5 (agent-authored motion, operability).

Phase 1 and Phase 2 can run in parallel because they touch different modules.
