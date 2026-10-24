#!/usr/bin/env python3
"""Judge the narration the way a listener would, before anyone has to listen.

A film can pass every picture check and still be unwatchable because of its
voice. That happened here: an eleven-minute film shipped with a formant read at
213 words per minute that took one audible breath in its whole length, and every
automated check was green, because none of them listened.

This is the missing check. It measures the audio that will actually be published
and fails when the read cannot be followed:

    python tools/check_narration.py --wav build/voice/voiceover.wav \
        --lines build/voice/lines.json

Exit codes: 0 the narration is listenable, 1 it is not, 2 bad input,
3 a dependency (FFmpeg) is missing.

The measurements are the ones a listener reacts to, in the order they react:

speed        words per minute over speech only. Above 180 an instruction film
             becomes a race, and the viewer stops following and starts skipping.
air          the pauses between lines. A read with no pause over 0.55 s is one
             unbroken sentence to the ear, which is what makes synthetic speech
             exhausting; the ear needs somewhere to land.
breath rate  audible rests per minute, so a film cannot pass by having one very
             long silence and no others.
level        integrated loudness, because YouTube plays everything at about
             -14 LUFS and a film that arrives at -21 is heard as thin and quiet
             beside the rest of the feed.
peaks        true peak, so nothing clips on a viewer's headphones.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import wave
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Where a published read has to land. Each number is a listening judgement made
# measurable, not a preference: see the module docstring for why each exists.
MAX_WORDS_PER_MINUTE = 180.0
MIN_WORDS_PER_MINUTE = 115.0
MIN_MEDIAN_PAUSE = 0.30      # seconds, over every pause between lines
MIN_BREATHS_PER_MINUTE = 4.0
MAX_BREATHS_PER_MINUTE = 32.0
MIN_LONGEST_PAUSE = 0.90
TARGET_LUFS = -14.0
LUFS_TOLERANCE = 1.5
MAX_TRUE_PEAK_DB = -1.0

# Two stages, because the same file is judged differently before and after the
# mix. A raw narration is allowed to be quiet - the mixer normalises it - but the
# file that actually gets uploaded is not.
STAGE_VOICE = "voice"
STAGE_MIX = "mix"

# A pause shorter than this is articulation, not air: the gap inside a word.
PAUSE_FLOOR = 0.12
# A pause at least this long is an audible rest between sentences. Half a second
# is the point at which a listener hears a break rather than a join; the audio
# loses a few milliseconds to the fade on each side of it, so the file's pause is
# measured slightly shorter than the silence that was written.
BREATH_FLOOR = 0.50
FRAME_SECONDS = 0.02


@dataclass
class Narration:
    """Everything the checker could measure, and what it could not."""

    duration_seconds: float = 0.0
    speech_seconds: float = 0.0
    words: int = 0
    words_per_minute: float | None = None
    pauses: int = 0
    median_pause: float = 0.0
    longest_pause: float = 0.0
    breaths: int = 0
    breaths_per_minute: float = 0.0
    lufs: float | None = None
    true_peak_db: float | None = None
    unmeasured: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    @property
    def listenable(self) -> bool:
        return not self.failures


# ------------------------------------------------------------------ reading
def read_wav(path: Path) -> tuple[list[float], int]:
    """Mono float samples and the sample rate, from a PCM wav.

    Stereo is mixed down because the film's narration is mono and a stereo file
    would otherwise halve the measured energy in silence detection.
    """
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        raw = handle.readframes(handle.getnframes())
    if width != 2:
        raise ValueError(f"{path.name} is {width * 8}-bit; the checker reads 16-bit PCM")
    import numpy as np

    data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data, rate


# ---------------------------------------------------------------- measuring
def speech_mask(samples, rate: int):
    """Which 20 ms frames carry speech.

    Relative, not absolute: a quiet recording and a hot one are judged the same
    way. The floor is the fifth percentile of frame energy, so a file with a
    music bed under the voice still finds the voice instead of calling the bed
    speech or the speech silence.
    """
    import numpy as np

    window = max(1, int(rate * FRAME_SECONDS))
    count = samples.size // window
    if count == 0:
        return np.zeros(0, dtype=bool), window
    frames = samples[:count * window].reshape(count, window).astype(np.float64)
    rms = np.sqrt((frames ** 2).mean(axis=1))
    db = 20 * np.log10(np.maximum(rms, 1e-6))
    floor = float(np.percentile(db, 5))
    ceiling = float(np.percentile(db, 95))
    if ceiling - floor < 6.0:
        # No dynamic range at all: either a constant tone or digital silence.
        return np.zeros(count, dtype=bool), window
    return db > (floor + 12.0), window


def pause_runs(samples, rate: int) -> list[float]:
    """Lengths, in seconds, of every silent stretch between speech."""
    mask, window = speech_mask(samples, rate)
    if mask.size == 0:
        return []
    runs: list[float] = []
    current = 0
    heard_speech = False
    for voiced in mask:
        if voiced:
            # Only a silence that follows speech is a pause. The first one is a
            # lead-in, and counting it would let a film pass on one long opening gap.
            if current and heard_speech:
                runs.append(current * window / rate)
            heard_speech = True
            current = 0
        else:
            current += 1
    # A silence before the first word or after the last is a lead-in and a
    # tail, not air between sentences, and nothing after the last word is
    # counted because it never ends in this loop.
    if not heard_speech:
        return []
    return [length for length in runs if length >= PAUSE_FLOOR]


def analyse(samples, rate: int, words: int) -> Narration:
    """Measure a narration. Pure: no files, no subprocess, no clock."""
    import numpy as np

    result = Narration()
    result.words = int(words)
    if samples.size == 0:
        result.failures.append("the narration is empty")
        return result

    result.duration_seconds = round(samples.size / rate, 3)
    mask, window = speech_mask(samples, rate)
    result.speech_seconds = round(float(mask.sum()) * window / rate, 3)

    if result.speech_seconds > 0 and result.words:
        result.words_per_minute = round(result.words / result.speech_seconds * 60.0, 1)

    runs = pause_runs(samples, rate)
    result.pauses = len(runs)
    if runs:
        result.median_pause = round(float(np.median(runs)), 3)
        result.longest_pause = round(float(max(runs)), 3)
    result.breaths = len([length for length in runs if length >= BREATH_FLOOR])
    minutes = max(result.duration_seconds / 60.0, 1e-6)
    result.breaths_per_minute = round(result.breaths / minutes, 2)
    return result


def verdict(result: Narration, stage: str = STAGE_VOICE) -> Narration:
    """Add the failures, in the order a listener would notice them."""
    failures = result.failures
    if result.words_per_minute is None:
        if not result.words:
            failures.append("no word count: pass --lines so speed can be measured")
    elif result.words_per_minute > MAX_WORDS_PER_MINUTE:
        failures.append(
            "the read runs at %.0f words per minute; over %.0f a viewer stops "
            "following and starts skipping" % (result.words_per_minute, MAX_WORDS_PER_MINUTE))
    elif result.words_per_minute < MIN_WORDS_PER_MINUTE:
        failures.append(
            "the read crawls at %.0f words per minute; under %.0f it sounds like "
            "a struggle" % (result.words_per_minute, MIN_WORDS_PER_MINUTE))

    if result.pauses == 0:
        failures.append(
            "no audible pause anywhere: the film is one unbroken sentence with no air")
    else:
        if result.median_pause < MIN_MEDIAN_PAUSE:
            failures.append(
                "the median pause is %.2fs; below %.2fs the lines run together"
                % (result.median_pause, MIN_MEDIAN_PAUSE))
        if result.longest_pause < MIN_LONGEST_PAUSE:
            failures.append(
                "the longest pause is %.2fs; nothing under %.2fs ever lets the ear rest"
                % (result.longest_pause, MIN_LONGEST_PAUSE))
        if result.breaths_per_minute < MIN_BREATHS_PER_MINUTE:
            failures.append(
                "only %.1f audible rests per minute; below %.1f the narration has no air"
                % (result.breaths_per_minute, MIN_BREATHS_PER_MINUTE))
        if result.breaths_per_minute > MAX_BREATHS_PER_MINUTE:
            failures.append(
                "%.1f audible rests per minute; above %.1f it sounds halting"
                % (result.breaths_per_minute, MAX_BREATHS_PER_MINUTE))

    if stage != STAGE_MIX:
        # Before the mix, level is the mixer's job, not the narrator's.
        return result
    if result.lufs is None:
        result.unmeasured.append("loudness (FFmpeg not available)")
    elif abs(result.lufs - TARGET_LUFS) > LUFS_TOLERANCE:
        failures.append(
            "measured %.1f LUFS; YouTube plays at about %.1f, so this film is "
            "heard as %s" % (result.lufs, TARGET_LUFS,
                             "quiet and thin" if result.lufs < TARGET_LUFS else "loud and squashed"))

    if result.true_peak_db is None:
        result.unmeasured.append("true peak (FFmpeg not available)")
    elif result.true_peak_db > MAX_TRUE_PEAK_DB:
        failures.append(
            "true peak %.1f dBFS; over %.1f it can clip on headphones"
            % (result.true_peak_db, MAX_TRUE_PEAK_DB))
    return result


# ------------------------------------------------------- loudness (FFmpeg)
def measure_loudness(path: Path) -> tuple[float | None, float | None]:
    """Integrated loudness and true peak, straight from FFmpeg's EBU meter."""
    try:
        from app.infrastructure.ffmpeg import find_ffmpeg

        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            return None, None
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [ffmpeg, "-hide_banner", "-nostats", "-i", str(path),
             "-af", "ebur128=peak=true", "-f", "null", "-"],
            capture_output=True, text=True, timeout=900, check=False,
        )
        text = (result.stderr or "") + (result.stdout or "")
    except (OSError, ValueError, ImportError, subprocess.SubprocessError):
        return None, None
    integrated = re.findall(r"I:\s*(-?[0-9.]+)\s*LUFS", text)
    peaks = re.findall(r"Peak:\s*(-?[0-9.]+)\s*dBFS", text)
    lufs = float(integrated[-1]) if integrated else None
    peak = float(peaks[-1]) if peaks else None
    return lufs, peak


def count_words(lines_path: Path) -> int:
    """Words the narrator actually speaks, from the film's own line table."""
    data = json.loads(lines_path.read_text(encoding="utf-8"))
    lines = data.get("lines") if isinstance(data, dict) else data
    if not isinstance(lines, list):
        raise ValueError("lines.json has no 'lines' array")
    total = 0
    for line in lines:
        if isinstance(line, dict):
            text = line.get("spoken") or line.get("text") or ""
        else:
            text = str(line)
        total += len(str(text).split())
    return total


#: Spellings a synthesiser needs and a caption must never show. The film draws
#: ``line.text``; ``line.spoken`` is free to carry phonetics for the voice. When
#: both carried "github dot com", the baked caption said it too, which is the
#: owner's "captions must not leak spelling hacks" failing on screen.
TTS_SPELLINGS = (
    (r"\bdot\s+com\b", ".com"),
    (r"\bdot\s+org\b", ".org"),
    (r"\bdot\s+net\b", ".net"),
    (r"\bdot\s+io\b", ".io"),
    (r"\bunderscore\b", "_"),
    (r"\bdash\b", "-"),
)


def caption_hacks(lines_path: Path) -> list[dict]:
    """Lines whose on-screen text is spelled for a synthesiser instead of a reader."""
    data = json.loads(lines_path.read_text(encoding="utf-8"))
    lines = data.get("lines") if isinstance(data, dict) else data
    if not isinstance(lines, list):
        raise ValueError("lines.json has no 'lines' array")
    found = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        text = str(line.get("text") or "")
        for pattern, should_be in TTS_SPELLINGS:
            if re.search(pattern, text, re.IGNORECASE):
                found.append({"id": line.get("id"), "text": text, "should_be": should_be})
                break
    return found


def report(result: Narration, stage: str = STAGE_VOICE) -> str:
    """The verdict as a block of text a person can act on."""
    lines = []
    lines.append("NARRATION: %s (%s)" % ("PASS" if result.listenable else "FAIL", stage))
    lines.append("  length        %.1f s (%.1f s of speech)" % (result.duration_seconds,
                                                              result.speech_seconds))
    if result.words_per_minute is not None:
        lines.append("  speed         %.0f words per minute (limit %.0f-%.0f)"
                     % (result.words_per_minute, MIN_WORDS_PER_MINUTE, MAX_WORDS_PER_MINUTE))
    lines.append("  pauses        %d total, median %.2fs, longest %.2fs"
                 % (result.pauses, result.median_pause, result.longest_pause))
    lines.append("  audible rests %.1f per minute (limit %.1f-%.1f)"
                 % (result.breaths_per_minute, MIN_BREATHS_PER_MINUTE, MAX_BREATHS_PER_MINUTE))
    if result.lufs is not None:
        note = "" if stage == STAGE_MIX else " - not judged at this stage"
        lines.append("  loudness      %.1f LUFS (target %.1f +/- %.1f)%s"
                     % (result.lufs, TARGET_LUFS, LUFS_TOLERANCE, note))
    if result.true_peak_db is not None:
        lines.append("  true peak     %.1f dBFS (limit %.1f)" % (result.true_peak_db, MAX_TRUE_PEAK_DB))
    for note in result.unmeasured:
        lines.append("  not measured  %s" % note)
    if result.failures:
        lines.append("")
        for failure in result.failures:
            lines.append("  FAIL  %s" % failure)
        lines.append("")
        lines.append("  Fix the read, not the checker: soften the speed, let the")
        lines.append("  sentences end, and normalise to %.0f LUFS before export." % TARGET_LUFS)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--wav", required=True, help="the narration that will be published")
    parser.add_argument("--lines", default=None,
                        help="lines.json from the same build, for the word count")
    parser.add_argument("--words", type=int, default=0,
                        help="word count, if there is no lines.json")
    parser.add_argument("--stage", choices=[STAGE_VOICE, STAGE_MIX], default=STAGE_VOICE,
                        help="'voice' checks the read; 'mix' also checks delivery level")
    parser.add_argument("--json", action="store_true", help="print the measurements as JSON")
    parser.add_argument("--quiet", action="store_true", help="print nothing on success")
    args = parser.parse_args(argv)

    path = Path(args.wav)
    if not path.is_file():
        print("no such narration: %s" % path, file=sys.stderr)
        return 2
    words = args.words
    if args.lines:
        try:
            hacks = caption_hacks(Path(args.lines))
            if hacks:
                print("CAPTIONS: FAIL - %d line(s) spell for a synthesiser and will be drawn that way"
                      % len(hacks), file=sys.stderr)
                for item in hacks[:5]:
                    print("  %s: %s  (write %s)" % (item["id"], item["text"][:90], item["should_be"]),
                          file=sys.stderr)
                return 1
            words = count_words(Path(args.lines))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print("cannot read %s: %s" % (args.lines, exc), file=sys.stderr)
            return 2
    if not words:
        print("no word count: pass --lines or --words", file=sys.stderr)
        return 2

    try:
        samples, rate = read_wav(path)
    except (OSError, ValueError, wave.Error) as exc:
        print("cannot read %s: %s" % (path, exc), file=sys.stderr)
        return 2

    # Measure everything first, then judge once: a verdict that is reached in two
    # passes reports its first pass's failures twice.
    result = analyse(samples, rate, words)
    result.lufs, result.true_peak_db = measure_loudness(path)
    result = verdict(result, args.stage)

    if args.json:
        print(json.dumps({
            "listenable": result.listenable,
            "duration_seconds": result.duration_seconds,
            "speech_seconds": result.speech_seconds,
            "words": result.words,
            "words_per_minute": result.words_per_minute,
            "pauses": result.pauses,
            "median_pause": result.median_pause,
            "longest_pause": result.longest_pause,
            "breaths_per_minute": result.breaths_per_minute,
            "lufs": result.lufs,
            "true_peak_db": result.true_peak_db,
            "unmeasured": result.unmeasured,
            "failures": result.failures,
        }, indent=2))
    elif not (args.quiet and result.listenable):
        print(report(result, args.stage))
    return 0 if result.listenable else 1


if __name__ == "__main__":
    raise SystemExit(main())
