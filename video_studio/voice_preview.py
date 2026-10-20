#!/usr/bin/env python3
"""Generate an audio-only Urdu-English voice preview without releasing a video.

This command intentionally bypasses the production-approval gate only for an isolated
WAV preview. It never creates an MP4 and never marks the configured voice as approved.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = (ROOT / "workspace").resolve()
sys.path.insert(0, str(ROOT / "video_studio"))
from captions import validate_narration_text
from voice_backends import get_urdu_tts_command, resolve_urdu_tts_command, urdu_voice_profile_sha256
from urdu_tts_adapter import inspect_wav


def resolve_preview_output(path, workspace=WORKSPACE, project_root=ROOT):
    """Resolve a preview WAV strictly beneath workspace and reject ambiguous extensions.

    Paths prefixed with "workspace/" are project-root-relative for the documented CLI;
    a bare filename or other relative path is relative to the workspace itself.
    """
    root = Path(workspace).expanduser().resolve()
    project = Path(project_root).expanduser().resolve()
    value = Path(path).expanduser()
    if value.is_absolute():
        destination = value.resolve()
    elif value.parts and value.parts[0].lower() == "workspace":
        destination = (project / value).resolve()
    else:
        destination = (root / value).resolve()
    try:
        destination.relative_to(root)
    except ValueError as exc:
        raise ValueError("Voice preview output must stay inside the project workspace.") from exc
    if destination == root:
        raise ValueError("Voice preview output must be a WAV file path, not the workspace directory.")
    if destination.suffix.lower() != ".wav":
        raise ValueError("Voice preview output must use the .wav extension.")
    return destination


def generate_voice_preview(text, output, overwrite=False):
    """Run one local Urdu TTS synthesis into a validated workspace WAV."""
    narration = validate_narration_text(text, "ur-en", "Voice preview text")
    destination = resolve_preview_output(output)
    if destination.exists() and not overwrite:
        raise FileExistsError(
            "Voice preview already exists: " + str(destination) + ". Choose another path or pass --overwrite."
        )
    if destination.exists() and destination.is_dir():
        raise ValueError("Voice preview output path is a directory.")
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    destination.parent.mkdir(parents=True, exist_ok=True)

    config_path = ROOT / "config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        config = {}
    except json.JSONDecodeError as exc:
        raise ValueError("config.json is invalid JSON; voice preview cannot trust the local settings.") from exc
    if not isinstance(config, dict):
        raise ValueError("config.json must contain a JSON object.")

    command_template = get_urdu_tts_command(config)
    approval_fingerprint = urdu_voice_profile_sha256(config)
    with tempfile.TemporaryDirectory(prefix="urdu-voice-preview-", dir=str(WORKSPACE)) as temp:
        temp_root = Path(temp)
        text_file = temp_root / "narration.txt"
        temp_output = temp_root / "preview.wav"
        manifest = temp_root / "manifest.json"
        text_file.write_text(narration + "\n", encoding="utf-8")
        manifest.write_text(json.dumps({
            "schema_version": 1,
            "items": [{"text_file": str(text_file.resolve()), "output_file": str(temp_output.resolve())}],
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        env = os.environ.copy()
        if any(Path(part).name == "urdu_tts_adapter.py" for part in command_template):
            video_config = config.get("video_studio", {}) if isinstance(config.get("video_studio", {}), dict) else {}
            prefix = video_config.get("kani_speaker_prefix", "")
            if not isinstance(prefix, str):
                raise ValueError("config.json video_studio.kani_speaker_prefix must be text.")
            env["AGENTHQ_KANI_SPEAKER_PREFIX"] = prefix.strip()

        if any("{manifest_file}" in part for part in command_template):
            command = resolve_urdu_tts_command(command_template, manifest_file=manifest)
        else:
            command = resolve_urdu_tts_command(
                command_template, text_file=text_file, output_file=temp_output
            )
        timeout = 1800
        print("Generating an audio-only Urdu-English preview; this does not approve a production voice.")
        print("Output:", destination)
        print("Speaker prefix configured:", "yes" if env.get("AGENTHQ_KANI_SPEAKER_PREFIX", "").strip() else "no")
        try:
            result = subprocess.run(
                command, cwd=str(ROOT), capture_output=True, text=True, check=False,
                timeout=timeout, env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Urdu voice preview exceeded the 30-minute limit; no approval was recorded.") from exc
        if result.stdout:
            print(result.stdout.rstrip())
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)
        if result.returncode != 0:
            raise RuntimeError("Urdu voice preview adapter failed with exit code " + str(result.returncode) + ".")
        try:
            audio_report = inspect_wav(temp_output)
        except (OSError, ValueError, RuntimeError) as exc:
            raise RuntimeError(
                "Voice preview did not pass PCM16, duration, and non-silence checks: " + str(exc)
            ) from exc
        # Copy only after technical audio validation succeeds so a failed preview never
        # replaces the selected destination.
        import shutil
        shutil.copy2(temp_output, destination)

    print("Voice preview created:", destination)
    print("Audio check:", json.dumps(audio_report, ensure_ascii=False))
    print("Voice profile SHA-256:", approval_fingerprint)
    print("Human review still required: adult-male voice identity, naturalness, Urdu pronunciation, and English technical terms.")
    print("Only after listening to this WAV, set video_studio.urdu_voice_human_approved=true and")
    print("video_studio.urdu_voice_approved_profile_sha256 to the exact fingerprint above in config.json.")
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", required=True, help="One Urdu-English narration sample, including English technical terms.")
    parser.add_argument("--output", default="workspace/urdu-voice-preview.wav", help="WAV path inside workspace; defaults to workspace/urdu-voice-preview.wav.")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing preview WAV after a successful synthesis.")
    args = parser.parse_args(argv)
    try:
        generate_voice_preview(args.text, args.output, args.overwrite)
    except (OSError, ValueError, RuntimeError) as exc:
        print("URDU VOICE PREVIEW FAILED:", str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
