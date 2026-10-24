# The roster, rebuilt around the film we actually make

**Applied in this branch.** The owner confirmed the shape, chose deletion for the
software-product roles rather than parking them, and kept the Urdu role live.

## What was true before (measured from the repo, not remembered)

| fact | number |
|---|---|
| roles in `agents/roster.json` | 52 |
| departments | 18 |
| roles never named by any code that runs the channel (`.py`, `.html`, `.mjs`, outside tests) | **24** |
| roles named exactly once, 9 of those only inside one set literal (`MOTION_ROLES`) | 13 |
| roles the film pipeline actually assigned (`DEFAULT_PIPELINE`) | 11 |

The roster had been written as a general media agency: trend analysis, competitor
analysis, music licensing, digital-product launches, release management. Our
product is one pipeline — an AI-tools-and-tech video, voiced, drawn and rendered
locally by our own code. Roles that served no step of that pipeline were not a
safety net; they were 24 names that made the real eleven hard to see.

Of the 13 named once, nine were named *only* as members of `MOTION_ROLES`, a set
whose single effect was appending a reference document to their prompt.

## The tree, as applied — 40 roles

One level. Parents own a deliverable and are the only roles the CEO hands work
to. Sub-agents own one craft each, are named by their parent, and carry a
`parent` field. `MOTION_ROLES` is now **derived** from `parent`, so a role joins
the motion tree by having a parent, not by being remembered in a list.

### Parents (11) — the only roles assigned work

| id | role | directs | owns |
|---|---|---|---|
| AGENT-01 | CEO / Coordinator | — | intake, delegation, the decision to publish |
| AGENT-02 | Research Lead | 3 | what is true about this AI tool |
| AGENT-09 | Script Architect | 6 | the words |
| AGENT-51 | Motion Graphics Director | 7 | the picture |
| AGENT-31 | Render Operator | 3 | the file |
| AGENT-27 | Narration Director | 2 | the voice |
| AGENT-26 | Caption Builder | — | the captions *(absorbs AGENT-34)* |
| AGENT-16 | Packaging Lead | 4 | title, description, chapters, review |
| AGENT-41 | Shorts Editor | 2 | the vertical cut |
| AGENT-37 | Compliance Lead | 2 | copyright, privacy, safety |
| AGENT-50 | Human Approval Gate | — | nothing — a boundary, never executed |

### Sub-agents (29)

| parent | sub-agents |
|---|---|
| AGENT-02 | 03 Source Auditor *(absorbs 35)* · 07 Topic Scout · 08 Fact Checker |
| AGENT-09 | 10 Hook · 11 Outline · 12 Explainer · **13 Urdu Localizer** · 14 English Editor · 15 Retention Editor |
| AGENT-51 | **21 Timing & Beat** · **23 Kinetic Typography** · **52 Transitions & Compositing** · 24 Palette · 25 Diagram · 20 Storyboard · 19 Thumbnail |
| AGENT-31 | 22 Canvas Animator · 32 Render Validator · 33 Visual QA |
| AGENT-27 | 28 TTS Operator · 29 Audio QA |
| AGENT-16 | 17 Description · 18 Chapters · 39 Brand · 40 Metadata QA |
| AGENT-41 | 42 Long-Form Editor · 43 Clip Selector |
| AGENT-37 | 36 Copyright · 38 Privacy |

Bold are the crafts the owner named when he described the model. `AGENT-21` is
*Timing & Beat* because timing is what it decides, and the one-second rule — two
different motion types in two different frame areas — now has a named owner and
sits in its mission. `AGENT-52` narrows to transitions and compositing; kinetic
typography moved to `AGENT-23`.

## Deleted (12) — chosen by the owner

| id | role | why it had no job |
|---|---|---|
| AGENT-04 | Trend Analyst | analysed "user-provided research data" that is never provided |
| AGENT-05 | Audience Analyst | the channel has one audience; it is not a per-video question |
| AGENT-06 | Competitor Analyst | compared "examples supplied by the user", which are not |
| AGENT-30 | Music Rights Checker | our audio is synthesised by `video_studio/audio_design.py`; nothing is licensed |
| AGENT-34 | Subtitle QA | merged into 26 — one role owns the caption's text *and* its timing |
| AGENT-35 | Source Citation Editor | merged into 03 — same job, split in two |
| AGENT-44 | Product Researcher | served product builds, not video, and no longer assigned |
| AGENT-45 | Product Architect | same |
| AGENT-46 | Prototype Builder | same — the tool pipeline writes the files, not this role |
| AGENT-47 | Documentation Writer | same |
| AGENT-48 | Test Engineer | same |
| AGENT-49 | Release Manager | same |

The software branch they fed in `orchestrate.heuristic_assignments` is gone with
them: a request to build software routes to the tool pipelines, which write the
files themselves, so no specialist's prose changed the outcome. `routing.py`
still claims those pipelines — the veto that "a YouTube automation studio is
software, not a video to render" is untouched.

`AGENT-13` (Urdu) stays live as a sub-agent of the script parent, per the owner.

## What changed in code

1. `agents/roster.json` — `parent` and `division` on every role; version 2.
2. `agents/skillbooks.json` — 12 profiles removed, names and scope rewritten for
   03, 16, 21, 23, 26, 37, 51, 52.
3. `agents/dispatch.py` — `roster_roles()`, `children_of()`, `subtree()`,
   `sub_agent_brief()`; `MOTION_ROLES` derived; a parent's playbook now carries
   the list of sub-agents it must direct.
4. `agents/orchestrate.py` — `DEFAULT_PIPELINE` names parents only; the
   no-model fallback assigns five parents plus the fact-check gate; the CEO
   prompt explains the tree; a repair goes to the parent that owns the
   deliverable.
5. `web/deck.html` — the roster view groups by division and shows `under AGENT-xx`.
6. Tests — the six that pinned the flat 52 now assert the tree, and
   `tests/test_dispatch.py` gained seven tests that fail if the roster flattens
   again or a deleted role comes back.

The film is untouched: `video_studio/` does not read the roster.
