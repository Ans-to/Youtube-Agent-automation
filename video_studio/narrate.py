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


def write_mix_wav(path: Path, samples: np.ndarray, *, stereo: bool = False) -> None:
    """Write bounded-memory PCM16; stereo is dual mono with no wrapped tail.

    Exported mono buses can then reconstruct both channels of this master. The
    older voice writer's circular delay would wrap the final samples to the start
    and make the right channel differ from those buses.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as handle:
        handle.setnchannels(2 if stereo else 1)
        handle.setsampwidth(2)
        handle.setframerate(SR)
        for start in range(0, len(samples), 1 << 20):
            part = samples[start:start + (1 << 20)]
            pcm = (np.clip(part, -1, 1) * 32767).astype('<i2')
            if stereo:
                pcm = np.repeat(pcm, 2)
            handle.writeframes(pcm.tobytes())


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


def smooth_same(signal: np.ndarray, kernel: np.ndarray, *, block_size: int = 1 << 18) -> np.ndarray:
    """Convolve a long ducking envelope in bounded FFT blocks.

    This matches ``np.convolve(signal, kernel, mode='same')`` to float32
    precision, including the alignment for even-length kernels. Direct
    convolution of a 15-minute 48 kHz track with a 220 ms window performs
    hundreds of billions of multiply-adds. Overlap-add keeps it practical
    without moving the narration or changing the ducking curve audibly.
    """
    if signal.ndim != 1 or kernel.ndim != 1 or not len(signal) or not len(kernel):
        raise ValueError('smoothing requires non-empty one-dimensional arrays')
    if block_size <= 0:
        raise ValueError('smoothing block size must be positive')
    if len(signal) <= len(kernel):
        return np.convolve(signal, kernel, mode='same').astype(np.float32)
    fft_size = 1 << (block_size + len(kernel) - 2).bit_length()
    kernel_fft = np.fft.rfft(kernel, fft_size)
    full = np.zeros(len(signal) + len(kernel) - 1, dtype=np.float32)
    for start in range(0, len(signal), block_size):
        part = signal[start:start + block_size]
        valid = len(part) + len(kernel) - 1
        filtered = np.fft.irfft(np.fft.rfft(part, fft_size) * kernel_fft, fft_size)
        full[start:start + valid] += filtered[:valid].astype(np.float32)
    offset = (len(kernel) - 1) // 2
    return full[offset:offset + len(signal)]


def mix(vo_dir: Path, score_path: Path, out_path: Path, duck: float = 0.42,
        starts_path: Path | None = None, *, target_lufs: float = -16.0,
        ceiling_dbfs: float = -1.5, score_gain: float = 0.62,
        timing_out: Path | None = None, stems_dir: Path | None = None) -> Path:
    """Mix against the film clock; optionally preserve separately measurable buses.

    The legacy path retains its existing normaliser. When stems are requested,
    the master is limited by *linear gain* rather than a nonlinear limiter so the
    two exported mono stems sum to the master. Headroom can prevent the requested
    loudness; measure the encoded video's LUFS and true peak independently.
    """
    if not math.isfinite(duck) or not 0 <= duck <= 1:
        raise ValueError('duck must be between 0 and 1')
    if not math.isfinite(score_gain) or score_gain < 0:
        raise ValueError('score gain must be finite and non-negative')
    if not math.isfinite(target_lufs) or not math.isfinite(ceiling_dbfs) or ceiling_dbfs > 0:
        raise ValueError('loudness and non-positive sample-peak ceiling must be finite')
    timing = json.loads((vo_dir / 'timing.json').read_text())
    if not isinstance(timing, list) or not timing:
        raise ValueError('the narration timing file is empty')
    starts = None
    if starts_path is not None:
        starts = json.loads(starts_path.read_text())
        timing = place_in_film(timing, starts)
    else:
        print('warning: no --starts given, so the voice is on its own clock')
    with wave.open(str(score_path)) as f:
        score_seconds = f.getnframes() / f.getframerate()
    if starts is not None:
        # Never extend the audio beyond the picture or silently trim a narration.
        # The score and shot clock have to refer to the same edit.
        total = float(starts[-1]['end'])
        if abs(score_seconds - total) > 0.05:
            raise ValueError('score duration does not match the film shot clock')
        if max(row['end'] for row in timing) > total:
            raise ValueError('narration extends beyond the film')
    else:
        total = max(max(row['end'] for row in timing) + 1.2, score_seconds)
    master = np.zeros(int(round(total * SR)), np.float32)

    for row in timing:
        line, rate = read_wav(vo_dir / row['file'])
        if rate != SR:
            line = V.resample(line, rate, SR)
        if abs(len(line) / SR - (row['end'] - row['start'])) > 0.025:
            raise ValueError(f"{row['shot']}: voice WAV duration does not match its timing metadata")
        at = int(row['start'] * SR)
        if at < 0 or at + len(line) > len(master):
            raise ValueError(f"{row['shot']}: voice WAV extends beyond the film")
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
    speech = smooth_same(speech, k)
    gain = 1.0 - duck * np.clip(speech, 0, 1).astype(np.float32)
    del speech
    score *= gain
    del gain
    score *= score_gain

    if stems_dir is not None:
        # A linear master gain is shared by both buses. This preserves the actual
        # relationship between them; a nonlinear limiter after the sum cannot be
        # honestly attributed to separate instruments. The stereo writer duplicates
        # the mono mix, so its BS.1770 loudness is roughly 3 dB higher than mono.
        # Reuse the master buffer to keep memory bounded on long-form cuts.
        master += score
        peak = float(np.max(np.abs(master))) if master.size else 0.0
        if peak <= 1e-10:
            raise ValueError('cannot master a silent mix')
        stereo_lufs = V.lufs(master) + 10 * math.log10(2)
        linear_gain = min(10 ** ((target_lufs - stereo_lufs) / 20),
                          10 ** (ceiling_dbfs / 20) / peak)
        master *= linear_gain
        score *= linear_gain
        stems_dir.mkdir(parents=True, exist_ok=True)
        master -= score  # recover the post-gain voice without another full buffer
        write_mix_wav(stems_dir / 'voice-stem.wav', master)
        write_mix_wav(stems_dir / 'music-stem.wav', score)
        master += score
        del score
        master_out = master
    else:
        master += score
        del score
        master_out = V.normalise(master, target=target_lufs, ceiling_db=ceiling_dbfs)

    if stems_dir is not None:
        write_mix_wav(out_path, master_out, stereo=True)
    else:
        V.write_wav(out_path, master_out, stereo=True)
    if timing_out is not None:
        timing_out.parent.mkdir(parents=True, exist_ok=True)
        timing_out.write_text(json.dumps(timing, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'wrote {out_path}: approximate mono {V.lufs(master_out):.1f} LUFS, {len(master_out)/SR:.1f}s; meter the encoded master')
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
    m.add_argument('--duck', type=float, default=0.42,
                   help='fractional reduction of the music during a spoken line, 0 to 1')
    m.add_argument('--starts', default=None,
                   help="the film's starts.json; the voice is placed shot by shot")
    m.add_argument('--target-lufs', type=float, default=-16.0,
                   help='mix target; the encoded master must still be independently metered')
    m.add_argument('--ceiling-dbfs', type=float, default=-1.5,
                   help='sample peak headroom, NOT a true-peak guarantee')
    m.add_argument('--score-gain', type=float, default=0.62)
    m.add_argument('--timing-out', help='write the actual placed narration timing JSON')
    m.add_argument('--stems-dir', help='write aligned voice-stem.wav and music-stem.wav using a linear master gain')

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
            starts_path=Path(args.starts) if args.starts else None,
            target_lufs=args.target_lufs, ceiling_dbfs=args.ceiling_dbfs,
            score_gain=args.score_gain,
            timing_out=Path(args.timing_out) if args.timing_out else None,
            stems_dir=Path(args.stems_dir) if args.stems_dir else None)


if __name__ == '__main__':
    main()
