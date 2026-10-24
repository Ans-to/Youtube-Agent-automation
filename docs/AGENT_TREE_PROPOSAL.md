# The roster, rebuilt around the film we actually make

Nothing here has been applied. This is the shape to approve or overrule.

## What is true today (measured from the repo, not remembered)

| fact | number |
|---|---|
| roles in `agents/roster.json` | 52 |
| departments | 18 |
| roles never named by any code that runs the channel (`.py`, `.html`, `.mjs`, outside tests) | **24** |
| roles named exactly once, 9 of those only inside one set literal (`MOTION_ROLES`) | 13 |
| roles the film pipeline actually assigns (`DEFAULT_PIPELINE`) | 11 |

The roster was written as a general media agency: trend analysis, competitor
analysis, music licensing, digital-product launches, release management. Our
product is one pipeline — an AI-tools-and-tech video, voiced, drawn and rendered
locally by our own code. Roles that serve no step of that pipeline are not a
safety net; they are 24 names that make the real eleven hard to see.

And of the 13 named once, nine are named *only* as members of `MOTION_ROLES`, a
set whose single effect is appending a reference document to their prompt. They
are not doing anything a tree would not do better.

## The shape you described

> a motion graphics agent whose sub agents are kinetic typography, transition, and so on

That is the right model and the code already wants it: `orchestrate.py` assigns
one parent a whole craft, and the parent's job is to pick the children who do the
pieces. One level. Parents own a deliverable and are the only roles the CEO hands
work to. Children own one craft each and are named by their parent, never by the
CEO.

### Parents (11) — the only roles assigned work

| id | role | owns |
|---|---|---|
| AGENT-01 | CEO / Coordinator | intake, delegation, the decision to publish |
| AGENT-02 | Research Lead | what is true about this AI tool |
| AGENT-09 | Script Architect | the words |
| AGENT-51 | Motion Graphics Director | the picture |
| AGENT-31 | Render Operator | the file |
| AGENT-27 | Narration Director | the voice |
| AGENT-26 | Caption Builder | the captions |
| AGENT-16 | Packaging Lead | title, description, chapters |
| AGENT-41 | Shorts Editor | the vertical cut |
| AGENT-37 | Compliance Lead | copyright, privacy, safety |
| AGENT-50 | Human Approval Gate | nothing — it is a boundary, not a worker |

### Children (28)

| parent | children |
|---|---|
| AGENT-02 | 03 Source Auditor *(absorbs 35)* · 07 Topic Scout · 08 Fact Checker |
| AGENT-09 | 10 Hook · 11 Outline · 12 Explainer · 14 English Editor · 15 Retention Editor |
| AGENT-51 | **21 Timing & Beat** · **23 Kinetic Typography** · **52 Transitions & Compositing** · 24 Palette · 25 Diagram · 20 Storyboard · 19 Thumbnail |
| AGENT-31 | 22 Canvas Animator · 32 Render Validator · 33 Visual QA |
| AGENT-27 | 28 TTS Operator · 29 Audio QA |
| AGENT-26 | *(none — absorbs 34 Subtitle QA)* |
| AGENT-16 | 17 Description · 18 Chapters · 39 Brand · 40 Metadata QA |
| AGENT-41 | 42 Long-Form Editor · 43 Clip Selector |
| AGENT-37 | 36 Copyright · 38 Privacy |

Bold are the three your example named. `AGENT-21` is renamed *Timing & Beat*
because timing is what it actually decides, and because the one-second rule —
two different motion types in two different frame areas — belongs to a named
owner. `AGENT-52` narrows to transitions and compositing; kinetic typography
leaves it for `AGENT-23`, which is where you asked for it.

**39 roles stay.** 52 → 11 parents + 28 children.

## Delete (6)

Every one of these is never named by the code, so nothing breaks.

| id | role | why it has no job |
|---|---|---|
| AGENT-04 | Trend Analyst | analyses "user-provided research data" that is never provided |
| AGENT-05 | Audience Analyst | the channel has one audience; it is not a per-video question |
| AGENT-06 | Competitor Analyst | compares "examples supplied by the user", which are not |
| AGENT-30 | Music Rights Checker | **our audio is synthesised by `video_studio/audio_design.py`; nothing is licensed** |
| AGENT-34 | Subtitle QA | merged into 26 — one role must own the caption's text *and* its timing |
| AGENT-35 | Source Citation Editor | merged into 03 — same job, split in two |

## Park (7) — kept in the file, off the content pipeline

| id | role | why parked, not deleted |
|---|---|---|
| AGENT-13 | Urdu Localizer | genuinely useful *if* you order an Urdu cut; costs nothing idle |
| AGENT-44–47 | Product Researcher, Product Architect, Prototype Builder, Documentation Writer | used by the software branch of `orchestrate.py` (`web_build`, `cli_tool`); deleting them guts a working feature |
| AGENT-48 | Test Engineer | same branch |
| AGENT-49 | Release Manager | same branch |

If you would rather have them gone outright, say so and I will also remove the
software branch they feed — but that branch builds websites and tools, and it is
the only thing in the repo that does.

## What this costs in code

1. `agents/roster.json` — add `parent` and `division` to each role, split a
   `"parked"` array out of `"agents"`.
2. `agents/skillbooks.json` — drop 6 profiles, keep the parked ones, rewrite the
   four roles whose scope moved (03, 21, 23, 52).
3. `agents/dispatch.py` — `children_of()` and `expand_assignments()`; and
   `MOTION_ROLES` is **derived from the tree** instead of a hand-written set of
   14 ids, so it can never drift from the roster again.
4. `agents/orchestrate.py` — `DEFAULT_PIPELINE` names parents only; one
   expansion point expands them to children.
5. `agents/routing.py` — untouched (it routes pipelines, not agents).
6. `app/services/status.py`, `web/deck.html` — render the tree instead of a flat
   list of 52.
7. Tests — `test_skillbooks`, `test_dispatch`, `test_orchestrate` pin ids and the
   roster/skillbook equality. They get updated with the change, not after it.

One commit, gate and full suite green before it lands. The film itself is not
touched by any of this; `video_studio/` does not read the roster.

## The three things I need you to answer

1. **The shape** — 11 parents over 28 children, one level, as drawn. Yes / fewer
   parents / something else.
2. **Park or delete 44–49** (digital products, test engineer, release manager).
3. **Urdu (13)** — park it, or is an Urdu cut actually coming?
