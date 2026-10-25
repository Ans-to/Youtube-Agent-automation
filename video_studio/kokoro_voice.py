#!/usr/bin/env python3
"""Kokoro narration: a neural voice that can be fetched without an account.

Piper was the only speech model this studio could reach, and it is a 2021-era
VITS voice: correct, intelligible, and unmistakably synthetic. Kokoro-82M is a
different generation - it carries sentence prosody, question rises and list
cadences on its own - and it is Apache-2.0, so it can ship with the studio.

The awkward part is getting the weights. Kokoro's usual home is HuggingFace,
which the build runners cannot reach. The weights happen to be published to
npm, which they can: `kokoro-q8-shards` carries the 82M model as six byte-range
shards, and `kokoro-js` carries the 54 voice embeddings. Both are Apache-2.0.
So this module downloads three ordinary npm tarballs, checks each against the
registry's own SHA-512, stitches the shards back into one `.onnx`, packs the
voice embeddings into one `.npz`, and caches the result. No account, no token,
no payment, and the download happens once per runner.

If npm is unreachable the studio keeps working: `voiceover.py` falls back to
Piper, and a film still ships with a voice rather than without one.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import shutil
import tarfile
import urllib.request
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

SAMPLE_RATE = 24000
DEFAULT_KOKORO_VOICE = "am_michael"

# Pinned exactly: a version that moves would change how every film sounds, and
# the integrity string is what makes the pin mean something.
PACKAGES: dict[str, dict[str, str]] = {
    "kokoro-q8-shards": {
        "version": "1.0.0",
        "url": "https://registry.npmjs.org/kokoro-q8-shards/-/kokoro-q8-shards-1.0.0.tgz",
        "integrity": "sha512-KoJQ203LxUOFrHAm12mu+hRmvqTmOcCgz61OVgTxmxX4isWaufLCF6kYz+QwOzVFYGNS62HHJWBHUbhzeoR43g==",
        "bytes": 61000000,
    },
    "kokoro-js": {
        "version": "1.2.1",
        "url": "https://registry.npmjs.org/kokoro-js/-/kokoro-js-1.2.1.tgz",
        "integrity": "sha512-oq0HZJWis3t8lERkMJh84WLU86dpYD0EuBPtqYnLlQzyFP1OkyBRDcweAqCfhNOpltyN9j/azp1H6uuC47gShw==",
        "bytes": 30400000,
    },
}
MODEL_SHARDS = 6
MAX_PHONEME_ROW = 509
# Kokoro's speed is 1.0 at its own tempo. The narration scripts were written
# against Piper's length_scale, where 0.82 is the neutral pace, so a line's
# `rate` is re-based here instead of being read as a Kokoro speed directly.
NEUTRAL_RATE = 0.82
# Kokoro's own tempo reads about 180 words a minute, which is a hurried
# explainer rather than a narrator. 0.86 lands a line near 155 wpm, the pace of
# the explainer channels this studio is modelled on.
KOKORO_TEMPO = 0.86
SPEED_FLOOR, SPEED_CEILING = 0.70, 1.25


class KokoroUnavailable(RuntimeError):
    """No Kokoro weights, session or voices could be produced."""


def cache_dir() -> Path:
    explicit = os.environ.get("AGENTHQ_KOKORO_DIR")
    if explicit:
        return Path(explicit)
    root = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(root) / "agent-hq" / "kokoro"


def _sha512(path: Path) -> str:
    digest = hashlib.sha512()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return "sha512-" + base64.b64encode(digest.digest()).decode("ascii")


def _download(name: str, target_dir: Path) -> Path:
    """Fetch one pinned tarball, or reuse the cached copy if it still matches."""
    spec = PACKAGES[name]
    target = target_dir / f"{name}-{spec['version']}.tgz"
    if target.is_file() and _sha512(target) == spec["integrity"]:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".part")
    try:
        with urllib.request.urlopen(spec["url"], timeout=180) as response, partial.open("wb") as sink:
            shutil.copyfileobj(response, sink, length=1 << 20)
    except Exception as exc:  # network, DNS, proxy - all the same to the caller
        partial.unlink(missing_ok=True)
        raise KokoroUnavailable(f"could not download {name}: {exc}") from exc
    got = _sha512(partial)
    if got != spec["integrity"]:
        partial.unlink(missing_ok=True)
        raise KokoroUnavailable(
            f"{name} failed its integrity check (expected {spec['integrity']}, got {got})")
    partial.replace(target)
    return target


def _members(tarball: Path) -> dict[str, tarfile.TarInfo]:
    with tarfile.open(tarball, "r:gz") as tf:
        return {member.name: member for member in tf.getmembers() if member.isfile()}


def _read(tarball: Path, member: str) -> bytes:
    with tarfile.open(tarball, "r:gz") as tf:
        handle = tf.extractfile(member)
        if handle is None:
            raise KokoroUnavailable(f"{tarball.name} has no {member}")
        return handle.read()


def build_model(target_dir: Path | None = None) -> Path:
    """Stitch the six shards into one ONNX graph. Idempotent."""
    target_dir = Path(target_dir) if target_dir else cache_dir()
    model = target_dir / "kokoro-82m-q8.onnx"
    if model.is_file() and model.stat().st_size > 80_000_000:
        return model

    tarball = _download("kokoro-q8-shards", target_dir)
    members = _members(tarball)
    parts = [f"package/kokoro-q8.part{index}.bin" for index in range(MODEL_SHARDS)]
    missing = [part for part in parts if part not in members]
    if missing:
        raise KokoroUnavailable(f"{tarball.name} is missing {', '.join(missing)}")

    partial = model.with_suffix(".onnx.part")
    with partial.open("wb") as sink:
        for part in parts:
            sink.write(_read(tarball, part))
    size = partial.stat().st_size
    if size < 80_000_000:
        partial.unlink(missing_ok=True)
        raise KokoroUnavailable(f"the stitched model is only {size} bytes, which is not a full model")
    partial.replace(model)
    return model


def build_voices(target_dir: Path | None = None, names: Iterable[str] | None = None) -> Path:
    """Pack the per-voice embeddings into the `.npz` kokoro-onnx expects."""
    target_dir = Path(target_dir) if target_dir else cache_dir()
    packed = target_dir / "voices.npz"
    wanted = sorted(set(names)) if names else None
    if packed.is_file():
        try:
            with np.load(packed) as archive:
                present = set(archive.files)
            if wanted is None or present.issuperset(wanted):
                return packed
        except Exception:
            pass  # a truncated cache is rebuilt rather than trusted

    # One writer at a time. A render forks several voice workers, and without
    # this each of them could start rebuilding the pack while another read it,
    # which surfaced as a bare EOFError from inside numpy.
    target_dir.mkdir(parents=True, exist_ok=True)
    lock_path = target_dir / "voices.lock"
    with lock_path.open("w") as lock:
        try:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        except Exception:
            pass  # Windows, or no fcntl: the atomic swap below still protects readers
        if packed.is_file():
            try:
                with np.load(packed) as archive:
                    present = set(archive.files)
                if wanted is None or present.issuperset(wanted):
                    return packed
            except Exception:
                pass

        tarball = _download("kokoro-js", target_dir)
        members = [name for name in _members(tarball)
                   if name.startswith("package/voices/") and name.endswith(".bin")]
        if not members:
            raise KokoroUnavailable("kokoro-js carries no voice embeddings")

        # Every voice is packed, not only the requested one: the file is one
        # cache entry shared by all of them, and rewriting it to add a voice is
        # what made a second render race the first.
        voices: dict[str, np.ndarray] = {}
        for member in sorted(members):
            name = Path(member).stem
            raw = np.frombuffer(_read(tarball, member), dtype=np.float32)
            if raw.size % 256:
                continue
            rows = raw.size // 256
            voices[name] = raw.reshape(rows, 1, 256)

        if wanted is not None:
            absent = sorted(set(wanted) - set(voices))
            if absent:
                raise KokoroUnavailable(f"no such Kokoro voice: {', '.join(absent)}")
        partial = packed.with_suffix(".part")
        # np.savez appends its own .npz unless it is handed a file object
        with partial.open("wb") as sink:
            np.savez(sink, **voices)
        partial.replace(packed)
        return packed


def available() -> bool:
    """Whether the runtime is importable. Weights are fetched lazily."""
    try:
        import kokoro_onnx  # noqa: F401
    except Exception:
        return False
    return True


_SESSION = None
_SESSION_KEY: tuple[str, str, str] | None = None


def session(voice: str = DEFAULT_KOKORO_VOICE):
    """One loaded model per process; loading takes about a second."""
    global _SESSION, _SESSION_KEY
    if not available():
        raise KokoroUnavailable("the kokoro-onnx package is not installed")
    model = build_model()
    voices = build_voices(names=[voice])
    # The voice name belongs in the key: the packed voices file has one path for
    # every voice, so a same-path check would keep serving the first voice loaded.
    key = (str(model), str(voices), voice)
    if _SESSION is None or _SESSION_KEY != key:
        from kokoro_onnx import Kokoro
        _SESSION = Kokoro(str(model), str(voices))
        # kokoro-onnx keeps a lazy NpzFile, which holds an open file handle. A
        # render forks workers, and a forked child sharing that handle reads at
        # the wrong offset: the symptom is a BadZipFile CRC error. Loading every
        # voice into memory closes the handle before any fork happens.
        _SESSION.voices = dict(_SESSION.voices)
        _SESSION_KEY = key
    return _SESSION


def reset_session() -> None:
    """Drop the loaded model so a forked worker opens its own handles."""
    global _SESSION, _SESSION_KEY
    _SESSION = None
    _SESSION_KEY = None


def voices_available() -> list[str]:
    """Every voice name the cached pack carries, for `--list-voices`."""
    try:
        with np.load(build_voices()) as archive:
            return sorted(archive.files)
    except Exception:
        return []


def _speed_for(rate: float) -> float:
    # `rate` is a pace multiplier, the same field Piper's length_scale is built
    # from: a higher number means a faster read. Kokoro's speed points the same
    # way, so it scales directly. Getting this backwards made a line marked
    # "slow" come out faster than the neutral one.
    speed = KOKORO_TEMPO * max(rate, 1e-6) / NEUTRAL_RATE
    return float(min(SPEED_CEILING, max(SPEED_FLOOR, speed)))


def synth_line(line, out_path: Path, *, voice: str = DEFAULT_KOKORO_VOICE) -> None:
    """Render one narration line with clause-level phrasing, then master it."""
    import voiceover
    import voice_production

    engine = session(voice)
    base_speed = _speed_for(getattr(line, "rate", NEUTRAL_RATE))
    text = voiceover.spoken_text(line.text)

    def synth_clause(clause: str, pace: float) -> np.ndarray:
        audio, rate = engine.create(clause, voice=voice, speed=base_speed * pace,
                                    lang="en-us", trim=True)
        audio = np.asarray(audio, dtype=np.float32).ravel()
        if audio.size == 0:
            return audio
        return voiceover.resample(audio, rate, SAMPLE_RATE)

    audio = voice_production.synthesise_line(text, synth_clause, SAMPLE_RATE)
    if audio.size == 0:
        raise KokoroUnavailable(f"kokoro produced no audio for {text!r}")
    # Level the line once, not each clause: per-clause normalisation pulls a
    # quiet clause up to full scale and flattens the sentence's own dynamics.
    peak = float(np.max(np.abs(audio)))
    if peak > 0:
        audio = audio / peak * 0.89
    voiceover.write_wav(Path(out_path), audio, SAMPLE_RATE)


def synth_batch(payload: tuple[list[tuple[str, str, float]], str, str]) -> list[str]:
    """Worker entry point: render a list of (id, text, rate) on one process.

    espeak-ng, which Kokoro phonemises with, keeps process-global state, so the
    lines are spread across processes rather than threads.
    """
    items, out_dir, voice = payload
    import voiceover

    reset_session()   # never inherit the parent's model or its file handles
    written = []
    for line_id, text, rate in items:
        line = voiceover.Line(text=text, rate=rate, id=line_id)
        target = Path(out_dir) / f"{line_id}.wav"
        synth_line(line, target, voice=voice)
        written.append(str(target))
    return written


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Prepare the Kokoro voice cache")
    parser.add_argument("--dir", default=None, help="cache directory")
    parser.add_argument("--voice", default=DEFAULT_KOKORO_VOICE)
    parser.add_argument("--speak", default=None, help="synthesise this text as a test")
    parser.add_argument("--out", default=None, help="where to write the test wav")
    args = parser.parse_args(argv)

    target = Path(args.dir) if args.dir else cache_dir()
    model = build_model(target)
    packed = build_voices(target, names=[args.voice])
    print(json.dumps({"model": str(model), "model_bytes": model.stat().st_size,
                      "voices": str(packed), "voice_bytes": packed.stat().st_size,
                      "voice": args.voice}, indent=2))
    if args.speak:
        out = Path(args.out or "kokoro-test.wav")
        import voiceover
        synth_line(voiceover.Line(text=args.speak, rate=NEUTRAL_RATE, id="test"), out,
                   voice=args.voice)
        print("wrote %s (%.2fs)" % (out, out.stat().st_size / (SAMPLE_RATE * 2)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
