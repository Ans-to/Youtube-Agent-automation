# Ten one-minute films, each built for its own script

Ten scripts, ten renders, ten different structures. The point of the page is not
that the studio can make ten films - it can - but that each film argues the way
its own script argues.

The first batch passed every gate and was still wrong: **"you are using the same
template for every video... every video is should have the template which is
compatible with the script, not copy paste one template on every video."** That
was accurate. Ten scripts had been poured into one skeleton, and every gate
passed, because a gate measures a film against the rules and a film can follow
every rule while looking like the last one.

So the acts were rebuilt from each argument. This page is generated from the
briefs, the plans and the renders that sit in this repository -
`python tools/ten_films_doc.py` - so it cannot drift from them. Of the
11 films here, 11 have their own act sequence
(0 share one with another film).

## The ten

| film | length | acts | craft | review copy |
|---|---|---|---|---|
| [Why Your Phone Dies at Twenty Percent](media/demos/battery-twenty.mp4) | 53.3 s | 7 | 18/18 | [mp4](media/demos/battery-twenty.mp4) - 9.7 MB |
| [How Compound Interest Actually Works](media/demos/compound-interest.mp4) | - | 0 | - | [mp4](media/demos/compound-interest.mp4) - 3.4 MB |
| [How to Give Feedback That Lands](media/demos/feedback-that-lands.mp4) | - | 0 | - | [mp4](media/demos/feedback-that-lands.mp4) - 3.8 MB |
| [Why Your Photos Look Flat](media/demos/flat-photos.mp4) | - | 0 | - | [mp4](media/demos/flat-photos.mp4) - 3.5 MB |
| [What a Free App Actually Costs](media/demos/free-app-cost.mp4) | - | 0 | - | [mp4](media/demos/free-app-cost.mp4) - 3.8 MB |
| [Why a Thirty Minute Meeting Feels Like Ninety](media/demos/meeting-length.mp4) | - | 0 | - | [mp4](media/demos/meeting-length.mp4) - 3.7 MB |
| [Read a Nutrition Label in Twenty Seconds](media/demos/read-a-label.mp4) | - | 0 | - | [mp4](media/demos/read-a-label.mp4) - 3.5 MB |
| [How to Review AI-Written Code in 60 Seconds](media/demos/review-ai-code.mp4) | - | 0 | - | not rendered yet |
| [Spot a Phishing Email in Five Seconds](media/demos/spot-phishing.mp4) | - | 0 | - | [mp4](media/demos/spot-phishing.mp4) - 3.4 MB |
| [Ten Minutes a Day Beats a Weekend](media/demos/ten-minutes.mp4) | - | 0 | - | [mp4](media/demos/ten-minutes.mp4) - 3.3 MB |
| [What Git Rebase Actually Does](media/demos/what-rebase-does.mp4) | - | 0 | - | [mp4](media/demos/what-rebase-does.mp4) - 3.7 MB |

Every film is 1280x720, 30 fps, H.264 High with AAC at 48 kHz, `+faststart`, and
loudness-normalised for YouTube. *Craft* is how many of the eighteen rules in
`video_studio/craft.py` pass; a dash means the report has not been published yet.

## The vocabulary

Two things make a picture: what is drawn, and how it lands. The studio has both,
and each is chosen by the beat, not by habit.

| picture | what it draws | films | which |
|---|---|---|---|
| `bar-compare` | bars grown to their values, for a share of a whole | 1 | battery-twenty |
| `command-console` | a window that types a command and shows it finish | 1 | battery-twenty |
| `count-up` | a figure the script claims, counted out under its label | 1 | battery-twenty |
| `fork-paths` | one thing splitting into two outcomes | 1 | battery-twenty |
| `kinetic-headline` | one spoken sentence, set as type that performs itself | 1 | battery-twenty |
| `matrix-grid` | tiles that fill in the order they are spoken | 1 | battery-twenty |
| `stamp-lockup` | the closing phrase impressed on the frame | 1 | battery-twenty |

| entrance | how the picture lands | films |
|---|---|---|
| `assembly` | two halves arriving from opposite sides and meeting | 1 |
| `draw-on` | drafted in from one side, a pen line at the edge | 1 |
| `iris` | a circle opening on the subject | 1 |
| `scan` | a scanner band passes and the figure lands behind it | 1 |
| `slit-scan` | vertical strips snapping into place in waves | 1 |
| `squash` | landing with squash and stretch | 1 |
| `whip` | sliding in with a short motion trail | 1 |

The entrances are ports of motion basics from
[howardc38/motion-fx-lab](https://github.com/howardc38/motion-fx-lab) (0BSD):
stroke reveals, clip wipes, iris openings, slit-scan strips, press and squash,
exploded assembly. `FITS` in `video_studio/motion/fxlab.mjs` records which
entrance each picture can carry, so a highlighter band is never drawn across a
dial, and an act never lands the same way as the act before it.

## How these were rendered

On GitHub, by a standard `ubuntu-24.04` runner, for nothing:
`.github/workflows/ten-films.yml` renders every brief in `video_studio/briefs` as
its own matrix job, runs the preflight and the craft gate on each, and then a
publish job commits the 720p copies, the captions and the contact sheets into
`docs/media/demos`. The renders are committed because a render that only exists
in a temporary directory is not a deliverable - that mistake cost a full batch.

To re-render one film, either run that workflow with `films` set to the slug, or
do it locally:

```bash
python tools/preflight_brief.py --brief video_studio/briefs/<slug>.json
python tools/brief_to_voice.py --brief video_studio/briefs/<slug>.json --out build/voice.json
python tools/render_authored_film.py \
  --script video_studio/films/from_brief.mjs \
  --script-args "--brief video_studio/briefs/<slug>.json" \
  --voice-script build/voice.json --voice-backend kokoro --voice am_michael \
  --out build/<slug> --width 1920 --height 1080 --delivery-height 720 --skip-4k
```

## The films, one by one

### Why Your Phone Dies at Twenty Percent

*You will know which of the three parts is lying before you buy anything.*

[watch](media/demos/battery-twenty.mp4) - [captions](media/demos/battery-twenty.srt) - [contact sheet](media/demos/battery-twenty-contact-sheet.jpg) - brief `video_studio/briefs/battery-twenty.json`

| act | picture | entrance | length |
|---|---|---|---|
| open | `kinetic-headline` | `whip` | 4.4 s |
| number | `count-up` | `squash` | 4.9 s |
| causes | `matrix-grid` | `slit-scan` | 10.6 s |
| error | `bar-compare` | `draw-on` | 9.0 s |
| lie | `fork-paths` | `assembly` | 10.1 s |
| check | `command-console` | `scan` | 4.5 s |
| close | `stamp-lockup` | `iris` | 4.7 s |

### How Compound Interest Actually Works

*You will see why the last ten years do more than the first twenty.*

[watch](media/demos/compound-interest.mp4) - [captions](media/demos/compound-interest.srt) - [contact sheet](media/demos/compound-interest-contact-sheet.jpg) - brief `video_studio/briefs/compound-interest.json`

*This film has not been rendered, so there is no schedule yet.*

### How to Give Feedback That Lands

*You will say what you saw, what it cost, and what you want instead.*

[watch](media/demos/feedback-that-lands.mp4) - [captions](media/demos/feedback-that-lands.srt) - [contact sheet](media/demos/feedback-that-lands-contact-sheet.jpg) - brief `video_studio/briefs/feedback-that-lands.json`

*This film has not been rendered, so there is no schedule yet.*

### Why Your Photos Look Flat

*You will find the light before you find the subject.*

[watch](media/demos/flat-photos.mp4) - [captions](media/demos/flat-photos.srt) - [contact sheet](media/demos/flat-photos-contact-sheet.jpg) - brief `video_studio/briefs/flat-photos.json`

*This film has not been rendered, so there is no schedule yet.*

### What a Free App Actually Costs

*You will see the three prices a free app charges, none of them money.*

[watch](media/demos/free-app-cost.mp4) - [captions](media/demos/free-app-cost.srt) - [contact sheet](media/demos/free-app-cost-contact-sheet.jpg) - brief `video_studio/briefs/free-app-cost.json`

*This film has not been rendered, so there is no schedule yet.*

### Why a Thirty Minute Meeting Feels Like Ninety

*You will cut a meeting to the part that actually decides something.*

[watch](media/demos/meeting-length.mp4) - [captions](media/demos/meeting-length.srt) - [contact sheet](media/demos/meeting-length-contact-sheet.jpg) - brief `video_studio/briefs/meeting-length.json`

*This film has not been rendered, so there is no schedule yet.*

### Read a Nutrition Label in Twenty Seconds

*You will read the label the way it is designed not to be read.*

[watch](media/demos/read-a-label.mp4) - [captions](media/demos/read-a-label.srt) - [contact sheet](media/demos/read-a-label-contact-sheet.jpg) - brief `video_studio/briefs/read-a-label.json`

*This film has not been rendered, so there is no schedule yet.*

### How to Review AI-Written Code in 60 Seconds

*You will review AI-written code in about a minute, before it ships.*

[watch](media/demos/review-ai-code.mp4) - [captions](media/demos/review-ai-code.srt) - [contact sheet](media/demos/review-ai-code-contact-sheet.jpg) - brief `video_studio/briefs/review-ai-code.json`

*This film has not been rendered, so there is no schedule yet.*

### Spot a Phishing Email in Five Seconds

*You will check three things before you click anything.*

[watch](media/demos/spot-phishing.mp4) - [captions](media/demos/spot-phishing.srt) - [contact sheet](media/demos/spot-phishing-contact-sheet.jpg) - brief `video_studio/briefs/spot-phishing.json`

*This film has not been rendered, so there is no schedule yet.*

### Ten Minutes a Day Beats a Weekend

*You will practise in ten-minute blocks and keep what you learn.*

[watch](media/demos/ten-minutes.mp4) - [captions](media/demos/ten-minutes.srt) - [contact sheet](media/demos/ten-minutes-contact-sheet.jpg) - brief `video_studio/briefs/ten-minutes.json`

*This film has not been rendered, so there is no schedule yet.*

### What Git Rebase Actually Does

*You will rebase your own branch without fear, and never a shared one.*

[watch](media/demos/what-rebase-does.mp4) - [captions](media/demos/what-rebase-does.srt) - [contact sheet](media/demos/what-rebase-does-contact-sheet.jpg) - brief `video_studio/briefs/what-rebase-does.json`

*This film has not been rendered, so there is no schedule yet.*
