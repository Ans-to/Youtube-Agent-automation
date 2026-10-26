# What makes a YouTube video get watched

This is the craft reference for the motion-graphics studio. It is written to be
**enforceable**: every principle ends in a number, and every number becomes a
check in `tools/check_craft.py`. A principle the machine cannot measure is
listed under "judgement calls" and never pretended to be automated.

Sources are cited inline. Where creators disagree, the range is given instead of
one invented "correct" answer.

---

## 1. The four decisions a viewer makes

| Moment | What is decided | What wins it |
| --- | --- | --- |
| Impression | Click or not | Thumbnail (seen roughly twice as long as the title — vidIQ) |
| 0–3 s | Stay or leave | Motion + a promise that matches the thumbnail |
| 3–30 s ("Intro") | Commit or drift | Value delivered early, no logo, no "hey guys" |
| 25–35 % in | Continue or bail | A re-hook, because setup has run out and payoff has not arrived |

YouTube Studio measures the first thirty seconds as its own key moment, the
**Intro**: "what percentage of your audience still watched your video after the
first 30 seconds" ([YouTube Help](https://support.google.com/youtube/answer/9314415)).
Everything else on this page is downstream of that number.

## 2. Retention, in real numbers

- Platform average retention is **around 24%** of the video watched; only about
  **1 in 6** videos hold more than half their audience
  ([Retention Rabbit 2025 benchmark, via gyre.pro](https://gyre.pro/blog/how-to-improve-audience-retention-on-youtube-top-tips)).
- **30% average percentage viewed** is a realistic good result for 6–9 minute
  education content; 50%+ is strong ([vidIQ](https://vidiq.com/blog/post/increase-audience-retention-youtube/)).
- **55% of viewers leave within the first minute** ([via virvid.ai](https://virvid.ai/blog/retention-graphs-how-to-read-youtube-analytics-2026)).
- A 10–15% drop in the first 30 s is normal; **over 30% means the intro failed**
  ([fenogent](https://fenogent.com/blog/youtube-audience-retention-watch-time-guide)).
- Videos holding **65%+ past the first minute** show **58% higher average view
  duration** across the rest of the video (Retention Rabbit, May 2025).
- Retention falls as length rises: 50–70% under 5 min, 40–55% for 10–20 min
  ([gyre.pro](https://gyre.pro/blog/how-to-increase-average-youtube-watch-time-and-why-it-matters)).

**Rules for this studio**

| Rule | Threshold | Why |
| --- | --- | --- |
| `hook-3s` | A motion event, a legible claim and a visible subject change inside the first **3.0 s** | 50–60% of drop-off happens in the first seconds; 71% decide within 3 s ([tukey.ai](https://tukey.ai/blog/the-youtube-hook-formula-that-stops-the-scroll-in-3-seconds-here-is-the-data)) |
| `intro-30s` | The video's promise is fully stated and the first concrete payoff is visible by **30 s** | Studio's Intro metric |
| `no-cold-open` | No logo, no title card alone, no greeting before the first claim | A title-only open spends the most valuable seconds on nothing |
| `rehook` | A visible structural change at **25–35%** of runtime | "Tutorial valley" cliff ([increditors](https://increditors.com/video-pacing-youtube-retention-science/)) |

## 3. Pacing

Cut rate depends on the audience; the sources disagree on purpose. Educational
and explainer content holds up at **3–5 cuts/min**, tutorials at 8–12/min
([increditors](https://increditors.com/video-pacing-youtube-retention-science/),
[wideframe](https://try.wideframe.com/blog/how-to-adjust-video-pacing-with-ai-analysis/)).
The transferable rule is smaller than a "cut": **change something visible every
5–7 seconds** ([editmyreels](https://editmyreels.com/how-to-edit-youtube-videos-for-higher-retention/)).

Pattern interrupts are the bigger structural beat:

- Every **45–90 s** in long-form. Below 45 s it feels chaotic; above 90 s
  habituation sets in ([prepublish.ai](https://prepublish.ai/guides/youtube-pattern-interrupts)).
- **8–12 per 10 minutes**, with 2–3 concentrated in the first minute.
- Front-load: 0–30 s = a change every 5–10 s; 30 s–2 min every 15–30 s; then
  stretch out ([instantviews](https://instantviews.net/pattern-interrupt-techniques)).
- Interrupts must vary in type, or they become the new monotony.

**Rules for this studio**

| Rule | Threshold | Why |
| --- | --- | --- |
| `beat-cadence` | A composition change at least every **7.0 s** | "Change something every 5–7 s" |
| `interrupt-density` | **6–18** structural interrupts in a 10–20 min film, none repeating the same type twice in a row | 8–12/10 min, varied |
| `interrupt-first-minute` | At least **2** inside the first 60 s | Front-loading |
| `no-long-hold` | No composition held longer than **12 s** | Existing composition gate |
| `no-dead-air` | No silent gap longer than **1.6 s** inside a section, none over **3.0 s** between sections | Long pauses read as buffering |
| `pacing-variation` | Standard deviation of beat length ≥ **0.35 ×** mean | Uniform clip length "reads as robotic" ([kudoflix](https://kudoflix.com/blog/2026/07/25/what-is-video-pacing-editing/)) |

## 4. The hook, written not just edited

A working hook does three things in one sentence: names the viewer, makes a
promise, and shows proof or cost. Hook types and their rough 30 s retention
([tubeanalytics](https://www.tubeanalytics.net/blog/youtube-video-hook-first-30-seconds)):

| Hook | 30 s retention | Risk |
| --- | --- | --- |
| Result ("this took 9 minutes") | 75–85% | overpromise |
| Question | 70–80% | mismatched question |
| Social proof | 70–80% | hollow numbers |
| Cliffhanger | 65–75% | weak payoff |
| Visual teaser | 60–75% | production-dependent |

**Rules for this studio**

| Rule | Threshold |
| --- | --- |
| `hook-length` | First spoken sentence ≤ **18 words**, ≤ **7.0 s** |
| `hook-types` | Opening beat must be tagged with a hook type from the table above |
| `promise-payoff` | The brief declares `promise`; the film must visually restate it at least twice (open and recap) |
| `open-loop` | At least one explicit forward reference ("in a minute you'll see…") before the 25% mark, closed later |

## 5. Packaging: thumbnail and title

- YouTube's own published band: **half of all channels sit between 2% and 10%
  CTR**; 4–6% is a healthy midpoint, 8%+ is strong
  ([vidIQ](https://vidiq.com/blog/post/youtube-custom-thumbnails-ctr/),
  [gyre.pro](https://gyre.pro/blog/video-icon-and-description-get-a-high-ctr)).
- Viewers fixate on the thumbnail roughly **twice as long as the title**; the
  title's job is to *confirm* the click, not earn it.
- Custom thumbnails vs auto-generated: **8.2% vs 3.2% CTR** in one benchmark
  ([lunabloom](https://blog.lunabloomai.com/youtube-thumbnail-optimization/)).
- Design elements that correlate with CTR: bold 3–5 word text (+44%), high
  contrast (+39%), outline/shadow (+23%) ([notelm](https://notelm.ai/blog/youtube-thumbnail-design-tips)).
- **Quality CTR**: high CTR followed by instant drop-off is now a negative
  signal. The thumbnail must be a frame the video actually delivers
  ([thumbnailinsight](https://thumbnailinsight.com/blog/what-is-a-good-youtube-ctr)).

**Rules for this studio**

| Rule | Threshold |
| --- | --- |
| `thumb-words` | Thumbnail text **2–5 words**, ≤ 4 characters per word average, ≥ 6:1 contrast against its plate |
| `thumb-not-a-lie` | The thumbnail frame must exist inside the film (a real extracted frame or a template composition also used in it) |
| `title-length` | Title ≤ **60 characters**, promise in the first 40 |
| `title-thumb-match` | Title and thumbnail must share at least one concrete noun (checked by token overlap) |

## 6. Captions and legibility

- Burned-in or platform captions lift watch time materially (one reported
  **+65%** from AI subtitles, [via mean.ceo](https://blog.mean.ceo/video-hook-retention-statistics/) — vendor claim, treat as directional).
- Captions must never carry the synthesiser's spelling hacks ("vee coder"),
  because viewers read them.
- One idea per caption line, ≤ 30 characters per line at 720p, held long enough
  to read: roughly **1 s per 13 characters**.

**Rules for this studio**

| Rule | Threshold |
| --- | --- |
| `caption-read` | Every cue ≥ `chars / 13` seconds, and ≥ 0.9 s |
| `caption-chars` | ≤ 30 characters per line, ≤ 2 lines |
| `caption-clean` | No phonetic respellings — a blocklist of espeak-isms and doubled vowels |
| `caption-sync` | Cue start within ±0.15 s of the narration line start |

## 7. Audio

- Speech at **−14 LUFS integrated**, true peak ≤ −1.5 dBTP; music bed
  **−18 to −24 dB** under the voice, ducked during speech.
- The bed must not stop dead at scene changes, and no sound effect may mask a
  consonant.
- One voice, consistent pace. A formant synthesiser ("espeak") is a timing tool,
  never a published voice; a neural voice (Piper, free, offline) is the floor.

**Rules for this studio**

| Rule | Threshold |
| --- | --- |
| `loudness` | −14.6 ± 1.0 LUFS integrated |
| `peak` | True peak ≤ −1.5 dBTP |
| `voice-pyramid` | Voice-to-bed ratio within the −18…−24 dB band |
| `no-clipping` | Zero samples at full scale outside the limiter's allowance |

## 8. Structure for a 10–20 minute explainer

```
0:00  hook        the promise, with proof, in ≤ 18 words
0:03  stake       why it matters / what it costs to get wrong
0:20  roadmap     what you will be able to do by the end (open loop)
0:35  beats 1..n  one idea per section, 60–120 s each, re-hook at 25–35 %
...   payoff      the thing the thumbnail promised
end   recap       three lines, visually restated
end+  next step   one action + one teaser
```

**Rules for this studio**

| Rule | Threshold |
| --- | --- |
| `chapter-count` | 4–12 chapters for a film ≥ 8 min |
| `chapter-length` | Each chapter 45 s–3 min, none shorter than 10 s (YouTube ignores shorter) |
| `chapters-from-zero` | First chapter at `00:00`, at least three total |

## 9. What the machine cannot decide

Taste, humour, a genuinely surprising fact, whether the topic is worth making.
The studio therefore does not *judge* a film; it refuses to ship one that breaks
the measurable rules above, and it shows the owner the numbers so the argument
is about the idea, not about whether the pacing was checked.

## 10. Cost and constraints

The whole pipeline is free and key-free by construction:

- Rendering, synthesis, encoding and the gates are local code.
- The voice is Piper (MIT-licensed code, CC/public voice models) installed from
  PyPI; no hosted API, no key, no per-word charge.
- The only compute is a GitHub-hosted runner, which is **free and unlimited
  for public repositories**, with 4 cores / 16 GB on `ubuntu-24.04`
  ([GitHub docs](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)),
  a 6-hour per-job ceiling and 10 GB per artifact
  ([limits](https://docs.github.com/en/actions/reference/limits)).
- Nothing in the pipeline calls a paid service, and no step fails when a
  secret is absent.
