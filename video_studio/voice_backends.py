"""Safe command selection for bundled and explicitly configured local Urdu TTS backends."""
import json
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


def urdu_voice_human_approved(config):
    """Return whether a human explicitly approved this exact local Urdu voice setup.

    This is a release gate, not a claim that a speaker is male or natural. Approval is
    intended only after listening to a real sample and checking Urdu pronunciation,
    retained English technical terms, and the required adult-male voice.
    """
    root = config.get("video_studio", {}) if isinstance(config, dict) else {}
    if not isinstance(root, dict):
        raise ValueError("config.json video_studio settings must be an object.")
    value = root.get("urdu_voice_human_approved", False)
    if not isinstance(value, bool):
        raise ValueError("config.json video_studio.urdu_voice_human_approved must be true or false.")
    return value


def builtin_urdu_tts_command():
    """Run the bundled CPU adapter using this exact Python interpreter."""
    adapter = Path(__file__).resolve().with_name("urdu_tts_adapter.py")
    return [sys.executable, str(adapter), "--manifest", "{manifest_file}"]


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
