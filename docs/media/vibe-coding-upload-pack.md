# Upload pack — Vibe Coding film

Built from the film's own narration (`voice/lines.json`, 151 lines, 17 scenes).
Nothing here invents a claim the film does not make.

## Title (pick one)

1. **Vibe Coding: Build a Real App Without Writing the Code**
2. I Built a Working App by Describing It — No Syntax, Just Prompts
3. Vibe Coding, Step by Step: From Empty Repo to Live Site

## Description

You describe what you want in plain English. An agent writes it, on GitHub,
while you watch. This is the whole loop, step by step, with nothing skipped.

The video covers the eleven steps that actually matter: the repository, the one
time connection, the first prompt, the branch the agent works in, how to read a
diff, letting the checks run, merging, what to do when it goes wrong, the prompt
patterns that work, keeping secrets out of the repository, and the habits that
keep it fast. A second feature is built in real time so you can watch the loop
repeat rather than take it on faith.

No frameworks to install, no syntax to memorise. You need a GitHub account and a
browser.

## Chapters

```
0:00 Intro
0:27 What vibe coding actually means
1:07 The loop we repeat
1:38 Step 1 — one empty repository
2:38 Step 2 — connect GitHub to Arena
3:25 Step 3 — the first prompt
4:29 Step 4 — the agent works in a branch
5:13 Step 5 — read the diff
6:00 Step 6 — let the checks run
6:46 Step 7 — merge and ship
7:27 Step 8 — a second feature, in real time
8:16 What to do when it goes wrong
8:59 The prompt patterns that work
9:48 Keeping secrets out of the repo
10:22 The habits that keep this fast
11:06 The whole loop, back together
11:42 You don't need to know every line
```

## Tags

`vibe coding, ai coding, ai agent, github, build an app with ai, no code, prompt
engineering, ai tools, cursor alternative, claude code, ai for beginners`

## Subtitles

`docs/media/vibe-coding.srt` (for YouTube) and `docs/media/vibe-coding.vtt` (for a
web player) hold the same 155 cues. They are written from `voice/lines.json` by
`tools/film_subtitles.py`, so a cue cannot drift away from the read it describes.

## Honest notes for the uploader

- The narration in this render is the **espeak-ng preview voice**. It is correct
  in timing and content and wrong in tone. Re-render with
  `--voice en_US-amy-medium` (Piper, free, offline after one download) before
  publishing; the picture, captions and score need no other change.
- The rendered cut is **12:02, 1280×720, 30 fps, −14.6 LUFS**, 21,662 frames.
  The sandbox that drew it has 3.9 GB of RAM and the 1080p frame render is
  killed by the kernel at about 3.6 GB, so the pixels are 720p. On a machine with
  more memory the same command at `--width 1920 --height 1080` gives a true 1080p
  master with no other change.
- Two of the film's own gates fail on this cut and are not hidden:
  - **composition** — one arrangement stays on screen for 37.0 s at 4:35, and
    eight stretches pass the 12 s limit, covering 26% of the film;
  - **repeat frames** — sixteen stretches hold an identical picture for up to
    1.4 s against a 1.0 s limit.
  The motion gate passes (mean frame delta 1.77 against a 0.82 baseline, 2.4%
  near-static frames against a 50% limit). Fixing the two failures means scene
  edits in `video_studio/films/vibe_coding.mjs` and a re-render of those sections.
- The content audit reports **no violations** and 13 rules it could not check
  without a vision model (profanity, violence, weapons, self-harm, hate speech,
  adult content, sentiment, children, music, clips, lip-sync).
- Every claim in the description appears in the narration; none was added.
