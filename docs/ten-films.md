# Ten one-minute films, end to end

Ten scripts, ten renders, no hand-tuning of the picture. This is the run that
answers a different question from the earlier rounds: not *can the studio make a
good film*, but *does it make ten different good films from ten different
scripts, without a person fixing anything between them*.

Every film below went through the same pipeline, on the same night, from a JSON
brief:

    brief -> narration (Kokoro) -> drawn frames (Canvas2D) -> mix -> master
          -> 720p web copy -> captions -> motion gate -> composition gate
          -> hold gate -> craft gate -> upload pack -> thumbnail

## The ten

| film | length | craft | motion / static | arrangements, longest | loudness | review / master |
|---|---|---|---|---|---|---|
| [Why Your Phone Dies at Twenty Percent](media/demos/battery-twenty.mp4) | 1:08.8 | 18/18 | 1.99 / 0.2% | 109, 2.0 s | -14.1 LUFS | 4.4 / 12.8 MB |
| [Ten Minutes a Day Beats a Weekend](media/demos/ten-minutes.mp4) | 1:00.6 | 18/18 | 2.01 / 0.4% | 84, 2.0 s | -14.3 LUFS | 3.8 / 11.0 MB |
| [Read a Nutrition Label in Twenty Seconds](media/demos/read-a-label.mp4) | 0:57.2 | 18/18 | 2.05 / 0.3% | 74, 3.5 s | -14.0 LUFS | 3.7 / 10.6 MB |
| [What Git Rebase Actually Does](media/demos/what-rebase-does.mp4) | 1:02.4 | 18/18 | 2.00 / 0.4% | 94, 2.5 s | -14.0 LUFS | 4.0 / 11.5 MB |
| [Why a Thirty Minute Meeting Feels Like Ninety](media/demos/meeting-length.mp4) | 1:07.7 | 18/18 | 2.01 / 0.3% | 98, 2.5 s | -14.2 LUFS | 4.3 / 12.5 MB |
| [Spot a Phishing Email in Five Seconds](media/demos/spot-phishing.mp4) | 1:03.5 | 18/18 | 2.03 / 0.3% | 95, 1.5 s | -14.2 LUFS | 4.1 / 11.8 MB |
| [What a Free App Actually Costs](media/demos/free-app-cost.mp4) | 1:04.5 | 18/18 | 2.05 / 0.4% | 88, 3.5 s | -14.1 LUFS | 4.1 / 12.1 MB |
| [How Compound Interest Actually Works](media/demos/compound-interest.mp4) | 1:02.8 | 18/18 | 2.03 / 0.3% | 89, 2.5 s | -14.1 LUFS | 4.0 / 11.6 MB |
| [Why Your Photos Look Flat](media/demos/flat-photos.mp4) | 1:03.7 | 18/18 | 2.04 / 0.3% | 92, 2.5 s | -14.2 LUFS | 4.1 / 11.9 MB |
| [How to Give Feedback That Lands](media/demos/feedback-that-lands.mp4) | 1:04.3 | 18/18 | 2.02 / 0.4% | 101, 3.0 s | -14.1 LUFS | 4.1 / 11.8 MB |

Every film: 1280x720, 30 fps, `+faststart`, H.264 High + AAC 48 kHz stereo,
true peak at or below -1.0 dBFS. *Craft* is the count of the eighteen rules in
`video_studio/craft.py` that passed. *Motion* is the mean frame-to-frame change
and the share of frames that barely change (floor 1.2, ceiling 15%). *Arrangements*
is how many distinct layouts the film composes and how long it holds one (ceiling
12 s). *Review / master* is the size of the file in this directory against the
size of the CRF-21 master the render actually writes - the review copy is the same
resolution, re-encoded at CRF 32 with the animation tuning so that ten films fit
in a repository.

## What went wrong, and what changed because of it

The first batch pass was a failure, and it is worth writing down, because none of
these were content problems - they were the pipeline being unable to tell a person
that their script could not be published until after it had spent the money.

1. **Six of ten scripts broke the caption band.** A spoken line that wraps past two
   lines of forty-two characters cannot be captioned, and `from_brief.mjs` threw
   after the voice had already been synthesised. The fix was not to widen the band:
   the scripts now break at sentence boundaries, which is also better to listen to.
   `tests/test_brief_sync.py` grew a test that reads the band's width straight out
   of the film script, so the rule and the check cannot drift apart.
2. **Three films left the screen unchanged for more than eight seconds** between
   changes. The cause is always the same: one long spoken line. Splitting it at a
   full stop fixes the cadence and gives the voice somewhere to breathe.
3. **One film's last chapter was 2.41 s**, and YouTube's own rules put the floor at
   2.5 s, so the chapter would not publish. The outro got one more sentence.
4. **Two films were too evenly paced to have a hook.** `sd/mean` of cue length is a
   blunt measurement of rhythm, but it is the right one: a film where every beat is
   four seconds long has no punchline. Both were rebuilt around a very short beat
   beside a long one.
5. **`tools/preflight_brief.py` exists because of all of the above.** It runs the
   cheap half of the pipeline - narration, captions, craft rules - and stops. A
   script that cannot pass now fails in about forty seconds instead of four
   minutes, and `motion-studio.yml` runs it before it draws a frame. The batch that
   taught us this cost nine minutes of wasted render; the next one will not.

One more thing the batch caught: a preflight that reuses a cached voice script can
report a pass for text that has already been rewritten. It no longer reuses one.

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
with the animation tuning - so that ten of them fit in a repository. The 720p CRF 21
masters the pipeline writes are 10-13 MB each; the workflow uploads those.

## The ten, one by one

### Why Your Phone Dies at Twenty Percent

*You will know which of the three parts is lying before you buy anything.*

[watch](media/demos/battery-twenty.mp4) - [contact sheet](media/demos/battery-twenty-contact-sheet.jpg) - [captions](media/demos/battery-twenty.srt) + brief in video_studio/briefs

The hook names a thing everyone has felt, then the film spends its whole budget separating the three possible causes and gives one of them 45% of the error.

The thumbnail line is **IT IS LYING**, drawn by the same design system as the film (see `video_studio/films/thumbnail.mjs`).

### Ten Minutes a Day Beats a Weekend

*You will practise in ten-minute blocks and keep what you learn.*

[watch](media/demos/ten-minutes.mp4) - [contact sheet](media/demos/ten-minutes-contact-sheet.jpg) - [captions](media/demos/ten-minutes.srt) + brief in video_studio/briefs

A claims film: one number, one comparison, one stack. The rail is the only bar in the set that is about time rather than money.

The thumbnail line is **TEN MINUTES**, drawn by the same design system as the film (see `video_studio/films/thumbnail.mjs`).

### Read a Nutrition Label in Twenty Seconds

*You will read the label the way it is designed not to be read.*

[watch](media/demos/read-a-label.mp4) - [contact sheet](media/demos/read-a-label-contact-sheet.jpg) - [captions](media/demos/read-a-label.srt) + brief in video_studio/briefs

Eight sections, the tightest of the ten. Every rule is a physical move on a pack, so the matrix grid holds instructions rather than ideas.

The thumbnail line is **READ THE BACK**, drawn by the same design system as the film (see `video_studio/films/thumbnail.mjs`).

### What Git Rebase Actually Does

*You will rebase your own branch without fear, and never a shared one.*

[watch](media/demos/what-rebase-does.mp4) - [contact sheet](media/demos/what-rebase-does-contact-sheet.jpg) - [captions](media/demos/what-rebase-does.srt) + brief in video_studio/briefs

The command-console film. The one place a real terminal line is drawn, and the verdict is drawn in two colours, not one.

The thumbnail line is **IT REWRITES**, drawn by the same design system as the film (see `video_studio/films/thumbnail.mjs`).

### Why a Thirty Minute Meeting Feels Like Ninety

*You will cut a meeting to the part that actually decides something.*

[watch](media/demos/meeting-length.mp4) - [contact sheet](media/demos/meeting-length-contact-sheet.jpg) - [captions](media/demos/meeting-length.srt) + brief in video_studio/briefs

Built on a 30-minute clock: the rail splits the half hour into context, discussion and decision, and the payoff asks you to cut the middle.

The thumbnail line is **CUT THE MIDDLE**, drawn by the same design system as the film (see `video_studio/films/thumbnail.mjs`).

### Spot a Phishing Email in Five Seconds

*You will check three things before you click anything.*

[watch](media/demos/spot-phishing.mp4) - [contact sheet](media/demos/spot-phishing-contact-sheet.jpg) - [captions](media/demos/spot-phishing.srt) + brief in video_studio/briefs

The fastest read. One beat is four words long, the next is five seconds, which is what the pacing rule actually measures.

The thumbnail line is **HOVER FIRST**, drawn by the same design system as the film (see `video_studio/films/thumbnail.mjs`).

### What a Free App Actually Costs

*You will see the three prices a free app charges, none of them money.*

[watch](media/demos/free-app-cost.mp4) - [contact sheet](media/demos/free-app-cost-contact-sheet.jpg) - [captions](media/demos/free-app-cost.srt) + brief in video_studio/briefs

The film with the oldest trick in it: three prices, none of them money, and a 12-hour bill drawn on a gauge.

The thumbnail line is **YOU PAY**, drawn by the same design system as the film (see `video_studio/films/thumbnail.mjs`).

### How Compound Interest Actually Works

*You will see why the last ten years do more than the first twenty.*

[watch](media/demos/compound-interest.mp4) - [contact sheet](media/demos/compound-interest-contact-sheet.jpg) - [captions](media/demos/compound-interest.srt) + brief in video_studio/briefs

Twelve lines, and the only film whose shape argument is the curve itself rather than a bar.

The thumbnail line is **NOT A LINE**, drawn by the same design system as the film (see `video_studio/films/thumbnail.mjs`).

### Why Your Photos Look Flat

*You will find the light before you find the subject.*

[watch](media/demos/flat-photos.mp4) - [contact sheet](media/demos/flat-photos-contact-sheet.jpg) - [captions](media/demos/flat-photos.srt) + brief in video_studio/briefs

Light is the subject, so the picture argues with the narration: flat light erases, raking light draws.

The thumbnail line is **FIND THE LIGHT**, drawn by the same design system as the film (see `video_studio/films/thumbnail.mjs`).

### How to Give Feedback That Lands

*You will say what you saw, what it cost, and what you want instead.*

[watch](media/demos/feedback-that-lands.mp4) - [contact sheet](media/demos/feedback-that-lands-contact-sheet.jpg) - [captions](media/demos/feedback-that-lands.srt) + brief in video_studio/briefs

The quietest film. Its rail is the only one that ends on a question rather than a number.

The thumbnail line is **SAY WHAT YOU SAW**, drawn by the same design system as the film (see `video_studio/films/thumbnail.mjs`).

