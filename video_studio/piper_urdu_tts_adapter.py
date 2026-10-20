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
# Fasih v2: a pinned full-model Urdu fine-tune, not the older catalogue v1.
# Published model MD5 and byte size are checked before the file is promoted.
DEFAULT_MODEL_ID = "IhorShevchuk/piper-voice-ur-fasih"
DEFAULT_MODEL_REVISION = "06202b7"
MODEL_SOURCE_FILENAME = "ur_PK-fasih-medium-model.onnx"
MODEL_FILENAME = "ur_PK-fasih-medium.onnx"
CONFIG_FILENAME = MODEL_FILENAME + ".json"
MODEL_MD5 = "f32ec2c6ebcc6bd1752cab0b932859c7"
MODEL_SIZE_BYTES = 64_832_023
# The v2 config is deterministically derived from the checksum-verified v1 sidecar
# plus the five published v2 diphthong IDs. The v1 file is used only as trusted input.
SOURCE_MODEL_REVISION = "7a6c333ec560f0e688371adc2fbb7bbe105028c6"
SOURCE_CONFIG_MD5 = "e9d386b28cc8da844e6342325e04608b"
SOURCE_CONFIG_SIZE_BYTES = 3_146
DEFAULT_LENGTH_SCALE = 1.15
FASIH_V2_PHONEME_IDS = {"aɪ": 161, "aʊ": 162, "eɪ": 163, "ɔɪ": 164, "oʊ": 165}
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


def _build_fasih_v2_config(source_config):
    """Build v2's sidecar from the checksum-verified v1 map and documented v2 additions."""
    if not isinstance(source_config, dict):
        raise ValueError("Pinned source Urdu voice config must be a JSON object.")
    language = source_config.get("language", {})
    audio = source_config.get("audio", {})
    if not isinstance(language, dict) or language.get("code") != "ur_PK":
        raise ValueError("Pinned source voice config is not the expected Pakistani Urdu voice.")
    if not isinstance(audio, dict) or audio.get("sample_rate") != 22050:
        raise ValueError("Pinned source voice config has an unexpected sample rate.")
    phoneme_map = source_config.get("phoneme_id_map")
    if not isinstance(phoneme_map, dict):
        raise ValueError("Pinned source voice config is missing phoneme_id_map.")
    used_ids = {
        item_id
        for values in phoneme_map.values()
        if isinstance(values, list)
        for item_id in values
        if isinstance(item_id, int)
    }
    for symbol, item_id in FASIH_V2_PHONEME_IDS.items():
        if symbol in phoneme_map and phoneme_map[symbol] != [item_id]:
            raise ValueError("Pinned source voice config unexpectedly defines a Fasih v2 diphthong.")
        if item_id in used_ids and phoneme_map.get(symbol) != [item_id]:
            raise ValueError("Fasih v2 diphthong ID collides with an existing source phoneme.")
        phoneme_map[symbol] = [item_id]
    result = dict(source_config)
    result["phoneme_id_map"] = phoneme_map
    result["piper_version"] = "1.5.0"
    return result


def _is_valid_fasih_v2_config(path):
    """Validate the generated v2 sidecar without trusting a mutable download."""
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(config, dict):
        return False
    language = config.get("language", {})
    audio = config.get("audio", {})
    phoneme_map = config.get("phoneme_id_map", {})
    return (
        isinstance(language, dict)
        and language.get("code") == "ur_PK"
        and isinstance(audio, dict)
        and audio.get("sample_rate") == 22050
        and config.get("piper_version") == "1.5.0"
        and isinstance(phoneme_map, dict)
        and all(phoneme_map.get(symbol) == [item_id] for symbol, item_id in FASIH_V2_PHONEME_IDS.items())
    )


def _ensure_fasih_v2_config(config_path):
    """Atomically create the exact sidecar schema compatible with the pinned v2 model."""
    if _is_valid_fasih_v2_config(config_path):
        return

    legacy_url = (
        "https://huggingface.co/rhasspy/piper-voices/resolve/"
        + SOURCE_MODEL_REVISION
        + "/ur/ur_PK/fasih/medium/ur_PK-fasih-medium.onnx.json?download=true"
    )
    source_config = None
    if (
        config_path.is_file()
        and config_path.stat().st_size == SOURCE_CONFIG_SIZE_BYTES
        and md5_file(config_path) == SOURCE_CONFIG_MD5
    ):
        source_config = json.loads(config_path.read_text(encoding="utf-8"))
    else:
        # Re-fetch the old sidecar into a temporary path and verify it before deriving v2.
        with tempfile.TemporaryDirectory(prefix="fasih-v1-config-", dir=str(config_path.parent)) as temp_dir:
            trusted_source = Path(temp_dir) / "source-v1.onnx.json"
            download_verified(legacy_url, trusted_source, SOURCE_CONFIG_MD5, SOURCE_CONFIG_SIZE_BYTES)
            source_config = json.loads(trusted_source.read_text(encoding="utf-8"))

    derived = _build_fasih_v2_config(source_config)
    if not all(derived["phoneme_id_map"].get(symbol) == [item_id] for symbol, item_id in FASIH_V2_PHONEME_IDS.items()):
        raise ValueError("Generated Fasih v2 config failed its diphthong-map validation.")
    output_bytes = (json.dumps(derived, ensure_ascii=False, indent=2) + "\\n").encode("utf-8")
    fd, temporary_name = tempfile.mkstemp(
        prefix=config_path.name + ".tmp-", suffix=".json", dir=str(config_path.parent)
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        temporary.write_bytes(output_bytes)
        temporary.replace(config_path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    if not _is_valid_fasih_v2_config(config_path):
        raise ValueError("Generated Fasih v2 config failed final validation.")


def ensure_voice_model():
    """Ensure the pinned Fasih v2 model and its compatible sidecar are present."""
    model_path, config_path, custom = resolve_model_paths()
    if custom:
        if not model_path.is_file():
            raise FileNotFoundError("Configured AGENTHQ_PIPER_URDU_MODEL_PATH does not exist: " + str(model_path))
        if not config_path.is_file():
            raise FileNotFoundError("Piper needs the matching model config file: " + str(config_path))
        return model_path, config_path

    model_url = (
        "https://huggingface.co/" + DEFAULT_MODEL_ID + "/resolve/"
        + DEFAULT_MODEL_REVISION + "/" + MODEL_SOURCE_FILENAME + "?download=true"
    )
    if not model_path.is_file() or model_path.stat().st_size != MODEL_SIZE_BYTES or md5_file(model_path) != MODEL_MD5:
        download_verified(model_url, model_path, MODEL_MD5, MODEL_SIZE_BYTES)
    _ensure_fasih_v2_config(config_path)
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
    # Fail fast before downloading a model if the isolated Piper runtime is absent.
    try:
        from piper import PiperVoice, SynthesisConfig
    except ImportError as exc:
        raise RuntimeError(
            "Piper Urdu voice dependencies are missing. Run "
            "powershell -NoProfile -ExecutionPolicy Bypass -File .\\setup_urdu_tts_windows.ps1"
        ) from exc
    model_path, _ = ensure_voice_model()
    print(
        "Loading Pakistani Urdu male voice: Fasih v2 (pinned ONNX model); "
        + "speech rate is slowed by " + str(round((DEFAULT_LENGTH_SCALE - 1.0) * 100))
        + "% to improve intelligibility.",
        flush=True,
    )
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
                voice.synthesize_wav(
                    item["text"],
                    wav_file,
                    SynthesisConfig(length_scale=DEFAULT_LENGTH_SCALE),
                )
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
