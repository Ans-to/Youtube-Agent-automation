#!/usr/bin/env python3
"""Evidence-based, fail-closed release audit for the 15-minute Nokia film.

This does not approve or publish anything. Measurements are made on the finished
file and aligned post-gain stems. Semantic judgments remain named human reviews;
missing evidence is never converted into a pass. See docs/media/nokia/nokia-release-audit.md.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import wave
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.infrastructure.ffmpeg import find_ffmpeg, find_ffprobe  # noqa: E402
from video_studio.audit.media import parse_subtitles  # noqa: E402
from video_studio.quality_audit import file_sha256  # noqa: E402

PROFILE = "nokia-empire-15m-v1"
TARGET_SECONDS = 900.0
DURATION_TOLERANCE = 60.0  # "close" is operationally defined as 14:00–16:00.
TARGET_LUFS = -14.0
LUFS_TOLERANCE = 1.5
MAX_TRUE_PEAK = -1.0
MAX_BLACK = 0.20
MAX_SILENCE = 1.50
MIN_END_TAIL = 0.20

REQUIRED_INPUTS = (
    "release-profile.json", "video.mp4", "script.md", "storyboard.json",
    "video.qc.json", "shots.json", "voice-timing.json", "facts.json",
    "voice-stem.wav", "music-stem.wav",
)
REVIEW_FILE = "nokia-review.json"
REPORT_FILE = "nokia.audit.json"
CHECK_IDS = (
    "profile", "duration", "narration_sync", "gaps", "visual_relevance",
    "historical_accuracy", "music_balance", "captions", "clean_ending", "master_audio",
)
MANUAL_IDS = ("narration_sync", "visual_relevance", "historical_accuracy",
              "music_balance", "captions", "clean_ending")


def finite(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _file(root: Path, name: str) -> Path:
    path = root / name
    if path.is_symlink() or path.resolve().parent != root.resolve():
        raise ValueError(f"{name} must be a regular file directly inside the package")
    return path


def input_manifest(root: Path, *, include_review: bool = False) -> dict[str, str]:
    """Hash exactly the current evidence, including any newly added captions."""
    names = set(REQUIRED_INPUTS)
    names.update(path.name for path in root.iterdir()
                 if path.suffix.lower() in {".srt", ".vtt"} and (path.is_file() or path.is_symlink()))
    if (root / "effects-stem.wav").exists():
        names.add("effects-stem.wav")
    if include_review:
        names.add(REVIEW_FILE)
    result = {}
    for name in sorted(names):
        path = _file(root, name)
        if path.is_file():
            result[name] = file_sha256(path)
    return result


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, str(exc)


def init_review(root: Path, *, force: bool = False) -> Path:
    """Create a blank review bound to current inputs; it contains no approvals."""
    root = root.resolve()
    if not root.is_dir():
        raise ValueError("package directory does not exist")
    profile_path = _file(root, "release-profile.json")
    if profile_path.exists():
        value, error = _load_json(profile_path)
        if error or value != {"profile": PROFILE}:
            raise ValueError("existing release profile is invalid; it was not overwritten")
    else:
        profile_path.write_text(json.dumps({"profile": PROFILE}, indent=2) + "\n", encoding="utf-8")
    path = _file(root, REVIEW_FILE)
    if path.exists() and not force:
        raise ValueError(f"{REVIEW_FILE} already exists; use --force to replace it")
    checks = {name: {"status": "unverified", "note": ""} for name in MANUAL_IDS}
    checks["visual_relevance"]["scenes"] = []
    checks["captions"]["mode"] = "unverified"
    review = {"schema_version": 1, "reviewed_by": "", "reviewed_inputs": input_manifest(root),
              "checks": checks}
    path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def probe_video(path: Path) -> dict:
    binary = find_ffprobe()
    if not binary:
        raise RuntimeError("ffprobe is unavailable")
    result = subprocess.run(
        [binary, "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,start_time,duration", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=120, check=False,
    )
    if result.returncode:
        raise RuntimeError("ffprobe could not read the final video: " + result.stderr[-500:])
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        raise RuntimeError("ffprobe returned invalid metadata")
    return data


def measure_master(path: Path) -> tuple[float, float]:
    """FFmpeg's EBU R128 integrated LUFS and oversampled true peak, not sample peak."""
    binary = find_ffmpeg()
    if not binary:
        raise RuntimeError("ffmpeg is unavailable")
    result = subprocess.run(
        [binary, "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0",
         "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True, timeout=1800, check=False,
    )
    text = result.stderr or ""
    if result.returncode:
        raise RuntimeError("FFmpeg true-peak/loudness meter failed: " + text[-500:])
    summary = text.rsplit("Summary:", 1)[-1]
    integrated = re.search(r"Integrated loudness:.*?\bI:\s*(-?[0-9.]+)\s*LUFS", summary, re.S)
    peak = re.search(r"True peak:.*?\bPeak:\s*(-?[0-9.]+)\s*dBFS", summary, re.S)
    if not integrated or not peak:
        raise RuntimeError("FFmpeg did not report integrated LUFS and true peak")
    lufs, true_peak = finite(integrated.group(1)), finite(peak.group(1))
    if lufs is None or true_peak is None:
        raise RuntimeError("FFmpeg returned non-finite loudness measurements")
    return lufs, true_peak


def _db(value):
    return round(20 * math.log10(value), 2) if value > 0 else None


def measure_stems(voice_path: Path, music_path: Path, duration: float) -> dict:
    """Measure aligned PCM16 buses in 50 ms speech-active windows.

    A -45 dBFS voice-energy gate is a reproducible approximation, not ASR or an
    intelligibility test. RMS is energy-weighted; peak is the voice sample peak.
    Effects are intentionally excluded from these two buses.
    """
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("numpy is needed to meter the separate stems") from exc
    with wave.open(str(voice_path), "rb") as voice, wave.open(str(music_path), "rb") as music:
        if any(w.getsampwidth() != 2 or w.getcomptype() != "NONE" or w.getnchannels() not in (1, 2)
               for w in (voice, music)):
            raise ValueError("stems must be mono/stereo, uncompressed PCM16 WAV files")
        rate = voice.getframerate()
        if not rate or music.getframerate() != rate or voice.getnframes() != music.getnframes():
            raise ValueError("voice and music stems must have the same rate and duration")
        if abs(voice.getnframes() / rate - duration) > 0.25:
            raise ValueError("stem duration does not match the finished video")
        block = max(1, int(rate * 0.05))
        voice_energy = music_energy = 0.0
        active_samples = active_windows = 0
        voice_peak = music_peak = 0.0
        while True:
            a, b = voice.readframes(block), music.readframes(block)
            if not a and not b:
                break
            x = np.frombuffer(a, dtype="<i2").astype(np.float64) / 32768.0
            y = np.frombuffer(b, dtype="<i2").astype(np.float64) / 32768.0
            frames = x.size // voice.getnchannels()
            if not frames or frames != y.size // music.getnchannels():
                raise ValueError("stems ended at different times")
            voice_peak = max(voice_peak, float(np.max(np.abs(x))))
            music_peak = max(music_peak, float(np.max(np.abs(y))))
            vx, my = float(np.mean(x * x)), float(np.mean(y * y))
            if vx >= 10 ** (-45.0 / 10):
                voice_energy += vx * frames
                music_energy += my * frames
                active_samples += frames
                active_windows += 1
        if not active_windows:
            raise ValueError("no speech-active voice windows were found")
        if music_peak <= 1e-8:
            raise ValueError("the music stem is silent")
        voice_rms = math.sqrt(voice_energy / active_samples)
        music_rms = math.sqrt(music_energy / active_samples)
        return {
            "method": "50 ms windows with voice RMS >= -45 dBFS; energy-weighted RMS",
            "active_seconds": round(active_samples / rate, 3),
            "narration_active_rms_dbfs": _db(voice_rms),
            "narration_sample_peak_dbfs": _db(voice_peak),
            "music_under_narration_rms_dbfs": _db(music_rms),
            "voice_above_music_db": round(20 * math.log10(voice_rms / music_rms), 2) if music_rms else None,
            "music_sample_peak_dbfs": _db(music_peak),
        }


def measure_effects(path: Path, duration: float) -> dict:
    """Measure the effects bus as a whole; individual cues still need review."""
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("numpy is needed to meter effects") from exc
    with wave.open(str(path), "rb") as effects:
        if effects.getsampwidth() != 2 or effects.getcomptype() != "NONE" or effects.getnchannels() not in (1, 2):
            raise ValueError("effects stem must be mono/stereo PCM16 WAV")
        rate = effects.getframerate()
        if not rate or abs(effects.getnframes() / rate - duration) > 0.25:
            raise ValueError("effects stem duration does not match the video")
        peak = energy = 0.0
        active_frames = 0
        while raw := effects.readframes(max(1, int(rate * 0.05))):
            samples = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
            frames = samples.size // effects.getnchannels()
            if not frames:
                continue
            peak = max(peak, float(np.max(np.abs(samples))))
            power = float(np.mean(samples * samples))
            if power >= 10 ** (-45.0 / 10):
                energy += power * frames
                active_frames += frames
        return {"active_rms_dbfs": _db(math.sqrt(energy / active_frames)) if active_frames else None,
                "sample_peak_dbfs": _db(peak), "active_seconds": round(active_frames / rate, 3),
                "method": "50 ms effect windows >= -45 dBFS; energy-weighted RMS"}


def validate_clock(shots, timing, duration: float) -> dict:
    """Check every shot has one complete line on the same continuous clock."""
    if not isinstance(shots, list) or not shots or not isinstance(timing, list) or not timing:
        raise ValueError("shots and voice timing must be non-empty arrays")
    if len(shots) != len(timing):
        raise ValueError("shot and narration-line counts differ")
    seen = set()
    scenes = set()
    previous_end = 0.0
    final_line_end = None
    for i, (shot, line) in enumerate(zip(shots, timing), 1):
        if not isinstance(shot, dict) or not isinstance(line, dict):
            raise ValueError(f"shot/line {i} is not an object")
        ident = shot.get("id")
        scene = shot.get("scene")
        if not isinstance(ident, str) or not ident.strip() or ident in seen:
            raise ValueError(f"shot {i} has a missing or duplicate id")
        if line.get("shot") != ident:
            raise ValueError(f"shot {ident}: narration is missing or out of order")
        if isinstance(scene, bool) or not isinstance(scene, int) or scene <= 0:
            raise ValueError(f"shot {ident}: scene must be a positive integer")
        if not isinstance(line.get("text"), str) or not line["text"].strip():
            raise ValueError(f"shot {ident}: narration text is empty")
        start, end = finite(shot.get("start")), finite(shot.get("end"))
        vo_start, line_start, line_end = (finite(shot.get("voStart")),
                                           finite(line.get("start")), finite(line.get("end")))
        if any(x is None for x in (start, end, vo_start, line_start, line_end)):
            raise ValueError(f"shot {ident}: invalid timestamps")
        if start < 0 or end <= start or abs(start - previous_end) > 0.002:
            raise ValueError(f"shot {ident}: picture clock has a gap, overlap or invalid duration")
        if (line_start < start - 0.002 or line_end <= line_start or line_end > end + 0.002
                or abs(line_start - vo_start) > 0.025):
            raise ValueError(f"shot {ident}: narration does not fit its picture")
        spoken_length = finite(line.get("vo"))
        if spoken_length is None or abs((line_end - line_start) - spoken_length) > 0.025:
            raise ValueError(f"shot {ident}: narration duration disagrees with the timing record")
        seen.add(ident)
        scenes.add(scene)
        previous_end, final_line_end = end, line_end
    if abs(previous_end - duration) > 0.25:
        raise ValueError("shot clock does not cover the finished video's duration")
    return {"shot_count": len(shots), "scenes": sorted(scenes),
            "last_line_end": final_line_end, "ending_tail_seconds": round(duration - final_line_end, 3)}


def validate_facts(ledger) -> int:
    """Validate the evidence ledger structure, not the truth of its sources."""
    claims = ledger.get("claims") if isinstance(ledger, dict) else None
    if not isinstance(ledger, dict) or ledger.get("coverage") != "complete":
        raise ValueError("the factual ledger must declare complete coverage after review")
    if not isinstance(claims, list) or not claims:
        raise ValueError("a claim-by-claim factual evidence ledger is required")
    for i, claim in enumerate(claims, 1):
        if not isinstance(claim, dict) or claim.get("verdict") != "supported":
            raise ValueError(f"claim {i} is not marked supported")
        if not all(isinstance(claim.get(key), str) and claim[key].strip() for key in ("claim", "location")):
            raise ValueError(f"claim {i} needs its text and a scene/timestamp")
        sources = claim.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ValueError(f"claim {i} has no source")
        for source in sources:
            if not isinstance(source, dict):
                raise ValueError(f"claim {i} has an invalid source")
            url = urlparse(str(source.get("url", "")))
            if url.scheme not in {"http", "https"} or not url.netloc:
                raise ValueError(f"claim {i} needs a real HTTP(S) source URL")
            if not isinstance(source.get("support"), str) or not source["support"].strip():
                raise ValueError(f"claim {i} needs a note explaining what the source supports")
    return len(claims)


def _words(text: str) -> list[str]:
    return re.findall(r"[\w]+(?:['’][\w]+)*", text.casefold(), re.UNICODE)


def validate_sidecar(path: Path, timing: list[dict]) -> int:
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    blocks = [b for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]
    if path.suffix.lower() == ".vtt":
        if not blocks or not blocks[0].strip().startswith("WEBVTT"):
            raise ValueError(f"{path.name}: missing WebVTT header")
        blocks = blocks[1:]
    cues = parse_subtitles(text)
    if not cues or len(cues) != len(blocks):
        raise ValueError(f"{path.name}: missing or malformed caption cues")
    expected, line_for_word = [], []
    for index, row in enumerate(timing):
        words = _words(row["text"])
        expected.extend(words)
        line_for_word.extend([index] * len(words))
    actual = []
    previous_end = 0.0
    cursor = 0
    for cue in cues:
        words = _words(cue.text)
        if not words or cue.start < previous_end - 0.001 or cue.end <= cue.start:
            raise ValueError(f"{path.name}: empty, overlapping or invalid caption cue")
        if (cursor + len(words) > len(expected)
                or expected[cursor:cursor + len(words)] != words):
            raise ValueError(f"{path.name}: caption text differs from the narration timing text")
        first, last = line_for_word[cursor], line_for_word[cursor + len(words) - 1]
        if cue.start < float(timing[first]["start"]) - 0.5 or cue.end > float(timing[last]["end"]) + 0.5:
            raise ValueError(f"{path.name}: caption timing is outside its narrated line")
        actual.extend(words)
        cursor += len(words)
        previous_end = cue.end
    if actual != expected:
        raise ValueError(f"{path.name}: captions omit narration")
    return len(cues)


def _review_state(review, binding: dict, key: str) -> tuple[str, str, dict]:
    if not isinstance(review, dict) or review.get("schema_version") != 1:
        return "unverified", "No valid named human review was supplied.", {}
    reviewer = review.get("reviewed_by")
    if not isinstance(reviewer, str) or not reviewer.strip():
        return "unverified", "The review needs the reviewer's name.", {}
    if review.get("reviewed_inputs") != binding:
        return "unverified", "Review inputs changed or were not bound to this exact package.", {}
    item = (review.get("checks") or {}).get(key, {}) if isinstance(review.get("checks"), dict) else {}
    if not isinstance(item, dict):
        return "unverified", "Review entry is missing.", {}
    if item.get("status") == "fail":
        return "failed", f"Reviewer {reviewer} reported a defect: {item.get('note', '')}", item
    if item.get("status") != "pass" or not isinstance(item.get("note"), str) or len(item["note"].strip()) < 10:
        return "unverified", "A named reviewer must pass this check and describe the evidence.", item
    return "attested", f"Reviewed by {reviewer}: {item['note'].strip()}", item


def _result(status, detail, **extra):
    return {"status": status, "detail": detail, **extra}


def _stream_coverage(probe: dict) -> tuple[float, int]:
    duration = finite((probe.get("format") or {}).get("duration"))
    streams = probe.get("streams")
    if duration is None or duration <= 0 or not isinstance(streams, list):
        raise ValueError("ffprobe returned no usable duration or stream metadata")
    videos = [s for s in streams if s.get("codec_type") == "video"]
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    if len(videos) != 1 or len(audios) != 1:
        raise ValueError("the Nokia delivery needs exactly one video and one audio stream; alternate audio is not audited")
    for stream in (videos[0], audios[0]):
        start, length = finite(stream.get("start_time")), finite(stream.get("duration"))
        if start is None or length is None or length <= 0:
            raise ValueError("audio/video stream start or duration could not be measured")
        if abs(start) > 0.1 or abs(start + length - duration) > 0.25:
            raise ValueError("audio or video stream does not cover the complete finished file")
    return duration, sum(s.get("codec_type") == "subtitle" for s in streams)


def _gap_check(qc, video_hash):
    if not isinstance(qc, dict):
        return _result("unverified", "Strict technical QA report is missing.")
    if (qc.get("strict") is not True or qc.get("passed") is not True or qc.get("warnings") != []
            or qc.get("video_sha256") != video_hash or not qc.get("audio_stream_count")):
        return _result("failed", "Strict technical QA did not pass for this exact video.")
    checks = qc.get("checks")
    if not isinstance(checks, dict):
        return _result("unverified", "Strict QA did not provide black-frame and silence measurements.")
    for key, maximum in (("black_frames", MAX_BLACK), ("audio_silence", MAX_SILENCE)):
        entry = checks.get(key)
        if not isinstance(entry, dict) or not isinstance(entry.get("events"), list):
            return _result("unverified", f"{key} was not measured")
        threshold = finite(entry.get("threshold_seconds"))
        if threshold is None or threshold <= 0 or threshold > maximum:
            return _result("unverified", f"{key} used a looser or unknown threshold")
        for event in entry["events"]:
            length = finite(event.get("duration")) if isinstance(event, dict) else None
            if length is None or length < 0:
                return _result("unverified", f"{key} has an invalid event")
            if length >= maximum or (key == "audio_silence" and length >= threshold):
                return _result("failed", f"{key} has a gap requiring correction or explicit technical review")
    return _result("passed", "Strict QA found no black gap >= 0.20 s or silence >= 1.50 s.")


def audit_package(root: Path) -> dict:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError("package directory does not exist")
    initial = input_manifest(root, include_review=True)
    binding = {name: value for name, value in initial.items() if name != REVIEW_FILE}
    missing = [name for name in REQUIRED_INPUTS if name not in initial]
    profile, _ = _load_json(_file(root, "release-profile.json"))
    review, _ = _load_json(_file(root, REVIEW_FILE))
    qc, _ = _load_json(_file(root, "video.qc.json"))
    shots, _ = _load_json(_file(root, "shots.json"))
    timing, _ = _load_json(_file(root, "voice-timing.json"))
    facts, _ = _load_json(_file(root, "facts.json"))
    video_hash = initial.get("video.mp4")
    checks = {}
    if profile != {"profile": PROFILE}:
        checks["profile"] = _result("unverified", "Nokia release profile is missing or invalid.")
    elif missing:
        checks["profile"] = _result("unverified", "Required package inputs are missing: " + ", ".join(missing))
    else:
        checks["profile"] = _result("passed", "Nokia 15-minute release profile and required inputs are present.")
    duration = None
    subtitle_streams = None
    if video_hash:
        try:
            duration, subtitle_streams = _stream_coverage(probe_video(_file(root, "video.mp4")))
            if abs(duration - TARGET_SECONDS) <= DURATION_TOLERANCE:
                checks["duration"] = _result("passed", f"Measured {duration:.2f}s; target is 900s ± 60s.")
            else:
                checks["duration"] = _result("failed", f"Measured {duration:.2f}s; expected 840–960s.")
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
            checks["duration"] = _result("unverified", f"Duration/stream coverage could not be verified: {exc}")
    else:
        checks["duration"] = _result("unverified", "Finished video is missing.")
    checks["gaps"] = _gap_check(qc, video_hash)

    clock = None
    if duration is not None and shots is not None and timing is not None:
        try:
            clock = validate_clock(shots, timing, duration)
        except (TypeError, ValueError) as exc:
            checks["narration_sync"] = _result("failed", str(exc))
    if "narration_sync" not in checks:
        if clock is None:
            checks["narration_sync"] = _result("unverified", "Shot clock or measured narration timing is missing.")
        else:
            status, detail, _ = _review_state(review, binding, "narration_sync")
            checks["narration_sync"] = _result(status, detail, shot_count=clock["shot_count"])

    if clock is None:
        checks["visual_relevance"] = _result("unverified", "A valid shot clock is needed to enumerate scenes.")
    else:
        status, detail, item = _review_state(review, binding, "visual_relevance")
        if status == "attested" and item.get("scenes") != clock["scenes"]:
            status, detail = "unverified", "The reviewer must list every scene in the actual shot clock."
        checks["visual_relevance"] = _result(status, detail, scenes=clock["scenes"])

    try:
        count = validate_facts(facts)
    except ValueError as exc:
        checks["historical_accuracy"] = _result("unverified", str(exc))
    else:
        status, detail, _ = _review_state(review, binding, "historical_accuracy")
        checks["historical_accuracy"] = _result(status, detail, claim_count=count,
                                                  limitation="Sources and claim coverage require human verification.")

    recommendations = []
    levels = None
    if duration is None or "voice-stem.wav" not in initial or "music-stem.wav" not in initial:
        checks["music_balance"] = _result("unverified", "Aligned, post-gain voice and music stems are required.")
    else:
        try:
            levels = measure_stems(_file(root, "voice-stem.wav"), _file(root, "music-stem.wav"), duration)
            voice_db = levels["narration_active_rms_dbfs"]
            music_db = levels["music_under_narration_rms_dbfs"]
            peak_db = levels["narration_sample_peak_dbfs"]
            if levels["voice_above_music_db"] is not None and levels["voice_above_music_db"] <= 0:
                checks["music_balance"] = _result("failed", "Music RMS meets or exceeds narration during speech-active windows.")
            else:
                status, detail, _ = _review_state(review, binding, "music_balance")
                checks["music_balance"] = _result(status, detail)
            for label, value, low, high in (
                ("Narration active RMS", voice_db, -18, -12),
                ("Narration sample peak", peak_db, -6, -3),
                ("Music under narration RMS", music_db, -30, -24),
            ):
                if value is None or not low <= value <= high:
                    recommendations.append(f"{label}: {value} dBFS; recommended {low} to {high} dBFS.")
            if levels["voice_above_music_db"] is not None and levels["voice_above_music_db"] < 6:
                recommendations.append("Music is less than 6 dB below active narration on average; listen for masking.")
        except (OSError, RuntimeError, ValueError, wave.Error) as exc:
            checks["music_balance"] = _result("unverified", f"Stem levels could not be verified: {exc}")
    effects_levels = None
    if "effects-stem.wav" not in initial or duration is None:
        recommendations.append("SFX level is unmeasured; if effects are used, review their separate bus against the -18 to -10 dBFS guide.")
    else:
        try:
            effects_levels = measure_effects(_file(root, "effects-stem.wav"), duration)
            recommendations.append("Review individual SFX cues: the -18 to -10 dBFS range is guidance and depends on the effect.")
        except (OSError, RuntimeError, ValueError, wave.Error) as exc:
            recommendations.append(f"SFX level was not measured: {exc}")

    sidecars = sorted(name for name in initial if Path(name).suffix.lower() in {".srt", ".vtt"})
    status, detail, item = _review_state(review, binding, "captions")
    mode = item.get("mode")
    if status == "attested":
        if mode not in {"none", "burned", "embedded", "sidecar", "multiple"}:
            status, detail = "unverified", "The reviewer must declare the caption mode."
        elif subtitle_streams is None:
            status, detail = "unverified", "Embedded subtitle streams could not be inspected."
        elif ((sidecars and mode not in {"sidecar", "multiple"})
              or (subtitle_streams and mode not in {"embedded", "multiple"})
              or (mode == "sidecar" and not sidecars)
              or (mode == "embedded" and not subtitle_streams)):
            status, detail = "failed", "Declared caption mode does not match the actual sidecars/embedded streams."
        elif sidecars:
            if clock is None:
                status, detail = "unverified", "Caption comparison needs the valid narration clock."
            else:
                try:
                    for name in sidecars:
                        validate_sidecar(_file(root, name), timing)
                except (OSError, UnicodeError, TypeError, ValueError, IndexError) as exc:
                    status, detail = "failed", str(exc)
    checks["captions"] = _result(status, detail, sidecars=sidecars, embedded_streams=subtitle_streams,
                                  limitation="Text/timing comparison is against the plan, not independent ASR; listen to the actual audio.")

    if clock is None:
        checks["clean_ending"] = _result("unverified", "A valid final narration timing is required.")
    elif clock["ending_tail_seconds"] < MIN_END_TAIL:
        checks["clean_ending"] = _result("failed", "The last spoken line has less than 0.20 s of picture after it.")
    else:
        status, detail, _ = _review_state(review, binding, "clean_ending")
        checks["clean_ending"] = _result(status, detail, tail_seconds=clock["ending_tail_seconds"])

    master = None
    if video_hash:
        try:
            lufs, true_peak = measure_master(_file(root, "video.mp4"))
            master = {"integrated_lufs": lufs, "true_peak_dbtp": true_peak,
                      "method": "FFmpeg ebur128=peak=true on the encoded video"}
            if abs(lufs - TARGET_LUFS) > LUFS_TOLERANCE or true_peak > MAX_TRUE_PEAK:
                checks["master_audio"] = _result("failed", f"Master is {lufs:.1f} LUFS, {true_peak:.1f} dBTP; expected -14 ± 1.5 LUFS and <= -1 dBTP.")
            else:
                checks["master_audio"] = _result("passed", f"Master is {lufs:.1f} LUFS and {true_peak:.1f} dBTP.")
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            checks["master_audio"] = _result("unverified", f"Master loudness/true peak was not measured: {exc}")
    else:
        checks["master_audio"] = _result("unverified", "Finished video is missing.")

    # Inputs can be edited while FFmpeg is running; never bind a stale report.
    final = input_manifest(root, include_review=True)
    if final != initial:
        checks["profile"] = _result("failed", "Package inputs changed during the audit; run it again.")
    states = {entry["status"] for entry in checks.values()}
    status = "FAILED" if "failed" in states else "INCOMPLETE" if "unverified" in states else "PASSED"
    return {
        "schema_version": 1, "profile": PROFILE, "status": status,
        "video_sha256": video_hash, "inputs": final, "missing_inputs": missing,
        "duration_seconds": duration, "master": master, "stem_levels": levels,
        "effects_levels": effects_levels, "recommendations": recommendations, "checks": checks,
        "scope_note": "Human attestations are not machine verification of speech, visual meaning, historical truth, mix intelligibility, or the ending.",
    }


def validate_release_report(root: Path) -> dict:
    """Revalidate an audit and all its input bindings at approval and upload."""
    root = root.resolve()
    profile, error = _load_json(_file(root, "release-profile.json"))
    if error or profile != {"profile": PROFILE}:
        raise ValueError("Nokia release profile is missing or invalid")
    report, error = _load_json(_file(root, REPORT_FILE))
    if error or not isinstance(report, dict) or report.get("schema_version") != 1:
        raise ValueError("Nokia audit report is missing or invalid")
    if report.get("profile") != PROFILE or report.get("status") != "PASSED":
        raise ValueError("Nokia project audit is not passed")
    current = input_manifest(root, include_review=True)
    if any(name not in current for name in (*REQUIRED_INPUTS, REVIEW_FILE)) or report.get("inputs") != current:
        raise ValueError("Nokia audit inputs are missing or changed; review and audit again")
    if report.get("video_sha256") != current["video.mp4"]:
        raise ValueError("Nokia audit is for a different video")
    checks = report.get("checks")
    if not isinstance(checks, dict) or set(checks) != set(CHECK_IDS):
        raise ValueError("Nokia audit is missing required checks")
    for name in CHECK_IDS:
        expected = "attested" if name in MANUAL_IDS else "passed"
        if not isinstance(checks[name], dict) or checks[name].get("status") != expected:
            raise ValueError(f"Nokia audit check {name} is not {expected}")
    duration = finite(report.get("duration_seconds"))
    master = report.get("master")
    lufs = finite(master.get("integrated_lufs")) if isinstance(master, dict) else None
    peak = finite(master.get("true_peak_dbtp")) if isinstance(master, dict) else None
    if duration is None or abs(duration - TARGET_SECONDS) > DURATION_TOLERANCE:
        raise ValueError("Nokia video duration is outside the release target")
    if lufs is None or peak is None or abs(lufs - TARGET_LUFS) > LUFS_TOLERANCE or peak > MAX_TRUE_PEAK:
        raise ValueError("Nokia master loudness or true peak is outside the release target")
    review, error = _load_json(_file(root, REVIEW_FILE))
    binding = {name: value for name, value in current.items() if name != REVIEW_FILE}
    if error or any(_review_state(review, binding, key)[0] != "attested" for key in MANUAL_IDS):
        raise ValueError("Nokia human review is missing, incomplete, or bound to different inputs")
    # Recheck the inexpensive structural evidence as well as the saved verdict.
    shots, shot_error = _load_json(_file(root, "shots.json"))
    timing, timing_error = _load_json(_file(root, "voice-timing.json"))
    facts, facts_error = _load_json(_file(root, "facts.json"))
    qc, qc_error = _load_json(_file(root, "video.qc.json"))
    if shot_error or timing_error or facts_error or qc_error:
        raise ValueError("Nokia evidence files cannot be read")
    clock = validate_clock(shots, timing, duration)
    if clock["ending_tail_seconds"] < MIN_END_TAIL:
        raise ValueError("Nokia narration ends too close to the cut")
    if review["checks"]["visual_relevance"].get("scenes") != clock["scenes"]:
        raise ValueError("Nokia visual review does not cover every scene")
    validate_facts(facts)
    if _gap_check(qc, current["video.mp4"])["status"] != "passed":
        raise ValueError("Nokia black-frame or silence evidence is not passing")
    levels = report.get("stem_levels")
    active = finite(levels.get("active_seconds")) if isinstance(levels, dict) else None
    if (not isinstance(levels, dict) or finite(levels.get("narration_active_rms_dbfs")) is None
            or finite(levels.get("narration_sample_peak_dbfs")) is None
            or finite(levels.get("music_sample_peak_dbfs")) is None or active is None or active <= 0):
        raise ValueError("Nokia narration/music stem measurements are missing")
    separation = finite(levels.get("voice_above_music_db"))
    if separation is not None and separation <= 0:
        raise ValueError("Nokia music is not below the narration")
    for name in current:
        if Path(name).suffix.lower() in {".srt", ".vtt"}:
            validate_sidecar(_file(root, name), timing)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, help="directory containing the final video and evidence")
    parser.add_argument("--init-review", action="store_true", help="enable the profile and write a blank human-review template")
    parser.add_argument("--force", action="store_true", help="replace an existing review template when initializing")
    args = parser.parse_args(argv)
    root = Path(args.package)
    try:
        if args.init_review:
            path = init_review(root, force=args.force)
            print(f"Blank review created: {path}. No checks have been approved.")
            return 0
        report = audit_package(root)
        report_path = _file(root.resolve(), REPORT_FILE)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        return {"PASSED": 0, "FAILED": 1, "INCOMPLETE": 2}[report["status"]]
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as exc:
        print(f"NOKIA AUDIT COULD NOT RUN: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
