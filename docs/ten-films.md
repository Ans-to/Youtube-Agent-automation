# Ten one-minute films, each built for its own script

Ten scripts, ten renders, ten different structures. Every film below went from a
JSON brief to an upload-ready 720p file in one pipeline, with no hand-tuning of
the picture between them:

    brief -> narration (Kokoro) -> drawn frames (Canvas2D) -> mix -> master
          -> 720p web copy -> captions -> motion gate -> composition gate
          -> hold gate -> craft gate -> contact sheet -> review copy

The batch before this one passed every gate and was still wrong, and the note that
found it was blunt: **"you are using the same template for every video... every
video should have the template which is compatible with the script, not copy paste
one template on every video."** It was true. All ten scripts had been poured into
one skeleton, with only the words changed. No gate could see it, because every gate
measures a film against the rules, and a film can follow every rule and still look
like the last one.

So each brief now names the shape for each act, and only where the library offers
that shape for that act's situation:

* a **share of a whole** goes on bars (`bar-compare`), not on a rail;
* a **span of time divided up** goes on a rail (`budget-rail`);
* a **single figure with a unit** is counted (`count-up`) or dialled (`ring-gauge`);
* a **command** types itself (`code-typing`) or runs in a console (`command-console`);
* **parallel parts** stack (`stack-push`), **steps in order** list (`list-build`),
  **conditions** tile (`matrix-grid`);
* **one thing becoming two** forks (`fork-paths`), **two states side by side**
  compare (`compare-pair`);
* the verdict is stamped (`stamp-lockup`) or set as type (`kinetic-headline`).

## The ten

| film | length | craft | motion / static | arrangements, longest | loudness / peak | review / master |
|---|---|---|---|---|---|---|
| [Why Your Phone Dies at Twenty Percent](media/demos/battery-twenty.mp4) | 0:53.3 | 18/18 | 1.98 / 0.3% | 90, 1.5 s | -14.1 LUFS / -1.6 dBTP | 3.2 / 9.7 MB |
| [Ten Minutes a Day Beats a Weekend](media/demos/ten-minutes.mp4) | 0:55.9 | 18/18 | 1.99 / 0.4% | 81, 2.0 s | -14.2 LUFS / -1.6 dBTP | 3.3 / 10.2 MB |
| [Read a Nutrition Label in Twenty Seconds](media/demos/read-a-label.mp4) | 0:57.2 | 18/18 | 2.03 / 0.5% | 81, 3.0 s | -14.0 LUFS / -1.7 dBTP | 3.5 / 10.4 MB |
| [What Git Rebase Actually Does](media/demos/what-rebase-does.mp4) | 1:02.4 | 18/18 | 1.98 / 0.5% | 94, 3.0 s | -14.0 LUFS / -1.7 dBTP | 3.7 / 11.1 MB |
| [Why a Thirty Minute Meeting Feels Like Ninety](media/demos/meeting-length.mp4) | 1:00.6 | 18/18 | 1.98 / 0.2% | 87, 2.5 s | -14.2 LUFS / -1.7 dBTP | 3.7 / 11.1 MB |
| [Spot a Phishing Email in Five Seconds](media/demos/spot-phishing.mp4) | 0:57.1 | 18/18 | 2.01 / 0.3% | 85, 1.5 s | -14.2 LUFS / -1.7 dBTP | 3.4 / 10.3 MB |
| [What a Free App Actually Costs](media/demos/free-app-cost.mp4) | 1:04.5 | 18/18 | 1.97 / 0.6% | 92, 2.5 s | -14.1 LUFS / -1.6 dBTP | 3.8 / 11.3 MB |
| [How Compound Interest Actually Works](media/demos/compound-interest.mp4) | 0:56.7 | 18/18 | 2.00 / 0.2% | 76, 4.0 s | -14.1 LUFS / -1.7 dBTP | 3.4 / 10.3 MB |
| [Why Your Photos Look Flat](media/demos/flat-photos.mp4) | 0:57.2 | 18/18 | 2.03 / 0.3% | 78, 2.5 s | -14.2 LUFS / -1.5 dBTP | 3.5 / 10.9 MB |
| [How to Give Feedback That Lands](media/demos/feedback-that-lands.mp4) | 1:03.9 | 18/18 | 1.99 / 0.5% | 90, 2.5 s | -14.1 LUFS / -1.6 dBTP | 3.8 / 11.5 MB |

Every film: 1280x720, 30 fps, `+faststart`, H.264 + AAC 48 kHz stereo, true peak at
or below -1.0 dBFS. *Craft* is how many of the eighteen rules in
`video_studio/craft.py` passed. *Motion* is the mean frame-to-frame change and the
share of frames that barely change (floor 1.2, ceiling 15 %). *Arrangements* is how
many distinct layouts the film composes and how long it holds one (ceiling 12 s).
*Review / master* is the file in this directory against the CRF-21 master the
render writes.

## Which shape, where

| template | what it draws | films | which |
|---|---|---|---|
| `fork-paths` | one thing splitting into two outcomes | 10 | battery-twenty, ten-minutes, read-a-label, what-rebase-does, meeting-length, spot-phishing, free-app-cost, compound-interest, flat-photos, feedback-that-lands |
| `kinetic-headline` | one sentence of type that performs itself | 10 | battery-twenty, ten-minutes, read-a-label, what-rebase-does, meeting-length, spot-phishing, free-app-cost, compound-interest, flat-photos, feedback-that-lands |
| `compare-pair` | two states held against each other, with a divider | 9 | ten-minutes, read-a-label, what-rebase-does, meeting-length, spot-phishing, free-app-cost, compound-interest, flat-photos, feedback-that-lands |
| `count-up` | a figure the script claims, counted out under its label | 7 | battery-twenty, ten-minutes, what-rebase-does, spot-phishing, free-app-cost, compound-interest, feedback-that-lands |
| `list-build` | rows arriving one at a time, in reading order | 7 | ten-minutes, read-a-label, what-rebase-does, spot-phishing, compound-interest, flat-photos, feedback-that-lands |
| `stamp-lockup` | the closing phrase impressed on the frame | 7 | ten-minutes, read-a-label, what-rebase-does, meeting-length, free-app-cost, compound-interest, flat-photos |
| `bar-compare` | bars grown to their values, for a share of a whole | 6 | battery-twenty, read-a-label, spot-phishing, free-app-cost, flat-photos, feedback-that-lands |
| `matrix-grid` | tiles that fill in the order they are spoken | 5 | battery-twenty, what-rebase-does, meeting-length, free-app-cost, feedback-that-lands |
| `budget-rail` | one span divided into the parts it is spent on | 3 | ten-minutes, meeting-length, compound-interest |
| `ring-gauge` | a dial sweeping to a claimed number | 3 | read-a-label, meeting-length, flat-photos |
| `stack-push` | slabs stacking up, each arrival pushing the last | 2 | ten-minutes, free-app-cost |
| `code-typing` | the line itself, typed with a caret | 1 | what-rebase-does |
| `command-console` | a window that types the command and shows it finish | 1 | battery-twenty |

Not used: `sweep-rule` - sweep-rule is a rule crossing the frame - punctuation, not information. None of these ten scripts has a beat that quiet.

Thirteen of the library's fourteen shapes appear somewhere in the ten. Exactly 2 appear in all ten - `fork-paths`, `kinetic-headline` - and they are the film's grammar rather than its content: every script opens on a line of type and every script's thesis splits one thing into two outcomes. Everything else is per-script: 6 films use bars, 7 count a figure, 7 list, 5 tile, 7 stamp a verdict, and 3 divide a span.

Shapes that belong to a single film, because only that film argues that way: `code-typing` in `what-rebase-does`; `command-console` in `battery-twenty`.

## What this round changed

The previous delivery had ten bespoke scripts on one skeleton. Fixing that turned
up six faults, and every one of them was invisible to the gates:

1. **One act was being drawn several times.** A section longer than its template's
   window was cut into beats, and a template that draws a single object - a number,
   a dial, a fork, a pair - has no "next piece" to reveal, so every beat drew the
   object again from zero: a counter that counted to 20 twice, a fork that grew its
   branches and then re-grew them. Acts that name one of those templates are now
   **one picture, on the section's clock**, arriving once and holding while the
   narration finishes the thought. `storedRows` lets the library accept a hold
   longer than its window, and a hard cap (2.2x the window, never past 11 s)
   refuses an act that is really two pictures' worth of argument.
2. **Half of every comparison was invisible.** `compare-pair` drew its left panel
   as white at six percent, with a white hairline - a card for a dark film. On
   `#F7F9FA` paper that is nothing at all, so the film showed one card and one
   floating label. The library now takes **surface tokens from the palette**
   (`panelFill`, `panelStroke`, `paper`, `slab`, `tile`) instead of hard-coded
   whites, and a comparison of two names is drawn as **two centred bands** rather
   than two tall empty cards.
3. **Three decorations shared one corner.** A ghost chapter numeral, a section
   arc, and a four-bar meter all sat in the bottom-right, on top of each other.
   At 720p that read as a watermark under the diagram. Two are gone; progress lives
   in one place, the chapter rule across the top.
4. **The background was drawing objects.** The ambient layer put a ring, a rotated
   plate and a row of bars behind the artwork - shapes with no meaning, floating in
   the frame, which is exactly what makes a film look templated. It is now four
   things paper can do (a dot field, ruled hairlines, a tonal wash, a hatch), at 55 %
   of the previous weight, chosen per section so no two chapters share a silhouette.
5. **Secondary labels failed the film's own contrast rule.** Labels were drawn in
   `UI.faint` (`#9A9AA5`), which is 2.6:1 on paper - under the 4.5:1 the craft gate
   requires of everything else. They now take the palette's caption colour
   (5.1:1).
6. **The catalogue disagreed with itself.** Three templates claimed situations
   their situation's preference list did not contain, so the chooser could never
   have preferred them. The claims were corrected and `agents/motion_templates.json`
   regenerated from the code.

All six are guarded: `tests/test_brief_sync.py` fails if two briefs share a template
sequence, if an act is pinned to a shape the library does not offer for that
situation, or if the ten briefs use fewer than ten of the library's shapes;
`tools/check_motion_library.py` scans every motion source for camera shake;
`node video_studio/motion/library_cli.mjs --selfcheck` renders 38 template/region
cases and measures them.

## Regenerating any of them

```bash
python tools/preflight_brief.py --brief video_studio/briefs/<slug>.json   # ~40 s
python tools/brief_to_voice.py --brief video_studio/briefs/<slug>.json --out build/voice.json
python tools/render_authored_film.py \
  --script video_studio/films/from_brief.mjs \
  --script-args "--brief video_studio/briefs/<slug>.json" \
  --voice-script build/voice.json --voice-backend kokoro --voice am_michael \
  --out build/<slug> --width 1920 --height 1080 --delivery-height 720 --skip-4k
```

Or run the `Motion graphics studio` workflow on GitHub, which does the same thing
on a standard runner for nothing and uploads the master, the 720p copy, the
captions, the plan and the gate reports as artifacts.

The copies in `docs/media/demos` are 720p review encodes - same resolution, CRF 32
with the animation tuning - so that ten of them fit in a repository. The masters
the pipeline writes are 9-12 MB each, and the workflow uploads those.

## The ten, one by one

### Why Your Phone Dies at Twenty Percent

*You will know which of the three parts is lying before you buy anything.*

[watch](media/demos/battery-twenty.mp4) - [contact sheet](media/demos/battery-twenty-contact-sheet.jpg) - [captions](media/demos/battery-twenty.srt) - brief: `video_studio/briefs/battery-twenty.json`

A diagnosis. The fork is the wrong blame, the bars are where the error actually comes from, and the console hands over the one check that settles it.

**7 acts:** kinetic-headline *(4.4s)* > count-up *(4.9s)* > fork-paths *(10.1s)* > matrix-grid *(10.6s)* > bar-compare *(9.0s)* > command-console *(4.5s)* > kinetic-headline *(4.7s)*

The thumbnail line is **IT IS LYING**, drawn by the same design system as the film.

### Ten Minutes a Day Beats a Weekend

*You will practise in ten-minute blocks and keep what you learn.*

[watch](media/demos/ten-minutes.mp4) - [contact sheet](media/demos/ten-minutes-contact-sheet.jpg) - [captions](media/demos/ten-minutes.srt) - brief: `video_studio/briefs/ten-minutes.json`

A habit film. Parts that are parallel in kind stack, steps in order list, and the two plans are held against each other as two bands.

**8 acts:** kinetic-headline *(6.0s)* > count-up *(4.5s)* > compare-pair *(6.8s)* > stack-push *(8.1s)* > budget-rail *(8.6s)* > list-build *(5.5s)* > fork-paths *(6.5s)* > stamp-lockup *(4.0s)*

The thumbnail line is **TEN MINUTES**, drawn by the same design system as the film.

### Read a Nutrition Label in Twenty Seconds

*You will read the label the way it is designed not to be read.*

[watch](media/demos/read-a-label.mp4) - [contact sheet](media/demos/read-a-label-contact-sheet.jpg) - [captions](media/demos/read-a-label.srt) - brief: `video_studio/briefs/read-a-label.json`

A procedure. The stopwatch is a dial because the sentence is a duration, the pack is a pair because the sentence is a comparison, and the day is bars because the sentence divides a whole.

**8 acts:** kinetic-headline *(5.1s)* > ring-gauge *(7.3s)* > list-build *(10.4s)* > compare-pair *(6.6s)* > bar-compare *(9.2s)* > fork-paths *(4.0s)* > list-build *(4.4s)* > stamp-lockup *(4.2s)*

The thumbnail line is **READ THE BACK**, drawn by the same design system as the film.

### What Git Rebase Actually Does

*You will rebase your own branch without fear, and never a shared one.*

[watch](media/demos/what-rebase-does.mp4) - [contact sheet](media/demos/what-rebase-does-contact-sheet.jpg) - [captions](media/demos/what-rebase-does.srt) - brief: `video_studio/briefs/what-rebase-does.json`

The one film with a terminal: the command types itself, and the headcount of people who can safely run it is counted rather than dialled.

**8 acts:** kinetic-headline *(5.5s)* > code-typing *(8.3s)* > compare-pair *(8.6s)* > matrix-grid *(10.6s)* > count-up *(5.1s)* > fork-paths *(8.2s)* > list-build *(5.5s)* > stamp-lockup *(4.6s)*

The thumbnail line is **IT REWRITES**, drawn by the same design system as the film.

### Why a Thirty Minute Meeting Feels Like Ninety

*You will cut a meeting to the part that actually decides something.*

[watch](media/demos/meeting-length.mp4) - [contact sheet](media/demos/meeting-length-contact-sheet.jpg) - [captions](media/demos/meeting-length.srt) - brief: `video_studio/briefs/meeting-length.json`

An anatomy. The half hour is a dial, the twenty five minutes are a rail, and the three rules are tiles - three shapes for three kinds of claim.

**7 acts:** kinetic-headline *(4.4s)* > ring-gauge *(8.2s)* > budget-rail *(8.6s)* > matrix-grid *(13.6s)* > compare-pair *(9.6s)* > fork-paths *(7.8s)* > stamp-lockup *(3.5s)*

The thumbnail line is **CUT THE MIDDLE**, drawn by the same design system as the film.

### Spot a Phishing Email in Five Seconds

*You will check three things before you click anything.*

[watch](media/demos/spot-phishing.mp4) - [contact sheet](media/demos/spot-phishing-contact-sheet.jpg) - [captions](media/demos/spot-phishing.srt) - brief: `video_studio/briefs/spot-phishing.json`

A checklist under time pressure: five seconds counted, three checks listed, and the trick's parts on bars because forty/thirty/thirty is a share of one thing.

**7 acts:** kinetic-headline *(4.2s)* > count-up *(8.2s)* > list-build *(11.5s)* > compare-pair *(7.9s)* > bar-compare *(7.6s)* > fork-paths *(8.5s)* > kinetic-headline *(4.1s)*

The thumbnail line is **HOVER FIRST**, drawn by the same design system as the film.

### What a Free App Actually Costs

*You will see the three prices a free app charges, none of them money.*

[watch](media/demos/free-app-cost.mp4) - [contact sheet](media/demos/free-app-cost-contact-sheet.jpg) - [captions](media/demos/free-app-cost.srt) - brief: `video_studio/briefs/free-app-cost.json`

Economics. The three prices stack because they are parallel, the revenue is bars because it sums to a hundred, and the bill is counted because it is twelve hours.

**8 acts:** kinetic-headline *(7.9s)* > stack-push *(11.3s)* > bar-compare *(10.7s)* > count-up *(7.7s)* > compare-pair *(5.5s)* > fork-paths *(5.2s)* > matrix-grid *(5.0s)* > stamp-lockup *(5.2s)*

The thumbnail line is **YOU PAY**, drawn by the same design system as the film.

### How Compound Interest Actually Works

*You will see why the last ten years do more than the first twenty.*

[watch](media/demos/compound-interest.mp4) - [contact sheet](media/demos/compound-interest-contact-sheet.jpg) - [captions](media/demos/compound-interest.srt) - brief: `video_studio/briefs/compound-interest.json`

Arithmetic. Seven percent is a dial, the decades are a rail because they are time, and the rules are rows because they are steps in a habit.

**7 acts:** kinetic-headline *(4.8s)* > count-up *(8.1s)* > compare-pair *(8.3s)* > budget-rail *(10.8s)* > list-build *(9.9s)* > fork-paths *(4.0s)* > stamp-lockup *(5.6s)*

The thumbnail line is **NOT A LINE**, drawn by the same design system as the film.

### Why Your Photos Look Flat

*You will find the light before you find the subject.*

[watch](media/demos/flat-photos.mp4) - [contact sheet](media/demos/flat-photos-contact-sheet.jpg) - [captions](media/demos/flat-photos.srt) - brief: `video_studio/briefs/flat-photos.json`

A craft film. The three fixes list, the lights compare, the angle is a dial, and the layers are bars - thirty/forty/thirty is a composition, not a clock.

**7 acts:** kinetic-headline *(8.6s)* > list-build *(12.3s)* > compare-pair *(7.6s)* > ring-gauge *(8.1s)* > bar-compare *(6.6s)* > fork-paths *(4.8s)* > stamp-lockup *(4.1s)*

The thumbnail line is **FIND THE LIGHT**, drawn by the same design system as the film.

### How to Give Feedback That Lands

*You will say what you saw, what it cost, and what you want instead.*

[watch](media/demos/feedback-that-lands.mp4) - [contact sheet](media/demos/feedback-that-lands-contact-sheet.jpg) - [captions](media/demos/feedback-that-lands.srt) - brief: `video_studio/briefs/feedback-that-lands.json`

The order matters more than the parts, so the film lists the moves, holds judgement against observation, and bars the three shares.

**8 acts:** kinetic-headline *(7.8s)* > list-build *(8.1s)* > compare-pair *(8.6s)* > bar-compare *(9.1s)* > count-up *(8.6s)* > fork-paths *(6.1s)* > matrix-grid *(5.5s)* > kinetic-headline *(4.0s)*

The thumbnail line is **SAY WHAT YOU SAW**, drawn by the same design system as the film.

