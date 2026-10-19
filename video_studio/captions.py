#!/usr/bin/env python3
"""Deterministic English subtitle generation and validation for video outputs."""
import re
from pathlib import Path

# Non-Latin scripts commonly used by non-English narration are rejected in this
# English-only pipeline. Latin-script language identification is prompt/model
# constrained and still needs human listening review.
NON_LATIN_SCRIPT = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\u0900-\u097F\u0400-\u04FF\u4E00-\u9FFF\uAC00-\uD7AF]")
TIMESTAMP_SRT = re.compile(r"^(\d{2,}:\d{2}:\d{2},\d{3}) --> (\d{2,}:\d{2}:\d{2},\d{3})$")


def validate_english_text(text, label="Narration"):
    value = str(text or "").strip()
    if not value:
        raise ValueError(label + " must not be empty.")
    if NON_LATIN_SCRIPT.search(value):
        raise ValueError(label + " must be English text; non-Latin script was detected.")
    return value


def validate_english_voice_model(model_path):
    model = Path(model_path).expanduser().resolve()
    config_path = Path(str(model) + ".json")
    if not model.is_file():
        raise ValueError("English voice model file does not exist: " + str(model))
    if not config_path.is_file():
        raise ValueError("Voice model config is required to verify English: " + str(config_path))
    import json
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Voice model config is invalid JSON.") from exc
    code = str(config.get("language", {}).get("code", ""))
    if not code.lower().startswith("en"):
        raise ValueError("English-only narration requires an en* Piper model; detected " + (code or "unknown") + ".")
    return code


def _wrap_words(text, max_chars=42):
    lines, current = [], ""
    for word in str(text).split():
        candidate = word if not current else current + " " + word
        if len(candidate) > max_chars and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _stamp(seconds, decimal=","):
    millis = max(0, round(float(seconds) * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{decimal}{millis:03d}"


def build_subtitles(storyboard):
    """Return (SRT, WebVTT); scene narration duration is preferred when TTS is used."""
    scenes = storyboard.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("Subtitle generation requires at least one scene.")
    cues = []
    cursor = 0.0
    for index, scene in enumerate(scenes, 1):
        narration = validate_english_text(scene.get("narration", ""), f"Scene {index} narration")
        # Keep on-screen Canvas captions identical to spoken words and sidecar subtitles.
        scene["caption"] = narration
        scene_duration = float(scene.get("duration_seconds", 0))
        spoken_duration = float(scene.get("narration_duration_seconds", scene_duration) or scene_duration)
        if scene_duration <= 0 or spoken_duration <= 0:
            raise ValueError(f"Scene {index} must have positive scene and narration durations.")
        spoken_duration = min(scene_duration, spoken_duration)
        lines = _wrap_words(narration)
        chunks = ["\n".join(lines[i:i + 2]) for i in range(0, len(lines), 2)]
        weights = [max(1, len(chunk.split())) for chunk in chunks]
        total_words = sum(weights)
        elapsed = 0.0
        for chunk, weight in zip(chunks, weights):
            start = cursor + spoken_duration * elapsed / total_words
            elapsed += weight
            end = cursor + spoken_duration * elapsed / total_words
            # Avoid zero-duration cues on extremely short test scenes.
            if end - start < 0.12:
                end = min(cursor + scene_duration, start + 0.12)
            if end > start:
                cues.append((start, end, chunk))
        cursor += scene_duration
    if not cues:
        raise ValueError("No subtitle cues were generated.")
    srt_parts, vtt_parts = [], ["WEBVTT", ""]
    for number, (start, end, text) in enumerate(cues, 1):
        clean = text.replace("-->", "—>")
        srt_parts.append(f"{number}\n{_stamp(start)} --> {_stamp(end)}\n{clean}\n")
        vtt_parts.append(f"{_stamp(start, '.')} --> {_stamp(end, '.')}\n{clean}\n")
    return "\n".join(srt_parts).rstrip() + "\n", "\n".join(vtt_parts).rstrip() + "\n"


def validate_subtitle_text(srt_text, vtt_text):
    """Fail closed on empty/invalid subtitle sidecars and malformed time ranges."""
    if not srt_text.strip() or not vtt_text.startswith("WEBVTT"):
        raise ValueError("Both non-empty SRT and WebVTT subtitle files are required.")
    blocks = [block for block in srt_text.strip().split("\n\n") if block.strip()]
    if not blocks:
        raise ValueError("SRT file contains no cues.")
    previous_end = -1.0
    def seconds(stamp):
        match = re.fullmatch(r"(\d{2,}):(\d{2}):(\d{2}),(\d{3})", stamp)
        if not match:
            raise ValueError("Invalid SRT timestamp: " + stamp)
        h, m, s, ms = map(int, match.groups())
        return h * 3600 + m * 60 + s + ms / 1000
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 3 or not lines[0].isdigit():
            raise ValueError("Malformed SRT cue block.")
        match = TIMESTAMP_SRT.fullmatch(lines[1])
        if not match:
            raise ValueError("Malformed SRT cue timing.")
        start, end = map(seconds, match.groups())
        if start < previous_end - 0.001 or end <= start:
            raise ValueError("Subtitle cues overlap, are unordered, or have invalid duration.")
        text = validate_english_text(" ".join(lines[2:]), "Subtitle cue")
        if len(text) > 1000:
            raise ValueError("Subtitle cue exceeds the 1000-character limit.")
        previous_end = end
    vtt_blocks = [block for block in vtt_text.strip().split("\\n\\n") if block.strip()]
    if not vtt_blocks or vtt_blocks[0].strip() != "WEBVTT":
        raise ValueError("WebVTT header is missing or malformed.")
    vtt_cues = vtt_blocks[1:]
    if len(vtt_cues) != len(blocks):
        raise ValueError("SRT and WebVTT cue counts do not match.")

    def normalize_cue_text(lines):
        return " ".join(" ".join(lines).split())

    def parse_vtt_stamp(stamp):
        match = re.fullmatch(r"(\\d{2,}):(\\d{2}):(\\d{2})\\.(\\d{3})", stamp)
        if not match:
            raise ValueError("Invalid WebVTT timestamp: " + stamp)
        h, m, sec, ms = map(int, match.groups())
        return h * 3600 + m * 60 + sec + ms / 1000

    for index, (srt_block, vtt_block) in enumerate(zip(blocks, vtt_cues), 1):
        srt_lines = srt_block.splitlines()
        vtt_lines = vtt_block.splitlines()
        if len(vtt_lines) < 2:
            raise ValueError("Malformed WebVTT cue block " + str(index) + ".")
        vtt_timing = re.fullmatch(r"(\\d{2,}:\\d{2}:\\d{2}\\.\\d{3}) --> (\\d{2,}:\\d{2}:\\d{2}\\.\\d{3})", vtt_lines[0])
        if not vtt_timing:
            raise ValueError("Malformed WebVTT cue timing at cue " + str(index) + ".")
        vtt_start, vtt_end = map(parse_vtt_stamp, vtt_timing.groups())
        srt_match = TIMESTAMP_SRT.fullmatch(srt_lines[1])
        srt_start, srt_end = map(seconds, srt_match.groups())
        if abs(vtt_start - srt_start) > 0.001 or abs(vtt_end - srt_end) > 0.001:
            raise ValueError("SRT and WebVTT cue timings differ at cue " + str(index) + ".")
        if normalize_cue_text(srt_lines[2:]) != normalize_cue_text(vtt_lines[1:]):
            raise ValueError("SRT and WebVTT subtitle text differs at cue " + str(index) + ".")
    return {"cue_count": len(blocks), "duration_seconds": previous_end}
