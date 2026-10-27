#!/usr/bin/env python3
"""Recover deterministic Kokoro *phrase* timings for the existing review voice.

This does not force-align words. It re-synthesizes each original phrase using the
same model, voice and performance, verifies that the concatenated sample count
matches the recorded WAV, and records phrase boundaries. Visual cues within each
phrase are still estimates and require human listening review. It never replaces
or alters the original narration or mix.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import wave
from pathlib import Path

# Do not oversubscribe a small workstation before NumPy/ONNX initializes.
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')

try:
    import voice as V
except ModuleNotFoundError:
    from . import voice as V


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def recover(rows: list[dict], voice_dir: Path, narrator: str = 'bm_george', rate: float = .95) -> dict:
    import onnxruntime as rt
    from kokoro_onnx import Kokoro
    options = rt.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    session = rt.InferenceSession(str(V.MODEL), sess_options=options, providers=['CPUExecutionProvider'])
    engine = Kokoro.from_session(session, str(V.VOICES))
    V.set_profile('calm')
    records = []
    for row in rows:
        audio_path = voice_dir / row['file']
        with wave.open(str(audio_path), 'rb') as wav:
            if wav.getframerate() != V.SR or wav.getnchannels() != 1:
                raise ValueError(f"{row['shot']}: original voice must be mono 48 kHz")
            original_frames = wav.getnframes()
        chunks = V.phrases(row['text'])
        frames = 0
        offset = 0
        phrases = []
        for index, (chunk, stop) in enumerate(chunks):
            trimmed_text = chunk.strip()
            char_start = row['text'].find(trimmed_text, offset)
            if char_start < 0:
                raise ValueError(f"{row['shot']}: phrase not found in source text")
            char_end = char_start + len(trimmed_text)
            offset = char_end
            samples, sr = engine.create(chunk, voice=narrator,
                                        speed=rate * V.shape_rate(index, len(chunks)), lang='en-us')
            samples = V.trim(V.resample(samples, sr, V.SR))
            start, end = frames, frames + len(samples)
            gap = int(V.PAUSE[stop] * V.PERFORMANCE[V.PROFILE]['pause'] * V.SR) if stop != 'none' else 0
            phrases.append({'text': trimmed_text, 'char_start': char_start, 'char_end': char_end,
                            'start_sample': start, 'end_sample': end, 'pause_samples': gap})
            frames = end + gap
        # Matching lengths verify the reconstruction's timebase, not word alignment
        # or a bit-for-bit match of the processed audio.
        if frames != original_frames:
            raise ValueError(f"{row['shot']}: regenerated {frames} frames, recorded {original_frames}; refusing timings")
        records.append({'shot': row['shot'], 'audio_sha256': sha256(audio_path),
                        'sample_rate': V.SR, 'samples': frames, 'phrases': phrases})
        print(f"{row['shot']}: {len(phrases)} phrases, {frames} verified samples", flush=True)
    return {'schema_version': 1, 'method': 'Kokoro phrase resynthesis; sample counts matched existing voice WAVs',
            'caveat': 'Word positions within each phrase are estimates; human listening and synchronization review required.',
            'voice': narrator, 'rate': rate, 'profile': 'calm', 'shots': records}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timing', type=Path, required=True)
    parser.add_argument('--voice-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads(args.timing.read_text())
    result = recover(rows, args.voice_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()
