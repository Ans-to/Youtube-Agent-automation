#!/usr/bin/env python3
"""Generate and explicitly approve an audio-only Urdu-English voice preview.

Preview generation never creates an MP4 or approves a production voice. Approval is a
separate interactive action tied to the exact WAV hash and current voice profile SHA-256.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = (ROOT / "workspace").resolve()
sys.path.insert(0, str(ROOT / "video_studio"))
from captions import validate_narration_text
from urdu_tts_adapter import inspect_wav
from voice_backends import (
    get_urdu_tts_command,
    resolve_urdu_tts_command,
    urdu_voice_human_approved,
    urdu_voice_profile_sha256,
)


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


def sidecar_path_for(preview_path):
    """Return the separate provenance/approval sidecar path for a preview WAV."""
    preview = Path(preview_path).expanduser().resolve()
    return preview.with_name(preview.name + ".preview.json")


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_write_json(path, value):
    destination = Path(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n",
            prefix=destination.name + ".", suffix=".tmp",
            dir=str(destination.parent), delete=False,
        ) as stream:
            temporary_name = stream.name
            stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, destination)
    finally:
        if temporary_name and Path(temporary_name).exists():
            Path(temporary_name).unlink()


def _atomic_copy(source, destination):
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = None
    try:
        with Path(source).open("rb") as input_stream, tempfile.NamedTemporaryFile(
            mode="wb", prefix=destination.name + ".", suffix=".tmp",
            dir=str(destination.parent), delete=False,
        ) as output_stream:
            temporary_name = output_stream.name
            shutil.copyfileobj(input_stream, output_stream)
            output_stream.flush()
            os.fsync(output_stream.fileno())
        os.replace(temporary_name, destination)
    finally:
        if temporary_name and Path(temporary_name).exists():
            Path(temporary_name).unlink()


def load_local_config(require_existing=False):
    config_path = ROOT / "config.json"
    try:
        raw = config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        if require_existing:
            raise ValueError("config.json is missing. Run START_HERE.bat before approving a voice.")
        return {}
    try:
        config = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("config.json is invalid JSON; voice preview cannot trust local settings.") from exc
    if not isinstance(config, dict):
        raise ValueError("config.json must contain a JSON object.")
    return config


def generate_voice_preview(text, output, overwrite=False):
    """Run one local Urdu TTS synthesis into a validated workspace WAV."""
    narration = validate_narration_text(text, "ur-en", "Voice preview text")
    destination = resolve_preview_output(output)
    sidecar = sidecar_path_for(destination)
    if (destination.exists() or sidecar.exists()) and not overwrite:
        raise FileExistsError(
            "Voice preview or its metadata already exists. Choose a new filename or pass --overwrite."
        )

    WORKSPACE.mkdir(parents=True, exist_ok=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    config = load_local_config()
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
        print("Generating an audio-only Urdu-English preview; this does not approve a production voice.")
        print("Output:", destination)
        print("Speaker prefix configured:", "yes" if env.get("AGENTHQ_KANI_SPEAKER_PREFIX", "").strip() else "no")
        try:
            result = subprocess.run(
                command, cwd=str(ROOT), capture_output=True, text=True, check=False,
                timeout=1800, env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Urdu voice preview exceeded the 30-minute limit; no approval was recorded.") from exc
        if result.stdout:
            print(result.stdout.rstrip())
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr, flush=True)
        if result.returncode != 0:
            raise RuntimeError("Urdu voice preview adapter failed with exit code " + str(result.returncode) + ".")

        try:
            audio_report = inspect_wav(temp_output)
        except (OSError, ValueError, RuntimeError) as exc:
            raise RuntimeError(
                "Voice preview did not pass PCM16, duration, and non-silence checks: " + str(exc)
            ) from exc

        latest_config = load_local_config()
        latest_fingerprint = urdu_voice_profile_sha256(latest_config)
        if latest_fingerprint != approval_fingerprint:
            raise RuntimeError("Voice settings changed while preview synthesis was running. The WAV was not installed; run the preview again.")

        _atomic_copy(temp_output, destination)
        metadata = {
            "schema_version": 1,
            "status": "awaiting_human_review",
            "preview_relative_path": destination.relative_to(WORKSPACE).as_posix(),
            "audio_sha256": file_sha256(destination),
            "voice_profile_sha256": approval_fingerprint,
            "audio_report": audio_report,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "human_approved": False,
        }
        _atomic_write_json(sidecar, metadata)

    print("Voice preview created:", destination)
    print("Audio check:", json.dumps(audio_report, ensure_ascii=False))
    print("Voice profile SHA-256:", approval_fingerprint)
    print("Review Urdu pronunciation, English technical terms, naturalness, and adult-male speaker identity.")
    print("After personally listening, record your explicit approval with:")
    print("  python video_studio/voice_preview.py --approve-existing " + str(destination.relative_to(ROOT).as_posix()))
    print("No approval was recorded by generating this preview.")
    return destination



def validate_preview_artifact(destination, config, workspace=WORKSPACE):
    """Validate that a WAV sidecar and current configured voice profile still match."""
    root = Path(workspace).expanduser().resolve()
    preview = Path(destination).expanduser().resolve()
    try:
        relative_path = preview.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError("Voice preview must remain inside the project workspace.") from exc

    sidecar = sidecar_path_for(preview)
    if not preview.is_file() or not sidecar.is_file():
        raise ValueError("Preview WAV and its .preview.json sidecar are both required. Generate a fresh preview first.")
    try:
        metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Voice preview sidecar is invalid JSON. Generate a fresh preview.") from exc
    if not isinstance(metadata, dict) or metadata.get("schema_version") != 1:
        raise ValueError("Voice preview sidecar schema is unsupported. Generate a fresh preview.")
    if metadata.get("preview_relative_path") != relative_path:
        raise ValueError("The preview file path no longer matches its sidecar. Generate a fresh preview.")
    if metadata.get("audio_sha256") != file_sha256(preview):
        raise ValueError("The preview WAV changed after synthesis. Generate and listen to a fresh preview.")
    audio_report = inspect_wav(preview)

    current_fingerprint = urdu_voice_profile_sha256(config)
    if metadata.get("voice_profile_sha256") != current_fingerprint:
        raise ValueError("The configured voice/model/speaker profile changed after this preview. Generate and listen to a fresh preview.")
    return {
        "preview_path": preview,
        "sidecar_path": sidecar,
        "metadata": metadata,
        "voice_profile_sha256": current_fingerprint,
        "audio_report": audio_report,
    }



def approve_existing_preview(path):
    """Interactively approve a WAV only when its sidecar and voice fingerprint still match."""
    destination = resolve_preview_output(path)
    config = load_local_config(require_existing=True)
    validated = validate_preview_artifact(destination, config)
    metadata = validated["metadata"]
    current_fingerprint = validated["voice_profile_sha256"]
    sidecar = validated["sidecar_path"]

    print("Preview WAV:", destination)
    print("Voice profile SHA-256:", current_fingerprint)
    print("You must personally listen to the WAV before approving it.")
    print("This confirmation attests to natural adult-male Pakistani Urdu, intelligible pronunciation,")
    print("and correct preservation of English technical terms.")
    answer = input("Type APPROVE only if you heard and accept this exact preview: ").strip()
    if answer != "APPROVE":
        print("Voice remains unapproved. No config settings were changed.")
        return False

    video_config = config.setdefault("video_studio", {})
    if not isinstance(video_config, dict):
        raise ValueError("config.json video_studio settings must be an object.")
    video_config["urdu_voice_human_approved"] = True
    video_config["urdu_voice_approved_profile_sha256"] = current_fingerprint
    _atomic_write_json(ROOT / "config.json", config)
    if not urdu_voice_human_approved(load_local_config(require_existing=True)):
        raise RuntimeError("Saved voice approval did not pass its fingerprint check. Leave production rendering blocked.")
    metadata["status"] = "human_approved_for_current_profile"
    metadata["human_approved"] = True
    metadata["human_approval_at_utc"] = datetime.now(timezone.utc).isoformat()
    _atomic_write_json(sidecar, metadata)
    print("Voice approval saved to local config.json for this exact profile fingerprint.")
    print("If the adapter, model revision, dependency spec, or speaker prefix changes, approval is invalidated.")
    print("This approval does not approve video visuals, factual claims, or YouTube publication.")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", help="Urdu-English narration sample text.")
    parser.add_argument("--output", default="workspace/urdu-voice-preview.wav", help="WAV path inside workspace; defaults to workspace/urdu-voice-preview.wav.")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing preview WAV and sidecar after a successful synthesis.")
    parser.add_argument("--approve-existing", metavar="WAV", help="Interactively approve an already generated WAV after listening.")
    args = parser.parse_args(argv)
    if bool(args.text) == bool(args.approve_existing):
        parser.error("Choose exactly one action: --text to synthesize a preview, or --approve-existing WAV after listening.")
    try:
        if args.approve_existing:
            approve_existing_preview(args.approve_existing)
        else:
            generate_voice_preview(args.text, args.output, args.overwrite)
    except (OSError, ValueError, RuntimeError, EOFError) as exc:
        print("URDU VOICE PREVIEW FAILED:", str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
