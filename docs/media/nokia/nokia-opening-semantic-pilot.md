# Nokia opening — semantic/style pilot

**Opening proof only, not a finished or approved 15-minute video.** This
34.9-second excerpt is a test of correcting visual meaning while retaining the
original Nokia film's motion-graphics format. The previous full-length motion
revision was rejected. This pilot itself still fails strict motion QA and has not
received a complete watch-and-listen review.

[Watch the opening pilot](nokia-opening-semantic-pilot.mp4) ·
[Technical QA report](nokia-opening-semantic-pilot.qc.json) ·
[Beat plan](../../../video_studio/films/nokia_semantic_pilot_plan.json)

## What changed

The picture uses the earlier Nokia film's drawing builders, type, palette,
product illustrations and optics. All visuals are code-drawn motion graphics;
there are no photographs, generated-image backgrounds or animated stills. The
opening narration and suspenseful music are reused from the rejected draft,
with a fade at the end of this standalone excerpt. They are not a new final mix.

| Approx. time | Narration idea | Intended motion-graphics meaning |
|---|---|---|
| 0:00–0:05.73 | A company reaching people around the world | A world map and connecting paths |
| 0:05.73–0:08.77 | People carry its products in their pockets | A drawn phone moves into a pocket |
| 0:08.77–0:13.93 | The company was Nokia | Its name appears |
| 0:13.93–0:19.63 | Nokia led the mobile-phone market | Labeled 2008 all-phone market comparison |
| 0:19.63–0:27.57 | The former leader came under pressure | Labeled decline in Nokia all-phone market share |
| 0:27.57–0:31.67 | A new smartphone generation arrived | A drawn smartphone appears |
| 0:31.67–0:34.90 | Touchscreens replaced buttons | Drawn keypad and touchscreen phones are compared |

The pocket cut starts at 5.733 seconds. Approximate word-onset estimates were
5.76 seconds from PocketSphinx forced alignment and 5.84 seconds from the Kokoro
model's predicted durations. They are estimates, **not** a verified listening
alignment. A named reviewer must watch and listen to the actual video to assess
whether the intended meanings and timing are achieved. The quoted on-screen
wording about touchscreens is an editorial simplification that still needs a
factual review; physical buttons did not disappear from every phone.

The market graphics distinguish worldwide *all-mobile-phone sales* from
smartphone-only/OS shares. Gartner's reported 2008 figures were Nokia 38.6%,
Samsung 16.3%, Motorola 8.7%, LG 8.4%, Sony Ericsson 7.6%, and others 20.3%
([Gartner 2008–09 table](https://www.palminfocenter.com/news/6579/gartner-reports-worldwide-mobile-phone-sales-for-2009/)).
2008's 38.6% is higher than 2007's 37.8%, so the chart uses 2008 for the
narrated peak. For Nokia, the plotted 2009, 2011, 2012, and 2013 shares are
respectively 36.4%, 23.8%, 19.1%, and 13.9% ([2009](https://www.palminfocenter.com/news/6579/gartner-reports-worldwide-mobile-phone-sales-for-2009/),
[2011–12](https://www.design-reuse.com/news/202523334-gartner-says-worldwide-mobile-phone-sales-declined-1-7-percent-in-2012-/),
[2013](https://www.gartner.com/en/newsroom/press-releases/2014-02-13-gartner-says-annual-smartphone-sales-surpassed-sales-of-feature-phones-for-the-first-time-in-2013)).
This check covers these plotted figures only, not every claim in the script.

## Checks and known problems

- Exact file: 1920×1080 H.264, 30 fps, 1,047 frames, 34.900 seconds, stereo AAC;
  SHA-256 `50946172ce43ea8bf345ec7c801d5315a01b90a763c87e9d51c5e3150c397127`.
- **Strict technical QA failed**: the content-based repeat check flagged eight
  near-static spans, longest 7.5 seconds at 0:20. The sampled animation is not
  sufficient for the existing release rule. It is not proof of encoder lag;
  meaningful motion and timing must be improved rather than adding noise or
  lowering the threshold. The same audit found no black, silence or FFmpeg
  freeze-detector events at its configured thresholds.
- This short excerpt's encoded audio measured **−14.5 LUFS integrated** and
  **−3.0 dBTP**. These figures do not measure intelligibility or establish the
  mix of a future full film. No caption track is included.
- The seven-row plan passes structural coverage tests. That cannot establish
  semantic correctness, actual word timing, historical truth or human approval.
- The previously published full draft has a separate defective financial-amount
  recording. A [corrected replacement and draft clocks](audio-repair-draft/README.md)
  were prepared and the scratch mix rebuilt, but the replacement is **not** in
  the old MP4 or this opening excerpt. Its listening review and a new
  synchronized picture remain outstanding.

The shortened 72-shot script is still an unapproved proposal. Completing the
remaining film, correcting any semantic drift, resolving the motion-QA failures,
and performing the fact, listening, visual, mix and final-ending checks remain
release blockers. See [the release workflow](nokia-release-audit.md).
