#!/usr/bin/env python3
"""Build the deterministic Nokia narration bed and Remotion cue props.

The repository's configured Kokoro narrator synthesizes each scene line. Clip
start/end samples are measured from those WAVs; word positions within a clip are
estimated from its measured duration because this backend exposes no forced
word aligner. The report keeps that distinction explicit.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
REPO = HERE.parents[1]
VIDEO_STUDIO = REPO / "video_studio"
sys.path.insert(0, str(VIDEO_STUDIO))

import kokoro_voice  # noqa: E402
import score  # noqa: E402
import voiceover  # noqa: E402

FPS = 30
DURATION_SECONDS = 30
SAMPLE_RATE = 48_000
SCENE_WINDOWS = {"mill": (0, 8), "pivot": (8, 18), "world": (18, 30)}


def write_stereo_wav(path: Path, samples: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(pcm.tobytes())


def dbfs(samples: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
    return 20 * math.log10(max(rms, 1e-12))


def build(script_path: Path, audio_path: Path, props_path: Path, report_path: Path,
          voice_name: str | None = None) -> dict:
    spec = json.loads(script_path.read_text(encoding="utf-8"))
    voice_name = voice_name or spec["voice"]
    lines = spec.get("lines")
    if not isinstance(lines, list) or not lines:
        raise ValueError("voiceover.json must contain a non-empty lines array")
    if set(row.get("sceneId") for row in lines) != set(SCENE_WINDOWS):
        raise ValueError("the voice script must cover mill, pivot, and world exactly once")
    if len({row.get("sceneId") for row in lines}) != len(lines):
        raise ValueError("each scene must have exactly one narration line")

    total_samples = DURATION_SECONDS * SAMPLE_RATE
    voice = np.zeros(total_samples, dtype=np.float32)
    cue_rows: list[dict] = []
    measured_lines = []
    work_dir = report_path.parent / "nokia-voice-clips"

    for row in lines:
        scene_id = row["sceneId"]
        start_seconds = float(row["start_seconds"])
        scene_start, scene_end = SCENE_WINDOWS[scene_id]
        if not scene_start <= start_seconds < scene_end:
            raise ValueError(f"{scene_id}: narration starts outside its scene")
        clip_path = work_dir / f"{row['id']}.wav"
        line = voiceover.Line(text=row["text"], rate=float(row.get("rate", 1.0)),
                              id=row["id"], scene=scene_id)
        kokoro_voice.synth_line(line, clip_path, voice=voice_name)
        clip, sample_rate = voiceover.read_wav(clip_path)
        clip = voiceover.resample(clip, sample_rate, SAMPLE_RATE)
        clip = voiceover.fade_edges(clip, SAMPLE_RATE)
        duration = len(clip) / SAMPLE_RATE
        end_seconds = start_seconds + duration
        if end_seconds > scene_end - 0.20:
            raise ValueError(
                f"{scene_id}: measured narration ends at {end_seconds:.3f}s, "
                f"past its {scene_end:.1f}s scene boundary; rewrite or retime the VO")
        offset = round(start_seconds * SAMPLE_RATE)
        if offset + len(clip) > total_samples:
            raise ValueError(f"{scene_id}: narration exceeds the 30-second picture")
        voice[offset:offset + len(clip)] += clip

        # The clip's start/end are sample-measured. Word boundaries are weighted
        # estimates from that actual speech window, not forced alignment.
        word_times = voiceover.word_timings(row["text"], start_seconds, end_seconds)
        scene_frame_start, scene_frame_end = int(scene_start * FPS), int(scene_end * FPS)
        for index, word in enumerate(word_times):
            start_frame = max(scene_frame_start, round(float(word["start"]) * FPS))
            end_frame = min(scene_frame_end, round(float(word["end"]) * FPS))
            end_frame = max(start_frame + 1, end_frame)
            if end_frame > scene_frame_end:
                raise ValueError(f"{scene_id}: word cue {word['text']!r} overruns the scene")
            cue_rows.append({"sceneId": scene_id, "word": word["text"], "index": index,
                             "startFrame": start_frame, "endFrame": end_frame})

        measured_lines.append({
            "id": row["id"], "sceneId": scene_id, "text": row["text"],
            "start_seconds": round(start_seconds, 4),
            "end_seconds": round(end_seconds, 4),
            "duration_seconds": round(duration, 4),
            "measured_sample_count": len(clip),
            "speech_wpm": round(len(row["text"].split()) / duration * 60, 1),
        })

    voice = voiceover.polish(voice, SAMPLE_RATE)
    voice48 = voiceover.resample(voice, SAMPLE_RATE, 48_000)
    # A restrained, deterministic score fills the intentional holds without
    # competing with the narration. The score generator's mix level is measured
    # and attenuated to -28 dBFS RMS before summing under the dialogue.
    bed = score.build(
        DURATION_SECONDS,
        [("calm", 0, 8), ("build", 8, 18), ("resolve", 18, 30)],
        stereo=True,
    ).astype(np.float32)
    bed_rms_db = dbfs(bed)
    bed_gain = 10 ** ((-28.0 - bed_rms_db) / 20)
    bed *= bed_gain
    voice_stereo = np.repeat(voice48[:, None], 2, axis=1)
    mix = voice_stereo + bed
    peak = float(np.max(np.abs(mix)))
    if peak > 0.92:
        mix *= 0.92 / peak
    write_stereo_wav(audio_path, mix)

    props = {
        "narrationSrc": "audio/nokia-evolution-voice.wav",
        "wordCues": cue_rows,
    }
    props_path.parent.mkdir(parents=True, exist_ok=True)
    props_path.write_text(json.dumps(props, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")

    report = {
        "duration_seconds": DURATION_SECONDS,
        "sample_rate": SAMPLE_RATE,
        "channels": 2,
        "backend": spec["backend"],
        "voice": voice_name,
        "voice_timing_status": "clip_sample_boundaries_measured_word_boundaries_estimated",
        "timing_note": spec["timing_note"],
        "lines": measured_lines,
        "word_cues": len(cue_rows),
        "music_bed_rms_dbfs": round(dbfs(bed), 2),
        "voice_active_rms_dbfs": round(dbfs(voice[np.abs(voice) > 0.01]), 2),
        "master_rms_dbfs": round(dbfs(mix), 2),
        "master_peak_dbfs": round(20 * math.log10(max(float(np.max(np.abs(mix))), 1e-12)), 2),
        "human_audio_review": "not performed by this build script",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--script", type=Path, default=HERE / "src/nokia/voiceover.json")
    parser.add_argument("--audio", type=Path,
                        default=HERE / "public/audio/nokia-evolution-voice.wav")
    parser.add_argument("--props", type=Path, default=HERE / "out/nokia-evolution-props.json")
    parser.add_argument("--report", type=Path, default=HERE / "out/nokia-voice-report.json")
    parser.add_argument("--voice", default=None)
    args = parser.parse_args()
    build(args.script, args.audio, args.props, args.report, args.voice)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
