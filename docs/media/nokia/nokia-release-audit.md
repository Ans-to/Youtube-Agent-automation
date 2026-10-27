# Nokia empire: music and release audit

## Status and editorial blocker

The existing empire edit has 3,116 verbatim words across 13 scenes and runs
**28:35** on its measured shot clock. The requested final is approximately
15 minutes; this workflow defines that as **14:00–16:00**. Keeping the entire
existing script at its present pace cannot meet the target. An author-approved
cut/rewrite, re-recording, retiming and final render are required; do not simply
speed up or truncate the voice. `docs/media/nokia/nokia-film.mp4` is a separate
7:51.5 film, not the 28:35 empire cut and not a 15-minute final.

A [15:35.6 review video](nokia-15-minute-review.mp4) and [proposed 72-shot
script](nokia-15-minute-script-draft.md) are available for author review. The cut
selects 1,688 words verbatim, in order, from the original narration and proposes
a replacement title; it is not author approval of the omissions or title. A
[partial research ledger](nokia-15-minute-facts-draft.json) records selected
claims and unresolved issues; it does not cover every claim. The [review-cut
report](nokia-15-minute-review.md) records a **failed** strict QA (held pictures)
and the remaining human and editorial checks.

No final 15-minute empire film, complete fact-check, listening/visual review,
approval or upload has been completed. The profile and generated score are
production tools; they are not evidence that these tasks happened.

A preliminary FFmpeg check of the **separate** 7:51.5 `nokia-film.mp4` measured
−13.4 LUFS and −1.3 dBTP and found no black or silence intervals at the default
thresholds. Its strict technical QA **failed** on repeated held pictures (the
longest was 10.4 seconds). This is not a review or approval of the empire edit.

The supplied title's "$300 billion" valuation also needs a dated, defensible
source before release: published accounts differ on the peak value and currency
(e.g. [CNBC's account of over $250bn](https://www.cnbc.com/2013/09/17/nokias-failure-no-flexibility-in-us-emerging-markets.html)
and the [Financial Times' €286bn estimate](https://www.ft.com/content/0a07cbc3-dac4-4b89-9f26-038deb833060)).
Resolve the exact date, metric and exchange rate with primary data, or request
an author-approved title change; do not silently treat the figure as verified.

## Five music sections

`video_studio/films/nokia_music.json` maps the requested direction to scene
numbers, and `nokia_music.py` computes section boundaries from the **actual**
shot clock. The opening is suspenseful/cinematic (scene 1); the rise is
inspiring/energetic (2–5); disruption is tense modern electronic (6–8); the
decline is emotional/restrained (9–11); and the final lesson is reflective,
cinematic (12–13). If the author-approved edit changes scene structure, update
the profile as well. Do not force these boundaries onto a different edit.

The optional score is a procedural *draft*: its moods are proxies, not a claim
of a finished cinematic composition. Listen through transitions, choose or
revise music for each section, and clear rights before release. The plan by
itself contains no audio.

## Build and package

Requirements: Python 3.10+, NumPy, Node with `npm ci` in `video_studio`, FFmpeg
and FFprobe on `PATH`, plus the voice engine/models needed by `narrate.py synth`.
Commands below run from the repository root. They are an example **after** an
author-approved edit has been incorporated into the picture and narration;
they do not make the existing 28:35 script fit 15 minutes.

```bash
PKG=workspace/nokia-release
mkdir -p "$PKG"
node video_studio/films/nokia_empire.mjs --lines "$PKG/lines.json"
python video_studio/narrate.py synth --lines "$PKG/lines.json" --out "$PKG/voice" \
  --voice bm_george --rate 0.95 --profile calm
# The picture reads voice lengths from its timing file. Regenerate the clock
# and all picture slices after the approved script or voice has changed:
cp "$PKG/voice/timing.json" video_studio/films/nokia_empire-timing.json
node video_studio/films/nokia_empire.mjs --starts "$PKG/shots.json"
python video_studio/nokia_music.py --starts "$PKG/shots.json" \
  --plan "$PKG/music-plan.json" --score "$PKG/score-draft.wav"
python video_studio/narrate.py mix --vo "$PKG/voice" --score "$PKG/score-draft.wav" \
  --starts "$PKG/shots.json" --out "$PKG/master.wav" --target-lufs -14 \
  --ceiling-dbfs -1.5 --score-gain 0.20 --duck 0.34 \
  --timing-out "$PKG/voice-timing.json" --stems-dir "$PKG"
```

Produce the complete picture using the **same** shot clock and mux it with the
mix as `video.mp4`; do not assume an individual render slice is complete. The
mixer rejects a score with a different duration and voice clips inconsistent
with their recorded lengths. Export captions, if used, for the same final clock.
For example, once a complete synchronized `picture.mp4` exists:

```bash
ffmpeg -i "$PKG/picture.mp4" -i "$PKG/master.wav" -map 0:v:0 -map 1:a:0 \
  -c:v copy -c:a aac -b:a 192k -movflags +faststart "$PKG/video.mp4"
```

This mux example does not add subtitle streams. Add the intended captions through
your normal delivery process and audit the resulting exact video; do not use
`-shortest` to hide an unequal picture/audio duration. Provide `script.md` (the
approved narration and title) and `storyboard.json` for the actual cut in the
package. WAV buses must reflect what is **actually in the delivered mix**,
post-duck and post-gain, aligned from zero to the end of the film. If a different
mixer, music or effects are used, export corresponding aligned stems. Stereo
PCM16 is accepted; the example `narrate.py` folds the score to mono, exports
mono PCM16 stems, and sums them to both channels of its dual-mono master. Use a
reviewed stereo-capable mixer if a stereo score is required. Do not put
sound effects into the music stem if the auditor is expected to meter music
separately.

Recommended levels are narration active RMS **−18 to −12 dBFS**, narration
sample peaks **−6 to −3 dBFS**, music under narration **−30 to −24 dBFS**, and
dramatic effects **−18 to −10 dBFS** depending on the effect. Target the encoded
master at **−14 LUFS integrated** with a maximum **−1 dBTP** true peak. The
mixer's sample ceiling and approximate loudness do not guarantee the AAC file's
true peak or LUFS. The Nokia auditor meters the encoded master with FFmpeg
`ebur128=peak=true`, meters the voice/music stems in 50 ms voice-active windows,
and optionally measures `effects-stem.wav` as a bus; listen to individual
sound-effect cues. User-level ranges are recommendations, not claims that these
numbers are met. A music stem that is silent, missing, or cannot be measured
cannot demonstrate music balance. A numerical average cannot prove intelligibility
or rule out masking on an individual word.

## Evidence and human review

Run strict technical QA on the **exact** final file:

```bash
python video_studio/quality_audit.py "$PKG/video.mp4" --strict \
  --report "$PKG/video.qc.json"
```

The direct package files must include `video.mp4`, `script.md`,
`storyboard.json`, `video.qc.json`, `shots.json`, `voice-timing.json`,
`facts.json`, `voice-stem.wav`, and `music-stem.wav`. Optional `.srt`/`.vtt`
sidecars and `effects-stem.wav` are also bound if present. `shots.json` is the
ordered, gapless shot clock (`id`, `scene`, `start`, `end`, `voStart`).
`voice-timing.json` contains one corresponding line per shot (`shot`, `start`,
`end`, `text`, and `vo`); the mixer exports this. The auditor checks that the
lines fit their shots and the clock covers the video, but this does **not**
prove that the recorded words are complete or correctly spoken.

Build a source ledger named `facts.json`, including **every** historical date,
financial figure, quantitative claim and material factual assertion from both
narration and on-screen graphics. Prefer primary sources; record the precise
scene/shot or time, period, units, market denominator and an explanation of what
the source supports. This is an intentionally incomplete example, not an
attestation:

```json
{
  "coverage": "partial",
  "claims": [{
    "claim": "The Microsoft deal was announced on 3 September 2013 for EUR 5.44 billion.",
    "location": "scene 10; announcement card",
    "verdict": "supported",
    "sources": [{
      "url": "https://news.microsoft.com/source/2013/09/03/microsoft-to-acquire-nokias-devices-services-business-license-nokias-patents-and-mapping-services/",
      "support": "Microsoft's announcement identifies the date, EUR 3.79bn business price and EUR 1.65bn patent license."
    }]
  }]
}
```

`coverage` must be changed to `complete` **only after exhaustive review**; every
claim needs `verdict: supported` and at least one HTTP(S) source plus a support
note. The tool validates the ledger's structure, not the sources, interpretation
or completeness. Unsupported claims need correction or author-approved script
changes, not a passed verdict.

After all required inputs and any optional captions/effects are in place,
initialize the Nokia profile and a **blank** human review. This creates
`release-profile.json` and `nokia-review.json`; it does not pass any checks.

```bash
python video_studio/nokia_audit.py --package "$PKG" --init-review
```

A named reviewer must watch and listen to the finished film, verify each item,
and edit `nokia-review.json`: set `reviewed_by`, each manual check's `status` to
`pass` or `fail`, and a substantive `note` describing the actual evidence.
`visual_relevance.scenes` must list all scene numbers in the clock. Caption
`mode` is `none`, `sidecar`, `embedded`, `burned`, or `multiple`; even `none`
requires inspection of the delivered picture and streams. When sidecars exist,
the auditor also compares their words and line-level timings with the planned
narration, but **not with actual speech**. Listen to the actual audio for caption
accuracy and synchronization, including embedded/burned captions. Review the
last word, the tail, and whether the ending is clean rather than clipped.

The template hashes every current evidence file, including the profile and all
caption sidecars; it is invalid if an input is added, removed or modified after
review starts. When that happens, re-run strict QA as appropriate, then use
`--init-review --force` to create a **new blank** review and review again. Do not
copy old attestations into a changed package without rechecking it.

```bash
python video_studio/nokia_audit.py --package "$PKG"
python video_studio/release_gate.py --package "$PKG"
```

`nokia.audit.json` is `PASSED` only if all required machine checks pass and all
six manual checks are attested; missing/unrun evidence is `INCOMPLETE`, and
observed defects are `FAILED`. Machine checks include duration 840–960 seconds,
coverage by exactly one video and one audio stream (alternate audio tracks are
not audited), strict QA with no warnings, black threshold ≤0.20 s, silence
threshold ≤1.50 s, the shot/narration clock, a ≥0.20 s post-narration picture
tail, master −14 ± 1.5 LUFS, and true peak ≤−1 dBTP. These thresholds are
conservative; a black or silent interval identified by strict QA fails even if
it might be intentional. Fix or redesign it rather than silently treating it as
a pass. Other legacy strict-QA checks, including repeat-frame warnings, also
remain in force.

The explicit `release-profile.json` marker selects the Nokia gate. The release
and upload paths additionally require the profile when the package identifies
this Nokia empire/rise-and-fall film in its directory name, first script heading
or upload title, or retains Nokia review/audit files. This is a safety net, not
universal content detection: **initialize the profile for this film even when
using a generic folder/title**. Approval binds the profile, audit, all evidence,
metadata, and final video; upload revalidates them. Generic unrelated packages
retain their existing gate. An actual human must still use `release_gate.py` and
type its confirmation; auditing never approves or uploads.

## Specific source corrections made so far — incomplete review

The picture code now distinguishes Gartner **all-mobile sales** from
smartphone/OS share and corrects selected figures; the narration remains verbatim.
These sources are useful starting points, not a complete factual ledger:

- Gartner's [2013 worldwide all-phone and smartphone OS tables](https://www.gartner.com/en/newsroom/press-releases/2014-02-13-gartner-says-annual-smartphone-sales-surpassed-sales-of-feature-phones-for-the-first-time-in-2013),
  [2012 all-phone table](https://www.design-reuse.com/news/202523334-gartner-says-worldwide-mobile-phone-sales-declined-1-7-percent-in-2012-/),
  [2009 all-phone table](https://www.palminfocenter.com/news/6579/gartner-reports-worldwide-mobile-phone-sales-for-2009/),
  and [2007 all-phone shares](https://www.computerworld.com/article/1563633/2007-was-a-blockbuster-year-for-mobile-phones.html).
  Gartner's 2007 full-year Nokia all-phone share was 37.8%; its roughly 40%
  quarter is a different period, and Nokia's 3% in early 2013 was a
  [smartphone share](https://www.bbc.com/news/technology-23947212), not
  full-year all-phone share. The earlier rise chart uses Gartner's
  [1998](https://money.cnn.com/1999/02/08/europe/nokia/),
  [2000](https://www.telecompaper.com/news/nokia-has-30-6-mobile-handset-market-share-in-2000--265610),
  [2003 comparative](https://www.domain-b.com/companies-organisations/firms-companies/30-per-cent-global-growth-in-handset-sales-in-2004-gartner),
  and [2006](https://evertiq.com/news/6877) estimates. Revisions and separate
  sales-versus-shipment definitions should not be mixed silently.
- Nokia's own [1998](https://web.lib.aalto.fi/fi/old/yrityspalvelin/pdf/1998/enokia.pdf),
  [1999](https://web.lib.aalto.fi/fi/old/yrityspalvelin/pdf/1999/Enokia.pdf),
  and [2000](https://web.lib.aalto.fi/fi/old/yrityspalvelin/pdf/2000/Enokia.pdf)
  reports support 40.8m, 78.5m and 128.4m company phone sales respectively.
- Nokia's [2008](https://www.nokia.com/sites/default/files/2018-11/05-nokia-in-2008-pdf.pdf)
  and [2010](https://www.nokia.com/sites/default/files/2018-11/07-agm-nokia-in-2010-pdf_0.pdf)
  annual reports give consolidated R&D expenses of €5.636bn, €5.968bn,
  €5.909bn, and €5.863bn for 2007–2010. The 2007 number is the 2008
  comparative, not the initially published figure.
- The 2007 smartphone OS chart uses the Gartner table
  [reproduced here](http://volkersthoughts.blogspot.com/2009/03/smartphone-market-shares-growth.html).
  The Android growth chart uses Gartner's [2009–10 figures](https://www.cnet.com/tech/mobile/gartner-android-ranks-2nd-in-global-smartphones/),
  [2011 rounded share](https://www.theguardian.com/technology/2012/feb/15/android-smartphones-apple-2011)
  and 2012–13 table above. Two unsupported numerical software-fragmentation
  charts were replaced by qualitative cards.
- The [2013 announcement](https://news.microsoft.com/source/2013/09/03/microsoft-to-acquire-nokias-devices-services-business-license-nokias-patents-and-mapping-services/)
  states that €5.44bn was the agreed business **plus patent-license** price;
  [completion was April 2014](https://www.nokia.com/newsroom/nokia-completes-sale-of-substantially-all-of-its-devices--services-business-to-microsoft/).

Other charts, figures and narrative claims remain unaudited. Every correction
still needs to be checked in the final render and covered by the completed ledger
and human review.
