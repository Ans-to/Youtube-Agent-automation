#!/usr/bin/env python3
"""CPU-friendly batch adapter for a pinned local KaniTTS Urdu model.

The supported KaniTTS API returns an audio waveform which the wrapper saves as WAV.
The model snapshot is pinned and cached, and one model instance serves all scenes in
a video. The small JSON/deterministic paths are tested without downloading model weights.
"""
import argparse
from array import array
import json
import math
import os
from pathlib import Path
import sys
import wave

DEFAULT_MODEL_ID = "mahwizzzz/kani-tts-400m-ur"
DEFAULT_MODEL_REVISION = "6f758dcedff6f33d74dacebab2876b3e536b8c89"
MAX_MANIFEST_BYTES = 2_000_000
MAX_ITEMS = 300
MAX_TEXT_CHARS = 6000


def load_pipeline(model_id=DEFAULT_MODEL_ID, revision=DEFAULT_MODEL_REVISION):
    """Load the documented KaniTTS API from a pinned Hugging Face snapshot."""
    try:
        import torch
        from huggingface_hub import snapshot_download
        from kani_tts import KaniTTS
    except ImportError as exc:
        raise RuntimeError(
            "Urdu TTS dependencies are missing. Run START_HERE.bat and choose local Urdu TTS setup, "
            "or install video_studio/requirements-urdu-tts.txt using its documented CPU-only steps."
        ) from exc

    raw_threads = os.environ.get("AGENTHQ_URDU_TTS_THREADS", "").strip()
    try:
        threads = max(1, min(4, int(raw_threads))) if raw_threads else max(1, min(4, os.cpu_count() or 1))
    except ValueError:
        threads = max(1, min(4, os.cpu_count() or 1))
    torch.set_num_threads(threads)
    print("Downloading/verifying pinned Urdu TTS model " + model_id + " at " + revision, flush=True)
    print("CPU threads: " + str(threads) + "; first use downloads and caches the model (~740 MB).", flush=True)
    try:
        snapshot_path = snapshot_download(repo_id=model_id, revision=revision)
        print("Loading KaniTTS from local model snapshot.", flush=True)
        return KaniTTS(str(snapshot_path))
    except Exception as exc:
        raise RuntimeError(
            "Could not load the pinned KaniTTS Urdu model on CPU. Check internet access, disk space, "
            "Python dependency versions, the model revision, and upstream KaniTTS requirements. "
            "Original error: " + type(exc).__name__ + ": " + str(exc)[:500]
        ) from exc


def read_manifest(path):
    """Validate an internal batch manifest before loading a large model."""
    manifest_path = Path(path).expanduser().resolve()
    if not manifest_path.is_file():
        raise ValueError("Urdu TTS manifest file is missing.")
    if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError("Urdu TTS manifest exceeds the 2 MB safety limit.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Urdu TTS manifest is not valid JSON.") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("items"), list):
        raise ValueError("Urdu TTS manifest must contain an items array.")
    items = manifest["items"]
    if not items or len(items) > MAX_ITEMS:
        raise ValueError("Urdu TTS manifest must contain 1 to " + str(MAX_ITEMS) + " scenes.")
    validated = []
    seen = set()
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict) or not item.get("text_file") or not item.get("output_file"):
            raise ValueError("Urdu TTS manifest item " + str(index) + " needs text_file and output_file.")
        text_path = Path(item["text_file"]).expanduser().resolve()
        output_path = Path(item["output_file"]).expanduser().resolve()
        if not text_path.is_file():
            raise ValueError("Urdu TTS text file for scene " + str(index) + " is missing.")
        text = text_path.read_text(encoding="utf-8").strip()
        if not text or len(text) > MAX_TEXT_CHARS:
            raise ValueError("Urdu TTS text for scene " + str(index) + " must contain 1 to " + str(MAX_TEXT_CHARS) + " characters.")
        if output_path in seen:
            raise ValueError("Urdu TTS manifest contains duplicate output paths.")
        seen.add(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        validated.append({"text": text, "output_file": output_path, "index": index})
    return validated


def _mono_samples(audio):
    """Convert list/numpy/torch float audio to mono samples for deterministic tests."""
    if hasattr(audio, "detach"):
        audio = audio.detach().cpu()
    if hasattr(audio, "squeeze"):
        audio = audio.squeeze()
    if hasattr(audio, "tolist"):
        audio = audio.tolist()
    if not isinstance(audio, (list, tuple)) or not audio:
        raise ValueError("Urdu TTS returned an empty or unsupported audio waveform.")
    if isinstance(audio[0], (list, tuple)):
        rows = audio
        if len(rows) > 8 and all(len(row) <= 8 for row in rows):
            if not rows or not rows[0]:
                raise ValueError("Urdu TTS returned a malformed audio array.")
            channel_count = len(rows[0])
            if any(len(row) != channel_count for row in rows):
                raise ValueError("Urdu TTS returned an inconsistent audio shape.")
            return (sum(float(value) for value in row) / channel_count for row in rows)
        if len(rows) > 8:
            raise ValueError("Urdu TTS returned an unexpected multi-dimensional audio shape.")
        sample_count = len(rows[0])
        if sample_count < 1 or any(len(row) != sample_count for row in rows):
            raise ValueError("Urdu TTS returned inconsistent channel lengths.")
        return (sum(float(row[i]) for row in rows) / len(rows) for i in range(sample_count))
    return (float(value) for value in audio)


def write_wav(output_path, audio, sample_rate):
    """Write float audio as non-silent mono PCM16 WAV without an external codec library."""
    try:
        rate = int(sample_rate)
    except (TypeError, ValueError) as exc:
        raise ValueError("Urdu TTS returned an invalid audio sample rate.") from exc
    if rate < 8000 or rate > 192000:
        raise ValueError("Urdu TTS sample rate is outside the supported 8–192 kHz range.")
    pcm = array("h")
    peak = 0.0
    sum_squares = 0.0
    count = 0
    for sample in _mono_samples(audio):
        if not math.isfinite(sample):
            raise ValueError("Urdu TTS audio contains a NaN or infinite sample.")
        sample = max(-1.0, min(1.0, sample))
        peak = max(peak, abs(sample))
        sum_squares += sample * sample
        count += 1
        pcm.append(int(round(sample * 32767)))
    if pcm.itemsize != 2:
        raise RuntimeError("This Python build does not provide 16-bit signed audio samples.")
    if count < int(rate * 0.1):
        raise ValueError("Urdu TTS output is too short to be valid narration.")
    rms = math.sqrt(sum_squares / count)
    if peak < 0.0001 or rms < 0.00001:
        raise ValueError("Urdu TTS returned effectively silent audio; refusing silent narration.")
    if sys.byteorder != "little":
        pcm.byteswap()
    destination = Path(output_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destination), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(pcm.tobytes())
    return inspect_wav(destination)


def inspect_wav(path):
    """Reject missing, too-short, malformed or effectively silent WAV output."""
    source = Path(path).expanduser().resolve()
    if not source.is_file() or source.stat().st_size < 1024:
        raise ValueError("Urdu TTS WAV output is missing or unexpectedly small.")
    try:
        with wave.open(str(source), "rb") as stream:
            channels = stream.getnchannels()
            width = stream.getsampwidth()
            rate = stream.getframerate()
            frames = stream.getnframes()
            if channels not in (1, 2) or width != 2 or rate < 8000 or rate > 192000:
                raise ValueError("Urdu TTS must produce a mono/stereo PCM16 WAV at 8–192 kHz.")
            audio = stream.readframes(frames)
    except (wave.Error, EOFError) as exc:
        raise ValueError("Urdu TTS output is not a valid PCM WAV file.") from exc
    samples = array("h")
    samples.frombytes(audio)
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples or frames < int(rate * 0.1):
        raise ValueError("Urdu TTS output is too short to be valid narration.")
    peak = max(abs(value) for value in samples) / 32768.0
    rms = math.sqrt(sum(value * value for value in samples) / len(samples)) / 32768.0
    if peak < 0.0001 or rms < 0.00001:
        raise ValueError("Urdu TTS returned effectively silent audio; refusing silent narration.")
    return {
        "sample_rate": rate,
        "channels": channels,
        "samples_per_channel": frames,
        "duration_seconds": round(frames / rate, 3),
        "peak": round(peak, 5),
        "rms": round(rms, 5),
    }


def synthesize_manifest(manifest_path, pipeline_instance=None):
    """Synthesize each scene sequentially with one loaded model and fail on any bad WAV."""
    items = read_manifest(manifest_path)
    tts = pipeline_instance if pipeline_instance is not None else load_pipeline(
        os.environ.get("AGENTHQ_URDU_TTS_MODEL", DEFAULT_MODEL_ID).strip() or DEFAULT_MODEL_ID,
        os.environ.get("AGENTHQ_URDU_TTS_REVISION", DEFAULT_MODEL_REVISION).strip() or DEFAULT_MODEL_REVISION,
    )
    reports = []
    for item in items:
        print("Synthesizing Urdu-English scene " + str(item["index"]) + "/" + str(len(items))
              + " (" + str(len(item["text"])) + " characters)", flush=True)
        try:
            result = tts(item["text"])
        except Exception as exc:
            raise RuntimeError(
                "Urdu TTS generation failed for scene " + str(item["index"]) + ": "
                + type(exc).__name__ + ": " + str(exc)[:500]
            ) from exc
        if isinstance(result, dict) and "audio" in result:
            sample_rate = result.get("sampling_rate", result.get("sample_rate"))
            report = write_wav(item["output_file"], result["audio"], sample_rate)
        elif isinstance(result, (tuple, list)) and result:
            audio = result[0]
            saver = getattr(tts, "save_audio", None)
            if not callable(saver):
                raise ValueError("KaniTTS returned an audio waveform but its save_audio API is unavailable.")
            saver(audio, str(item["output_file"]))
            report = inspect_wav(item["output_file"])
        else:
            raise ValueError("Urdu TTS did not return a recognized KaniTTS waveform for scene " + str(item["index"]) + ".")
        report["scene"] = item["index"]
        report["output_file"] = str(item["output_file"])
        reports.append(report)
        print("Created scene audio " + str(item["index"]) + ": " + str(report["duration_seconds"]) + " s", flush=True)
    print(json.dumps({
        "status": "completed",
        "model": os.environ.get("AGENTHQ_URDU_TTS_MODEL", DEFAULT_MODEL_ID),
        "revision": os.environ.get("AGENTHQ_URDU_TTS_REVISION", DEFAULT_MODEL_REVISION),
        "items": reports,
    }, ensure_ascii=False, indent=2), flush=True)
    return reports


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="JSON file listing text and output WAV paths for all scenes")
    args = parser.parse_args(argv)
    try:
        synthesize_manifest(args.manifest)
    except (OSError, ValueError, RuntimeError, wave.Error) as exc:
        print("URDU TTS FAILED: " + str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
