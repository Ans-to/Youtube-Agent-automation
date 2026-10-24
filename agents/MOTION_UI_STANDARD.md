# UI in motion graphics: what the standards actually say

Research pass for the build window in `video_studio/motion/buildview.mjs`, run before
any further layout work. It answers one question: what does a panel like this do in a
professional motion-graphics film, and what does ours do wrong?

Evidence image: `docs/media/panel-legibility.jpg` — the 29 s frame at true 1080p, the
same window at 1:1, and at 2×.

## 1. Sources

| Source | What it is | The part that matters here |
|---|---|---|
| [legibility.info — Rules for text in videos](https://legibility.info/rules-for-text-in-videos) | German accessibility research (FFA, ARD/ZDF subtitle standards) + font-size calculator | 1080p body text **40–60 px minimum**, titles ≥50 % larger; max **30 characters** a line, **3 lines** at once; dwell **1 s per 13 characters**; text on a contrasting plate, never a busy background |
| [Material 3 — Easing and duration](https://m3.material.io/styles/motion/easing-and-duration) | Google motion spec | **200 ms** exit, **250–400 ms** entry, **300 ms** on-screen change, **500 ms** emphasized; ease-out in, ease-in out |
| [IBM Carbon — Motion](https://v10.carbondesignsystem.com/guidelines/motion/overview/) | IBM motion spec | Duration scales with distance and size; nothing is linear; "productive" curve `cubic-bezier(.2,0,.38,.9)` |
| [Toptal — Motion design principles](https://www.toptal.com/designers/ux/motion-design-principles) | Design writing | Easing on everything; masking to show progress; movement must explain a relationship |
| [bettermockups — motion principles](https://www.bettermockups.com/blogs/resources/motion-design-principles) | Design writing | Motion **originates from the trigger**; stagger children **30–60 ms**; overshoot a few px at most |
| [CursorClip — the zoom problem](https://cursorclip.com/blog/how-to-make-a-product-explainer-video-without-animation/) | Practitioner essay | A real app window at native size is **unreadable on video** — 14–20 px controls read as texture; the fix is to enlarge, not to add detail |
| [advids — animated interface UI videos](https://advids.co/blog/animated-interface-ui-videos) | Agency analysis of 20+ product films | **85 %** abstracted the UI into oversized core elements instead of a literal interface; **71 %** used one enlarged cursor as the viewer's avatar |
| [moonb — product explainer formats](https://www.moonb.io/blog/product-explainer-video) | Agency guide | **One task per video**; pause before each important click; check labels at phone size |
| [Apple HIG — Motion](https://developer.apple.com/design/human-interface-guidelines/motion) | Platform spec | Motion communicates status and change; never decorative; respect reduced motion |

## 2. What I measured in our own frame

Design space is 3840×2160, delivered at 1920×1080, so a design size `S` is `S/2`
pixels on screen. Every text size in `buildview.mjs`, converted:

| Element | Design | On screen | Standard | Verdict |
|---|---|---|---|---|
| App title `BOOKS I HAVE READ` | 58 | 29 px | 40 px floor (an actual title wants 60+) | under |
| Book row | 46 | 23 px | 40 px | under |
| Search text | 38 | 19 px | 40 px | under |
| Address bar | 30 | 15 px | — | decoration |
| Status strip | 28 | 14 px | — | decoration |
| Command pill | 30 | 15 px | — | decoration |
| Repo file name | 36 | 18 px | 40 px | decoration |
| Diff line | 32 | 16 px | 40 px | decoration |
| Check name | 36 | 18 px | 40 px | decoration |

Two findings, and they are different problems.

**The window is small, not blurry.** All 540 px of it, inside a 1920 px frame. At
1:1 (see the evidence image) the rows *can* be read, but only if you look at the
window instead of the film. That is not what a demo does. The reference work solved
this by showing **two to four oversized elements** rather than a whole application,
and by letting the cursor be the one big thing that moves.

**Half the panel carries no information at all.** Address bar, status strip, command
pill and the `added / changed` column exist to make the window look like an app. At
14–18 px they cannot be read in motion, so they contribute only texture — the thing
the owner called decoration, and the standard calls clutter. Either they grow until
they are readable or they go.

## 3. The rules we adopt

**Type**
1. Anything a viewer must read is **≥80 design units** (40 px at 1080p); a title is
   **≥120**. Secondary marks are allowed below that only if they carry no words.
2. Max **30 characters** a line, max **3 lines** at once.
3. Text sits on a solid plate; 4.5:1 contrast.
4. A 15 px address bar or status line is removed, not shrunk.

**Content**
5. **One task per beat.** The window shows what the sentence is about and nothing else.
6. **2–4 oversized elements**, not a whole application — the 85 % pattern.
7. Every state change is caused by something visible: a click, a step landing, a row
   arriving. Nothing advances on its own clock.
8. A state holds at least **1 s per 13 characters** shown.

**Motion**
9. Arrivals **250–350 ms** ease-out, exits **200 ms** ease-in, never over **700 ms**.
10. Stagger children **60–100 ms**; motion originates from its trigger.
11. Overshoot only on a click release, and only a few pixels.

**Cursor** — 71 % of the reference films make it the main character
12. Drawn at **1.6×**, travel eased over **0.6 s**, hover **0.8 s** before the press.
13. Press: scale **0.88** over 80 ms, ripple out over 500 ms, small overshoot on release.

**Layout**
14. UI motion and camera motion never at once. Our camera is locked, so this holds.
15. Everything inside the title-safe 90 % box.

## 4. Where our film breaks these rules

| Rule | Our frame | Fault |
|---|---|---|
| 5 — one task | A whole browser with rows, search, tag and status, whatever the line says | shows everything every beat |
| 6 — oversized elements | 6 to 10 elements at 23 px and under | looks like a thumbnail of an app |
| 4 — no unreadable chrome | address bar, status sentence, command pill, `added/changed` | texture posing as information |
| 7 — caused change | `stageFor(kind, lineIndex)` swaps whole screens between lines | changes arrive on a line boundary, not from a click |
| 12 — cursor is the character | pointer appears only when a `query` exists, at 1× | it is punctuation, not a guide |
| 8 — dwell | stages swap at line boundaries; longer lines get no more time | a 6-word line and a 20-word line get the same state hold |
| 1 — title size | app title 29 px in a film whose captions are 44 px | the panel is quieter than the subtitles |

The last one is the clearest single number: **the subtitles are larger than anything
in the window.** Whatever the window is for, it currently ranks below the captions.

## 5. What I propose — for approval, not yet built

1. **Bigger window, fewer things.** Keep the window where it is (2700→3780) but show
   **two** rows, one field, and a title at **120/90 design units** (60/45 px on
   screen). Drop to two visible items so the type can double.
2. **Delete the unreadable chrome.** No address text (dots only), no status sentence,
   no `added/changed` column, no command pill in the body. Where a command matters it
   becomes a single 80-unit line, and only while it is spoken.
3. **One hero per beat.** The element the sentence is about — the new row, the search
   result, the failing check — is drawn at 1.3× the rest and arrives with a 300 ms
   ease-out plus a 60 ms stagger.
4. **Every change from a click.** The pointer travels (0.6 s), hovers over the target
   (0.8 s), presses (0.88 scale, ripple), and only then does the state change. If the
   line has no action in it, nothing in the window changes — it holds.
5. **Dwell follows the words.** A stage's hold is `max(1 s, characters/13)`, capped by
   the line, so short lines do not get furniture and long lines do not get flicker.

Items 1–5 are a rewrite of `buildview.mjs` and the two call sites in
`second_unit.mjs`. They do not touch the rest of the film. After approval I would do
chunk 0–30 s first, gate it, show it, and only then re-fit the later scenes.
