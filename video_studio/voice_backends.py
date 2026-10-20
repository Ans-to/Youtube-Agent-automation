"""Safe command selection for bundled and explicitly configured local Urdu TTS backends."""
import hashlib
import json
import os
from pathlib import Path
import sys


def load_project_config(project_root):
    """Load local config as an object; malformed config is an error, not a silent fallback."""
    path = Path(project_root).expanduser().resolve() / "config.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise ValueError("config.json is invalid JSON; narration settings cannot be trusted.") from exc
    if not isinstance(data, dict):
        raise ValueError("config.json must contain a JSON object.")
    return data


def urdu_voice_profile_sha256(config):
    """Fingerprint the configured Urdu TTS route, pinned model, and executable adapter."""
    root = config.get("video_studio", {}) if isinstance(config, dict) else {}
    if not isinstance(root, dict):
        raise ValueError("config.json video_studio settings must be an object.")
    prefix = root.get("kani_speaker_prefix", "")
    if not isinstance(prefix, str):
        raise ValueError("config.json video_studio.kani_speaker_prefix must be text.")
    command = root.get("urdu_tts_command", [])
    if command is None:
        command = []
    if not isinstance(command, list) or any(not isinstance(part, str) for part in command):
        raise ValueError("config.json video_studio.urdu_tts_command must be an array of strings.")

    source_hashes = {}
    module_path = Path(__file__).resolve()
    project_root = module_path.parents[1]
    if not command:
        from piper_urdu_tts_adapter import (
            DEFAULT_MODEL_ID,
            DEFAULT_MODEL_REVISION,
            MODEL_MD5,
            CONFIG_MD5,
        )
        model_id = os.environ.get("AGENTHQ_PIPER_URDU_MODEL_PATH", "").strip() or DEFAULT_MODEL_ID
        revision = DEFAULT_MODEL_REVISION
        route = "bundled-piper-onnx-cpu"
        codec_model = "none; Piper ONNX Runtime"
        source_paths = [
            module_path,
            module_path.with_name("piper_urdu_tts_adapter.py"),
            module_path.with_name("requirements-urdu-tts.txt"),
        ]
        voice_artifact_hashes = {"onnx_md5": MODEL_MD5, "config_md5": CONFIG_MD5}
        # The model is pinned and downloaded with these checksums. Do not fingerprint
        # local cache presence, or approval would change merely because first use
        # populated the model cache after the audio preview was generated.
        speaker_profile = "Fasih Pakistani Urdu male voice (single speaker)"
    else:
        model_id = os.environ.get("AGENTHQ_URDU_TTS_MODEL", "custom-adapter").strip() or "custom-adapter"
        revision = os.environ.get("AGENTHQ_URDU_TTS_REVISION", "external-model-unspecified").strip()
        route = "custom-adapter"
        codec_model = os.environ.get("AGENTHQ_URDU_TTS_CODEC", "external-codec-unspecified").strip()
        source_paths = [module_path]
        for part in command:
            if Path(part).suffix.lower() == ".py":
                candidate = Path(part).expanduser()
                if not candidate.is_absolute():
                    candidate = project_root / candidate
                source_paths.append(candidate.resolve())
        voice_artifact_hashes = {}
        speaker_profile = prefix.strip()

    for source_path in source_paths:
        label = str(source_path.resolve().relative_to(project_root)) if source_path.resolve().is_relative_to(project_root) else source_path.name
        try:
            source_hashes[label] = hashlib.sha256(source_path.read_bytes()).hexdigest()
        except OSError:
            source_hashes[label] = "unavailable"

    payload = {
        "schema_version": 3,
        "route": route,
        "command": command,
        "model_id": model_id,
        "model_revision": revision,
        "voice_artifact_hashes": voice_artifact_hashes,
        "codec_model": codec_model,
        "speaker_profile": speaker_profile,
        "source_sha256": source_hashes,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def urdu_voice_human_approved(config):
    """Return true only when a human approval matches the current Urdu voice profile."""
    root = config.get("video_studio", {}) if isinstance(config, dict) else {}
    if not isinstance(root, dict):
        raise ValueError("config.json video_studio settings must be an object.")
    value = root.get("urdu_voice_human_approved", False)
    if not isinstance(value, bool):
        raise ValueError("config.json video_studio.urdu_voice_human_approved must be true or false.")
    approved_profile = root.get("urdu_voice_approved_profile_sha256", "")
    if not isinstance(approved_profile, str):
        raise ValueError("config.json video_studio.urdu_voice_approved_profile_sha256 must be text.")
    if not value:
        return False
    current_profile = urdu_voice_profile_sha256(config)
    return approved_profile.strip().lower() == current_profile



def require_urdu_voice_human_approval(config):
    """Raise until a human has approved the exact currently configured Urdu voice profile."""
    current_profile = urdu_voice_profile_sha256(config)
    if not urdu_voice_human_approved(config):
        raise ValueError(
            "Urdu-English production render is blocked pending human voice approval for the current voice profile. "
            "Run video_studio/voice_preview.py and listen to the WAV for adult-male voice identity, Urdu pronunciation, "
            "and English technical terms. Then set video_studio.urdu_voice_human_approved=true and "
            "video_studio.urdu_voice_approved_profile_sha256 to this exact SHA-256 in config.json: "
            + current_profile + ". The fingerprint becomes invalid when the model, adapter, or speaker prefix changes."
        )


def builtin_urdu_tts_command():
    """Use the isolated Piper Urdu interpreter when installed, else show its setup error."""
    module = Path(__file__).resolve()
    project_root = module.parents[1]
    adapter = module.with_name("piper_urdu_tts_adapter.py")
    if sys.platform == "win32":
        candidates = [project_root / ".venv-urdu-tts" / "Scripts" / "python.exe"]
    else:
        candidates = [project_root / ".venv-urdu-tts" / "bin" / "python"]
    interpreter = next((candidate for candidate in candidates if candidate.is_file()), Path(sys.executable))
    return [str(interpreter), str(adapter), "--manifest", "{manifest_file}"]


def get_urdu_tts_command(config):
    """Return a validated argv template; empty config selects the bundled local adapter.

    The built-in adapter accepts a manifest so the model is loaded once for every scene
    in a video. A custom adapter may instead expose a manifest interface or the legacy
    one-scene {text_file}/{output_file} interface. Commands are never shell strings.
    """
    root = config.get("video_studio", {}) if isinstance(config, dict) else {}
    if not isinstance(root, dict):
        raise ValueError("config.json video_studio settings must be an object.")
    command = root.get("urdu_tts_command", [])
    if command is None or command == []:
        return builtin_urdu_tts_command()
    if not isinstance(command, list) or not command or any(
        not isinstance(part, str) or not part.strip() for part in command
    ):
        raise ValueError("video_studio.urdu_tts_command must be a non-empty array of command arguments.")
    has_manifest = any("{manifest_file}" in part for part in command)
    has_text = any("{text_file}" in part for part in command)
    has_output = any("{output_file}" in part for part in command)
    if has_manifest and (has_text or has_output):
        raise ValueError("Urdu TTS command must use either {manifest_file} or the text/output placeholders, not both.")
    if not has_manifest and not (has_text and has_output):
        raise ValueError("Urdu TTS command must include {manifest_file}, or both {text_file} and {output_file}.")
    return list(command)


def resolve_urdu_tts_command(template, text_file=None, output_file=None, manifest_file=None):
    """Substitute only documented absolute-path placeholders; never invoke a shell."""
    if not isinstance(template, list) or not template:
        raise ValueError("Urdu TTS adapter command is not configured.")
    replacements = {}
    if text_file is not None:
        replacements["{text_file}"] = str(Path(text_file).expanduser().resolve())
    if output_file is not None:
        replacements["{output_file}"] = str(Path(output_file).expanduser().resolve())
    if manifest_file is not None:
        replacements["{manifest_file}"] = str(Path(manifest_file).expanduser().resolve())
    resolved = []
    for part in template:
        value = part
        for token, path in replacements.items():
            value = value.replace(token, path)
        if "{" in value or "}" in value:
            raise ValueError("Urdu TTS adapter command contains an unsupported or unresolved template placeholder.")
        resolved.append(value)
    return resolved
