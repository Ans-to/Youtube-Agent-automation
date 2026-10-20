#!/usr/bin/env python3
"""Generate a deterministic, royalty-free procedural ambience and scene-change cues."""
import math
import wave
from array import array
from pathlib import Path


def render_sound_design(output, duration_seconds, scene_durations, sample_rate=24000):
    """Write quiet synthetic underscore plus soft scene cues as mono PCM16 WAV.

    This is deliberately restrained and generated locally: no third-party music or
    downloaded assets. Voice remains the foreground. Scene cues are timed from the
    storyboard, not arbitrary wall-clock or frame-counter values.
    """
    try:
        duration = float(duration_seconds)
        durations = [float(value) for value in scene_durations]
    except (TypeError, ValueError) as exc:
        raise ValueError("Sound design requires numeric duration values.") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Sound design duration must be finite and positive.")
    if not durations or any(not math.isfinite(value) or value <= 0 for value in durations):
        raise ValueError("Scene durations must be finite and positive.")
    if not isinstance(sample_rate, int) or not 8000 <= sample_rate <= 48000:
        raise ValueError("Sound design sample rate must be between 8 and 48 kHz.")

    scene_starts = []
    cursor = 0.0
    for value in durations:
        scene_starts.append(cursor)
        cursor += value
    scene_starts = scene_starts[1:]  # no transition sound before the opening scene
    cue_window = 0.24
    beat_seconds = 60.0 / 118.0
    frame_count = int(math.ceil(duration * sample_rate))
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)

    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        chunk_frames = sample_rate
        for start in range(0, frame_count, chunk_frames):
            end = min(frame_count, start + chunk_frames)
            samples = array("h")
            for frame in range(start, end):
                t = frame / sample_rate
                # Low-level, slowly pulsing tonal bed; kept deliberately below speech.
                pulse = 0.72 + 0.28 * math.sin(2.0 * math.pi * t / beat_seconds)
                bed = pulse * (0.020 * math.sin(2.0 * math.pi * 55.0 * t)
                               + 0.012 * math.sin(2.0 * math.pi * 82.41 * t)
                               + 0.006 * math.sin(2.0 * math.pi * 110.0 * t))
                cue = 0.0
                for cue_start in scene_starts:
                    elapsed = t - cue_start
                    if 0.0 <= elapsed < cue_window:
                        fade = max(0.0, 1.0 - elapsed / cue_window)
                        # Short descending digital sweep and a crisp, low-level click.
                        sweep_phase = 2.0 * math.pi * (720.0 * elapsed - 420.0 * elapsed * elapsed)
                        sweep = 0.045 * fade * math.sin(sweep_phase)
                        click = 0.0
                        if elapsed < 0.035:
                            click = 0.035 * math.exp(-elapsed * 115.0) * math.sin(2.0 * math.pi * 1550.0 * elapsed)
                        cue += sweep + click
                value = max(-0.12, min(0.12, bed + cue))
                samples.append(int(value * 32767))
            if __import__("sys").byteorder != "little":
                samples.byteswap()
            wav.writeframesraw(samples.tobytes())
        wav.writeframes(b"")
    return {"path": str(path), "duration_seconds": frame_count / sample_rate,
            "sample_rate": sample_rate, "scene_cue_count": len(scene_starts),
            "design": "procedural low-level synth bed with timed transition sweeps and clicks"}
