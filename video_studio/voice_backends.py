"""Small, shell-free adapter contract for an explicitly configured local Urdu TTS engine.

No voice model is bundled or assumed to be licensed. A configured adapter must accept a
UTF-8 text file and write a non-empty WAV file to the provided output path.
"""
import json
from pathlib import Path


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


def get_urdu_tts_command(config):
    """Return a validated argument-array template, or None when Urdu TTS is not configured.

    The command is an argv list, never a shell string. It must include {text_file} and
    {output_file} placeholders so the renderer can control input/output paths.
    """
    root = config.get("video_studio", {}) if isinstance(config, dict) else {}
    if not isinstance(root, dict):
        raise ValueError("config.json video_studio settings must be an object.")
    command = root.get("urdu_tts_command", [])
    if command is None or command == []:
        return None
    if not isinstance(command, list) or not command or any(
        not isinstance(part, str) or not part.strip() for part in command
    ):
        raise ValueError("video_studio.urdu_tts_command must be a non-empty array of command arguments.")
    if not any("{text_file}" in part for part in command):
        raise ValueError("Urdu TTS adapter command must include a {text_file} argument placeholder.")
    if not any("{output_file}" in part for part in command):
        raise ValueError("Urdu TTS adapter command must include an {output_file} argument placeholder.")
    return list(command)


def resolve_urdu_tts_command(template, text_file, output_file):
    """Substitute only the two documented placeholders; never invoke a shell."""
    if not isinstance(template, list) or not template:
        raise ValueError("Urdu TTS adapter command is not configured.")
    text_path = str(Path(text_file).expanduser().resolve())
    output_path = str(Path(output_file).expanduser().resolve())
    resolved = [
        part.replace("{text_file}", text_path).replace("{output_file}", output_path)
        for part in template
    ]
    if any("{" in part or "}" in part for part in resolved):
        raise ValueError("Urdu TTS adapter command contains an unsupported template placeholder.")
    return resolved
