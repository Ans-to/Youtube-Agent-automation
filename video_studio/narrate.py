"""Narration: lines in, timed wavs out, mixed under the score.

The voice is `voice.py` - phrasing, pauses, EQ, compression, -16 LUFS. This file
only does the bookkeeping: which line belongs to which shot, how long it took, and
how it sits against the music.
"""
from __future__ import annotations

import argparse
import json
import math
import wave
from pathlib import Path

import numpy as np

try:                      # run as a script: `python narrate.py ...`
    import voice as V
except ModuleNotFoundError:  # imported as a package, by the tests
    from . import voice as V

SR = V.SR


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path)) as f:
        n, channels, rate = f.getnframes(), f.getnchannels(), f.getframerate()
        data = np.frombuffer(f.readframes(n), dtype='<i2').astype(np.float32) / 32768
    return data.reshape(-1, channels).mean(axis=1), rate


def synth(lines: list[dict], out_dir: Path, voice: str = 'bm_george',
          rate: float = 0.95, engine: str = 'kokoro') -> list[dict]:
    V.require_engine(engine)
    out_dir.mkdir(parents=True, exist_ok=True)
    timing = []
    at = 0.0
    for i, line in enumerate(lines):
        audio = V.synth(line['text'], voice, base_rate=rate)
        # Half a second of air before the first word, a beat between lines.
        lead = 0.55 if i == 0 else 0.30
        name = f'{i:02d}-{line["shot"]}.wav'
        V.write_wav(out_dir / name, audio)
        start = at + lead
        end = start + len(audio) / SR
        timing.append({
            'shot': line['shot'],
            'file': name,
            'start': round(start, 3),
            'end': round(end, 3),
            'vo': round(len(audio) / SR, 3),
            'text': line['text'],
            'words': len(line['text'].split()),
        })
        at = end + 0.35
    (out_dir / 'timing.json').write_text(json.dumps(timing, indent=2))
    return timing


# The picture leads the voice by this much. An edit that cuts and speaks on the
# same frame sounds like a slideshow with a commentary; letting the new shot land
# a beat before the line starts is what makes the voice sound *in* the film.
LEAD = 0.30
LEAD_FIRST = 0.55


def place_in_film(timing: list[dict], starts: list[dict]) -> list[dict]:
    """Put every line in its own shot, on the film's clock.

    This is the fix for the film being out of sync. The voice track used to be
    built by adding up its own gaps (0.30 lead + 0.35 between lines) while the
    picture added up `vo + PAD`, which is a different sum - the two clocks drifted
    a second apart by the end. There is one clock now: the film's, which is
    computed from these same voice lengths, and a line starts LEAD seconds after
    its own shot does.
    """
    # The film's file calls the field `id`; the voice's calls it `shot`.
    by_shot = {(row.get('shot') or row.get('id')): row for row in starts}
    out = []
    for i, row in enumerate(timing):
        shot = by_shot.get(row['shot'])
        if shot is None:
            raise SystemExit(f"no shot called {row['shot']!r} in the starts file")
        # The film publishes voStart. Fall back to this module's own constants only
        # for a starts file that predates it - two independent numbers is exactly
        # what made the film drift a second out of sync.
        start = shot.get('voStart', shot['start'] + (LEAD_FIRST if i == 0 else LEAD))
        end = start + row['vo']
        # A line may not run past its own shot: the cut would happen mid-word.
        if end > shot['end'] + 1e-6:
            raise SystemExit(
                f"{row['shot']}: the line ends at {end:.2f}s but the shot ends at "
                f"{shot['end']:.2f}s - increase that shot's PAD")
        out.append({**row, 'start': round(start, 3), 'end': round(end, 3)})
    return out


def mix(vo_dir: Path, score_path: Path, out_path: Path, duck: float = 0.42,
        starts_path: Path | None = None) -> Path:
    """Voice over the score, with the score ducking under the words."""
    timing = json.loads((vo_dir / 'timing.json').read_text())
    if starts_path is not None:
        timing = place_in_film(timing, json.loads(starts_path.read_text()))
    else:
        print('warning: no --starts given, so the voice is on its own clock')
    # As long as the film, always. The score is cut to the film's exact length, so
    # the voice track may not be shorter than it - `-shortest` at mux time would
    # then cut the last shot off to match the audio.
    with wave.open(str(score_path)) as f:
        score_seconds = f.getnframes() / f.getframerate()
    total = max(max(row['end'] for row in timing) + 1.2, score_seconds)
    master = np.zeros(int(total * SR), np.float32)

    for row in timing:
        line, rate = read_wav(vo_dir / row['file'])
        if rate != SR:
            line = V.resample(line, rate, SR)
        at = int(row['start'] * SR)
        master[at:at + len(line)] += line

    score, rate = read_wav(score_path)
    if rate != SR:
        score = V.resample(score, rate, SR)
    if len(score) < len(master):
        score = np.pad(score, (0, len(master) - len(score)))
    score = score[:len(master)]
    del score_seconds

    # Duck: a smooth envelope that dips where speech is and opens in the gaps.
    speech = np.zeros(len(master), np.float32)
    for row in timing:
        a, b = int(row['start'] * SR), int(row['end'] * SR)
        speech[a:b] = 1.0
    k = np.hanning(int(0.22 * SR))
    k /= k.sum()
    speech = np.convolve(speech, k, mode='same')
    gain = 1.0 - duck * np.clip(speech, 0, 1)
    master_out = master + score * gain * 0.62

    # Loudness first, peak second. Normalising to a peak left the film at -19 LUFS,
    # which is three decibels under every other video on the platform.
    master_out = V.normalise(master_out, target=-16.0, ceiling_db=-1.5)
    V.write_wav(out_path, master_out, stereo=True)
    print(f'wrote {out_path}: {V.lufs(master_out):.1f} LUFS, {len(master_out)/SR:.1f}s')
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)

    s = sub.add_parser('synth')
    s.add_argument('--lines', required=True)
    s.add_argument('--out', required=True)
    s.add_argument('--voice', default='bm_george')
    s.add_argument('--rate', type=float, default=0.95)
    s.add_argument('--engine', default='kokoro')
    s.add_argument('--profile', default='calm',
                   choices=['calm', 'dramatic'],
                   help="how the line is performed; 'dramatic' is the old trailer read")

    m = sub.add_parser('mix')
    m.add_argument('--vo', required=True)
    m.add_argument('--score', required=True)
    m.add_argument('--out', required=True)
    m.add_argument('--duck', type=float, default=0.42)
    m.add_argument('--starts', default=None,
                   help="the film's starts.json; the voice is placed shot by shot")

    args = ap.parse_args()
    if args.cmd == 'synth':
        if hasattr(V, 'set_profile'):
            V.set_profile(args.profile)
        rows = synth(json.loads(Path(args.lines).read_text()), Path(args.out),
                     voice=args.voice, rate=args.rate, engine=args.engine)
        for row in rows:
            print(f"  {row['shot']:<18} {row['vo']:5.2f}s  {row['text'][:52]}")
        print(f"spoken: {sum(r['vo'] for r in rows):.1f}s across {len(rows)} lines")
    else:
        mix(Path(args.vo), Path(args.score), Path(args.out), duck=args.duck,
            starts_path=Path(args.starts) if args.starts else None)


if __name__ == '__main__':
    main()
