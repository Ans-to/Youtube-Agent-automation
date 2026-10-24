#!/usr/bin/env python3
"""Ask whether two different things are moving in the same second.

Why this exists
---------------
The composition check answers "has the arrangement changed?" over a whole frame
and a whole scene. It passes a film whose scene changes every five seconds while
a viewer still stares at one thing for those five. The owner's bar is smaller and
harder: **in any one second, two different things should be happening in the
picture.** His example is the opening line, "want to do vibe coding for free" -
in that second a subtitle is moving and code is being typed, in two parts of the
frame, so the eye always has somewhere to go.

A whole-frame measurement cannot see that distinction. One thing moving and two
things moving produce the same whole-frame number, and a big camera push produces
a bigger one than two small live details. So this measures *regions*: the frame is
cut into a grid, each region is thumbnailed the way ``composition.py`` thumbnails
a frame, and a second passes only when at least two different regions changed
inside it.

What a "region" is
------------------
The picture area only. The top band (chapter label and timecode) and the bottom
band (progress rule and captions) are cut away first, because both tick on their
own and neither is the picture: counting them would let a film pass on a clock
and a progress bar. What is left is divided into three columns by two rows, six
regions, each thumbnailed to a 5x3 grid of average brightness. Six regions is a
deliberate compromise: fine enough that "left" and "right" are different places,
coarse enough that a letter arriving does not register as activity in a region
nobody is looking at.

What counts as a change
-----------------------
Grey levels, not a correlation. Each region is a 5x3 grid of average brightness;
a region is *candidate live* when some cell in it moves by at least
``CELL_CHANGE`` grey levels inside the second. Two grey levels out of 255 is
below what a viewer can see, and grain - even the heavy grain this film draws -
moves a pooled 5x3 cell by well under one.

The first version of this module compared regions the way the composition check
compares frames: centred, unit-normalised, threshold at 0.97. It was wrong, and
measurably so. Most of this film is a dark stage, where a region's standard
deviation is under one grey level; normalising noise produces confident nonsense,
an empty corner scored 0.266 against itself, and once those samples were dropped
the check called 60% of the film empty - including seconds where the step rail
and the typing console were both visibly moving. Absolute grey levels do not have
that failure: a flat region simply does not change.

And a camera is not two things, in practice
-------------------------------------------
A push or a reframe moves every region at once. A rule dividing each region's
change by the median across all six was written for that, calibrated, and then
thrown away: on this film a large single element lifts the median of the other
five, so the multiplier discarded the very seconds that were visibly busy. It is
not needed. Measured, a gentle push keeps every region under four grey levels
while a designed element lands between eight and a hundred and thirty, so the
absolute floor separates them without arithmetic.

Honest limits
-------------
* Two live regions is a floor, not a standard. Two dull things moving meet it.
  This check cannot tell a beautiful second from a busy one; it can only refuse
  a second that has one thing happening or none.
* A region playing a looping animation - a spinner, a pulsing dot - goes *back*
  to where it was, so comparing against the start of the second can miss it. The
  stream is therefore compared against every sample in the second, not just the
  last one: a spinner that returns to its start still shows a different frame
  mid-second.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from video_studio.repeat_frames import iter_video_frames, resolve_ffmpeg, timecode

# Sampling inside a second. Six samples a second catches a beat that lasts a
# fifth of a second and is still cheap on a long film.
SAMPLES_PER_SECOND = 6
FRAME_WIDTH = 320
FRAME_HEIGHT = 180

# The picture, without the furniture. 108/2160 of the top band; 238/2160 of the
# bottom (progress rule plus the two caption rows above it).
CONTENT_TOP = 0.055
CONTENT_BOTTOM = 0.885

# Three columns, two rows.
COLUMNS = 3
ROWS = 2

# Each region is thumbnailed to this grid before it is compared.
CELL_X = 5
CELL_Y = 3

# How far a cell has to move, in grey levels of 255, to count as a change inside
# one second. Measured on this film at 640 wide: an untouched region in an idle
# second moves 0.5 levels (grain pools away almost completely), a gentle camera
# push stays under 4, and a designed element - a card arriving, a typed line
# scrolling in, the rail's bar stepping - lands between 8 and 130. Six levels
# sits in the empty middle of that gap.
CELL_CHANGE = 6.0

# The bar the owner set: two different things happening, every second.
MIN_LIVE_REGIONS = 2


@dataclass(frozen=True)
class Region:
    """One rectangle of the picture, in fractions of the frame."""

    name: str
    x0: float
    y0: float
    x1: float
    y1: float


def build_regions(columns: int = COLUMNS, rows: int = ROWS) -> list[Region]:
    """The picture area as a grid of named regions, top-left first."""
    width = 1.0 / columns
    height = (CONTENT_BOTTOM - CONTENT_TOP) / rows
    regions = []
    for row in range(rows):
        for column in range(columns):
            regions.append(Region(
                name=f"r{row + 1}c{column + 1}",
                x0=column * width,
                y0=CONTENT_TOP + row * height,
                x1=(column + 1) * width,
                y1=CONTENT_TOP + (row + 1) * height,
            ))
    return regions


REGIONS = build_regions()


def region_signature(frame: np.ndarray, region: Region) -> np.ndarray:
    """One region of one frame, as a small grid of average brightness."""
    height, width = frame.shape
    top = int(round(region.y0 * height))
    bottom = int(round(region.y1 * height))
    left = int(round(region.x0 * width))
    right = int(round(region.x1 * width))
    patch = frame[top:bottom, left:right]
    if patch.size == 0:
        raise ValueError("region %s is empty in a %dx%d frame" % (region.name, width, height))
    cell_h = patch.shape[0] // CELL_Y
    cell_w = patch.shape[1] // CELL_X
    if cell_h == 0 or cell_w == 0:
        raise ValueError("region %s is too small to pool" % region.name)
    return patch[:cell_h * CELL_Y, :cell_w * CELL_X].reshape(
        CELL_Y, cell_h, CELL_X, cell_w).mean(axis=(1, 3))


def frame_signatures(frame: np.ndarray, regions: list[Region] | None = None) -> dict[str, np.ndarray]:
    """Every region of one frame, keyed by region name."""
    return {region.name: region_signature(frame, region) for region in (regions or REGIONS)}


@dataclass
class SecondVerdict:
    """What happened inside one second."""

    index: int
    live: list[str] = field(default_factory=list)
    unjudged: list[str] = field(default_factory=list)

    @property
    def start(self) -> float:
        return float(self.index)

    @property
    def passed(self) -> bool:
        return len(self.live) >= MIN_LIVE_REGIONS


@dataclass
class SecondReport:
    """Every second judged, and how many passed."""

    seconds: list[SecondVerdict] = field(default_factory=list)
    cell_change: float = CELL_CHANGE
    min_live: int = MIN_LIVE_REGIONS

    @property
    def judged(self) -> int:
        return len(self.seconds)

    @property
    def failed(self) -> list[SecondVerdict]:
        return [second for second in self.seconds if not second.passed]

    @property
    def passed(self) -> bool:
        return bool(self.seconds) and not self.failed

    @property
    def pass_share(self) -> float:
        if not self.seconds:
            return 0.0
        return (len(self.seconds) - len(self.failed)) / len(self.seconds)

    def worst(self, limit: int = 8) -> list[SecondVerdict]:
        """The emptiest seconds, for a report that names what to fix."""
        return sorted(self.seconds, key=lambda second: len(second.live))[:limit]


def _region_change(first: np.ndarray, others: list[np.ndarray]) -> float:
    """How far the busiest cell of a region moved, in grey levels."""
    best = 0.0
    for other in others:
        best = max(best, float(np.max(np.abs(first - other))))
    return best


def _region_change(first: np.ndarray, others: list[np.ndarray]) -> float:
    """How far the busiest cell of a region moved, in grey levels."""
    best = 0.0
    for other in others:
        best = max(best, float(np.max(np.abs(first - other))))
    return best


def analyse_stream(streams: list[dict[str, np.ndarray]], *,
                   samples_per_second: int = SAMPLES_PER_SECOND,
                   cell_change: float = CELL_CHANGE) -> SecondReport:
    """Judge every whole second of already-decoded region signatures. Pure.

    A second passes when at least two regions changed by ``cell_change`` grey
    levels. The change is absolute on purpose: see the module docstring for the
    normalised version this replaced, and for the separation rule that was tried
    and measured out - one large object in one region lifts the median of the
    other five, so a multiplier on the median throws away the very second that
    is visibly busy.
    """
    report = SecondReport(cell_change=cell_change)
    if not streams or samples_per_second <= 0:
        return report
    complete = len(streams) // samples_per_second
    for second in range(complete):
        window = streams[second * samples_per_second:(second + 1) * samples_per_second]
        verdict = SecondVerdict(index=second)
        for name in window[0]:
            first = window[0][name]
            # Against every sample, not only the last: something looping returns
            # to where it started by the end of the second.
            amount = _region_change(first, [frame[name] for frame in window[1:]])
            if amount >= cell_change:
                verdict.live.append(name)
            else:
                verdict.unjudged.append(name)
        report.seconds.append(verdict)
    return report


def analyse_video(path: Path | str, *, ffmpeg: str | None = None,
                  samples_per_second: int = SAMPLES_PER_SECOND,
                  cell_change: float = CELL_CHANGE) -> SecondReport:
    """Decode a file and judge every whole second of it."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    binary = resolve_ffmpeg(ffmpeg)
    if not binary:
        raise RuntimeError("FFmpeg is not available, so the film cannot be measured")
    streams = []
    frames = iter_video_frames(source, fps=float(samples_per_second),
                               width=FRAME_WIDTH, height=FRAME_HEIGHT, ffmpeg=binary)
    for frame in frames:
        streams.append(frame_signatures(frame))
    return analyse_stream(streams, samples_per_second=samples_per_second,
                          cell_change=cell_change)


def format_report(report: SecondReport, *, limit: int = 12) -> str:
    """The verdict, and the emptiest seconds in it."""
    if not report.seconds:
        return "LAYERS: nothing judged - the file is shorter than one second."
    lines = []
    if report.passed:
        lines.append("LAYERS: PASSED - two things moving in every one of %d seconds"
                     % report.judged)
    else:
        lines.append("LAYERS: FAILED - %d of %d seconds (%.0f%%) have fewer than %d things "
                     "moving in them"
                     % (len(report.failed), report.judged,
                        100 * len(report.failed) / report.judged, report.min_live))
    counts = [len(second.live) for second in report.seconds]
    lines.append("  live regions per second: mean %.1f, best %d, worst %d"
                 % (float(np.mean(counts)), max(counts), min(counts)))
    worst = report.worst(limit)
    lines.append("  emptiest seconds:")
    for second in worst:
        lines.append("    %s  %d live  %s" % (
            timecode(second.start), len(second.live),
            " ".join(second.live) if second.live else "(nothing moving)"))
    return "\n".join(lines)
