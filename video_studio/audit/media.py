"""Signal extraction adapters.

These are the only parts of the auditor that touch a file, a subprocess, or an
optional model. Everything degrades to "signal absent" rather than raising, so
the auditor can always produce a report — with honest gaps — on a bare machine.

No network access is used anywhere in this module.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from . import audio, vision
from .signals import Interval, MediaSignals, TextBlock, TranscriptCue

FFMPEG_TIMEOUT_SECONDS = 1_800
FRAME_WIDTH = 64
FRAME_HEIGHT = 36
LUMA = (0.2126, 0.7152, 0.0722)  # Rec.709


def capabilities() -> dict[str, bool]:
    """What this machine can actually measure right now."""
    tesseract = bool(shutil.which("tesseract"))
    pytesseract = _module_available("pytesseract")
    return {
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "ffprobe": bool(shutil.which("ffprobe")),
        "ocr": tesseract and pytesseract,
        "ocr_engine": tesseract,
        "asr": _module_available("faster_whisper") or _module_available("whisper"),
        "audio_analysis": True,
        "vision_observations": True,
        "local_model": False,
    }


def _module_available(name: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def probe(path: Path) -> dict:
    """Read container metadata. Returns an empty dict when ffprobe is unavailable."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {}
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, resolved binary, no shell
            [ffprobe, "-v", "error", "-show_entries",
             "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=120, check=False,
        )
        if result.returncode != 0:
            return {}
        return json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return {}


def _read_exact(stream, size: int) -> bytes | None:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            return None
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def extract_frames(path: Path, sample_fps: float = 10.0,
                   ffmpeg: str | None = None) -> tuple[
                       list[tuple[float, float]],
                       list[tuple[float, float]],
                       list[tuple[float, float]],
                       list[tuple[float, tuple[float, ...]]],
                   ]:
    """Stream small RGB frames and return (luminance, motion, red, 3x3 grid motion, peak luminance).

    Frames are decoded at low resolution and streamed, so memory stays flat even
    for long videos. Values are 0..1. The 3x3 grid is how mouth-region motion is
    measured when face boxes are supplied by a local detector.
    """
    ffmpeg = ffmpeg or shutil.which("ffmpeg")
    if not ffmpeg:
        return [], [], [], [], []
    command = [
        ffmpeg, "-hide_banner", "-nostats", "-loglevel", "error", "-i", str(path),
        "-an", "-vf", f"fps={sample_fps},scale={FRAME_WIDTH}:{FRAME_HEIGHT}",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]
    frame_bytes = FRAME_WIDTH * FRAME_HEIGHT * 3
    luminance: list[tuple[float, float]] = []
    peak: list[tuple[float, float]] = []
    motion: list[tuple[float, float]] = []
    red: list[tuple[float, float]] = []
    grid_motion: list[tuple[float, tuple[float, ...]]] = []
    previous: bytes | None = None
    index = 0
    try:
        process = subprocess.Popen(  # noqa: S603 - fixed argv, resolved binary, no shell
            command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
        )
    except OSError:
        return [], [], [], [], []
    try:
        while True:
            frame = _read_exact(process.stdout, frame_bytes)
            if frame is None:
                break
            time = index / sample_fps
            # Sample every fourth pixel; the image is already tiny.
            luma_total = 0.0
            red_total = 0.0
            peak_luma = 0.0
            pixels = 0
            for offset in range(0, frame_bytes, 12):
                r, g, b = frame[offset], frame[offset + 1], frame[offset + 2]
                luma = LUMA[0] * r + LUMA[1] * g + LUMA[2] * b
                luma_total += luma
                red_total += r
                if luma > peak_luma:
                    peak_luma = luma
                pixels += 1
            luminance.append((time, luma_total / (pixels * 255.0)))
            # A dark title card and a dead signal both have a low mean. The peak
            # separates them: type and graphics still put a bright pixel on screen.
            peak.append((time, peak_luma / 255.0))
            red.append((time, red_total / (pixels * 255.0)))
            if previous is not None:
                difference = 0
                cells = [0] * 9
                counts = [0] * 9
                for offset in range(0, frame_bytes, 12):
                    delta = (
                        abs(frame[offset] - previous[offset])
                        + abs(frame[offset + 1] - previous[offset + 1])
                        + abs(frame[offset + 2] - previous[offset + 2])
                    )
                    difference += delta
                    pixel = offset // 3
                    column = (pixel % FRAME_WIDTH) * 3 // FRAME_WIDTH
                    row = (pixel // FRAME_WIDTH) * 3 // FRAME_HEIGHT
                    cell = row * 3 + column
                    cells[cell] += delta
                    counts[cell] += 1
                motion.append((time, difference / (pixels * 3 * 255.0)))
                grid_motion.append((time, tuple(
                    round(cells[cell] / (max(1, counts[cell]) * 3 * 255.0), 5) for cell in range(9)
                )))
            previous = frame
            index += 1
    finally:
        process.stdout.close()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
    return luminance, motion, red, grid_motion, peak


def extract_audio_rms(path: Path, window: float = 0.1, sample_rate: int = 16_000,
                      ffmpeg: str | None = None) -> list[tuple[float, float]]:
    """Stream mono PCM and return per-window RMS in 0..1."""
    ffmpeg = ffmpeg or shutil.which("ffmpeg")
    if not ffmpeg:
        return []
    command = [
        ffmpeg, "-hide_banner", "-nostats", "-loglevel", "error", "-i", str(path),
        "-vn", "-ac", "1", "-ar", str(sample_rate), "-f", "s16le", "-",
    ]
    samples_per_window = max(1, int(sample_rate * window))
    values: list[tuple[float, float]] = []
    try:
        process = subprocess.Popen(  # noqa: S603 - fixed argv, resolved binary, no shell
            command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
        )
    except OSError:
        return []
    import array

    index = 0
    try:
        while True:
            block = _read_exact(process.stdout, samples_per_window * 2)
            if block is None:
                break
            samples = array.array("h")
            samples.frombytes(block)
            if not samples:
                break
            total = 0.0
            for sample in samples:
                value = sample / 32768.0
                total += value * value
            values.append((index * window, min(1.0, (total / len(samples)) ** 0.5)))
            index += 1
    finally:
        process.stdout.close()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
    return values


def parse_subtitles(text: str) -> list[TranscriptCue]:
    """Parse SRT or WebVTT into cues. Tolerates both comma and dot separators."""
    cues: list[TranscriptCue] = []
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip())
    stamp = re.compile(
        r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
    )
    for block in blocks:
        match = stamp.search(block)
        if not match:
            continue
        hours, minutes, seconds, millis, end_h, end_m, end_s, end_ms = match.groups()
        start = int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis.ljust(3, "0")) / 1000
        end = int(end_h) * 3600 + int(end_m) * 60 + int(end_s) + int(end_ms.ljust(3, "0")) / 1000
        body = block[match.end():].strip()
        body = re.sub(r"<[^>]+>", "", body).strip()
        if body:
            cues.append(TranscriptCue(start=start, end=end, text=" ".join(body.split()), source="subtitles"))
    return cues


def transcribe(path: Path, model_size: str = "base", language: str | None = None) -> list[TranscriptCue]:
    """Local ASR via faster-whisper, if the operator installed it.

    The model runs on the local CPU and downloads once. Nothing is sent anywhere.
    """
    if not _module_available("faster_whisper"):
        return []
    try:
        from faster_whisper import WhisperModel  # type: ignore[import-not-found]
    except ImportError:
        return []
    try:
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(path), language=language, vad_filter=True)
        return [
            TranscriptCue(
                start=float(segment.start), end=float(segment.end),
                text=str(segment.text).strip(), source="asr",
                confidence=float(getattr(segment, "avg_logprob", 0.0) or 0.0),
            )
            for segment in segments
            if str(segment.text).strip()
        ]
    except Exception:  # noqa: BLE001 - any model failure means "no transcript", never a crash
        return []


def read_on_screen_text(path: Path, duration: float, *, sample_seconds: float = 1.0,
                        ffmpeg: str | None = None) -> list[TextBlock]:
    """OCR sampled frames with local Tesseract, if installed.

    Each detected line becomes a :class:`TextBlock` covering a +/-0.5 s window,
    carrying its height as a fraction of frame height so disclosure legibility can
    be judged rather than guessed.
    """
    if not duration or duration <= 0:
        return []
    if not (shutil.which("tesseract") and _module_available("pytesseract")):
        return []
    ffmpeg = ffmpeg or shutil.which("ffmpeg")
    if not ffmpeg:
        return []
    try:
        import pytesseract  # type: ignore[import-not-found]
        from PIL import Image  # type: ignore[import-not-found]
    except ImportError:
        return []

    import io

    blocks: list[TextBlock] = []
    height = 720
    time = 0.0
    while time < duration:
        command = [
            ffmpeg, "-hide_banner", "-nostats", "-loglevel", "error", "-ss", f"{time:.3f}",
            "-i", str(path), "-frames:v", "1", "-vf", f"scale=-2:{height}",
            "-f", "image2pipe", "-vcodec", "png", "-",
        ]
        try:
            result = subprocess.run(  # noqa: S603 - fixed argv, no shell
                command, capture_output=True, timeout=120, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            break
        if result.returncode != 0 or not result.stdout:
            time += sample_seconds
            continue
        try:
            image = Image.open(io.BytesIO(result.stdout))
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        except Exception:  # noqa: BLE001 - OCR failure means "no text found"
            time += sample_seconds
            continue
        grouped: dict[tuple, list[str]] = {}
        for index, word in enumerate(data.get("text", [])):
            if not str(word).strip():
                continue
            try:
                confidence = float(data["conf"][index])
                word_height = float(data["height"][index])
            except (KeyError, TypeError, ValueError):
                continue
            if confidence < 40:
                continue
            key = (data.get("block_num", [0] * (index + 1))[index],
                   data.get("par_num", [0] * (index + 1))[index])
            grouped.setdefault(key, []).append(str(word).strip())
            blocks.append(TextBlock(
                start=max(0.0, time - sample_seconds / 2),
                end=time + sample_seconds / 2,
                text=str(word).strip(),
                confidence=confidence / 100.0,
                height_ratio=word_height / height,
            ))
        time += sample_seconds
    return blocks


def collect(path: str | Path, *, sample_fps: float = 10.0,
            subtitle_path: str | Path | None = None,
            whisper_model: str | None = None,
            ocr: bool = False,
            competitor_terms: list[str] | None = None,
            observations_path: str | Path | None = None) -> MediaSignals:
    """Build :class:`MediaSignals` from a media file plus whatever tools exist."""
    path = Path(path)
    signals = MediaSignals(competitor_terms=list(competitor_terms or []))
    meta = probe(path)
    if meta:
        streams = meta.get("streams", [])
        video = next((item for item in streams if item.get("codec_type") == "video"), {})
        signals.width = video.get("width")
        signals.height = video.get("height")
        try:
            signals.duration = float(meta.get("format", {}).get("duration", 0) or 0)
        except (TypeError, ValueError):
            signals.duration = 0.0
        rate = str(video.get("avg_frame_rate", "0/1"))
        try:
            numerator, _, denominator = rate.partition("/")
            signals.fps = round(float(numerator) / float(denominator), 3) if float(denominator) else None
        except (TypeError, ValueError, ZeroDivisionError):
            signals.fps = None

    luminance, motion, red, grid_motion, peak = extract_frames(path, sample_fps=sample_fps)
    signals.luminance, signals.motion, signals.red_level = luminance, motion, red
    signals.peak_luminance = peak
    signals.grid_motion = grid_motion
    if luminance:
        signals.sources["luminance"] = f"ffmpeg frames at {sample_fps:g} fps"
        signals.duration = signals.duration or luminance[-1][0]

    profile = audio.analyze_file(path)
    rms: list[tuple[float, float]] = []
    if profile is not None and profile.frames:
        signals.audio_profile = profile
        rms = [(frame.time, 10 ** (frame.rms_db / 20.0)) for frame in profile.frames]
        signals.music_detected = profile.music.present
        signals.music_confidence = profile.music.confidence
        signals.sources["audio_profile"] = (
            f"local DSP: {profile.integrated_db:.1f} dBFS integrated, "
            f"music heuristics: {'bed detected' if profile.music.present else 'no bed'} "
            f"({profile.music.confidence:.0f}% confidence)"
        )
    else:
        rms = extract_audio_rms(path)
    signals.audio_rms = rms
    if rms:
        signals.sources.setdefault("audio_rms", "ffmpeg PCM, 0.1 s windows")
        signals.duration = signals.duration or rms[-1][0]

    signals.silence = [
        Interval(item["start"], item["end"])
        for item in _silence_intervals(path, signals.duration)
    ] if rms else []

    if subtitle_path:
        try:
            cues = parse_subtitles(Path(subtitle_path).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            cues = []
        if cues:
            signals.transcript = cues
            signals.sources["transcript"] = f"subtitles: {Path(subtitle_path).name}"
    elif whisper_model:
        cues = transcribe(path, model_size=whisper_model)
        if cues:
            signals.transcript = cues
            signals.sources["transcript"] = f"local ASR (faster-whisper, {whisper_model})"

    if observations_path:
        observations, provider = vision.load_observations(observations_path)
        signals.observations = observations
        signals.sources["vision"] = f"observations: {Path(observations_path).name}" + (
            f" ({provider})" if provider else ""
        )
        signals.mouth_motion = vision.mouth_motion_series(grid_motion, vision.face_observations(observations))
        if signals.mouth_motion:
            signals.sources["mouth_motion"] = "lower face-box motion from local observations"

    if ocr:
        blocks = read_on_screen_text(path, signals.duration)
        if blocks:
            signals.ocr = blocks
            signals.sources["ocr"] = "local Tesseract"
    if not signals.duration:
        signals.notes.append("Duration could not be determined; time ranges may be incomplete.")
    return signals


def _silence_intervals(path: Path, duration: float) -> list[dict]:
    """Ask FFmpeg for silence spans; returns [] when unavailable."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return []
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [ffmpeg, "-hide_banner", "-nostats", "-i", str(path), "-vn",
             "-af", "silencedetect=noise=-45dB:d=1.5", "-f", "null", "-"],
            capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_SECONDS, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    starts = [float(value) for value in re.findall(r"silence_start:\s*(-?[0-9.]+)", result.stderr)]
    ends = [float(value) for value in re.findall(r"silence_end:\s*(-?[0-9.]+)", result.stderr)]
    events = [{"start": start, "end": end} for start, end in zip(starts, ends, strict=False) if end >= start]
    if starts and (not ends or starts[-1] > ends[-1]) and duration >= starts[-1] >= 0:
        events.append({"start": starts[-1], "end": duration, "continues_to_eof": True})
    return events
