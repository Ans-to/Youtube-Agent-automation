#!/usr/bin/env python3
"""Render the thirty-second test film with its sound and mux the two together.

The picture is drawn by ``video_studio/films/render_test.mjs``. The sound is
synthesised here, from the same plan the picture was drawn from: the film emits
one JSON document with its shots and its cue sheet, and this tool renders that
sheet, mixes it under the procedural bed from ``audio_design``, brings the result
to delivery loudness, and joins it to the frames.

Nothing here is sampled or downloaded. Every sound is arithmetic.

    python tools/render_test_film.py                       # full 30 s at 1280
    python tools/render_test_film.py --width 1920          # master size
    python tools/render_test_film.py --frames-only         # picture, no sound
    python tools/render_test_film.py --audio-only          # sound, no picture

Exit codes: 0 delivered, 1 a step failed, 2 a tool is missing, 3 the film and
its cue sheet disagree about time.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video_studio"))

import audio_design  # noqa: E402 - path set up above

FILM = ROOT / "video_studio" / "films" / "render_test.mjs"
FPS = 30
LOUDNESS_TARGET = -20.0  # LUFS, integrated: this film has no voice, see --lufs
TRUE_PEAK_CEILING = -1.0  # dBTP
# The bed sits under the design. The subject of this film is a sound - keys, a
# press, a plate landing - so the underscore gives way to it instead of the cues
# being pushed up until a keystroke is louder than a click.
BED_GAIN = 0.85


class ToolMissing(RuntimeError):
    pass


def resolve_ffmpeg() -> str:
    try:
        import imageio_ffmpeg  # noqa: WPS433 - optional dependency, resolved at run
        path = imageio_ffmpeg.get_ffmpeg_exe()
        if path and Path(path).exists():
            return path
    except Exception:  # pragma: no cover - fallback only
        pass
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise ToolMissing("FFmpeg not found (pip install imageio-ffmpeg)")


def resolve_node() -> str:
    found = shutil.which("node")
    if not found:
        raise ToolMissing("node not found")
    return found


def plan_from_film(node: str) -> dict:
    """The film's own plan: shots, cues, duration. One source of truth."""
    result = subprocess.run(
        [node, str(FILM), "--cues"],
        cwd=str(ROOT), capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("the film could not describe itself:\n" + result.stderr[-2000:])
    return json.loads(result.stdout)


def check_plan(plan: dict) -> None:
    duration = float(plan["duration"])
    shots = plan["shots"]
    covered = 0.0
    for shot in shots:
        if shot["end"] <= shot["start"]:
            raise ValueError("shot %s ends before it starts" % shot["id"])
        covered += shot["end"] - shot["start"]
    if abs(covered - duration) > 1e-6:
        raise ValueError("shots cover %.3f s of a %.3f s film" % (covered, duration))
    for cue in plan["cues"]:
        if not 0.0 <= cue["at"] < duration:
            raise ValueError("cue at %.3f s is outside the film" % cue["at"])
        if not 0.02 <= cue["length"] <= 2.0:
            raise ValueError("cue at %.3f s has a length out of range" % cue["at"])
        if not 0.0 <= cue["gain"] <= 1.0:
            raise ValueError("cue at %.3f s has a gain out of range" % cue["at"])
    for a, b in zip(shots, shots[1:]):
        if a["arrive"] == b["arrive"] and a["arrive"] != "cut":
            # A repeated device back to back is the owner's "don't always use the
            # same transition" note, and it is cheap to catch here.
            raise ValueError("shots %s and %s repeat the %r transition"
                             % (a["id"], b["id"], a["arrive"]))


def render_frames(node: str, plan: dict, out_dir: Path, width: int) -> Path:
    frames = out_dir / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    have = len(list(frames.glob("frame-*.jpg")))
    want = int(round(float(plan["duration"]) * FPS))
    if have == want:
        print("frames: %d already rendered" % have)
        return frames
    result = subprocess.run(
        [node, str(FILM), "--out", str(frames), "--width", str(width),
         "--from", "0", "--to", str(want), "--quiet"],
        cwd=str(ROOT), check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("the film failed to render")
    have = len(list(frames.glob("frame-*.jpg")))
    if have != want:
        raise RuntimeError("expected %d frames, found %d" % (want, have))
    print("frames: %d rendered at %d px" % (have, width))
    return frames


def render_sound(plan: dict, out_dir: Path) -> tuple[Path, dict]:
    """The bed, the scene markers and the authored cues, in one pass."""
    duration = float(plan["duration"])
    shots = plan["shots"]
    scene_durations = [round(s["end"] - s["start"], 6) for s in shots]
    mix = out_dir / "mix.wav"
    report = audio_design.render_sound_design(
        mix, duration, scene_durations, sfx_cues=plan["cues"], bed_gain=BED_GAIN,
    )
    print("sound: %d cues (%d authored) over %.2f s"
          % (report["sfx_cue_count"] + report["scene_cue_count"],
             report["sfx_cue_count"], duration))
    return mix, report


LOUDNESS = re.compile(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS")
TRUE_PEAK = re.compile(r"Peak:\s*(-?\d+(?:\.\d+)?)\s*dBFS")


def measure(path: Path, ffmpeg: str) -> tuple[float, float]:
    """Integrated loudness and true peak, from FFmpeg's own meter.

    Only the summary block is read. ``ebur128`` also prints one line per moment
    of audio, and the first of those is always "I: -70.0 LUFS" because it is
    measured at the start of the file. Reading the whole log and taking the first
    match made this tool believe a perfectly good mix was silent and apply
    fifty-six decibels of gain to it.
    """
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-nostats", "-i", str(path),
         "-filter_complex", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("could not measure loudness:\n" + result.stderr[-1500:])
    summary = result.stderr.rsplit("Summary:", 1)[-1]
    loud = LOUDNESS.search(summary)
    peak = TRUE_PEAK.search(summary)
    if not (loud and peak):
        raise RuntimeError("loudness summary not understood")
    return float(loud.group(1)), float(peak.group(1))


args_verbose = [False]


def master_audio(mix: Path, out_dir: Path, ffmpeg: str, target: float) -> tuple[Path, dict]:
    """Bring the mix to the delivery loudness with a linear gain and a limiter.

    Two things were learned the hard way here and both are now checked rather
    than assumed.

    First, one pass is not enough: a limiter takes energy out, so the gain the
    measurement asks for no longer reaches the number it asked from. Each pass
    re-measures the file it actually wrote.

    Second, the ceiling is fixed, not walked down. An earlier version lowered the
    ceiling every time the peak was over, which made the file quieter, which
    asked for more gain, which needed more limiting - it drove itself into four
    decibels of crush and still missed the target. The limiter sits at a fixed
    -2.5 dBFS because it limits sample peaks while the meter reports true peaks,
    and on a signal as clicky as this one those sit about a decibel and a half
    above the sample peaks.
    """
    before_lufs, before_peak = measure(mix, ffmpeg)
    limit_db = TRUE_PEAK_CEILING - 3.0
    gain = target - before_lufs
    mastered = out_dir / "master.wav"
    after_lufs, after_peak = before_lufs, before_peak
    passes = 0
    for passes in range(1, 6):
        filters = "volume=%.3fdB,alimiter=limit=%.4f:attack=2:release=50:level=false" % (
            gain, 10 ** (limit_db / 20.0),
        )
        subprocess.run(
            [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(mix),
             "-af", filters, "-ar", "48000", "-c:a", "pcm_s16le", str(mastered)],
            check=True,
        )
        after_lufs, after_peak = measure(mastered, ffmpeg)
        if args_verbose[0]:
            print("  pass %d: gain %+.1f dB -> %.1f LUFS, %.1f dBTP"
                  % (passes, gain, after_lufs, after_peak))
        if abs(after_lufs - target) <= 0.3:
            break
        gain += target - after_lufs
    data = {
        "target_lufs": target,
        "lufs_before": round(before_lufs, 2),
        "lufs_after": round(after_lufs, 2),
        "gain_db": round(gain, 2),
        "passes": passes,
        "peak_before_dbfs": round(before_peak, 2),
        "peak_after_dbfs": round(after_peak, 2),
        "limiter_ceiling_db": round(limit_db, 2),
        # How hard the limiter had to work, in decibels. Written down because it
        # is the number that says whether a loudness target cost the sound
        # anything: nothing on a mix with headroom, a lot on a sparse one.
        "limiting_db": round(max(0.0, before_peak + gain - limit_db), 2),
        "peak_ceiling_dbtp": TRUE_PEAK_CEILING,
    }
    print("loudness: %.1f -> %.1f LUFS (gain %+.1f dB, %d pass%s), true peak %.1f dBTP"
          % (before_lufs, after_lufs, gain, passes, "" if passes == 1 else "es", after_peak))
    if after_peak > TRUE_PEAK_CEILING + 0.05:
        raise RuntimeError("true peak %.1f dBTP is over the ceiling" % after_peak)
    if abs(after_lufs - target) > 0.6:
        raise RuntimeError(
            "could not reach %.1f LUFS without crushing the transients; best was %.1f"
            % (target, after_lufs))
    return mastered, data


def mux(frames: Path, audio: Path | None, out: Path, ffmpeg: str) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-framerate", str(FPS), "-i", str(frames / "frame-%06d.jpg"),
    ]
    if audio is not None:
        command += ["-i", str(audio)]
    command += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
    ]
    if audio is not None:
        command += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
    command += ["-movflags", "+faststart", str(out)]
    subprocess.run(command, check=True)
    print("film: %s" % out)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(ROOT / "workspace" / "generated" / "render-test"),
                        help="working directory for frames, audio and the film")
    parser.add_argument("--width", type=int, default=1280, help="output width in pixels")
    parser.add_argument("--frames-only", action="store_true", help="picture, no sound")
    parser.add_argument("--audio-only", action="store_true", help="sound, no picture")
    parser.add_argument("--verbose", action="store_true", help="show each mastering pass")
    parser.add_argument("--lufs", type=float, default=LOUDNESS_TARGET,
                        help="integrated loudness target (default %.1f)" % LOUDNESS_TARGET)
    args = parser.parse_args(argv)

    args_verbose[0] = args.verbose
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        node = resolve_node()
        ffmpeg = resolve_ffmpeg()
    except ToolMissing as exc:
        print("missing tool: %s" % exc, file=sys.stderr)
        return 2

    plan = plan_from_film(node)
    try:
        check_plan(plan)
    except ValueError as exc:
        print("plan refused: %s" % exc, file=sys.stderr)
        return 3

    report = {"duration": plan["duration"], "shots": plan["shots"],
              "cue_count": len(plan["cues"])}
    audio = None
    if not args.frames_only:
        mix, sound_report = render_sound(plan, out_dir)
        report["sound"] = sound_report
        audio, loudness = master_audio(mix, out_dir, ffmpeg, args.lufs)
        report["loudness"] = loudness
    if not args.audio_only:
        frames = render_frames(node, plan, out_dir, args.width)
        name = "render-test-%d.mp4" % args.width
        mux(frames, audio, out_dir / name, ffmpeg)
        report["film"] = str(out_dir / name)

    (out_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n",
                                         encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
