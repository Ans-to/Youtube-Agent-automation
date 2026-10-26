#!/usr/bin/env python3
"""Render the hand-authored film in ``video_studio/films/`` end to end.

The film is a real authored animation script (Canvas drawing code with an
explicit timeline), not a storyboard template. This driver only wraps it:

0. voice     - optional: narrate the film's script with a local neural voice and
                hand the picture the measured line timings and mouth envelope;
1. frames    - run the film script; it rasterises 3840x2160 frames itself
                and writes ``manifest.json`` / ``film.json`` / ``timeline.txt``;
2. soundtrack- synthesise the score the film declares in ``film.json``;
2b. mix      - when there is a voice, duck the score under it and sum the two;
3. validate  - contiguous numbering, exact dimensions, real image headers;
4. encode    - H.264 + AAC 4K master and a delivery copy with FFmpeg;
5. motion    - measure real frame-to-frame change on the encoded delivery copy
                and fail if the film drifts back into static slides;
5b. holds    - ask the delivered file whether the *picture* ever stopped moving
                for more than a second, ignoring grain and drifting decoration;
                a film that holds is a failed film, so this fails the render;
6. audit     - run the studio's content/brand/legal/technical auditor.

Everything runs locally: no cloud renderer, no API key, no third-party assets.

    python tools/render_authored_film.py --out workspace/generated/motion-film

Exit codes: 0 rendered, 1 a step failed, 2 invalid input, 3 a dependency is
missing (node, the canvas module, or FFmpeg).
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "video_studio"))

import render_motion_film as base  # noqa: E402 - path set up above

DEFAULT_SCRIPT = "video_studio/films/every_frame_is_code.mjs"


# The rejected first cut measured a mean delta of 0.819 with 51.4% near-static
# frames. These gates are deliberately stricter than that baseline.
MIN_MEAN_DELTA = 1.2
MAX_STATIC_SHARE = 0.15

# Defaults for the kinetic film. A film may declare `motion_gate` in its own
# film.json and override these; the summary always records which gate was used.
DEFAULT_GATE = {"min_mean": MIN_MEAN_DELTA, "max_static": MAX_STATIC_SHARE}
STATIC_BELOW = 0.5

# Longest a picture may sit still. Grain, a drifting dot field, a progress bar or
# a creeping camera do not buy a shot any extra time: the check removes all four
# before it decides. One second is already long enough for a viewer to think the
# video has stalled.
MAX_STILL_SECONDS = 1.0
# The bar for a picture that actually changes. See ``video_studio/composition.py``:
# measured on this repository's films, the character film's longest arrangement
# is 10.5 s and this tutorial film's is 79.5 s. Twelve seconds is generous.
MAX_COMPOSITION_HOLD_SECONDS = 12.0

# The contact sheet is a 5x2 tile: this many frames spans the whole film.
CONTACT_TILES = 10


def contact_sheet_fps(duration_seconds: float) -> float:
    """Sampling rate that fills the contact sheet exactly once, whatever the length.

    A fixed cap truncates short films: 0.5 fps over a 12 s cut gives six frames
    for a ten-tile sheet, so four tiles were black. Too low a floor truncates long
    ones, which is why the rate is derived from the duration rather than chosen.
    """
    return max(0.02, CONTACT_TILES / max(0.1, float(duration_seconds)))


def log(message: str) -> None:
    base.log(message)


def step_frames(
    script: Path, frames_dir: Path, width: int, height: int, fps: int, quality: int,
    voice_lines: Path | None = None, slice_frames: int = 0, script_args: list[str] | None = None,
) -> dict:
    """Draw the film, in slices of `slice_frames` when asked.

    A canvas renderer allocates native pixel buffers that the V8 heap never sees,
    so a long film climbs to several gigabytes of RSS and then stops: the
    collector has nothing to feel. Restarting the process every few thousand
    frames puts a ceiling on that, at the cost of re-running the script setup,
    and the frames land in one directory named by absolute index, so the encode
    does not care how they were made.
    """
    def command_for(start, stop):
        command = [
            base.resolve_node(),
            str(script),
            "--out",
            str(frames_dir),
            "--width",
            str(width),
            "--height",
            str(height),
            "--fps",
            str(fps),
            "--quality",
            str(quality),
        ]
        if voice_lines is not None:
            command += ["--voice-lines", str(voice_lines)]
        # A generated film needs its brief; a hand-authored one has none. Both
        # are the same renderer, so the extra arguments are passed through
        # rather than forking the tool.
        if script_args:
            command += list(script_args)
        if slice_frames:
            command += ["--from", str(start), "--to", str(stop)]
        return command

    if not slice_frames:
        result = base.run(command_for(0, 0), timeout=7200)
        if result.returncode != 0:
            tail = (result.stderr or result.stdout or "")[-2000:]
            raise RuntimeError("the film script failed:\n" + tail)
    else:
        plan = base.run(command_for(0, 0) + ["--plan"], timeout=600)
        if plan.returncode != 0:
            tail = (plan.stderr or plan.stdout or "")[-2000:]
            raise RuntimeError("the film script could not report its plan:\n" + tail)
        total = int(json.loads(plan.stdout)["frames"])
        for start in range(0, total, slice_frames):
            stop = min(total, start + slice_frames)
            log("   frames %d-%d of %d" % (start, stop - 1, total))
            result = base.run(command_for(start, stop), timeout=7200)
            if result.returncode != 0:
                tail = (result.stderr or result.stdout or "")[-2000:]
                raise RuntimeError("the film script failed at frame %d:\n%s" % (start, tail))

    manifest_path = frames_dir / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("the film script did not write manifest.json")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


# The loudness a published film should arrive at. YouTube normalises playback to
# about -14 LUFS, and a film that arrives at -21 is turned up by the viewer and
# then sounds thin beside everything else in the feed. Measured, then corrected:
# never a guess, and never a second encode of the picture.
TARGET_LUFS = -14.0
LOUDNESS_CEILING_DB = 18.0
# A delivery above -1.0 dBFS true peak crackles on headphones once it is AAC.
TARGET_TRUE_PEAK = -1.0


def measure_loudness(path: Path, ffmpeg: str) -> float | None:
    """Integrated loudness of a file in LUFS, or None if it cannot be measured."""
    result = base.run([
        ffmpeg, "-hide_banner", "-nostats", "-i", str(path),
        "-af", "loudnorm=print_format=json", "-f", "null", "-",
    ], timeout=1800)
    text = (result.stderr or "") + (result.stdout or "")
    match = re.search(r'"input_i"\s*:\s*"?(-?[0-9.]+)"?', text)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    return value if -70.0 < value < 0.0 else None


def measure_true_peak(path: Path, ffmpeg: str) -> float | None:
    """True peak of a file in dBFS, or None if it cannot be measured.

    True peak, not sample peak: the AAC encoder the delivery is written with can
    put an inter-sample overshoot between two samples that were both inside the
    limiter. It is inaudible on speakers and audible as a crackle on headphones,
    which is exactly why it is measured on the finished file.
    """
    result = base.run([
        ffmpeg, "-hide_banner", "-nostats", "-i", str(path),
        "-af", "loudnorm=print_format=json", "-f", "null", "-",
    ], timeout=1800)
    text = (result.stderr or "") + (result.stdout or "")
    match = re.search(r'"input_tp"\s*:\s*"?(-?[0-9.]+)"?', text)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    return value


def normalise_loudness(path: Path, ffmpeg: str, target: float = TARGET_LUFS) -> dict:
    """Bring a mix to the delivery loudness, limiting rather than clipping.

    The gain is applied once, from a measurement of the real file, and the limiter
    is what stops the peaks from folding over when a mix is pushed up by several
    dB. Both numbers are reported so the artifact can be checked afterwards.
    """
    before = measure_loudness(path, ffmpeg)
    if before is None:
        return {"status": "unmeasured", "target": target}

    # The limiter takes back some of what the gain adds, so one pass overshoots
    # low: -20.9 arrived at -15.3 when asked for -14. Measure, correct, repeat
    # until it is within half a dB, and stop rather than chase it for ever.
    total_gain = 0.0
    current = before
    for _ in range(3):
        gain = target - current
        if abs(gain) < 0.4:
            break
        gain = max(-12.0, min(LOUDNESS_CEILING_DB, gain))
        temporary = path.with_name(path.stem + ".normalised.wav")
        result = base.run([
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(path),
            "-af", f"volume={gain:.2f}dB,alimiter=limit=0.95:level=false",
            str(temporary),
        ], timeout=1800)
        if result.returncode != 0 or not temporary.is_file():
            temporary.unlink(missing_ok=True)
            break
        temporary.replace(path)
        total_gain += gain
        measured = measure_loudness(path, ffmpeg)
        if measured is None:
            break
        current = measured

    return {
        "status": "normalised" if abs(total_gain) > 0.05 else "already",
        "lufs_before": round(before, 1),
        "gain_db": round(total_gain, 1),
        "lufs_after": round(current, 1),
        "target": target,
    }


def step_soundtrack(film_json: Path, output: Path) -> dict:
    """Synthesise exactly the cues the film declares, so picture and sound agree."""
    import audio_design

    film = json.loads(film_json.read_text(encoding="utf-8"))
    cues = film.get("score") or []
    scenes = [round(shot["end"] - shot["start"], 3) for shot in film.get("shots", [])]
    output.parent.mkdir(parents=True, exist_ok=True)
    info = audio_design.render_sound_design(
        output, float(film["duration_seconds"]), scenes, sfx_cues=cues
    )
    info["path"] = str(output)
    return info


def step_voice(script: Path, out_dir: Path, *, voice: str, allow_download: bool,
               backend: str, fps: int) -> dict:
    """Narrate the script locally; writes voiceover.wav, lines.json, envelope.json.

    A formant read is only allowed when it was asked for by name. Left on
    "auto", a machine without Piper would otherwise narrate an eleven-minute film
    in espeak-ng without saying so, which is how the first cut of the long film
    came to exist.
    """
    import voiceover

    out_dir.mkdir(parents=True, exist_ok=True)
    return voiceover.build(
        script, out_dir, voice=voice, allow_download=allow_download,
        backend=backend, fps=fps, allow_formant=(backend == "espeak"),
    )


def judge_narration(wav: Path, lines: Path | None, *, stage: str) -> dict:
    """Run the listening gate; returns its findings, raises nothing.

    The caller decides whether a failure stops the render, so a preview render
    can still be inspected while a master cannot be shipped past it.
    """
    import check_narration

    samples, rate = check_narration.read_wav(wav)
    words = check_narration.count_words(lines) if lines and lines.is_file() else 0
    result = check_narration.analyse(samples, rate, words)
    result.lufs, result.true_peak_db = check_narration.measure_loudness(wav)
    result = check_narration.verdict(result, stage)
    return {
        "listenable": result.listenable,
        "stage": stage,
        "words_per_minute": result.words_per_minute,
        "median_pause": result.median_pause,
        "longest_pause": result.longest_pause,
        "breaths_per_minute": result.breaths_per_minute,
        "lufs": result.lufs,
        "true_peak_db": result.true_peak_db,
        "failures": result.failures,
        "statement": check_narration.report(result, stage),
    }


def master_audio(path: Path, ffmpeg: str, target: float = TARGET_LUFS) -> dict:
    """Make the bed an upload master: true peaks, 48 kHz, and the delivery level.

    The stems are 24 kHz, because that is what the neural narrator speaks at, and
    the mix inherits it with a sample peak close to full scale. That combination
    is a trap: an encoder resampling 24 kHz up to 48 kHz introduces inter-sample
    peaks about a decibel and a half above the samples, loudnorm refuses to lift a
    file past its true-peak ceiling, and the delivered film lands at -14.7 LUFS
    when it was asked for -14.0. Every earlier pass was guessing at peaks that
    only exist between the samples.

    So this limits on a four-times oversampled copy, drops to 48 kHz, and only
    then normalises - two passes, from a measurement of the real file. The result
    is a bed whose peaks are its peaks, at the rate YouTube expects, and a
    loudnorm that is free to land on the target.
    """
    mastered = path.with_name(path.stem + ".mastered.wav")
    result = base.run([
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(path),
        "-af", "aresample=192000,alimiter=limit=0.72:attack=4:release=50:level=false,"
               "aresample=48000",
        "-ac", "2", "-ar", "48000", str(mastered),
    ], timeout=1800)
    if result.returncode != 0 or not mastered.is_file():
        mastered.unlink(missing_ok=True)
        return {"status": "failed", "path": str(path)}

    first = loudnorm_pass(mastered, ffmpeg, target, TARGET_TRUE_PEAK - 0.8)
    chain = loudnorm_pass(mastered, ffmpeg, target, TARGET_TRUE_PEAK - 0.8, measured=first)["chain"]
    normalised = path.with_name(path.stem + ".mastered.delivery.wav")
    result = base.run([
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(mastered),
        "-af", chain, "-ar", "48000", str(normalised),
    ], timeout=1800)
    if result.returncode != 0 or not normalised.is_file():
        normalised.unlink(missing_ok=True)
        return {"status": "unnormalised", "path": str(mastered)}
    mastered.unlink(missing_ok=True)

    lufs = measure_loudness(normalised, ffmpeg)
    peak = measure_true_peak(normalised, ffmpeg)
    return {
        "status": "mastered",
        "path": str(normalised),
        "sample_rate": 48000,
        "channels": 2,
        "lufs": lufs,
        "true_peak_db": peak,
        "target": target,
    }


def step_mix(score: Path, voice_path: Path, output: Path, depth_db: float) -> dict:
    """Duck the score under the voice and print the exact gain it applied."""
    import voice_mix

    return voice_mix.mix(score, voice_path, output, depth_db=depth_db)


def segment_plan(total_frames: int, segments: int) -> list[tuple[int, int]]:
    """Split a frame range into contiguous [start, count) runs for one-pass-each.

    Encoding a 3840x2160 film in a single x264 process needs far more memory than
    a 4 GB laptop or a small CI box has; the process is killed part-way through
    and the driver sees only an empty error. Chunking bounds the encoder's frame
    pools, and concat joins the parts losslessly afterwards.
    """
    if total_frames <= 0:
        raise ValueError("a film needs at least one frame")
    segments = max(1, min(int(segments), total_frames))
    base = total_frames // segments
    extra = total_frames % segments
    plan = []
    cursor = 0
    for index in range(segments):
        count = base + (1 if index < extra else 0)
        plan.append((cursor, count))
        cursor += count
    return plan


def encode_segmented(frames_dir: Path, audio: Path, output: Path, ffmpeg: str, *,
                     fps: int, crf: int, preset: str, audio_bitrate: str,
                     total_frames: int, segments: int, work_dir: Path,
                     extra: list[str] | None = None) -> dict:
    """Encode in chunks, concat them, then mux the audio. Same result, less RAM."""
    work_dir.mkdir(parents=True, exist_ok=True)
    parts = []
    for index, (start, count) in enumerate(segment_plan(total_frames, segments)):
        part = work_dir / ("part-%03d.mp4" % index)
        command = [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-framerate", str(fps), "-start_number", str(start),
            "-i", str(frames_dir / "frame-%06d.jpg"),
            "-frames:v", str(count),
            "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
            "-pix_fmt", "yuv420p",
        ]
        if extra:
            command += extra
        command += [str(part)]
        result = base.run(command, timeout=7200)
        if result.returncode != 0 or not part.is_file() or part.stat().st_size == 0:
            raise RuntimeError("segmented encode failed at part %d: %s"
                               % (index, (result.stderr or result.stdout or "")[-800:]))
        parts.append(part)
        log("   part %d/%d: frames %d-%d" % (index + 1, len(parts) if False else segments,
                                             start, start + count - 1))

    listing = work_dir / "concat.txt"
    listing.write_text("".join("file '%s'\n" % part.resolve() for part in parts), encoding="utf-8")
    command = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(listing),
    ]
    if audio.is_file():
        command += ["-i", str(audio)]
    command += ["-c:v", "copy"]
    if audio.is_file():
        command += ["-c:a", "aac", "-b:a", audio_bitrate, "-ar", "48000", "-shortest"]
    command += ["-movflags", "+faststart", str(output)]
    result = base.run(command, timeout=3600)
    if result.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("concat failed: " + (result.stderr or result.stdout or "")[-1200:])
    for part in parts:
        part.unlink(missing_ok=True)
    listing.unlink(missing_ok=True)
    return {
        "path": str(output),
        "bytes": output.stat().st_size,
        "sha256": base.sha256_file(output),
        "command": command,
        "mode": "segmented",
        "segments": len(parts),
    }


def write_subtitles(lines_path: Path, out_dir: Path) -> dict:
    """Write the SRT and WebVTT a viewer needs, from the lines the voice used.

    A film is not uploadable without a subtitle track, and typing one by hand is
    how a cue drifts half a second away from the read. The cues come from
    ``lines.json`` - the same file the voice stage timed - so the track cannot
    disagree with what is heard.
    """
    if str(Path(__file__).resolve().parent) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
    import film_subtitles  # noqa: PLC0415 - sibling tool, imported on use

    hacks = film_subtitles.caption_hacks(lines_path)
    if hacks:
        raise RuntimeError(
            "the narration text still spells for a synthesiser: "
            + ", ".join("%s %r" % (hack["id"], hack["text"]) for hack in hacks))
    cues = film_subtitles.build_cues(film_subtitles.load_lines(lines_path))
    srt, vtt = film_subtitles.to_srt(cues), film_subtitles.to_vtt(cues)
    film_subtitles.validate_subtitle_text(srt, vtt)
    srt_path, vtt_path = out_dir / "film.srt", out_dir / "film.vtt"
    srt_path.write_text(srt, encoding="utf-8")
    vtt_path.write_text(vtt, encoding="utf-8")
    return {"srt": str(srt_path), "vtt": str(vtt_path), "cues": len(cues),
            "longest_cue_characters": max(len(text) for _, _, text in cues)}


def step_validate(frames_dir: Path) -> dict:
    result = base.run(
        [
            sys.executable,
            str(ROOT / "video_studio" / "validate_frames.py"),
            "--frames",
            str(frames_dir),
            "--manifest",
            str(frames_dir / "manifest.json"),
        ],
        timeout=1800,
    )
    if result.returncode != 0:
        raise RuntimeError("frame validation failed:\n" + (result.stdout or "")[-1200:] + (result.stderr or "")[-1200:])
    try:
        return json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return {"raw": result.stdout.strip()}


def loudnorm_pass(path: Path, ffmpeg: str, target: float, true_peak: float,
                  measured: dict | None = None) -> dict:
    """Measure for a loudnorm pass, or apply one with a previous measurement.

    Two passes, because one is not enough: a single pass has to guess what the
    limiter will take back, and the guess lands a decibel low. The first pass
    reports the file's own numbers, the second lands on the target with a true
    peak that survives an AAC encode.
    """
    chain = ("loudnorm=I=%.1f:TP=%.1f:LRA=11" % (target, true_peak))
    if measured:
        chain += (":measured_I=%s:measured_TP=%s:measured_LRA=%s:measured_thresh=%s"
                  % (measured["input_i"], measured["input_tp"], measured["input_lra"],
                     measured["input_thresh"]))
        if measured.get("target_offset") is not None:
            chain += ":offset=%s" % measured["target_offset"]
        chain += ":linear=true"
    result = base.run([
        ffmpeg, "-hide_banner", "-nostats", "-i", str(path),
        "-af", chain + ":print_format=json", "-f", "null", "-",
    ], timeout=1800)
    text = (result.stderr or "") + (result.stdout or "")
    if measured:
        # The apply pass still prints a report; the caller measures the file itself.
        return {"chain": chain}
    values = {}
    for key in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset"):
        match = re.search(r'"%s"\s*:\s*"?(-?[0-9.]+)"?' % key, text)
        values[key] = match.group(1) if match else "0"
    return values


def verify_delivery_loudness(delivery: Path, audio_track: Path, ffmpeg: str,
                             log=print, target: float = TARGET_LUFS) -> dict:
    """Measure the finished file, and correct it if the encoder changed it.

    Every earlier step works on audio that has not been muxed yet; the file a
    viewer downloads is the only one that matters, so its level and its true peak
    are measured here. When either is wrong, the narration bed is re-normalised
    with a two-pass loudnorm and remuxed under the copied picture - a sound fix
    never costs a second picture encode.

    True peak is checked as well as loudness because the AAC encoder can put an
    overshoot between two samples that were both inside the limiter: inaudible on
    speakers, a crackle on headphones, and invisible to a loudness meter.
    """
    measured = measure_loudness(delivery, ffmpeg)
    if measured is None:
        log("   delivery level could not be measured")
        return {"status": "unmeasured", "target": target}
    peak = measure_true_peak(delivery, ffmpeg)
    # Three tenths, not a whole decibel. A film that measures -14.7 when it was
    # asked for -14 is not "within tolerance"; it is half a decibel quiet, and the
    # trim below costs one audio pass.
    within_level = abs(measured - target) <= 0.3
    within_peak = peak is None or peak <= TARGET_TRUE_PEAK
    if within_level and within_peak:
        log("   delivery %.1f LUFS (target %.1f), true peak %s dBFS (limit %.1f)"
            % (measured, target,
               "%.1f" % peak if peak is not None else "unmeasured", TARGET_TRUE_PEAK))
        return {"status": "ok", "lufs": measured, "true_peak_db": peak, "target": target}

    # Three tenths of a decibel below the limit: the AAC encode of the corrected
    # bed adds about that much back as inter-sample peak.
    headroom = TARGET_TRUE_PEAK - 0.8
    first = loudnorm_pass(audio_track, ffmpeg, target, headroom)
    corrected = audio_track.with_name(audio_track.stem + ".delivery.wav")
    chain = loudnorm_pass(audio_track, ffmpeg, target, headroom, measured=first)["chain"]
    result = base.run([
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(audio_track),
        "-af", chain, "-ar", "48000", str(corrected),
    ], timeout=1800)
    if result.returncode != 0 or not corrected.is_file():
        corrected.unlink(missing_ok=True)
        log("   the delivery correction failed; the file is left as encoded")
        return {"status": "failed", "lufs": measured, "true_peak_db": peak, "target": target}

    temporary = delivery.with_name(delivery.stem + ".remux" + delivery.suffix)
    result = base.run([
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(delivery), "-i", str(corrected),
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest",
        "-movflags", "+faststart", str(temporary),
    ], timeout=3600)
    corrected.unlink(missing_ok=True)
    if result.returncode != 0 or not temporary.is_file():
        temporary.unlink(missing_ok=True)
        log("   delivery is %.1f LUFS and the correction failed" % measured)
        return {"status": "failed", "lufs": measured, "target": target}
    temporary.replace(delivery)

    after = measure_loudness(delivery, ffmpeg)
    after_peak = measure_true_peak(delivery, ffmpeg)
    log("   delivery was %.1f LUFS / %s dBFS true peak; corrected to %.1f LUFS / %s"
        " (target %.1f / %.1f, two-pass loudnorm, picture copied)"
        % (measured, "%.1f" % peak if peak is not None else "?",
           after if after is not None else float("nan"),
           "%.1f" % after_peak if after_peak is not None else "?",
           target, TARGET_TRUE_PEAK))

    # The AAC encode costs about half a decibel of loudness and hands back more
    # than a decibel of inter-sample peak, and loudnorm can see neither: it works
    # on a WAV, not on the file a viewer downloads. This is the loop that closes
    # that gap. It measures the delivered file, and if either number is wrong it
    # re-cuts the audio bed from the original with a cumulative gain and a limiter
    # ceiling, remuxes under a copied picture, and measures again - aiming, then
    # measuring, then correcting, up to four times. On this film it takes two
    # passes and about four seconds.
    trim = 0.0
    ceiling_db = TARGET_TRUE_PEAK - 0.8
    for _ in range(4):
        level_ok = after is not None and abs(target - after) <= 0.3
        peak_ok = after_peak is None or after_peak <= TARGET_TRUE_PEAK
        if level_ok and peak_ok:
            break
        if not peak_ok:
            ceiling_db -= (after_peak - TARGET_TRUE_PEAK) + 0.25
        if not level_ok and after is not None:
            trim += target - after
        trimmed = audio_track.with_name(audio_track.stem + ".trim.wav")
        # Only limit when the gain would actually push the bed's peaks into the
        # ceiling. Limiting a bed that has headroom left squashes it for nothing,
        # and a limiter's own release tail is what put a decoded true peak of
        # -0.4 dBFS on a file whose samples never went above -1.8.
        source_peak = measure_true_peak(audio_track, ffmpeg)
        needs_limit = source_peak is not None and source_peak + trim > TARGET_TRUE_PEAK - 1.0
        chain = "volume=%.2fdB" % trim
        if needs_limit:
            chain += ",alimiter=limit=%.4f:level=false" % (10 ** (ceiling_db / 20))
        result = base.run([
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(audio_track),
            "-af", chain, "-ar", "48000", str(trimmed),
        ], timeout=1800)
        temporary = delivery.with_name(delivery.stem + ".trim" + delivery.suffix)
        if result.returncode == 0 and trimmed.is_file():
            result = base.run([
                ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(delivery), "-i", str(trimmed),
                "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest",
                "-movflags", "+faststart", str(temporary),
            ], timeout=3600)
        trimmed.unlink(missing_ok=True)
        if result.returncode != 0 or not temporary.is_file():
            temporary.unlink(missing_ok=True)
            break
        temporary.replace(delivery)
        after = measure_loudness(delivery, ffmpeg)
        after_peak = measure_true_peak(delivery, ffmpeg)
        log("   trimmed %+.2f dB, ceiling %.1f dBFS: the file now measures %.1f LUFS / %s dBFS true peak"
            % (trim, ceiling_db, after if after is not None else float("nan"),
               "%.1f" % after_peak if after_peak is not None else "?"))

    return {"status": "corrected", "lufs_before": measured, "lufs": after,
            "true_peak_db": after_peak, "target": target, "trim_db": round(trim, 2)}


def measure_motion(video: Path, ffmpeg: str, work_dir: Path, gate: dict | None = None) -> dict:
    """Frame-to-frame luma difference, the same measure the critique was based on."""
    stats_file = work_dir / ".motion-stats.txt"
    if stats_file.exists():
        stats_file.unlink()
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(video),
        "-vf",
        f"tblend=all_mode=difference,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file={stats_file}",
        "-f", "null", "-",
    ]
    result = base.run(command, timeout=3600)
    if result.returncode != 0 or not stats_file.is_file():
        raise RuntimeError("motion measurement failed: " + (result.stderr or "")[-800:])
    values = [float(m.group(1)) for m in re.finditer(r"YAVG=([0-9.]+)", stats_file.read_text())]
    if not values:
        raise RuntimeError("motion measurement produced no samples")
    ordered = sorted(values)
    metrics = {
        "frames_measured": len(values),
        "mean_delta": round(statistics.mean(values), 3),
        "median_delta": round(statistics.median(values), 3),
        "p90_delta": round(ordered[int(len(ordered) * 0.9)], 3),
        "static_share": round(sum(1 for v in values if v < STATIC_BELOW) / len(values), 4),
        "baseline_mean_delta": 0.819,
        "baseline_static_share": 0.514,
    }
    limits = gate or DEFAULT_GATE
    min_mean = float(limits.get("min_mean", DEFAULT_GATE["min_mean"]))
    max_static = float(limits.get("max_static", DEFAULT_GATE["max_static"]))
    metrics["gate"] = {"min_mean": min_mean, "max_static": max_static}
    passed = metrics["mean_delta"] >= min_mean and metrics["static_share"] <= max_static
    metrics["status"] = "passed" if passed else "failed"
    metrics["statement"] = (
        "MOTION SPEC: %s - mean frame delta %.2f (baseline 0.82), "
        "%.1f%% near-static frames (baseline 51.4%%, limit %.0f%%)"
        % (
            "PASSED" if passed else "FAILED",
            metrics["mean_delta"],
            100 * metrics["static_share"],
            100 * max_static,
        )
    )
    return metrics


def mmss(seconds: float) -> str:
    """m:ss for the hold log lines."""
    total = max(0, int(seconds))
    return "%d:%02d" % (total // 60, total % 60)


def measure_composition(video: Path, limit: float = MAX_COMPOSITION_HOLD_SECONDS) -> dict:
    """How often the arrangement on screen changes. See ``video_studio/composition.py``.

    ``measure_motion`` above is satisfied by grain, and the repeat-frame check is
    satisfied by a ticking caption. This one is not satisfied by either, because
    it compares thumbnails of the layout rather than pixels: decoration moves
    every pixel and rearranges nothing.
    """
    import composition as composition_module

    return composition_module.analyse_video(video, max_hold_seconds=limit)


def measure_repeat_frames(video: Path, limit: float = MAX_STILL_SECONDS) -> dict:
    """Frozen-span check on the encoded file. See ``video_studio/repeat_frames.py``.

    ``measure_motion`` above averages the whole film, so a one-second hold inside
    four thousand moving frames disappears into its mean. This one looks for the
    hold itself, and fails closed if it cannot run.
    """
    try:
        import repeat_frames
    except ImportError as exc:  # numpy missing
        raise RuntimeError(
            "the repeat-frame check needs numpy (python -m pip install numpy): %s" % exc)
    return repeat_frames.analyse_video(video, max_still_seconds=limit)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--script", default=DEFAULT_SCRIPT, help="film script to render")
    parser.add_argument("--out", required=True, help="directory for the delivered film")
    parser.add_argument("--width", type=int, default=3840)
    parser.add_argument("--height", type=int, default=2160)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--quality", type=int, default=92)
    parser.add_argument("--delivery-height", type=int, default=1080)
    parser.add_argument("--skip-4k", action="store_true")
    parser.add_argument("--slice-frames", type=int, default=0,
                        help="draw in chunks of this many frames, one process each "
                             "(0 draws the film in a single process)")
    parser.add_argument("--frames", default=None,
                        help="reuse an existing frame directory (skips rendering)")
    parser.add_argument("--script-args", default="",
                        help="extra arguments for the film script, e.g. '--brief path/to/brief.json'")
    parser.add_argument("--voice-script", default=None,
                        help="JSON narration script; synthesise a voiceover and mix it in")
    parser.add_argument("--voice-dir", default=None,
                        help="where the voiceover lives (default: <out>/voice)")
    parser.add_argument("--voice", default="en_US-lessac-medium", help="Piper voice name")
    parser.add_argument("--voice-backend", default="auto", choices=["auto", "kokoro", "piper", "espeak"])
    parser.add_argument("--voice-offline", action="store_true",
                        help="never download voice weights (fail instead)")
    parser.add_argument("--allow-voice-warnings", action="store_true",
                        help="render even if the narration fails the listening gate")
    parser.add_argument("--duck-db", type=float, default=8.5,
                        help="how far the score drops under speech")
    parser.add_argument("--encode-segments", type=int, default=0,
                        help="encode the master in N chunks (0 = one pass, fall back "
                             "to 6 chunks if the single pass is killed)")
    parser.add_argument("--master-crf", type=int, default=20, help="CRF for the master")
    parser.add_argument("--json", action="store_true", help="print the summary as JSON")
    args = parser.parse_args(argv)

    started = time.time()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = out_dir / "build" / "frames"
    script = (ROOT / args.script).resolve()
    script_args = shlex.split(args.script_args or "")
    # A brief is resolved against the repository so the same command works from
    # a checkout, from CI, and from a subdirectory.
    for index, value in enumerate(script_args):
        if value == "--brief" and index + 1 < len(script_args):
            script_args[index + 1] = str((ROOT / script_args[index + 1]).resolve())
        elif value.startswith("--brief="):
            script_args[index] = "--brief=" + str((ROOT / value.split("=", 1)[1]).resolve())

    try:
        ffmpeg, ffprobe = base.resolve_ffmpeg()
    except base.DependencyMissing as exc:
        print(str(exc), file=sys.stderr)
        return 3
    if not script.is_file():
        print("film script not found: %s" % script, file=sys.stderr)
        return 2
    # A narration script that sits next to the film is picked up automatically.
    # Before this, a film shipped silent unless the caller remembered
    # --voice-script, and the default render of a talking-character film had no
    # voice at all — the exact bug a viewer notices first.
    if args.voice_script is None:
        companion = script.with_suffix(".voice.json")
        if companion.is_file():
            args.voice_script = str(companion.relative_to(ROOT)) if companion.is_relative_to(ROOT) else str(companion)
            print("[render] narration script found beside the film: %s" % companion.name)

    if not base.canvas_module_available():
        print("the canvas module is not installed (cd video_studio && npm ci)", file=sys.stderr)
        return 3

    voice_dir = Path(args.voice_dir).resolve() if args.voice_dir else out_dir / "voice"
    step_no = 0

    def step(label: str) -> str:
        # No denominator: the number of steps depends on whether a voice exists,
        # whether subtitles can be written and whether a render is resumed, and a
        # guessed total printed "9/9 measure motion" for four more steps.
        nonlocal step_no
        step_no += 1
        return "== %d %s" % (step_no, label)

    try:
        voice_info = None
        mixed = None
        narration = None
        mix_narration = None
        delivery_level = None
        voice_wav = voice_dir / "voiceover.wav"
        voice_lines = voice_dir / "lines.json"
        if args.voice_script:
            log(step("voice"))
            voice_info = step_voice(
                (ROOT / args.voice_script).resolve(), voice_dir, voice=args.voice,
                allow_download=not args.voice_offline, backend=args.voice_backend,
                fps=args.fps,
            )
            log("   %s, %.2fs, %d lines" % (voice_info["backend"], voice_info["duration_seconds"],
                                            voice_info["line_count"]))
        elif voice_wav.is_file():
            # A pre-rendered narration (a hosted model, a human read) is assembled
            # by tools/assemble_voiceover.py; read its report so the summary says
            # what the picture was actually cut to, not just that a file existed.
            voice_info = {"path": str(voice_wav), "reused": True}
            report_path = voice_dir / "voiceover.json"
            if report_path.is_file():
                report = json.loads(report_path.read_text(encoding="utf-8"))
                for key in ("backend", "voice", "duration_seconds", "line_count", "model"):
                    if report.get(key) is not None:
                        voice_info[key] = report[key]
            elif voice_lines.is_file():
                voice_info["line_count"] = len(
                    json.loads(voice_lines.read_text(encoding="utf-8")).get("lines", []))
            log("   voice present: %s%s" % (
                voice_wav.name,
                " (%s, %.2fs, %d lines)" % (voice_info.get("backend", "pre-rendered"),
                                            voice_info["duration_seconds"],
                                            voice_info["line_count"])
                if voice_info.get("duration_seconds") and voice_info.get("line_count") else ""))
        if voice_info is not None and not voice_lines.is_file():
            raise RuntimeError("a voice track exists without lines.json; the picture cannot sync to it")

        narration = None
        if voice_info is not None and voice_wav.is_file():
            log(step("listen to the narration"))
            narration = judge_narration(voice_wav, voice_lines, stage="voice")
            log("   " + narration["statement"].replace("\n", "\n   "))
            if not narration["listenable"]:
                if args.allow_voice_warnings:
                    log("   rendering anyway (--allow-voice-warnings)")
                else:
                    raise RuntimeError(
                        "the narration is not listenable, so this render is stopped "
                        "before it spends an hour on frames.\n"
                        + "\n".join("  - " + item for item in narration["failures"])
                        + "\nFix the voice or the pauses, then run again. "
                          "To render a rough cut anyway: --allow-voice-warnings")

        if args.frames:
            frames_dir = Path(args.frames).resolve()
            manifest = json.loads((frames_dir / "manifest.json").read_text(encoding="utf-8"))
            # A previous pass moves film.json / timeline.txt out to the delivery
            # folder, so a *second* pass over the same frames must read them there.
            if not (frames_dir / "film.json").is_file() and (out_dir / "film.json").is_file():
                log("   using %s from the previous pass" % (out_dir / "film.json").name)
                film_json = out_dir / "film.json"
            else:
                film_json = frames_dir / "film.json"
            log(step("reuse %d frames at %dx%d" % (manifest["frame_count"], manifest["width"], manifest["height"])))
        else:
            log(step("render frames"))
            manifest = step_frames(script, frames_dir, args.width, args.height, args.fps, args.quality,
                                   voice_lines if voice_info else None,
                                   slice_frames=args.slice_frames,
                                   script_args=script_args)
            log("   %d frames at %dx%d" % (manifest["frame_count"], manifest["width"], manifest["height"]))
            film_json = frames_dir / "film.json"

        log(step("soundtrack"))
        soundtrack = out_dir / "soundtrack.wav"
        audio_info = step_soundtrack(film_json, soundtrack)
        log("   %d sfx cues, %.1fs" % (audio_info.get("sfx_cue_count", 0), audio_info["duration_seconds"]))

        audio_track = soundtrack
        mix_info = None
        if voice_info is not None:
            log(step("mix voice over score"))
            mixed = out_dir / "mix.wav"
            mix_info = step_mix(soundtrack, voice_wav, mixed, args.duck_db)
            audio_track = mixed
            log("   duck %.1f dB, voice %.1f dB above the bed, peak %.2f"
                % (mix_info["duck_depth_db"], mix_info["voice_to_bed_db"], mix_info["peak"]))
            log(step("master the mix"))
            ffmpeg_for_audio = base.resolve_ffmpeg()[0]
            # Judge the narration on the mix, not on the master: the master is a
            # stereo limiter pass, and measuring pauses and breaths on a limited
            # stereo fold-down reports rests the listener never hears.
            mix_narration = judge_narration(audio_track, voice_lines, stage="mix")
            mastered = master_audio(audio_track, ffmpeg_for_audio)
            if mastered.get("status") in ("mastered", "unnormalised"):
                audio_track = Path(mastered["path"])
                log("   %.1f LUFS / %s dBTP true peak, 48 kHz stereo, target %.1f"
                    % (mastered["lufs"] if mastered.get("lufs") is not None else float("nan"),
                       "%.1f" % mastered["true_peak_db"] if mastered.get("true_peak_db") is not None else "?",
                       mastered["target"]))
            else:
                log("   the master pass failed; the mix is used as mixed")

            if not mix_narration["listenable"]:
                log("   delivery level: " + "; ".join(mix_narration["failures"]))
            if voice_info.get("path") and Path(voice_info["path"]).is_file():
                # keep a copy next to the film so the mix is auditable after the fact
                target = out_dir / "voiceover.wav"
                if Path(voice_info["path"]).resolve() != target.resolve():
                    target.write_bytes(Path(voice_info["path"]).read_bytes())

        log(step("validate frames"))
        validation = step_validate(frames_dir)

        log(step("encode"))
        outputs = []
        # A 4K x264 pass needs more memory than a small laptop or CI box has. The
        # single pass is tried first because it is fastest when it fits; if the
        # encoder is killed (exit 137, empty stderr) the chunked path takes over
        # and produces the same file.
        segment_mode = args.encode_segments or 0

        def encode_master(path: Path) -> dict:
            nonlocal segment_mode
            if segment_mode:
                log("   encoding %d segments" % segment_mode)
                return encode_segmented(
                    frames_dir, audio_track, path, ffmpeg, fps=args.fps, crf=args.master_crf,
                    preset="veryfast", audio_bitrate="192k",
                    total_frames=manifest["frame_count"], segments=segment_mode,
                    work_dir=out_dir / "build" / "segments",
                    extra=["-threads", "2", "-x264-params", "rc-lookahead=4:ref=1:bframes=0"])
            try:
                return base.encode(frames_dir, audio_track, path, ffmpeg, fps=args.fps,
                                   crf=args.master_crf, preset="veryfast", audio_bitrate="192k",
                                   extra=["-threads", "1",
                                          "-x264-params", "rc-lookahead=8:ref=1:bframes=2"])
            except RuntimeError as exc:
                message = str(exc)
                out_of_memory = any(token in message for token in ("137", "Killed", "killed")) \
                    or message.rstrip().endswith("(no output)")
                if not out_of_memory:
                    raise  # a real encode error, not an out-of-memory kill
                log("   single-pass encode was killed; retrying in 6 segments")
                segment_mode = 6
                path.unlink(missing_ok=True)
                return encode_master(path)

        if not args.skip_4k:
            master = out_dir / ("film-%dx%d.mp4" % (args.width, args.height))
            info = encode_master(master)
            info.setdefault("mode", "single-pass")
            outputs.append(info)
            log("   master %s (%.1f MB, %s)" % (master.name, info["bytes"] / 1048576, info["mode"]))
        delivery = out_dir / ("film-%dp.mp4" % args.delivery_height)
        outputs.append(
            base.encode(frames_dir, audio_track, delivery, ffmpeg, fps=args.fps, crf=21,
                        preset="medium", audio_bitrate="160k",
                        scale="scale=-2:%d:flags=lanczos" % args.delivery_height)
        )
        log("   delivery %s (%.1f MB)" % (delivery.name, delivery.stat().st_size / 1048576))
        delivery_level = verify_delivery_loudness(delivery, audio_track, ffmpeg, log=log)

        subtitles = None
        if voice_lines.is_file():
            log(step("subtitles"))
            subtitles = write_subtitles(voice_lines, out_dir)
            log("   %d cues, longest %d characters -> %s"
                % (subtitles["cues"], subtitles["longest_cue_characters"],
                   Path(subtitles["srt"]).name))

        log(step("measure motion"))
        film_meta = json.loads(film_json.read_text(encoding="utf-8"))
        gate = film_meta.get("motion_gate") or DEFAULT_GATE
        motion = measure_motion(delivery, ffmpeg, out_dir / "build", gate)
        log("   " + motion["statement"])

        log(step("measure composition"))
        composition_report = measure_composition(delivery, MAX_COMPOSITION_HOLD_SECONDS)
        log("   " + composition_report["statement"].splitlines()[0])
        for span in composition_report.get("spans", [])[:5]:
            log("   hold %s  %.1f s" % (span["start"], span["seconds"]))

        log(step("measure holds"))
        holds = measure_repeat_frames(delivery, MAX_STILL_SECONDS)
        log("   " + holds["statement"])
        for span in holds.get("spans", [])[:5]:
            log("   hold %s -> %s  %.1f s" % (
                mmss(span["start"]), mmss(span["end"]),
                span["seconds"]))

        probed = base.probe(delivery, ffprobe)
        film_duration = float(probed.get("duration_seconds") or 0) or float(
            manifest["frame_count"] / args.fps)

        log(step("content audit"))
        audit = base.step_audit(delivery, out_dir / "audit", ffmpeg)
        log("   " + audit["statement"])

        contact = out_dir / "contact-sheet.jpg"
        # The sheet has to show the *whole* film, not the first ten beats of it: a
        # fixed 1 frame every 2 s silently truncated anything longer than 20 s, so
        # the sampling rate is derived from the delivered duration instead. The
        # old upper cap of 0.5 fps also truncated short films: a 12 s cut sampled
        # at 0.5 fps yields six frames for a 5x2 tile, so four tiles came out black.
        sheet_fps = contact_sheet_fps(film_duration)
        base.run(
            [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(delivery),
             "-vf", "fps=%.4f,scale=480:-2:flags=lanczos,tile=5x2:padding=6:color=0x101010"
                    % sheet_fps,
             "-frames:v", "1", str(contact)],
            timeout=600,
        )

        film = json.loads(film_json.read_text(encoding="utf-8"))
        summary = {
            "title": film["title"],
            "source": args.script,
            "canvas": {"width": args.width, "height": args.height, "fps": args.fps},
            "frames": {"count": manifest["frame_count"]},
            "elapsed_seconds": round(time.time() - started, 1),
            "motion_spec": motion,
            "composition": {key: composition_report[key] for key in
                            ("status", "statement", "compositions", "longest_hold_seconds",
                             "longest_hold_at", "share_over_limit", "spans")
                            if key in composition_report},
            "holds": {key: holds[key] for key in
                      ("status", "statement", "limit_seconds", "longest_still_seconds",
                       "still_share_of_frames", "spans", "fix_hint")
                      if key in holds},
            "audit": {key: audit[key] for key in ("status", "statement", "summary") if key in audit},
            "soundtrack": {key: audio_info[key] for key in ("duration_seconds", "sfx_cue_count", "sample_rate") if key in audio_info},
            "voice": ({key: voice_info[key] for key in ("backend", "voice", "duration_seconds", "line_count", "path", "reused") if key in voice_info}
                      if voice_info else None),
            "mix": mix_info,
            "narration": ({key: narration[key] for key in
                           ("listenable", "words_per_minute", "median_pause",
                            "longest_pause", "breaths_per_minute", "failures")}
                          if narration else None),
            "delivery_level": delivery_level,
            "subtitles": subtitles,
            "validation": validation,
            "outputs": [
                {
                    "path": item["path"],
                    "bytes": item["bytes"],
                    "sha256": item["sha256"],
                    "probe": base.probe(Path(item["path"]), ffprobe),
                }
                for item in outputs
            ],
            "timeline": film,
        }
        (out_dir / "render-summary.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
        for name in ("film.json", "timeline.txt"):
            source = frames_dir / name
            if source.is_file() and source.resolve() != (out_dir / name).resolve():
                source.replace(out_dir / name)

        ok = (motion["status"] == "passed" and audit.get("status") != "flagged"
              and holds.get("status") == "passed"
              and composition_report.get("status") == "passed")
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print()
            print("FILM:", summary["title"], "|", summary["frames"]["count"], "frames |",
                  summary["elapsed_seconds"], "s")
            print(motion["statement"])
            print(composition_report["statement"])
            print(holds["statement"])
            print(audit["statement"])
            for item in summary["outputs"]:
                print("OUTPUT:", Path(item["path"]).name, "%.1f MB" % (item["bytes"] / 1048576))
        return 0 if ok else 1
    except base.DependencyMissing as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        print("render failed: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
