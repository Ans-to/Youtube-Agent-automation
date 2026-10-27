# Nokia opening — pacing and visual revision

**Opening-only proof, not the requested finished 15-minute film or a release.**
This 34.9-second revision responds to feedback on the earlier opening: keep the
same Nokia motion-graphics format, but give its visuals and narration more
purposeful pacing. It has not had a complete human watch-and-listen review.

[Watch the revised opening](nokia-opening-pacing-pilot.mp4) ·
[Technical QA](nokia-opening-pacing-pilot.qc.json) ·
[Beat plan](../../../video_studio/films/nokia_semantic_pilot_plan.json) ·
[Estimated word cues](../../../video_studio/films/nokia_pacing_pilot_cues.json) ·
[Previous opening](nokia-opening-semantic-pilot.md)

## The pacing pass

The original house typography, palette, product builders, composition and
cinematic finish remain. Every picture is drawn programmatically as motion
graphics; there are no photographs, AI-generated backgrounds or animated
stills. The existing opening narration and music are reused without re-encoding
or changing their content. The on-screen headlines are editorial graphics, not
a subtitle track.

| Approximate time | Narration idea | Intended visual action |
|---|---|---|
| 0:00–0:05.73 | Company and people around the world | World connections grow; a symbolic group holding phones assembles as the wording develops. The icons do not represent a measured count. |
| 0:05.73–0:08.77 | Carrying its products in pockets | A drawn handset moves into a fabric pocket. |
| 0:08.77–0:13.93 | The company was Nokia | Many drawn phones gather; the name and a central handset resolve into view. |
| 0:13.93–0:19.63 | Nokia led the market | Proportionally scaled 2008 all-phone vendor bars build, then focus on Nokia and Samsung, the two largest individual vendors in that comparison. |
| 0:19.63–0:27.57 | Former leader under pressure | Labeled annual all-phone shares build on an elapsed-year axis, then resolve to the 2008/2013 endpoints. |
| 0:27.57–0:31.67 | A new smartphone generation | Three drawn smartphones arrive and their app screens build. |
| 0:31.67–0:34.90 | Touchscreens replaced buttons | A key press, directional transition, screen touch and opening interface illustrate the change in interaction. |

The word cue manifest is a planning aid, based on approximate PocketSphinx
forced alignment and the existing shot clock. It is **not** a verified
word-by-word synchronization: a person still needs to watch and listen to the
encoded file. The narration's “billions of people” needs factual substantiation;
“touchscreens replaced buttons” is an editorial simplification, not a claim that
all physical buttons disappeared.

The chart uses Gartner's worldwide **all-mobile-phone sales**, not
smartphone-only or operating-system shares. The comparison gives Nokia 38.6%,
Samsung 16.3%, Motorola 8.7%, LG 8.4%, Sony Ericsson 7.6%, and the aggregate
“Others” 20.3% in 2008 ([Gartner 2008–09 table](https://www.palminfocenter.com/news/6579/gartner-reports-worldwide-mobile-phone-sales-for-2009/)).
The Nokia series shows 38.6% in 2008, 36.4% in 2009, 23.8% in 2011, 19.1% in
2012, and 13.9% in 2013 ([2009](https://www.palminfocenter.com/news/6579/gartner-reports-worldwide-mobile-phone-sales-for-2009/),
[2011–12](https://www.design-reuse.com/news/202523334-gartner-says-worldwide-mobile-phone-sales-declined-1-7-percent-in-2012-/),
[2013](https://www.gartner.com/en/newsroom/press-releases/2014-02-13-gartner-says-annual-smartphone-sales-surpassed-sales-of-feature-phones-for-the-first-time-in-2013)).
The 2009–2011 gap is twice the 2008–2009 gap on the series axis; the line and
intermediate years fade before the endpoints move into a two-bar comparison.
These source checks cover the plotted numbers, not the entire script.

## Checks on this exact encoded file

- H.264, **1920×1080**, 30 fps, **1,047 decoded video frames**, 34.900 seconds;
  stereo AAC at 48 kHz. SHA-256:
  `236c9f48f57dbe2f83a3a35389b68020126f182f77a9d111f427a6e2a00e82e4`.
- All 1,047 decoded video presentation timestamps were spaced at 1/30 second
  within a microsecond. This checks encoded cadence, not subjective smoothness.
- Strict technical QA **passed** its configured heuristics: no black interval
  of at least 0.2 s, FFmpeg freeze of at least 3 s, or silence of at least
  1.5 s; the longest content-based near-static span was 1.0 s, with no span
  *longer* than the 1.0 s limit. The same check flagged eight longer spans in
  the prior opening, with a longest of 7.5 s. This is not a semantic or
  aesthetic approval.
- The encoded mixed audio measured **−14.5 LUFS integrated** and **−3.0 dBTP**.
  The copied AAC packets have the same SHA-256 as the prior opening when
  extracted as ADTS: `6bc1bb191b2ce01893aae3f4fb2d938a11beeded0b8ab06e78e6b6d77781ffbf`.
  Separate narration/music levels and intelligibility have **not** been
  independently verified for this excerpt. No caption/subtitle track is present.
- The full automated suite passed **1,585 tests**, with one skip. The cue and
  frame tests check structure and picture change; they cannot establish the
  meaning of an image, audible word timing, historical truth, or mix quality.

The shortened 72-shot script is still a proposal, not author-approved. The
rejected full-length draft has not been repaired by this opening-only revision.
Full-film production, factual checks, per-cue visual/semantic review,
watch-and-listen synchronization, narration/music balance, captions if added,
and final-ending review remain outstanding.

## Reproduce this opening

From the repository root with the studio Node dependencies, FFmpeg and FFprobe
installed:

```sh
node video_studio/films/nokia_pacing_pilot.mjs --validate
set -o pipefail
node video_studio/films/nokia_pacing_pilot.mjs --pipe | \
  ffmpeg -f rawvideo -pix_fmt rgba -s 1920x1080 -framerate 30 -i pipe:0 \
    -i docs/media/nokia/nokia-opening-semantic-pilot.mp4 \
    -map 0:v:0 -map 1:a:0 -map_metadata -1 -c:v libx264 -preset medium \
    -crf 18 -pix_fmt yuv420p -fps_mode passthrough -c:a copy \
    -movflags +faststart -y docs/media/nokia/nokia-opening-pacing-pilot.mp4
python video_studio/quality_audit.py docs/media/nokia/nokia-opening-pacing-pilot.mp4 \
  --strict --fail-on-still --report docs/media/nokia/nokia-opening-pacing-pilot.qc.json
```

The render relies on the complete 1,047-frame raw stream and copies the existing
opening audio. Avoid adding `-shortest` without rechecking the exact encoded
frame timestamps: one intermediate mux dropped the penultimate video frame.
