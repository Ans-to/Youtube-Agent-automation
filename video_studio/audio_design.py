#!/usr/bin/env python3
"""Generate a deterministic, royalty-free procedural ambience and scene-change cues."""
import math
import wave
from array import array
from pathlib import Path


def render_sound_design(output, duration_seconds, scene_durations, sample_rate=24000,
                        sfx_cues=None, bed_gain=1.0):
    """Write quiet synthetic underscore plus soft scene cues as mono PCM16 WAV.

    This is deliberately restrained and generated locally: no third-party music or
    downloaded assets. Voice remains the foreground. Scene cues are timed from the
    storyboard, not arbitrary wall-clock or frame-counter values.

    ``bed_gain`` sets the underscore against the cues, and only the underscore:
    the drum pulse and the tonal pad. A film whose subject is a sound - typing, a
    click, an impact - needs its bed lower so that sound can be heard; measured
    on the render test, the keystrokes sat 1.6 dB above the kick on average with
    the bed at unity, which is a typing shot with no typing in it. Scaling the
    cues up instead would have made a key press louder than a mouse click, which
    is not what either of them sounds like.
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
    try:
        bed_gain = float(bed_gain)
    except (TypeError, ValueError) as exc:
        raise ValueError("Sound design bed gain must be numeric.") from exc
    if not math.isfinite(bed_gain) or not 0.0 <= bed_gain <= 1.5:
        raise ValueError("Sound design bed gain must be between 0 and 1.5.")

    scene_starts = []
    cursor = 0.0
    for value in durations:
        scene_starts.append(cursor)
        cursor += value
    scene_starts = scene_starts[1:]  # no transition sound before the opening scene
    cue_window = 0.24
    # 120 BPM = 0.5 s per beat, which divides the 4-second shot grid used by the
    # direction compiler, so cuts can land on the pulse instead of near it.
    beat_seconds = 60.0 / 120.0
    sfx_mix = _sfx_mix(duration, sample_rate, sfx_cues or [])
    frame_count = int(math.ceil(duration * sample_rate))
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)

    noise_state = 20260121  # fixed seed: the same brief always gets the same bed
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        chunk_frames = sample_rate
        cue_index = 0
        for start in range(0, frame_count, chunk_frames):
            end = min(frame_count, start + chunk_frames)
            samples = array("h")
            for frame in range(start, end):
                t = frame / sample_rate
                # A quiet kick/hat on each beat. Without a transient the bed has
                # no detectable pulse, so a cut could never be checked against it.
                beat_phase = t % beat_seconds
                noise_state = (noise_state * 1103515245 + 12345) & 0x7FFFFFFF
                beat_noise = (noise_state / 0x7FFFFFFF) * 2.0 - 1.0
                kick = bed_gain * 0.052 * math.exp(-beat_phase * 26.0) * math.sin(
                    2.0 * math.pi * (62.0 * math.exp(-beat_phase * 9.0) + 34.0) * beat_phase)
                hat = bed_gain * 0.016 * math.exp(-beat_phase * 180.0) * beat_noise
                # Low-level, slowly pulsing tonal bed; kept deliberately below speech.
                pulse = 0.72 + 0.28 * math.sin(2.0 * math.pi * t / beat_seconds)
                bed = bed_gain * pulse * (0.020 * math.sin(2.0 * math.pi * 55.0 * t)
                                          + 0.012 * math.sin(2.0 * math.pi * 82.41 * t)
                                          + 0.006 * math.sin(2.0 * math.pi * 110.0 * t))
                while cue_index < len(scene_starts) and t - scene_starts[cue_index] >= cue_window:
                    cue_index += 1
                cue = 0.0
                if cue_index < len(scene_starts):
                    elapsed = t - scene_starts[cue_index]
                    if 0.0 <= elapsed < cue_window:
                        fade = max(0.0, 1.0 - elapsed / cue_window)
                        # Short descending digital sweep and a crisp, low-level click.
                        sweep_phase = 2.0 * math.pi * (720.0 * elapsed - 420.0 * elapsed * elapsed)
                        sweep = 0.045 * fade * math.sin(sweep_phase)
                        click = 0.0
                        if elapsed < 0.035:
                            click = 0.035 * math.exp(-elapsed * 115.0) * math.sin(2.0 * math.pi * 1550.0 * elapsed)
                        cue = sweep + click
                value = max(-0.9, min(0.9, bed + cue + kick + hat + (sfx_mix[frame] if frame < len(sfx_mix) else 0.0)))
                samples.append(int(value * 32767))
            if __import__("sys").byteorder != "little":
                samples.byteswap()
            wav.writeframesraw(samples.tobytes())
        wav.writeframes(b"")
    return {"path": str(path), "duration_seconds": frame_count / sample_rate,
            "sample_rate": sample_rate, "scene_cue_count": len(scene_starts),
            "sfx_cue_count": len(sfx_cues or []),
            "design": "procedural low-level synth bed with timed transition sweeps and clicks"}


SFX_KINDS = ("whoosh", "riser", "swell", "glitch", "click", "impact", "pop", "key")


def _envelope(t, length, attack=0.012, release=0.08):
    """Simple attack/release envelope, in seconds."""
    if t < 0 or t > length:
        return 0.0
    if t < attack:
        return t / attack
    remaining = length - t
    if remaining < release:
        return max(0.0, remaining / release)
    return 1.0


def _sfx_mix(duration, sample_rate, cues):
    """Mix SFX cues into a sample buffer (used by the bed renderer)."""
    total = int(math.ceil(duration * sample_rate))
    mix = [0.0] * total
    for index, cue in enumerate(cues):
        if not isinstance(cue, dict):
            raise ValueError("Cue %d must be an object" % index)
        kind = str(cue.get("kind", "")).lower()
        if kind not in SFX_KINDS:
            raise ValueError("Cue %d uses unknown kind %r" % (index, cue.get("kind")))
        at = float(cue.get("at", 0.0))
        length = float(cue.get("length", 0.3))
        gain = float(cue.get("gain", 0.3))
        if not 0.0 <= at < duration:
            continue
        if not 0.02 <= length <= 2.0:
            raise ValueError("Cue %d length out of range" % index)
        if not 0.0 <= gain <= 1.0:
            raise ValueError("Cue %d gain out of range" % index)
        values = _synth_cue(kind, length, sample_rate, seed=7919 + index * 104729)
        start = int(at * sample_rate)
        for offset, value in enumerate(values):
            position = start + offset
            if position >= total:
                break
            mix[position] += value * gain
    return mix


def _synth_cue(kind, length, sample_rate, seed=1):
    """Procedural one-shot sound effect. Deterministic, no samples or licences."""
    count = max(1, int(length * sample_rate))
    values = []
    state = seed & 0x7FFFFFFF or 1
    # Keystrokes are the one kind that plays many times in a row. Twelve cues
    # with the same pitch read as a machine gun, so each one takes a small
    # detune from its own seed. The seed is already deterministic per cue index,
    # so the take still renders identically every time - it just is not fifteen
    # copies of one stroke.
    detune = ((seed % 97) / 96.0) - 0.5
    for index in range(count):
        t = index / sample_rate
        progress = t / max(1e-6, length)
        envelope = _envelope(t, length)
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        noise = (state / 0x7FFFFFFF) * 2.0 - 1.0
        if kind == "whoosh":
            # Band-limited noise with a fast sweep: air moving past a microphone.
            sweep = math.sin(2 * math.pi * (220.0 + 1600.0 * progress) * t)
            value = (0.55 * noise + 0.45 * sweep) * envelope * (1.0 - 0.4 * progress)
        elif kind == "riser":
            frequency = 90.0 * (2.0 ** (3.2 * progress))
            value = (0.62 * math.sin(2 * math.pi * frequency * t)
                     + 0.20 * noise) * envelope * (0.35 + 0.65 * progress)
        elif kind == "swell":
            frequency = 140.0 + 60.0 * progress
            value = (0.55 * math.sin(2 * math.pi * frequency * t)
                     + 0.25 * math.sin(2 * math.pi * frequency * 2.01 * t)
                     + 0.10 * noise) * envelope * math.sin(math.pi * progress)
        elif kind == "glitch":
            gate = 1.0 if (int(t * 90) % 3) else 0.15
            value = (0.5 * noise + 0.3 * math.sin(2 * math.pi * (600 + 900 * ((int(t * 60) % 4))) * t)) * envelope * gate
        elif kind == "click":
            value = (0.7 * noise + 0.5 * math.sin(2 * math.pi * 2100.0 * t)) * math.exp(-t * 90.0)
        elif kind == "impact":
            frequency = 58.0 * math.exp(-t * 3.0)
            value = (0.85 * math.sin(2 * math.pi * frequency * t)
                     + 0.35 * noise * math.exp(-t * 22.0)) * envelope
        elif kind == "pop":
            frequency = 700.0 * math.exp(-t * 12.0) + 180.0
            value = 0.7 * math.sin(2 * math.pi * frequency * t) * math.exp(-t * 30.0)
        elif kind == "key":
            # A keystroke is three things at once, and all three matter: the
            # hard contact tick of the cap bottoming out (broadband noise, dead
            # in five milliseconds), the plastic click of the switch above it,
            # and a low body resonance from the case underneath. No envelope is
            # applied on top - the decays are the envelope, and a release ramp
            # would soften the transient that makes it read as a key at all.
            # The attack ramp exists only so sample zero is not a step, which
            # would add a click of its own.
            attack = min(1.0, t / 0.0015)
            contact = noise * math.exp(-t * 480.0)
            click = math.sin(2 * math.pi * 2600.0 * (1.0 + 0.05 * detune) * t) * math.exp(-t * 340.0)
            body = math.sin(2 * math.pi * (190.0 + 40.0 * progress + 14.0 * detune) * t) * math.exp(-t * 62.0)
            value = (0.62 * contact + 0.30 * click + 0.24 * body) * attack
        else:
            raise ValueError("Unknown SFX kind %r. Choose one of: %s" % (kind, ", ".join(SFX_KINDS)))
        values.append(max(-1.0, min(1.0, value)))
    return values


def render_motion_sfx(output, duration_seconds, cues, sample_rate=24000):
    """Mix procedural transition and impact cues into a mono PCM16 WAV.

    ``cues`` are the plan emitted by ``motion.beat.cue_sheet`` or the direction
    compiler: ``{at, kind, gain, length}``. The mix is deliberately quiet; it is
    designed to sit under narration, not compete with it.
    """
    try:
        duration = float(duration_seconds)
    except (TypeError, ValueError) as exc:
        raise ValueError("SFX duration must be numeric") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("SFX duration must be finite and positive")
    if not isinstance(sample_rate, int) or not 8000 <= sample_rate <= 48000:
        raise ValueError("SFX sample rate must be between 8 and 48 kHz")
    if not isinstance(cues, list):
        raise ValueError("Cues must be a list")

    total = int(math.ceil(duration * sample_rate))
    mix = [0.0] * total
    rendered = 0
    for index, cue in enumerate(cues):
        if not isinstance(cue, dict):
            raise ValueError("Cue %d must be an object" % index)
        kind = str(cue.get("kind", "")).lower()
        if kind not in SFX_KINDS:
            raise ValueError("Cue %d uses unknown kind %r" % (index, cue.get("kind")))
        at = float(cue.get("at", 0.0))
        length = float(cue.get("length", 0.3))
        gain = float(cue.get("gain", 0.3))
        if not (0.0 <= at < duration):
            continue
        if not 0.02 <= length <= 2.0:
            raise ValueError("Cue %d length out of range" % index)
        if not 0.0 <= gain <= 1.0:
            raise ValueError("Cue %d gain out of range" % index)
        values = _synth_cue(kind, length, sample_rate, seed=7919 + index * 104729)
        start = int(at * sample_rate)
        for offset, value in enumerate(values):
            position = start + offset
            if position >= total:
                break
            mix[position] += value * gain
        rendered += 1

    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        samples = array("h")
        for value in mix:
            samples.append(int(max(-1.0, min(1.0, value)) * 32767))
        if __import__("sys").byteorder != "little":
            samples.byteswap()
        wav.writeframes(samples.tobytes())
    peak = max((abs(value) for value in mix), default=0.0)
    return {
        "path": str(path),
        "duration_seconds": total / sample_rate,
        "sample_rate": sample_rate,
        "cue_count": rendered,
        "peak": round(peak, 4),
        "design": "procedural transition cues: sweeps, noise, impacts, clicks",
    }
