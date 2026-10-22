# Running on a weak machine

The system is meant to be installable on a cheap laptop, an old desktop, or a
mini PC with 4 GB of RAM. The rule for those machines is simple:

> **Do not crash. Do not make the desktop stutter. Being slow is allowed.**

Slow is acceptable. A frozen window, a swap storm, or a run that dies at 80%
with a memory error is not. So the system measures the machine, decides how much
work it may do at once, and writes that decision down.

## How the decision is made

`tools/resources.py` reads the hardware and picks one of four tiers.

- `minimal` — under 4 GB of RAM, or a single core.
- `low` — 4 to 8 GB.
- `balanced` — 8 to 16 GB.
- `high` — 16 GB or more.

If the RAM figure cannot be read, the machine is treated as `balanced`. Guessing
low would quietly shrink the limits of a capable machine, which is the same kind
of wrong answer as guessing high on a weak one.

The tier is chosen once per run and never changes mid-run, so two stages cannot
disagree about the budget.

You can see the decision without starting anything:

```
python tools/resources.py
python tools/resources.py --json
```

## What a smaller machine gets

Only *batch* limits move — how long one step may run, how much data it may read,
how many repair attempts it gets.

| | minimal | low | balanced | high |
| --- | --- | --- | --- | --- |
| heavy jobs at once | 1 | 1 | 1 | 1 |
| one model call may wait | 180 s | 240 s | 300 s | 600 s |
| generated section cap | 1,200 tokens | 1,600 | 2,400 | 4,000 |
| one tool step may run | 300 s | 600 s | 900 s | 1,800 s |
| one shell command may run | 60 s | 90 s | 120 s | 180 s |
| repairs per step | 1 | 2 | 2 | 2 |
| dataset read ceiling | 500 KB | 1 MB | 2 MB | 8 MB |
| suite run timeout | 60 s | 90 s | 120 s | 180 s |
| disk recommended free | 200 MB | 500 MB | 1 GB | 2 GB |

The point of the shorter model timeout is not speed. It is that a run which
cannot finish a generation on a 2-core CPU should say so in three minutes rather
than appear hung for ten.

**One heavy job at a time, on every tier.** The pipeline is sequential by design.
That is the main reason a small machine stays usable while a build runs.

## What does not change, ever

These are stated in the plan itself, under `never_changes`, so a reviewer can
check that none of them moved:

- the video resolution and frame rate that were asked for;
- the narration language and voice;
- the content of a report or document — measured numbers stay measured;
- chart values — every bar is a real value, never sampled down;
- whether a run is marked complete.

A weaker machine produces the **same artifact, later**. If something really does
have to be smaller, it is listed in the plan under `degradations`, in words, and
printed when the run starts. Nothing is silently reduced.

## Memory and disk

Before the run starts, the plan compares free RAM to total RAM. Under 15% free,
the limits drop one tier **for that run only** and the reason is recorded. That
is the case where a machine is already busy with something else, and the honest
answer is to ask less of it.

Low disk is a warning, not a refusal. A run that cannot write its output should
fail at the file with the reason attached, not refuse to start.

## Where you see it

`pipeline-status.json` gains a `resources` block:

```json
"resources": {
  "schema": 1,
  "tier": "minimal",
  "detected_tier": "minimal",
  "pressure": null,
  "facts": {"cpu_count": 2, "total_memory_bytes": 4131278848, "available_memory_bytes": 3850391552},
  "limits": {"model_timeout_seconds": 180, "dataset_max_bytes": 500000},
  "degradations": ["one local-model call may wait at most 180s instead of 300s"],
  "never_changes": ["requested video resolution and frame rate"],
  "warnings": [],
  "reasons": ["detected 2 core(s) and 3.8 GiB RAM"]
}
```

The CLI prints one line as well:

```
Resources: tier=minimal cores=2 ram=3.8GiB heavy_jobs=1 tool_loop=300s dataset=500000B
  reduced: one repair attempt per step instead of two
```

## Forcing a tier

Auto-detection can be wrong about a machine — a shared server, a VM with a
borrowed CPU quota, a laptop on battery.

```
python agents/orchestrate.py --task "..." --profile low
```

or set `AGENT_HQ_PROFILE=low`, or `"resources": {"profile": "low"}` in
`config.json`. An explicit choice is recorded as explicit, alongside the tier
that was actually detected, so the manifest never claims the hardware said
something it did not.

## What is still not adaptive

Being honest about the edges:

- **No shared wall-clock budget across stages yet.** Each stage has its own
  ceiling; a run of seven slow stages can still take a long time in total.
- **The renderer's own memory use is not capped per frame.** `video_studio`
  reports a thread count and never downgrades a requested resolution, but it does
  not yet refuse a frame that would not fit in RAM.
- **The queue does not pause when the desktop is busy.** It will not start a
  second heavy job, but it does not check whether you are already using the CPU
  for something else.
- **A slow run is still slow.** Nothing here makes a 2-core machine fast; it
  makes it survive.

## Candidate pieces for the low-end path

Researched, not yet adopted. Recorded here so the next increment does not
re-research it.

- **Piper for narration.** CPU-only neural TTS, 20–80 MB per voice, runs faster
  than real time on a Raspberry Pi 4/5. Caveat: the original `rhasspy/piper` is
  MIT and archived; the maintained fork `OHF-Voice/piper1-gpl` is **GPL-3.0**.
  Adopting it changes the project's licence story, so that decision comes before
  the dependency. `sherpa-onnx` and `kokoro-onnx` are Apache-2.0 alternatives.
- **Streaming image decode.** `libvips`/`sharp` decode an 8K image at roughly
  20 MB peak against 400 MB for ImageMagick or Pillow. If any image step is added
  to the default path, this is the difference between finishing and swapping.
- **`resvg` for SVG→PNG.** Tiny (under 5 MB, no system dependencies) but the Node
  binding has open RSS-growth reports across repeated renders; render frames in
  one long-lived process or use the CLI, never a fresh process per frame.

Nothing here needs a GPU, a key, or a network call.

## Verifying it

```
python -m unittest tests.test_resources -v
```

The tests pin the two halves of the promise: limits really do fall as the machine
gets smaller, and the things you asked for do not move at all.
