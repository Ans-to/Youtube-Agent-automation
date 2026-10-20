#!/usr/bin/env python3
"""Windows/CPU-friendly batch adapter for a pinned Pakistani Urdu Piper voice.

This is the default Windows Urdu-English backend. It uses ONNX Runtime rather
than the Kani/NeMo/PyTorch stack. Model files are checksum-verified on first use.
"""
from __future__ import annotations

from array import array
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import urllib.request
import wave

ROOT = Path(__file__).resolve().parents[1]
VOICE_DIR = ROOT / "video_studio" / "voices"
DEFAULT_MODEL_ID = "rhasspy/piper-voices/ur_PK-fasih-medium"
DEFAULT_MODEL_REVISION = "7a6c333ec560f0e688371adc2fbb7bbe105028c6"
MODEL_FILENAME = "ur_PK-fasih-medium.onnx"
CONFIG_FILENAME = MODEL_FILENAME + ".json"
MODEL_MD5 = "275113cbb8ffb29e3f8d51d53d266318"
CONFIG_MD5 = "e9d386b28cc8da844e6342325e04608b"
MODEL_SIZE_BYTES = 63_532_015
CONFIG_SIZE_BYTES = 3_146
MAX_DOWNLOAD_BYTES = 100_000_000
MAX_MANIFEST_BYTES = 2_000_000
MAX_ITEMS = 300
MAX_TEXT_CHARS = 6000


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_verified(url: str, destination: Path, expected_md5: str, expected_size: int) -> None:
    """Download one pinned public voice file with a bounded size and checksum."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=destination.name + ".download-",
        suffix=".tmp",
        dir=str(destination.parent),
    )
    os.close(fd)
    temporary = Path(temp_name)
    digest = hashlib.md5()
    byte_count = 0
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Offline-Agent-HQ/1.0 (Piper Urdu voice setup)"},
    )
    try:
        print("Downloading " + destination.name + " from the pinned Piper voice revision...", flush=True)
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                byte_count += len(chunk)
                if byte_count > MAX_DOWNLOAD_BYTES:
                    raise ValueError("Voice model download exceeded the 100 MB safety limit.")
                digest.update(chunk)
                output.write(chunk)
        if byte_count != expected_size:
            raise ValueError(
                destination.name + " download has an unexpected size: expected "
                + str(expected_size) + " bytes, received " + str(byte_count) + "."
            )
        if digest.hexdigest().lower() != expected_md5.lower():
            raise ValueError(destination.name + " failed its published checksum; refusing to use it.")
        temporary.replace(destination)
        print("Verified " + destination.name + " (" + str(round(byte_count / 1_000_000, 1)) + " MB).", flush=True)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def resolve_model_paths():
    """Resolve the pinned voice or an explicitly configured custom ONNX model."""
    custom = os.environ.get("AGENTHQ_PIPER_URDU_MODEL_PATH", "").strip()
    if custom:
        model_path = Path(custom).expanduser().resolve()
        return model_path, Path(str(model_path) + ".json"), True
    model_path = VOICE_DIR / MODEL_FILENAME
    return model_path, Path(str(model_path) + ".json"), False


def ensure_voice_model():
    """Ensure model and sidecar exist and are integrity-checked."""
    model_path, config_path, custom = resolve_model_paths()
    if custom:
        if not model_path.is_file():
            raise FileNotFoundError("Configured AGENTHQ_PIPER_URDU_MODEL_PATH does not exist: " + str(model_path))
        if not config_path.is_file():
            raise FileNotFoundError("Piper needs the matching model config file: " + str(config_path))
        return model_path, config_path

    base = "https://huggingface.co/rhasspy/piper-voices/resolve/" + DEFAULT_MODEL_REVISION + "/ur/ur_PK/fasih/medium/"
    if not model_path.is_file() or model_path.stat().st_size != MODEL_SIZE_BYTES or md5_file(model_path) != MODEL_MD5:
        download_verified(base + MODEL_FILENAME + "?download=true", model_path, MODEL_MD5, MODEL_SIZE_BYTES)
    if not config_path.is_file() or config_path.stat().st_size != CONFIG_SIZE_BYTES or md5_file(config_path) != CONFIG_MD5:
        download_verified(base + CONFIG_FILENAME + "?download=true", config_path, CONFIG_MD5, CONFIG_SIZE_BYTES)
    return model_path, config_path


def read_manifest(path):
    """Validate the bounded scene manifest before loading the TTS model."""
    manifest_path = Path(path).expanduser().resolve()
    if not manifest_path.is_file():
        raise ValueError("Piper Urdu TTS manifest file is missing.")
    if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError("Piper Urdu TTS manifest exceeds the 2 MB safety limit.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Piper Urdu TTS manifest is not valid JSON.") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("items"), list):
        raise ValueError("Piper Urdu TTS manifest must contain an items array.")
    items = manifest["items"]
    if not items or len(items) > MAX_ITEMS:
        raise ValueError("Piper Urdu TTS manifest must contain 1 to " + str(MAX_ITEMS) + " scenes.")
    validated = []
    seen = set()
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict) or not item.get("text_file") or not item.get("output_file"):
            raise ValueError("Piper Urdu TTS item " + str(index) + " needs text_file and output_file.")
        text_path = Path(item["text_file"]).expanduser().resolve()
        output_path = Path(item["output_file"]).expanduser().resolve()
        if not text_path.is_file():
            raise ValueError("Piper Urdu TTS text file for scene " + str(index) + " is missing.")
        if output_path.suffix.lower() != ".wav":
            raise ValueError("Piper Urdu TTS output paths must end in .wav.")
        text = text_path.read_text(encoding="utf-8").strip()
        if not text or len(text) > MAX_TEXT_CHARS:
            raise ValueError(
                "Piper Urdu TTS text for scene " + str(index) + " must contain 1 to "
                + str(MAX_TEXT_CHARS) + " characters."
            )
        if output_path in seen:
            raise ValueError("Piper Urdu TTS manifest contains duplicate output paths.")
        seen.add(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        validated.append({"text": text, "output_file": output_path, "index": index})
    return validated


def inspect_wav(path):
    """Reject absent, malformed, too-short, or effectively silent Piper audio."""
    source = Path(path).expanduser().resolve()
    if not source.is_file() or source.stat().st_size < 1024:
        raise ValueError("Piper produced a missing or unexpectedly small WAV file.")
    try:
        with wave.open(str(source), "rb") as stream:
            channels = stream.getnchannels()
            width = stream.getsampwidth()
            rate = stream.getframerate()
            frames = stream.getnframes()
            pcm_bytes = stream.readframes(frames)
    except (wave.Error, EOFError) as exc:
        raise ValueError("Piper output is not a valid PCM WAV file.") from exc
    if channels not in (1, 2) or width != 2 or not 8000 <= rate <= 192000:
        raise ValueError("Piper must produce mono/stereo PCM16 audio at 8–192 kHz.")
    samples = array("h")
    samples.frombytes(pcm_bytes)
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples or frames < int(rate * 0.1):
        raise ValueError("Piper audio is too short to be valid narration.")
    peak = max(abs(value) for value in samples) / 32768.0
    rms = math.sqrt(sum(value * value for value in samples) / len(samples)) / 32768.0
    if peak < 0.0001 or rms < 0.00001:
        raise ValueError("Piper produced effectively silent audio; refusing silent narration.")
    return {
        "sample_rate": rate,
        "channels": channels,
        "samples_per_channel": frames,
        "duration_seconds": round(frames / rate, 3),
        "peak": round(peak, 5),
        "rms": round(rms, 5),
    }


def check_dependencies():
    try:
        import importlib.metadata
        import onnxruntime
        from piper import PiperVoice
    except ImportError as exc:
        raise RuntimeError(
            "Piper Urdu voice dependencies are missing from this interpreter. "
            "Run powershell -NoProfile -ExecutionPolicy Bypass -File .\\setup_urdu_tts_windows.ps1"
        ) from exc
    try:
        version = importlib.metadata.version("piper-tts")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"
    print(
        "Piper Urdu runtime imports OK; piper-tts=" + version
        + "; onnxruntime=" + str(getattr(onnxruntime, "__version__", "unknown"))
        + "; API=" + str(PiperVoice.__name__),
        flush=True,
    )


def synthesize_manifest(manifest_path):
    """Load the small CPU voice once, render each scene, and verify each WAV."""
    items = read_manifest(manifest_path)
    model_path, _ = ensure_voice_model()
    try:
        from piper import PiperVoice
    except ImportError as exc:
        raise RuntimeError(
            "Piper Urdu voice dependencies are missing. Run "
            "powershell -NoProfile -ExecutionPolicy Bypass -File .\\setup_urdu_tts_windows.ps1"
        ) from exc
    print("Loading Pakistani Urdu male voice: Fasih (Piper medium, pinned revision).", flush=True)
    try:
        voice = PiperVoice.load(str(model_path), use_cuda=False)
    except Exception as exc:
        raise RuntimeError(
            "Could not load the Piper Urdu ONNX voice on CPU: "
            + type(exc).__name__ + ": " + str(exc)[:500]
        ) from exc

    reports = []
    for item in items:
        print(
            "Synthesizing Urdu-English scene " + str(item["index"]) + "/" + str(len(items))
            + " (" + str(len(item["text"])) + " characters)",
            flush=True,
        )
        temporary = item["output_file"].with_name(
            item["output_file"].stem + ".tmp-" + str(os.getpid()) + ".wav"
        )
        try:
            with wave.open(str(temporary), "wb") as wav_file:
                voice.synthesize_wav(item["text"], wav_file)
            report = inspect_wav(temporary)
            temporary.replace(item["output_file"])
        except Exception as exc:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            raise RuntimeError(
                "Piper Urdu synthesis failed for scene " + str(item["index"]) + ": "
                + type(exc).__name__ + ": " + str(exc)[:500]
            ) from exc
        report["scene"] = item["index"]
        report["output_file"] = str(item["output_file"])
        reports.append(report)
        print("Created scene audio " + str(item["index"]) + ": " + str(report["duration_seconds"]) + " s", flush=True)
    print(json.dumps({
        "status": "completed",
        "engine": "piper-tts",
        "model": DEFAULT_MODEL_ID,
        "revision": DEFAULT_MODEL_REVISION,
        "items": reports,
    }, ensure_ascii=False, indent=2), flush=True)
    return reports


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--manifest", help="JSON file listing text and output WAV paths for all scenes")
    group.add_argument("--download-model", action="store_true", help="Download/verify the pinned 64 MB Urdu voice model")
    group.add_argument("--check-dependencies", action="store_true", help="Check local Piper and ONNX Runtime imports")
    args = parser.parse_args(argv)
    try:
        if args.check_dependencies:
            check_dependencies()
        elif args.download_model:
            model, config = ensure_voice_model()
            print("Pinned Urdu voice model ready: " + str(model))
            print("Voice config ready: " + str(config))
        else:
            synthesize_manifest(args.manifest)
    except (OSError, ValueError, RuntimeError, wave.Error) as exc:
        print("PIPER URDU TTS FAILED: " + str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
