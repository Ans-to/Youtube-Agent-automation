#!/usr/bin/env python3
"""CPU-friendly batch adapter for local Urdu KaniTTS using Transformers.

The model is downloaded from Hugging Face on first use and cached by Transformers.
No shell is invoked. A manifest allows one model load to synthesize every scene in a
video instead of reloading hundreds of MB of weights for each scene.
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
    """Load the local CPU pipeline once. Missing dependencies/model errors are fatal."""
    try:
        import torch
        from transformers import pipeline
    except ImportError as exc:
        raise RuntimeError(
            "Urdu TTS dependencies are missing. Run setup_all_windows.ps1 or install "
            "video_studio/requirements-urdu-tts.txt before rendering Urdu-English video."
        ) from exc

    thread_limit = os.environ.get("AGENTHQ_URDU_TTS_THREADS", "").strip()
    try:
        threads = max(1, min(4, int(thread_limit))) if thread_limit else max(1, min(4, os.cpu_count() or 1))
    except ValueError:
        threads = max(1, min(4, os.cpu_count() or 1))
    torch.set_num_threads(threads)
    print("Loading local Urdu TTS model " + model_id + " at pinned revision " + revision, flush=True)
    print("CPU thread limit: " + str(threads) + "; first use downloads and caches the model.", flush=True)
    try:
        return pipeline(
            "text-to-speech",
            model=model_id,
            revision=revision,
            device=-1,
            model_kwargs={"torch_dtype": torch.float32},
        )
    except Exception as exc:
        raise RuntimeError(
            "Could not load the configured Urdu TTS model on CPU. Check internet access, "
            "disk space, model revision, and the installed Transformers/PyTorch versions. "
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
    """Convert a Hugging Face AudioOutput waveform to an iterable mono sample stream."""
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
            # [frames, channels] layout
            if not rows or not rows[0]:
                raise ValueError("Urdu TTS returned a malformed audio array.")
            channel_count = len(rows[0])
            if any(len(row) != channel_count for row in rows):
                raise ValueError("Urdu TTS returned an inconsistent audio shape.")
            return (sum(float(value) for value in row) / channel_count for row in rows)
        # Transformers normally returns [channels, samples]; downmix to mono.
        if len(rows) > 8:
            raise ValueError("Urdu TTS returned an unexpected multi-dimensional audio shape.")
        sample_count = len(rows[0])
        if sample_count < 1 or any(len(row) != sample_count for row in rows):
            raise ValueError("Urdu TTS returned inconsistent channel lengths.")
        return (sum(float(row[i]) for row in rows) / len(rows) for i in range(sample_count))
    return (float(value) for value in audio)


def write_wav(output_path, audio, sample_rate):
    """Write verified float audio as mono PCM16 WAV without requiring an audio codec library."""
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
    if not destination.is_file() or destination.stat().st_size < 1024:
        raise RuntimeError("Urdu TTS WAV output is missing or unexpectedly small.")
    return {"sample_rate": rate, "samples": count, "duration_seconds": round(count / rate, 3),
            "peak": round(peak, 5), "rms": round(rms, 5)}


def synthesize_manifest(manifest_path, pipeline_instance=None):
    """Synthesize each scene sequentially with one loaded model and fail on any bad WAV."""
    items = read_manifest(manifest_path)
    tts = pipeline_instance or load_pipeline(
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
        if not isinstance(result, dict) or "audio" not in result:
            raise ValueError("Urdu TTS did not return an audio waveform for scene " + str(item["index"]) + ".")
        sample_rate = result.get("sampling_rate", result.get("sample_rate"))
        report = write_wav(item["output_file"], result["audio"], sample_rate)
        report["scene"] = item["index"]
        report["output_file"] = str(item["output_file"])
        reports.append(report)
        print("Created scene audio " + str(item["index"]) + ": " + str(report["duration_seconds"]) + " s", flush=True)
    print(json.dumps({"status": "completed", "model": os.environ.get("AGENTHQ_URDU_TTS_MODEL", DEFAULT_MODEL_ID),
                      "revision": os.environ.get("AGENTHQ_URDU_TTS_REVISION", DEFAULT_MODEL_REVISION),
                      "items": reports}, ensure_ascii=False, indent=2), flush=True)
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
