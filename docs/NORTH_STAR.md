# North Star — the rules this system is built to keep

This document is the project's constitution. It is not marketing copy: every
rule below has an **ID**, a **reason**, and an **enforcement** mechanism. A rule
without enforcement is a wish, so adding or weakening a rule requires changing
the document *and* `tools/check_invariants.py` in the same change.

**Enforced by:** `python tools/check_invariants.py` (run in CI and in
`tools/run_quality_gate.py`). The checker also fails if this document stops
containing any rule ID that the checker knows about, so the two cannot drift.

---

## 1. Mission

Build a **general-purpose, zero-marginal-cost automation system** that runs on
the operator's own computer, produces professional creative work, and can take a
plain-language goal — a video, a website, a document, a data task — and carry it
from plan to verified artifact without a human doing the steps by hand.

Three promises define "done":

1. **Free** — no subscription, no per-token bill, no credit card, ever.
2. **Sovereign** — no account, no API key, no prompt leaving the machine.
3. **Real** — output is verified, and when it is degraded the system says so
   instead of pretending.

---

## 2. Invariants

### P1 — No paid services and no API keys

**Rule.** The system must never require or accept a paid credential. No cloud
inference, no hosted TTS, no hosted image/video generation, no "free tier"
signup that expires.

**Why.** A key is a dependency on someone else's billing account and terms. One
key quietly turns a free local system into a metered one.

**Enforcement.** `NO_PAID_SDK` blocks imports of hosted-AI SDKs; `NO_BILLABLE_ENDPOINT`
blocks literal URLs to billable AI/TTS/vision hosts; `NO_SECRET_LITERAL` blocks
committed keys and tokens. YouTube upload is the single documented exception
(P7) because Google offers no local alternative for publishing to that platform.

### P2 — Model inference only over loopback

**Rule.** A model call may target only a literal loopback IP with an explicit
port, over plain HTTP, with redirects disabled and proxies bypassed.

**Why.** This is the difference between "my model" and "someone else's model".
It also stops SSRF and DNS-rebinding tricks from redirecting a local call.

**Enforcement.** Implemented in `agent.py`, `agents/dispatch.py`,
`product_studio/build_product.py`; `LOOPBACK_MODEL_ONLY` verifies the shipped
default endpoint is loopback and that the example config ships with the model
**disabled**.

### P3 — Rendering is local, deterministic and asset-free

**Rule.** Video and motion graphics are produced by the in-repository
Canvas2D + FFmpeg pipeline. Same storyboard + same environment ⇒ same frames.
No stock-footage APIs, no cloud render farms, no "AI video" service.

**Why.** Reproducibility is what makes quality measurable and regressions
catchable. Anything non-deterministic cannot be reviewed frame by frame.

**Enforcement.** Renderer validation (`video_studio/render.js`) rejects unknown
visual types, transitions, camera moves, and out-of-budget jobs;
`NO_BILLABLE_ENDPOINT` blocks hosted render APIs.

### P4 — Offline by default, degraded modes are labelled

**Rule.** With no model enabled, the system still produces artifacts — and every
such artifact is explicitly marked as template/scaffold output, never presented
as AI-written work.

**Why.** Silent degradation is worse than failure: it makes a user trust output
that was never generated.

**Enforcement.** `generation_mode` and `note` fields are written into
`pipeline-status.json`; `video_studio/production.py` refuses to present a
template as a requested full video; the checker's `HONEST_DEGRADATION` rule
requires the offline marker to remain present in the orchestration code.

### P5 — Everything generated stays inside `workspace/`

**Rule.** Tools and pipelines may read the repository but may only **write**
under `workspace/`. Source files change only through an explicit, reviewed
edit — never as a side effect of running a task.

**Why.** An agent that can rewrite its own source while running is unauditable
and can disable its own safety checks.

**Enforcement.** `tools/tool_runtime.py` resolves every path through
`tools/path_utils.py` and refuses anything outside the sandbox root; the
checker's `TOOL_SANDBOX_PRESENT` rule fails if the confinement helper is removed.

### P6 — Irreversible actions are approval-gated

**Rule.** Publish, send, pay, delete, and deploy require explicit human
approval (`AGENT-50`). Everything reversible may run autonomously.

**Why.** Autonomy should remove *labour*, not *authority*. The blast radius of a
mistake must stay smaller than "it is already public".

**Enforcement.** `video_studio/publish_youtube.py` approval gate;
`bridge/bridge.py` requires `approved: true`; `AGENT-50` cannot be executed as
an automatic role (`agents/dispatch.py`).

### P7 — The network boundary is a closed, documented list

**Rule.** Exactly four outbound paths are permitted:

| Boundary | Purpose | Cost | Gate |
| --- | --- | --- | --- |
| Web research (`video_studio/research.py`) | Free page retrieval for evidence | Free | SSRF-hardened, size- and time-capped |
| GitHub bridge (`bridge/bridge.py`) | Allowlisted control channel | Free | Token + `approved: true` |
| YouTube upload (`video_studio/publish_youtube.py`) | Publishing a finished video | Free | OAuth + human approval |
| Installer downloads (setup scripts) | One-time tool/voice-model install | Free | Documented, checksum-pending (see audit M5) |

Adding a fifth boundary is a design decision, not an implementation detail.

**Enforcement.** `NO_BILLABLE_ENDPOINT`; this table is the reviewed list.

### P8 — Execution-capable tools are opt-in

**Rule.** Reading and writing inside the sandbox may be enabled by default.
Running a subprocess may not: it requires an explicit flag
(`AGENT_HQ_ALLOW_EXEC=1` / `allow_exec=True`) and a program allowlist. No shell.

**Why.** `subprocess` with `shell=True` plus model-authored strings is remote
code execution with extra steps. The allowlist is small on purpose.

**Enforcement.** `tools/tool_runtime.py` refuses to construct an exec tool
without `allow_exec=True`; `SAFE_SUBPROCESS` in the checker rejects
`shell=True` in first-party modules.

---

## 3. Capability maturity

"Professional" and "general-purpose" are claims we must be able to measure.
Levels are cumulative.

| Level | Definition | Evidence required |
| --- | --- | --- |
| **L0 — Offline** | Runs with no network and no key | Full test suite + quality gate pass offline |
| **L1 — Single-domain** | One pipeline produces a finished, verified artifact | Script → storyboard → TTS → MP4 → technical QA |
| **L2 — Tool-using** | Agent can write files, run commands, and verify results inside a sandbox | Sandboxed runtime + verified build artifacts |
| **L3 — General task** | Any goal is decomposed into tool steps and repaired until verified | Plan → act → verify → repair loop with budgets |
| **L4 — Professional creative** | Output survives side-by-side review against commercial work | Reviewed reference comparison, defect log, regression fixtures |

**Where this repository stands today** (kept honest on purpose):

| Capability | Level | Note |
| --- | --- | --- |
| Offline operation | **L0 ✅** | 274 tests, quality gate, no key required |
| Video pipeline | **L1 ✅** | Deterministic MP4 with technical QA; not studio-grade |
| Tool use | **L2 ✅** | `tools/tool_runtime.py` + `tools/tool_agent.py`, wired into `agents/orchestrate.py`; web builds are confined, verified, and repaired (`tests/test_tool_agent.py`) |
| General task automation | **L3 🚧** | The CEO plans tool steps from the catalog, but only for web builds, with one planning call plus at most two repairs — no long-horizon memory or multi-artifact decomposition |
| Professional motion design | **L4 ❌ partly L2** | 10 visual types, 7 transitions, 5 camera moves, box-figure rig |

Do not raise a level in this table without linking the evidence.

---

## 4. What "fully automated" means here

| Autonomy | Meaning | Status |
| --- | --- | --- |
| A0 | Suggest steps; human executes | — |
| A1 | Execute one approved step | — |
| A2 | Execute a planned sequence, human reviews the result | current pipeline |
| A3 | Plan → execute → verify → repair within budgets | target |
| A4 | Unbounded self-directed operation | **explicitly out of scope** |

A4 is out of scope because it conflicts with P6. The goal is a system that does
the work without being driven step by step — not a system that cannot be
stopped.

---

## 5. Changing these rules

1. Open a change that edits this document **and** `tools/check_invariants.py`.
2. If the rule weakens a boundary, state the threat-model change in the commit
   message and update `SECURITY.md`.
3. `python tools/check_invariants.py` must pass with the new rule active.
4. A rule may be relaxed only with a human decision — never by an agent run.

The audit in `AUDIT.md` records the baseline this document was adopted against.
