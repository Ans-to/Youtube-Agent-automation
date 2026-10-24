#!/usr/bin/env python3
"""Measure how often the *arrangement* on screen changes, not how much it twinkles.

Why this exists
---------------
The other motion checks in this repository ask whether the picture moved. Every
one of them can be satisfied without the picture changing at all:

* a frame-to-frame difference is answered by grain, which moves every pixel;
* the block comparison in ``repeat_frames.py`` is answered by a caption ticking
  over or a progress bar advancing;
* a measured mean of 1.71 against a floor of 0.8 was reported as "moving" on a
  film whose layout changed thirty times in eleven and a half minutes.

A viewer does not see pixels. They see an arrangement: where the title is, which
panel is open, whether anything is in a new place. That is what this module
measures. Decoration cannot fake it, because decoration does not rearrange a
composition.

How it is measured
------------------
1. Frames are sampled at a low rate and shrunk to 320x180, then pooled into a
   16x9 grid of cells (144 of them). Each cell is one number: average brightness.
   That is a thumbnail of the layout, and pooling it removes grain.
2. Each thumbnail is centred and unit-normalised, so the comparison ignores
   overall brightness and contrast. A fade does not count as a change; moving a
   panel to a new place does.
3. Each thumbnail is compared with the one the current arrangement *started*
   on, with a dot product: 1.0 is the same arrangement, 0.0 is unrelated. A
   boundary is declared below ``CHANGE_BREAK``, and the next shot is compared
   against that new frame.

   Comparing neighbours instead - "did it change since half a second ago?" -
   was the first thing this module did, and it was wrong in the direction that
   matters: a camera that pushes in over a second moves a little every frame and
   therefore never crosses the threshold, so a shot that is visibly travelling
   is scored as one long held frame. Measured on this repository's films, asking
   "is this the same as when the shot began?" finds 86 arrangements where the
   neighbour test found 40, and lowers the longest hold from 79.5 s to 59.5 s on
   the tutorial film while leaving the character film's verdict (passes) and a
   frozen frame wearing grain (fails) untouched.
4. A flat frame (a black card, a plain background, a fade to white) has no
   arrangement to compare, and normalising pure noise produces confident
   nonsense: measured on a frozen black frame plus grain, unprepared similarity
   ran to -0.2 and the check called a still image "moving constantly". So a
   frame with less than ``MIN_CONTRAST`` structure is not compared at all. Two
   such frames are the same composition by definition, which is what a viewer
   sees.

The verdict
-----------
Two numbers, both in seconds:

* **longest hold** - the longest a single arrangement stays on screen.
* **share over the limit** - how much of the running time sits inside holds that
  run longer than the limit.

An explainer needs a new arrangement every few seconds; twelve is generous.
Calibrated on the repository's own films rather than invented:

===================  ==========  ==============  ===============
film                 longest     share over 12s  verdict
===================  ==========  ==============  ===============
vibe-coding-preview  79.5 s      95%             fails
stickman-film        10.5 s      0%              passes
frozen frame + grain 20.0 s      100%            fails
===================  ==========  ==============  ===============

Used by ``tools/check_composition.py`` and by the film build, which fails the
render when a cut is a slideshow.
"""

from __future__ import annotations

import statistics
import subprocess  # noqa: F401 - kept for the type of the decode error path
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from video_studio.repeat_frames import iter_video_frames, resolve_ffmpeg, timecode

# Sampling. Two frames a second is enough to see a beat, cheap enough to run on a
# twenty-minute film, and the verdict was checked to be identical at 1, 2 and 4
# frames a second on both reference films.
SAMPLE_FPS = 2.0
FRAME_WIDTH = 320
FRAME_HEIGHT = 180

# The thumbnail grid. 16x9 cells of 20x20 pixels: coarse enough that a letter
# arriving is a change of one cell, fine enough that a panel opening is many.
GRID_X = 16
GRID_Y = 9

# Below this standard deviation a frame has no arrangement to speak of: it is a
# flat colour plus noise. Measured at 0.8 on a black frame with heavy grain,
# against 43.8 and 58.9 on the two reference films.
MIN_CONTRAST = 8.0

# Similarity below which two thumbnails are different arrangements. Measured
# between a film's own cuts (0.2-0.7) and within a held scene (0.99+).
CHANGE_BREAK = 0.90

# The bar. A new arrangement at least every twelve seconds. The share is not a
# second way to pass: a held frame is a failed film at any length, which is the
# owner's rule and the reason the previous checks were useless. It is reported
# because it says how much work is left, not whether there is any.
MAX_HOLD_SECONDS = 12.0


@dataclass
class Hold:
    """One arrangement, and how long it stayed."""

    start: float
    seconds: float

    @property
    def end(self) -> float:
        return self.start + self.seconds


@dataclass
class CompositionReport:
    """Everything measured, and everything that could not be measured."""

    duration_seconds: float = 0.0
    sampled_frames: int = 0
    structures: int = 0
    holds: list[Hold] = field(default_factory=list)
    median_similarity: float = 1.0
    unjudged_frames: int = 0
    spans: list[dict] = field(default_factory=list)

    @property
    def longest_hold(self) -> Hold | None:
        return max(self.holds, key=lambda hold: hold.seconds) if self.holds else None

    def share_over(self, limit: float) -> float:
        """Fraction of the running time spent inside holds longer than ``limit``."""
        if self.duration_seconds <= 0:
            return 0.0
        over = sum(hold.seconds for hold in self.holds if hold.seconds > limit)
        return over / self.duration_seconds

    @property
    def judged(self) -> bool:
        """False when the file was too short or too flat to say anything."""
        return self.duration_seconds > 0 and (self.structures >= 2 or self.unjudged_frames > 0)


def signature(frame: np.ndarray) -> np.ndarray:
    """A frame as a small grid of average brightness."""
    height, width = frame.shape
    if height % GRID_Y or width % GRID_X:
        raise ValueError("frame %dx%d does not divide into a %dx%d grid"
                         % (width, height, GRID_X, GRID_Y))
    return frame.reshape(GRID_Y, height // GRID_Y, GRID_X, width // GRID_X).mean(axis=(1, 3))


def has_structure(signature_grid: np.ndarray) -> bool:
    """True when there is an arrangement worth comparing."""
    return float(np.std(signature_grid)) >= MIN_CONTRAST


def similarity(first: np.ndarray, second: np.ndarray) -> float:
    """How alike two arrangements are, ignoring brightness and contrast.

    Returns 1.0 for two flat frames: neither has anything on it, so from the
    viewer's point of view they are the same picture. Returning 0.0 there, as a
    raw normalised dot product does, is how a still image gets called movement.
    """
    first_centred = first - first.mean()
    second_centred = second - second.mean()
    first_norm = float(np.linalg.norm(first_centred))
    second_norm = float(np.linalg.norm(second_centred))
    if first_norm < 1e-6 or second_norm < 1e-6:
        return 1.0
    return float(np.sum(first_centred * second_centred) / (first_norm * second_norm))


def analyse_signatures(signatures: list[np.ndarray], *, fps: float = SAMPLE_FPS,
                       change_break: float = CHANGE_BREAK) -> CompositionReport:
    """Find the arrangements in a stream of thumbnails. Pure: no files, no clock."""
    report = CompositionReport()
    report.sampled_frames = len(signatures)
    if not signatures:
        return report
    report.duration_seconds = round(len(signatures) / fps, 3)

    boundaries = [0]
    answered = []
    reference = None
    for index, current in enumerate(signatures):
        if not has_structure(current):
            # A flat frame tells us nothing, and comparing it would be noise.
            report.unjudged_frames += 1
            continue
        report.structures += 1
        if reference is None:
            reference = current
            boundaries = [index]
            continue
        value = similarity(reference, current)
        answered.append(value)
        if value < change_break:
            boundaries.append(index)
            reference = current

    if answered:
        report.median_similarity = round(statistics.median(answered), 4)

    for position, start in enumerate(boundaries):
        end = boundaries[position + 1] if position + 1 < len(boundaries) else len(signatures)
        report.holds.append(Hold(start=round(start / fps, 3), seconds=round((end - start) / fps, 3)))
    return report


def analyse_frames(frames, *, fps: float = SAMPLE_FPS,
                   change_break: float = CHANGE_BREAK) -> CompositionReport:
    """Same analysis, streaming: one decoded frame at a time."""
    signatures = [signature(frame) for frame in frames]
    return analyse_signatures(signatures, fps=fps, change_break=change_break)


def decide(report: CompositionReport, *, max_hold_seconds: float = MAX_HOLD_SECONDS) -> dict:
    """Turn measurements into a verdict a person can act on.

    A check that could not run is not a check that passed, so an unjudgeable
    file fails rather than passing by default.
    """
    verdict = {
        "status": "passed",
        "passed": True,
        "duration_seconds": report.duration_seconds,
        "compositions": len(report.holds),
        "median_similarity": report.median_similarity,
        "unjudged_frames": report.unjudged_frames,
        "longest_hold_seconds": 0.0,
        "longest_hold_at": None,
        "share_over_limit": 0.0,
        "limit_seconds": max_hold_seconds,
        "spans": [],
    }
    if report.duration_seconds <= 0 or not report.holds:
        verdict.update({
            "status": "not_run",
            "passed": False,
            "statement": "COMPOSITION: COULD NOT RUN - the file produced no frames to judge",
        })
        return verdict

    longest = report.longest_hold
    share = report.share_over(max_hold_seconds)
    over = sorted((hold for hold in report.holds if hold.seconds > max_hold_seconds),
                  key=lambda hold: hold.seconds, reverse=True)
    verdict.update({
        "longest_hold_seconds": round(longest.seconds, 1),
        "longest_hold_at": timecode(longest.start),
        "share_over_limit": round(share, 4),
        "spans": [{"start": timecode(hold.start), "seconds": round(hold.seconds, 1)}
                  for hold in over[:10]],
    })

    if over:
        worst = over[0]
        verdict.update({
            "status": "failed",
            "passed": False,
            "statement": (
                "COMPOSITION: FAILED - one arrangement stays on screen for %.1f s at %s "
                "(limit %.0f s); %d hold(s) over the limit, covering %.0f%% of the film"
                % (worst.seconds, timecode(worst.start), max_hold_seconds,
                   len(over), 100 * share)
            ),
            "fix_hint": (
                "Cut inside the scene instead of holding it: a new panel, a new "
                "crop, an element arriving in a new place, every few seconds. "
                "Grain, drift and a ticking caption do not count."
            ),
        })
    else:
        verdict.update({
            "statement": (
                "COMPOSITION: PASSED - %d arrangements, the longest %.1f s "
                "(limit %.0f s)"
                % (len(report.holds), longest.seconds, max_hold_seconds)
            ),
        })
    return verdict


def analyse_video(path: Path | str, *, sample_fps: float = SAMPLE_FPS,
                  max_hold_seconds: float = MAX_HOLD_SECONDS,
                  ffmpeg: str | None = None) -> dict:
    """Run the whole check on a video file and return the verdict."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    binary = resolve_ffmpeg(ffmpeg)
    if not binary:
        raise RuntimeError("FFmpeg is required for the composition check")
    frames = iter_video_frames(path, fps=sample_fps, width=FRAME_WIDTH,
                               height=FRAME_HEIGHT, ffmpeg=binary)
    report = analyse_frames(frames, fps=sample_fps)
    verdict = decide(report, max_hold_seconds=max_hold_seconds)
    verdict["file"] = str(path.resolve())
    return verdict


def format_report(verdict: dict, *, limit: int = 8) -> str:
    """The verdict and its evidence, as text for a terminal."""
    lines = [verdict.get("statement", "COMPOSITION: no verdict")]
    if verdict.get("compositions"):
        lines.append("  %d arrangements over %.1f s (median similarity to the shot's first frame %.3f)"
                     % (verdict["compositions"], verdict["duration_seconds"],
                        verdict.get("median_similarity", 1.0)))
        lines.append("  longest %.1f s at %s; %.0f%% of the film is in holds over %.0f s"
                     % (verdict["longest_hold_seconds"], verdict.get("longest_hold_at"),
                        100 * verdict["share_over_limit"], verdict["limit_seconds"]))
        spans = verdict.get("spans") or []
        if spans:
            lines.append("  worst holds:")
            for span in spans[:limit]:
                lines.append("    %8s  %5.1f s" % (span["start"], span["seconds"]))
    if verdict.get("fix_hint"):
        lines.append("  " + verdict["fix_hint"])
    return "\n".join(lines)
