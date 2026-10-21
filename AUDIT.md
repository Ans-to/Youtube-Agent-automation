# Repository audit — Offline Agent HQ (`Youtube-Agent-automation`)

**Audit date:** 2026-10-21  
**Commit reviewed:** `9ffdf178efb7c29ada6e0c53de3dfe5709795083` — *Video production: add cinematic camera and character motion* (`main`)  
**Working branch:** `arena/118abf10-youtube-agent-automation`  
**Scope:** entire repository (~19,260 tracked lines; 12,705 Python), CI workflows, documentation, dependency and release controls.  
**Method:** manual review, Ruff static analysis, unit tests, coverage, the project's own quality gate, a live dashboard smoke test, an end-to-end offline task run, renderer validation checks, `npm audit`, and GitHub API inspection.

Severity key: **Critical** = remote compromise/data loss; **High** = serious security or privacy defect; **Medium** = control gap, broken documented workflow, or risk under specific conditions; **Low** = hygiene, maintainability, or UX.

---

## 1. Executive summary

**Verdict: no critical or high-severity vulnerabilities were found.** This is a security-conscious codebase with real fail-closed behavior, not just security claims in Markdown. The strongest parts are the dashboard request boundary, the loopback-only model client, the SSRF-hardened research fetcher, the cross-process queue lock, the GitHub bridge allowlist/deduplication, and the publishing approval gate.

The main weaknesses are **documentation drift** (several documents describe controls or features that differ from the code), **duplicated security-critical helpers**, **configuration-boundary bypasses**, an **ineffective CI guard**, and **thin unit coverage of the highest-risk media modules**.

| Area | Rating | Summary |
| --- | --- | --- |
| Security controls | **Strong** | Loopback/SSRF/approval/queue controls are implemented and tested; live checks passed |
| Reliability & state management | **Strong** | Atomic queue writes, cross-process lock, Windows-safe liveness, no silent replay |
| Test suite | **Good** | 274 tests pass; 71% coverage; security paths well covered, media pipeline thin |
| CI/CD | **Good, one broken guard** | Green on `main`; Actions pinned; the "immutable action" check runs before checkout and is a no-op |
| Documentation accuracy | **Weak** | Multiple direct contradictions with code (bridge actions, disabled CLIs, "practice lab") |
| Maintainability | **Fair** | 75 Ruff findings, duplicated helpers, dead state, 1,082-line orchestrator |
| Supply chain | **Fair** | Actions/voice models pinned; portable FFmpeg download unverified; `npm install` vs `npm ci` |
| Governance | **Weak** | Public repository with **no LICENSE**; 62 branches; 14 open PRs (10 are Dependabot, incl. major bumps) |

### Top actions, in order

1. Move the "Enforce immutable GitHub Action references" step **after** `actions/checkout` (currently a silent no-op).
2. Reconcile the bridge documentation with the implemented `create_task` action; the repo is public and these docs are its security contract.
3. Consolidate the duplicated loopback-model validator and external-action guard into shared modules.
4. Route all config reads through `app_config.load_config()`; stop silently downgrading on malformed `config.json`.
5. Pin/verify the portable FFmpeg download and switch local installs to `npm ci`.
6. Add a top-level `LICENSE` or make the repository private.

---

## 2. What the repository is

A local-first task command center with five execution surfaces:

| Surface | Entry point | Purpose |
| --- | --- | --- |
| Local task application | `dashboard.py`, `agent.py`, `queue_store.py` | Loopback dashboard, durable queue, worker |
| Agent orchestration | `agents/orchestrate.py`, `agents/dispatch.py`, `agents/practice.py` | CEO-led specialist pipeline, research, review gate |
| Video production | `video_studio/production.py`, `studio.py`, `render.js`, `render.html` | Script/storyboard/MP4/TTS/QA pipeline |
| Product builder | `product_studio/build_product.py` | HTML/ZIP prototype generator |
| External boundary | `bridge/bridge.py`, `video_studio/publish_youtube.py` | Allowlisted GitHub control channel; approval-gated upload |

Architecture, module boundaries, and the intended dependency direction are documented in `docs/ARCHITECTURE.md`.

---

## 3. Verification performed

| Check | Command / method | Result |
| --- | --- | --- |
| Unit tests | `python3 -m unittest discover -s tests` | **274 passed, 1 skipped** (~3.9 s) |
| Coverage | `coverage run --source=. -m unittest discover -s tests` | **71%** (8,230 statements, 2,356 missed) |
| Project quality gate | `python3 tools/run_quality_gate.py --report /tmp/quality-gate.json` | **37 passed / 0 failed / 0 skipped — PASS** |
| Python compile (all tracked `.py`) | `python3 -m py_compile $(git ls-files '*.py')` | **PASS** |
| JavaScript syntax | `node --check video_studio/render.js` | **PASS** |
| Renderer input validation | `node render.js storyboard.invalid-transition.json` / `storyboard.over-limit.json` | Correctly rejected (exit 1) with the expected messages |
| Renderer dependencies | `npm ci --ignore-scripts` in `video_studio/` | **PASS** (lockfile v3, Puppeteer 25.14.0) |
| Dependency audit | `npm audit --omit=dev` | **0 vulnerabilities** |
| Static analysis | `ruff check --select F,E9,B,S --exclude tests .` (Ruff 0.17.1) | **75 findings** (see §6) |
| Dashboard live smoke | Bound to `127.0.0.1:8799`, then `curl` | `GET /` 200; `/api/state` valid JSON; POST without `Origin` **403**; same-origin POST **303**; `/output` with a nonexistent/traversal ID **404**; CSP / `X-Frame-Options: DENY` / Permissions-Policy present |
| End-to-end offline run | Real task queued through the dashboard with no model | `pipeline-status.json`: `status=partial`, `quality_gate=unconfirmed`, `delegation_mode=heuristic_no_model`; research failure disclosed as `failure_disclosed`; task `needs_human_action`. No fabricated citations. |
| GitHub checks on `main` | `gh api .../commits/main/check-runs` | **5/5 success** (pipeline, PowerShell safe-sync, CodeQL, render previews, pip graph) |
| Repository metadata | `gh repo view`, `gh api .../branches` | Public, default `main`, **no license**, 62 branches, 14 open PRs (10 Dependabot), open issues #7 (P0) and #43 |
| Secret patterns | `grep`, `git log -S` | No hardcoded credentials, `eval`/`exec`/`pickle`/`yaml.load`/`os.system`/`shell=True` found |

Runtime artifacts created by the smoke test (task queue, logs, outputs, orchestration/research reports) were removed afterwards; the working tree is clean.

**Not verified (environment limits):** actual MP4 rendering locally (no FFmpeg/FFprobe in this sandbox), Windows/Termux runtime behavior, YouTube upload (no OAuth credentials), branch-protection settings and secret-scanning alerts (GitHub API returns 403 for this token), and commit history (the local clone is shallow — one commit).

---

## 4. Strengths (verified)

1. **Dashboard request boundary is defense-in-depth.** `validate_post_request` (`dashboard.py:258`) requires a loopback `Host` with the exact bound port, a mandatory same-host/port `Origin`, URL-encoded form content, and rejects `Transfer-Encoding`. Bodies are capped at 128,000 bytes (`dashboard.py:19`), output is HTML-escaped, and a strict CSP/XFO/Permissions policy is sent on every response (`dashboard.py:301-305`).
2. **Loopback-only model client.** `post_local_model` (`agent.py:25`) accepts only plain HTTP on a literal loopback IP with an explicit port, rejects userinfo/query/fragment, disables proxies and redirects, and bounds response reads.
3. **SSRF-hardened research.** `video_studio/research.py` validates scheme/host, rejects private/loopback/link-local/reserved addresses after DNS resolution (`research.py:128`), validates every redirect hop (`research.py:154`), bounds page size/text, and redacts common secrets, emails, phone numbers, and CNIC patterns before sending queries (`research.py:272`).
4. **Durable queue semantics.** `queue_store.py` uses `O_CREAT|O_EXCL` lock files with PID ownership, conservative stale-lock handling only after 600 s and a dead owner, non-destructive Windows process probing, and atomic `os.replace` writes. Orphaned `running` tasks become `needs_human_action`, never replayed (`agent.py:346`).
5. **Bridge least privilege.** Only `status`, `self_test`, `create_task`, `run_task` are accepted; extra fields are rejected (`bridge/bridge.py:454-459`); request IDs are path-safe; replay is blocked by `O_EXCL` processing markers and strict dedup state; results are write-once and sanitized (`bridge.py:163`, `bridge.py:191`).
6. **Publishing is genuinely approval-gated.** Approval must match the video SHA-256, package directory, `script.md`, `storyboard.json`, and `video.qc.json` hashes; strict QC is re-validated; an `O_EXCL` upload lock plus an `in_progress` marker are persisted before the upload; `--confirm-publish` and (for public) `--confirm-public` are mandatory (`video_studio/publish_youtube.py:33-124`).
7. **Honest failure semantics.** The pipeline refuses to mark template-only output complete; research failures are written as explicit failure reports and surfaced as `failure_disclosed`; reviewer verdicts are parsed only from exactly one explicit `OVERALL QUALITY GATE` line (`agents/orchestrate.py:70-75`). This was confirmed end-to-end.
8. **CI hygiene.** All external Actions are pinned to 40-character SHAs, workflows declare least-privilege `permissions`, CodeQL, `npm audit`, Docker clean-room tests, Windows PowerShell validation, and a real CEO→MP4 end-to-end render are included.
9. **Renderer is data-driven and bounded.** `render.js` enforces 320–3840 width, 180–2160 height, 1–60 fps, ≤100 scenes, ≤30,000 frames, ≤1,000 s, field-length and array limits; `render.html` draws text through Canvas only (no `innerHTML`, `eval`, or `document.write`).
10. **Tests target real behavior.** 274 tests cover approval reuse, hash mismatches, bridge replay/interruption, Windows liveness, corrupted dedup state, path traversal, reviewer gate parsing, retry policy, queue recovery, and artifact validation.

---

## 5. Findings

### 5.1 Medium

#### M1 — The CI "immutable Action" guard is a no-op

**Location:** `.github/workflows/tests.yml:24-45` (guard) vs `.github/workflows/tests.yml:46` (`actions/checkout`)

**Evidence:** The first step runs a Python heredoc that scans `Path(".github/workflows").glob("*.y*ml")`. It executes **before** the repository is checked out, so on a fresh runner the directory is empty and the loop finds nothing, prints `PASS`, and exits 0. Reproduced in an empty directory:

```text
failures: []
PASS: every external GitHub Action is pinned
```

All Actions are in fact pinned today (verified independently), but the control cannot enforce that for future changes.

**Impact:** A supply-chain policy gate silently passes for any workflow change. This is a false sense of enforcement rather than an immediate vulnerability.

**Recommendation:** Move the step after checkout (or use a `pre-checkout`-safe mechanism), and add a negative self-test proving an unpinned `uses:` fails.

---

#### M2 — Bridge documentation contradicts the implemented `create_task` action

**Location:** `bridge/README.md:5-11`, `SECURITY.md:8`, `README.md:26` and `:34`, `README.local.md` (bridge section); implementation at `bridge/bridge.py:38`, `:281`, `:454-459`; the correct description exists only in `MOBILE_PC_GUIDE.md:45` and `README.md:114`

**Evidence:** Code allows four actions: `status`, `self_test`, `create_task`, `run_task`. `create_task` accepts bounded remote text (`title` 1–160 chars, `input` 1–16,000 chars, allowlisted `kind`). Meanwhile:

- `bridge/README.md` lists only three actions and states: "No remote task text … accepted."
- `SECURITY.md` lists only `status`, `self_test`, `run_task`.
- `README.md:34` states "The GitHub bridge does not accept new task text," then `README.md:114` documents adding `create_task` requests.
- `README.local.md` repeats "It does not accept task text."

**Impact:** The repository is public. A reviewer approving the bridge from `SECURITY.md` or `bridge/README.md` would be approving a different threat model than the code implements. This is a security-documentation defect, not an exploit on its own: requests still require `approved: true` and, for `create_task`, a repository write by a collaborator.

**Recommendation:** Update all four documents to include `create_task`, its bounds, and its privacy implications; add a test asserting the documented action set equals `ALLOWED_ACTIONS`. Consider making `create_task` opt-in via an environment flag if it is not intended as a default capability.

---

#### M3 — Security-critical helpers are duplicated and have already drifted

**Locations:**
- `post_local_model` — `agent.py:25`, `agents/dispatch.py:35`, `product_studio/build_product.py:15` (three near-identical copies)
- External-action guard — `agent.py:279-298` and `bridge/bridge.py:353-365` (two copies)
- `load_config`/`is_within` — `video_studio/production.py:38`, `agents/practice.py:27,33` vs `app_config.py:41` and `tools/path_utils.py:49`

**Evidence:** The three model validators enforce the same rules but differ in formatting and in surrounding behavior. The two external-action guards are the same regex list compiled separately. The bridge's `run_task` kind allowlist (`bridge.py:348`) omits `youtube_package`, while `create_task` (`bridge.py:285`) accepts it — a real capability asymmetry that is undocumented.

**Impact:** A future hardening fix applied to one copy will silently leave the others permissive. These are the controls that keep the app on loopback and keep the bridge from triggering external actions.

**Recommendation:** Extract `tools/local_model.py`, `tools/external_actions.py`, and a single config accessor; import them everywhere. Keep behavior-preserving characterization tests.

---

#### M4 — Configuration boundary is bypassed, and malformed config is silently ignored

**Location:** `video_studio/production.py:38-42` and `:430`; `agents/practice.py:33-36`; `video_studio/voice_backends.py:9-20`; contract in `docs/ARCHITECTURE.md:38-56`

**Evidence:** `docs/ARCHITECTURE.md` states that `app_config.load_config()` is the shared configuration boundary and that "malformed config is an actionable error." In practice:

- `production.py` and `practice.py` read `config.json` directly and catch `json.JSONDecodeError` by returning `{}`. A malformed config silently disables model use and produces template output instead of failing.
- `voice_backends.load_project_config` raises on malformed JSON (correct) but still does not apply `AGENT_HQ_*` environment overrides.
- `AGENT_HQ_MODEL_ENABLED`, `AGENT_HQ_MODEL_BASE_URL`, etc. therefore have no effect on the video/product CLI paths.

**Impact:** A user can set an environment override, see the dashboard honor it, and still get template-only video output with no error. Silent downgrade is worse than a clear failure for a system whose trust model depends on labelling generated vs template content.

**Recommendation:** Make all modules use `app_config.load_config(path, environ=...)`; propagate `ConfigError`. If a module must read directly, test that malformed config is rejected rather than defaulted.

---

#### M5 — Installer and CI dependency hygiene

**Location:** `setup_all_windows.ps1:59-64`; `setup_windows.ps1:58`; `.github/workflows/human-review-video.yml:55`

**Evidence:**
- Portable FFmpeg is downloaded from `https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip` with only a size sanity check; there is no SHA-256 or signature verification (`grep Get-FileHash` finds nothing).
- Local setup runs `npm install` despite a committed `package-lock.json`; CI correctly uses `npm ci` in `tests.yml:100`, but `human-review-video.yml` uses `npm install`.
- `npm audit` currently reports 0 vulnerabilities, so this is preventive.

**Impact:** An unverified executable archive is unpacked and executed (`ffmpeg -version`) during first-run setup; `npm install` can resolve newer transitive versions than the lockfile review covered.

**Recommendation:** Pin a specific FFmpeg build with a published SHA-256 (or use winget with a pinned package version) and verify before extraction; use `npm ci` everywhere a lockfile exists.

---

#### M6 — Documented commands and features that do not work

**Locations:**
- `README.md:238` — "The dashboard includes a Specialist practice lab." No such UI exists; `POST /practice-agent` always returns **403** `"Direct specialist execution is disabled"` (`dashboard.py:372-373`). The practice CLI (`agents/practice.py`) does work.
- `README.md:262` — `python agents/dispatch.py --agent AGENT-09 --task "..."`. `dispatch.main()` unconditionally raises `SystemExit("Direct specialist execution is disabled…")` (`agents/dispatch.py:274-278`). Verified: exits 1 with that message regardless of arguments.
- `README.md:59` — "Submit a task; **Run pending** sends queued tasks…". `POST /add` calls `start_task_runner()` immediately (`dashboard.py:369-370`), so the queue is already being processed; `RUN PENDING` is effectively redundant for new submissions.

**Impact:** Users follow documented workflows and hit dead ends. It also suggests docs were not updated when specialist execution was consolidated under the CEO.

**Recommendation:** Either restore the documented surfaces or remove them from the README; add a doc test that greps for commands and endpoints that exist. Document the auto-start behavior of `QUEUE TASK` explicitly.

---

#### M7 — Public repository has no license

**Location:** repository root (no `LICENSE`/`COPYING`); `skills/i-have-adhd/LICENSE` is MIT for the bundled skill only. GitHub reports `licenseInfo: null`.

**Impact:** Without a license, default copyright applies: others may view the public code but have no clear right to use, modify, or redistribute it — including the users the README invites to download, run, and modify the project. This is a governance/legal gap rather than a technical defect.

**Recommendation:** Add an explicit license (MIT/Apache-2.0 if intended for reuse) or make the repository private. Confirm the bundled skill's MIT notice is retained.

---

#### M8 — Unit coverage is thin exactly where failures are expensive

**Location:** coverage output; `tools/run_quality_gate.py`

**Evidence:** Overall **71%**. The core security paths are well covered (`queue_store` 86%, `agents/dispatch` 86%, `agents/orchestrate` 78%, `app_config` 82%), but:

| Module | Coverage |
| --- | --- |
| `video_studio/validate_render.py` | 23% |
| `video_studio/capabilities.py` | 29% |
| `video_studio/quality_audit.py` | 30% |
| `video_studio/voice_preview.py` | 30% |
| `video_studio/production.py` | 36% |
| `video_studio/release_gate.py` | 36% |
| `video_studio/studio.py` | 38% |
| `bridge/bridge.py` | 39% |
| `dashboard.py` | 43% |

CI does run real renders end-to-end for pushes and pull requests targeting `main`, but the default local quality-gate run does not render, and the unit-level signal for these modules is weak. Contributors working offline therefore have little pre-merge coverage of the media pipeline.

**Recommendation:** Add focused tests for `production.py` scene allocation/validation, `release_gate.validate_qc_report`, `studio.py` storyboard validation and failure paths, and `bridge.run_once` orchestration (mocked GitHub). Consider a coverage floor for security modules (e.g., 80%) rather than overall.

---

### 5.2 Low

| ID | Location | Finding | Recommendation |
| --- | --- | --- | --- |
| L1 | `dashboard.py:336-338` | `GET /output` serves **any file under the repo root** if a task's `output_file` points there (e.g., `config.json`). Not remotely reachable (`output_file` is set by the runner), but there is no allowlist. | Restrict to `outputs/` and `workspace/`, e.g. `is_within(candidate, OUTPUTS or WORKSPACE)`. |
| L2 | `dashboard.py:301` | CSP allows `'unsafe-inline'` for scripts and styles (the app is one inline document). Escaping is correct, but CSP provides weaker XSS defense than necessary. | Move JS/CSS to static files or use per-response nonces/hashes. |
| L3 | `dashboard.py:29-30,99`; `agent.py:109-111`; `video_studio/production.py:567,572`; `dashboard.py:7`; `agents/dispatch.py:3`; `agents/practice.py:9`; `product_studio/build_product.py:3` | Dead/vestigial code: `TRAINING_RUNNING`/`TRAINING_LAST_OUTPUT` are exported in `/api/state` but never mutated (no training route remains); `build_prompt()` is only called by a test; `context_limit` and `actual_target_seconds` are assigned but unused; four unused imports. | Remove dead state and code, or wire the training state to a real endpoint; update the test that keeps `build_prompt` alive. |
| L4 | repo-wide | Ruff (F,E9,B,S) reports 75 findings: 23 `S603` (all subprocess calls use list args — informational), 17 `B904`, 11 `S310`, 7 `B905`, 6 `F841`, 4 `F401`, 4 `S110`, 2 `S324` (MD5 used only to verify a pinned public voice checksum — acceptable, but document why), 1 `S105` false positive (`language_token`). No linter runs in CI. | Add Ruff with a documented rule set; add `raise ... from` in `B904` sites; annotate intentional silent cleanups. |
| L5 | `.github/workflows/tests.yml:5` | Push trigger still includes the stale branch `integration/agent-hq-complete-20261020`; the remote has 62 branches and 14 open PRs (Dependabot #33–#42 plus older feature PRs #5, #6, #10, #45), including several major bumps (`actions/checkout` 7, `setup-python` 7, CodeQL 4, NeMo 3, Transformers 5). | Remove the stale trigger; close or batch stale branches/PRs; group Dependabot updates and schedule major bumps deliberately. |
| L6 | `start.sh:1`, `run_once.sh:1`, `overnight.sh:1`; `git ls-files -s` | Shell launchers use a Termux-only shebang and are committed mode `100644` (not executable). `video_studio/studio.py:441` accepts an arbitrary `--output` path while `production.py`, `build_product.py`, and the quality gate enforce workspace containment. | Use `#!/usr/bin/env sh` (or document Termux-only), `chmod +x`, and apply the same containment rule to `studio.py --output`. |
| L7 | `video_studio/research.py:128-140`, `:227` | DNS is resolved for the public-address check, then resolved again by `urllib` when connecting — a classic DNS-rebinding TOCTOU window. Redirects are separately validated. | Pin the validated address for the connection (custom opener/resolver) or document the residual risk explicitly in `SECURITY.md`. |
| L8 | `dashboard.py:72-74,128`; `queue_store.py:129-134` | Dashboard reads (`load`) swallow any JSON error and display an empty queue, while writes use strict `load_tasks`. A corrupt `tasks.json` therefore looks like "no tasks" in the UI and stalls the worker silently. `save_tasks` does not `fsync` before `os.replace`. | Surface parse errors in `/api/state`; `fsync` the temp file before replacement for power-loss durability. |
| L9 | `dashboard.py:516` | `HTTPServer` is single-threaded with no socket timeout; a slow client or long request blocks the 4-second UI refresh. | Use `ThreadingHTTPServer` with a request timeout while keeping the same validation. |
| L10 | `.gitignore:19-20,26` | Unanchored `*token*` / `*secret*` patterns can silently ignore future legitimate files (e.g., a tokenizer), and `/workspace/` is ignored yet a file inside it is tracked (`workspace/orchestration/CEO_FULL_PIPELINE_EXECUTION_MANDATE.md`). | Anchor the secret patterns to real credential filenames; move the mandate to `docs/` or document the exception. |
| L11 | `bridge/bridge.py:407-409` | The GitHub token file is read without checking permissions (e.g., world-readable on multi-user systems). | Warn or fail if the token file is group/other-readable on POSIX; set `0o600` when creating. |
| L12 | `EXAMPLE_TASKS.md:17`; `README.md:281-298`; `agents/MOTION_DESIGN_SYSTEM.md:11-12` | Minor doc defects: valid-kinds list omits `youtube_package`; backticks are escaped as ``\` `` (renders literal backslashes/backticks instead of code); one README section claims GitHub Actions runs only on main/PR (it also runs on the stale branch). | Fix the kind list and Markdown escaping; add a docs formatting check. |
| L13 | `README.md:22`, `video_studio/research.py:272` | Research sends redacted, task-derived queries to DuckDuckGo, a third party, but the privacy section does not state this egress explicitly (only that secrets/identifiers are redacted). | Add a one-line privacy disclosure naming the search provider and what is sent; note that even redacted task text leaves the device. |

---

## 6. Static analysis detail

Ruff 0.17.1, `--select F,E9,B,S --exclude tests --exclude node_modules`:

| Rule | Count | Assessment |
| --- | --- | --- |
| `S603` | 23 | All subprocess calls use argument lists; no `shell=True`. Acceptable; suppress with justification. |
| `B904` | 17 | Missing `raise ... from` inside `except`. Style/diagnostics quality, not a bug. |
| `S310` | 11 | URL opens are intentional, but the schemes are validated by callers. Add `# noqa` with rationale or centralize. |
| `B905` | 7 | `zip()` without `strict=`. Checked the relevant sites: `captions.py:227` is guarded by an explicit cue-count equality check; others are bounded FFmpeg parsing. Safe today, still worth `strict=True` where lengths must match. |
| `F841` | 6 | Unused variables, including the dead `context_limit` and `actual_target_seconds` (see L3). |
| `F401` | 4 | Unused imports (see L3). |
| `S110` | 4 | `try/except/pass` in best-effort cleanup paths. Mostly deliberate; annotate. |
| `S324` | 2 | MD5 used to verify public voice-model checksums (`piper_urdu_tts_adapter.py:46,63`). Integrity pinning, not authentication; acceptable with a comment. |
| `S105` | 1 | False positive: `language_token` regex name. |

No `eval`, `exec`, `pickle`, `yaml.load`, `os.system`, or `shell=True` usage was found. No hardcoded credentials were found.

---

## 7. Security model review

### Trust boundaries

| Boundary | Controls observed | Residual risk |
| --- | --- | --- |
| Browser → dashboard | Loopback bind enforced in `main()`; `Host` + `Origin` + content-type + no `Transfer-Encoding`; body cap; CSP/XFO; escaped Markdown | No authentication; any local process/user with loopback access can read tasks/outputs and queue work. Documented. |
| Dashboard/agents → model | Literal loopback IP, plain HTTP, explicit port, no userinfo/query/fragment, proxies/redirects disabled, bounded response | A local process impersonating the model endpoint can return arbitrary text; treated as untrusted text and cross-checked, but not authenticated. Documented as local-only. |
| Research fetcher → internet | Scheme/host validation, DNS public-address check, per-hop redirect validation, size/text caps, query redaction | DNS-rebinding TOCTOU (L7); task-derived queries still leave the device (see L13 below). |
| GitHub → bridge | `approved: true`, exact field set, path-safe IDs, action allowlist, `O_EXCL` claim, strict dedup state, sole-pending-task rule for `run_task`, external-action heuristic | A collaborator with write access can queue bounded tasks (documented for `mobile-agent-inbox`, understated elsewhere — M2). Heuristic filter can miss or over-match (documented). |
| Local artifacts → publisher | SHA-256 binding for video/script/storyboard/QC, strict QC re-validation, approval reuse prevention, `O_EXCL` upload lock, `in_progress` marker, explicit confirmations | Local users can edit approval files; by design, a human gate — not tamper-proof against the same local user. |
| Model/web content → prompts | Multiple "treat as untrusted" instructions; no tool execution from model text; fixed builders only | Prompt injection can still influence wording/JSON; validators constrain artifacts. No hidden technical enforcement. |

### Notable non-findings

- `research._host_is_public` correctly rejects localhost, `.local`, non-global IPs, and unresolved hosts; redirects are validated per hop and the final URL is re-validated.
- The dashboard's `/task` and `/output` handlers escape all task text and use a restricted Markdown renderer that escapes before formatting (`web/markdown_renderer.py`).
- Bridge `public_result()` strips prompts, paths, stdout/stderr, and logs; the local result keeps the tails but never publishes them (`bridge.py:163-190`).
- `publish_youtube.py` refuses reuse of a consumed approval and treats `in_progress`/`outcome_unknown` as blocking (`publish_youtube.py:33-59`).
- The renderer's fixed `frames/` directory is protected by an OS-level render lock; stale frame files matching the fixed pattern are removed before render.

---

## 8. Testing and CI assessment

**Test suite quality is above average.** Tests are behavioral, use mocks for subprocess/network, and cover failure modes rather than only happy paths. Examples: `test_one_million_deterministic_retry_scenarios`, approval reuse/uncertainty, corrupted bridge state, Windows liveness semantics, reviewer-gate parsing with exactly one verdict, artifact hash mismatch, and queue recovery without replay.

**CI is well designed** — one consolidated Linux job to reduce runner usage, a clean Docker unit-test pass, Windows PowerShell parsing/validation, CodeQL, `npm audit`, renderer negative tests, an end-to-end synthetic CEO→MP4 render, and artifact retention for human inspection.

Gaps:

1. **M1**: the pinning guard cannot see the repository.
2. **No lint gate**: 75 Ruff findings accumulate unmanaged.
3. **No Python dependency audit**: `pip-audit`/`safety` is not run for the optional TTS/publish requirements.
4. **No coverage threshold**: media modules can regress below current levels unnoticed.
5. **Human-review preview renders** run only on `main` pushes/manual dispatch (a deliberate runner-minute trade-off), so rendered visual previews are not attached to most PRs; the consolidated pipeline still runs the synthetic render smoke for PRs to `main`.

---

## 9. Recommended roadmap

### P0 — this week

1. Fix the CI guard ordering (`tests.yml:24-46`) and add a negative self-test.
2. Update `bridge/README.md`, `SECURITY.md`, `README.md:26/34`, and `README.local.md` for `create_task`; add a documentation test that compares the documented set with `ALLOWED_ACTIONS`.
3. Add a top-level `LICENSE` (or make the repo private).
4. Route `production.py`, `practice.py`, and `voice_backends.py` through `app_config.load_config()`; make malformed config an error.
5. Replace `npm install` with `npm ci` in `setup_windows.ps1` and `human-review-video.yml`.

### P1 — next iteration

6. Extract shared `post_local_model`, external-action guard, and `is_within`/`load_config` helpers; add characterization tests.
7. Fix the two broken documented workflows (dispatch CLI, dashboard practice lab) or remove them.
8. Pin and checksum the portable FFmpeg download.
9. Restrict `/output` to `outputs/` + `workspace/`; add a traversal test.
10. Add Ruff + coverage floor + `pip-audit` to CI (non-blocking for legacy findings, blocking for new ones).
11. Expand unit tests for `production.py`, `studio.py`, `release_gate.py`, and `bridge.run_once`.

### P2 — hygiene

12. Remove dead training state/`build_prompt`/unused imports; fix `B904` sites.
13. Harden CSP (nonces or external assets); consider `ThreadingHTTPServer` with timeouts.
14. Resolve the research DNS-rebinding TOCTOU or document it; add an explicit privacy note that redacted task-derived queries are sent to DuckDuckGo.
15. Remove the stale CI branch, prune merged branches, batch Dependabot majors.
16. Add `#!/usr/bin/env sh` + executable bits, or scope the launchers to Termux in docs.
17. Fix README/Markdown escaping and `EXAMPLE_TASKS.md` kinds.

---

## 10. Audit limitations

- This was a **white-box review plus dynamic smoke tests**, not a penetration test or a formal threat model with an adversary.
- The local clone is **shallow** (one commit), so Git history and historical secret exposure could not be reviewed.
- **FFmpeg/FFprobe are absent** in the audit sandbox, so no real MP4 was rendered end-to-end here; renderer validation was exercised through `render.js` negative tests, and CI logs show green renders on `main`.
- **Windows/Termux behavior** was assessed from code, tests, and CI configuration, not executed on those platforms.
- **YouTube upload** could not be exercised without OAuth credentials; the approval gate is covered by unit tests only.
- Branch protection, secret scanning, and Dependabot alerts could not be queried (GitHub API 403 for this token); the GitHub-side hardening checklist in `SECURITY.md` is the right control, but its actual state is unverified.
- Dependency advisories were checked only for npm (`npm audit`: 0); Python optional stacks were not installed or audited.
