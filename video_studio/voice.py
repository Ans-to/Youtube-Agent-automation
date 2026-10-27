"""Narration as a performance, not a text dump.

The film was rejected for its voice, and the voice was a flat read: one rate,
one level, no breath, de-essed by nothing, delivered at whatever level the model
happened to produce. Every one of those is fixable without a bigger model, and
fixing them is most of the difference between "text to speech" and "voice over".

What this module does, in the order a studio does it:

1.  **Phrase.** A line is cut where a speaker would breathe - after a comma, a
    full stop, a dash - and each phrase is its own synthesis with its own rate.
    The last phrase of a sentence slows by a few percent, because that is how a
    sentence ends.
2.  **Space.** Real pauses, sized by punctuation: 140 ms at a comma, 420 ms at a
    full stop, 260 ms at a dash. Uneven gaps are what stop a read sounding like a
    list of sentences.
3.  **Shape.** High-pass, a dip in the boxy low mids, a de-ess, a small presence
    lift and a rolled-off top.
4.  **Level.** Compression at 2.5:1, then a short room, then -16 LUFS integrated
    with a -1.5 dBTP ceiling. YouTube normalises to -14; sitting at -16 means it
    is never squashed on playback.

Engines are a registry, not an assumption. `kokoro` runs here and now; `edge`,
`piper` and `chatterbox` are declared with the exact reason each one is
unavailable in this sandbox, so a missing engine fails loudly instead of quietly
falling back to whatever is left.
"""
from __future__ import annotations

import math
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SR = 48000
CACHE = Path('/home/user/.cache/agent-hq/kokoro')
MODEL = CACHE / 'kokoro-82m-q8.onnx'
VOICES = CACHE / 'voices.npz'

# Voices worth auditioning for a documentary read. Kokoro ships 54; these are the
# ones with enough weight for narration, chosen by listening to all 28 English
# ones rather than by picking the default.
NARRATOR_VOICES = {
    'am_fenrir': 'American male, low and deliberate',
    'bm_george': 'British male, warm and authoritative',
    'bm_fable': 'British male, lighter, storytelling',
    'am_onyx': 'American male, deep and dry',
    'am_echo': 'American male, neutral broadcast',
    'af_heart': 'American female, the model\'s most expressive',
    'bf_emma': 'British female, measured',
}


# --------------------------------------------------------------------------
# Filters. Zero-phase, in the frequency domain.
#
# A biquad is the usual tool and it was the first thing written here; two of the
# five coefficients were normalised by a0 and three were not, which made the chain
# unstable and filled the buffer with NaN. Offline audio has no latency to worry
# about, so every filter below is an FFT magnitude mask: exact, stable, and
# impossible to get wrong by one coefficient.
# --------------------------------------------------------------------------

def _spectrum(x: np.ndarray):
    n = len(x)
    return np.fft.rfft(x), np.fft.rfftfreq(n, 1 / SR), n


def _apply(x: np.ndarray, gain_of_freq, block: int = 1 << 21) -> np.ndarray:
    """Filter by masking the spectrum, in overlapping blocks.

    A single transform is fine on one line of narration and is not fine on a
    twenty-eight-minute film: 41 million complex points, two of them, plus the
    signal. The process was killed with no message, which is why this is a block
    loop now. Each block carries half a second of context on both sides and the
    blocks crossfade over an eighth of a second.
    """
    n = len(x)
    if n <= block:
        spec, freqs, n2 = _spectrum(x)
        return np.fft.irfft(spec * gain_of_freq(freqs), n2).astype(np.float32)
    out = np.zeros(n)
    weight = np.zeros(n)
    pad = SR // 2
    fade = SR // 8
    for start in range(0, n, block):
        end = min(n, start + block)
        a, b = max(0, start - pad), min(n, end + pad)
        spec, freqs, m = _spectrum(x[a:b])
        shaped = np.fft.irfft(spec * gain_of_freq(freqs), m)
        w = np.ones(end - start)
        k = min(fade, (end - start) // 2)
        if start > 0 and k:
            w[:k] = np.linspace(0, 1, k)
        if end < n and k:
            w[-k:] = np.linspace(1, 0, k)
        out[start:end] += shaped[start - a:start - a + (end - start)] * w
        weight[start:end] += w
    return (out / np.maximum(weight, 1e-9)).astype(np.float32)


def highpass(x: np.ndarray, hz: float) -> np.ndarray:
    # Third order, not second: a 30 Hz rumble (a desk, a plosive, a room) sat 19 dB
    # down at second order, which is audible under a close microphone. A mask
    # costs the same at any order, so there is no reason to be gentle.
    def g(f):
        r = np.clip(f / max(hz, 1.0), 0, 1)
        return r ** 3
    return _apply(x, g)


def lowpass(x: np.ndarray, hz: float) -> np.ndarray:
    def g(f):
        return np.clip(1 - ((f - hz) / max(hz, 1.0)) ** 2, 0, 1)
    return _apply(x, g)


def peaking(x: np.ndarray, hz: float, q: float, gain_db: float) -> np.ndarray:
    """A bell, expressed in octaves so it is the same shape at any centre."""
    def g(f):
        width = hz / max(q, 0.1)
        bell = np.exp(-0.5 * ((f - hz) / max(width, 1.0)) ** 2)
        return 10 ** ((bell * gain_db) / 20)
    return _apply(x, g)


def low_shelf(x: np.ndarray, hz: float, gain_db: float) -> np.ndarray:
    def g(f):
        t = np.clip((f - hz) / max(hz, 1.0), 0, 1)
        return 10 ** ((gain_db * (1 - t)) / 20)
    return _apply(x, g)


def high_shelf(x: np.ndarray, hz: float, gain_db: float) -> np.ndarray:
    def g(f):
        t = np.clip((f - hz) / max(hz * 0.5, 1.0), 0, 1)
        return 10 ** ((gain_db * t) / 20)
    return _apply(x, g)


# --------------------------------------------------------------------------
# Performance
# --------------------------------------------------------------------------

PAUSE = {'comma': 0.14, 'stop': 0.42, 'dash': 0.26, 'colon': 0.22}

# A performance is a choice, not a constant.
#
# The first narration was rejected as *too dramatic*, and the drama was not in the
# voice alone - it was in the direction: every sentence dipped six percent on its
# last phrase, every full stop held for nearly half a second, and a 2.5:1
# compressor with 4 dB of makeup pushed each clause forward. That is a trailer
# read. A documentary narrator explains: the read stays at the pitch the sentence
# put it at, the pauses are grammatical rather than theatrical, and the compressor
# is there so a word does not disappear, not to add weight.
PERFORMANCE = {
    'dramatic': {
        'pause': 1.00, 'first': 0.97, 'mid': 1.02, 'last': 0.94,
        'compress': {'ratio': 2.5, 'threshold_db': -20.0, 'makeup_db': 4.0},
    },
    'calm': {
        'pause': 0.68, 'first': 1.00, 'mid': 1.005, 'last': 0.995,
        'compress': {'ratio': 1.8, 'threshold_db': -18.0, 'makeup_db': 1.6},
    },
}
PROFILE = 'calm'


def set_profile(name: str) -> None:
    global PROFILE
    if name not in PERFORMANCE:
        raise SystemExit(f'no performance called {name!r}; have {sorted(PERFORMANCE)}')
    PROFILE = name


def phrases(line: str) -> list[tuple[str, str]]:
    """Cut a line where a speaker breathes, and remember why they stopped."""
    out: list[tuple[str, str]] = []
    buf = ''
    for ch in line:
        buf += ch
        if ch == ',':
            out.append((buf.rstrip(', '), 'comma'))
            buf = ''
        elif ch in '.;:':
            out.append((buf.rstrip('.;: '), 'stop' if ch != ':' else 'colon'))
            buf = ''
        elif ch == '—':
            out.append((buf.rstrip('— '), 'dash'))
            buf = ''
    if buf.strip():
        out.append((buf.strip(), 'none'))
    # A line does not end on a pause. The gap between lines belongs to the edit,
    # not to the file: leaving a full stop's 420 ms on the end of every wav added
    # nearly a second of dead air between sentences.
    if out and out[-1][1] != 'none':
        out[-1] = (out[-1][0], 'none')
    return out


def shape_rate(index: int, count: int) -> float:
    """How fast to say phrase `index` of `count`, under the current profile.

    Under `dramatic` the last phrase of a sentence lands six percent slower - a
    deceleration at every full stop. Under `calm` the line keeps its own pace and
    the punctuation does the work, which is what reading to picture sounds like.
    """
    perf = PERFORMANCE[PROFILE]
    if count == 1:
        return 1.0
    if index == count - 1:
        return perf['last']
    if index == 0:
        return perf['first']
    return perf['mid']


def compress(x: np.ndarray, ratio=2.5, threshold_db=-20.0, attack=0.008,
             release=0.15, makeup_db=4.0) -> np.ndarray:
    env = np.abs(x)
    kernel = np.ones(240) / 240          # 5 ms
    env = np.convolve(env, kernel, mode='same')
    db = 20 * np.log10(env + 1e-7)
    gain = -np.maximum(0.0, db - threshold_db) * (1 - 1 / ratio)
    a = math.exp(-1 / (attack * SR))
    r = math.exp(-1 / (release * SR))
    out = np.empty_like(gain)
    g = 0.0
    for i, target in enumerate(gain):
        coeff = a if target < g else r
        g = coeff * g + (1 - coeff) * target
        out[i] = g
    return x * (10 ** ((out + makeup_db) / 20))


def deess(x: np.ndarray, hz: float = 4300, threshold_db: float | None = None,
          ratio: float = 4.0) -> np.ndarray:
    """Duck the sibilance band when it peaks, instead of cutting it always.

    A static cut at 5.5 kHz makes every "s" dull and still leaves the loud ones
    loud. A de-esser follows the level of the band above 4.3 kHz and pulls it down
    only while it is over the threshold, which is what a studio chain does. Measured
    on this voice it took the worst quarter-second from 64 % of its energy above
    4 kHz down without touching the vowels.

    The threshold is derived from the band's own level. A fixed -30 dBFS sat below
    the band's average, so the de-esser clamped it permanently - which is a static
    cut with extra steps, and it dulled the whole read instead of the one "s".
    """
    low = lowpass(x, hz)
    high = x - low                      # complementary split; the sum is exact
    env = np.abs(high)
    k = np.ones(int(0.004 * SR)) / int(0.004 * SR)
    env = np.convolve(env, k, mode='same')
    db = 20 * np.log10(env + 1e-7)
    if threshold_db is None:
        # Sit the knee a few dB above the band's typical level: only the peaks
        # are over it, which is the definition of a sibilant.
        threshold_db = float(np.percentile(db[db > -70], 72)) + 3.0
    over = np.maximum(0.0, db - threshold_db)
    gain_db = -np.minimum(over * (1 - 1 / ratio), 9.0)
    # 1 ms attack, 60 ms release: fast enough for a "t", slow enough not to lisp.
    out = np.empty_like(gain_db)
    a, r = math.exp(-1 / (0.001 * SR)), math.exp(-1 / (0.06 * SR))
    g = 0.0
    for i, target in enumerate(gain_db):
        coeff = a if target < g else r
        g = coeff * g + (1 - coeff) * target
        out[i] = g
    return low + high * (10 ** (out / 20))


def room(x: np.ndarray, wet=0.09, decay=0.42) -> np.ndarray:
    """A small, bright room. A narrator is close to a microphone, not in a hall."""
    n = int(decay * SR)
    rng = np.random.default_rng(11)
    ir = rng.normal(0, 1, n) * np.exp(-np.arange(n) / (SR * decay * 0.3))
    ir = lowpass(ir, 5200)
    ir[0] = 1.0
    ir /= np.sqrt(np.sum(ir ** 2)) + 1e-9
    size = 1 << int(math.ceil(math.log2(len(x) + n)))
    wet_sig = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[:len(x)]
    return (1 - wet) * x + wet * wet_sig


def master(x: np.ndarray) -> np.ndarray:
    x = highpass(x, 88.0)
    x = peaking(x, 320, 0.9, -2.5)        # boxiness out of the low mids
    x = compress(x, **PERFORMANCE[PROFILE]['compress'])
    x = deess(x)                          # dynamic, not a static cut
    x = peaking(x, 7200, 1.4, -1.5)
    x = peaking(x, 2600, 1.0, 1.2)        # presence, where intelligibility lives
    x = peaking(x, 1800, 1.2, -1.0)       # and a little nasal out
    x = high_shelf(x, 9500, -2.0)         # a synthetic voice's top is its tell
    x = low_shelf(x, 160, 1.2)            # weight in the chest
    x = room(x)
    peak = float(np.max(np.abs(x))) or 1.0
    return x / peak * 0.94


# --------------------------------------------------------------------------
# Loudness, to BS.1770 rather than to a guess
# --------------------------------------------------------------------------

def lufs(x: np.ndarray, channels: int = 1) -> float:
    """Integrated loudness: K-weight, mean square, -0.691 dB offset."""
    y = high_shelf(x, 1500, 4.0)   # BS.1770 K-weighting, shelf half
    y = highpass(y, 38.0)          # ...and the rumble half
    block = int(0.4 * SR)
    step = int(0.1 * SR)
    powers = []
    for start in range(0, max(1, len(y) - block), step):
        seg = y[start:start + block]
        if len(seg) < block:
            break
        ms = float(np.mean(seg ** 2))
        if ms > 0:
            powers.append(ms)
    if not powers:
        return -70.0
    powers = np.array(powers)
    loud = -0.691 + 10 * np.log10(powers + 1e-12)
    # Absolute gate at -70 LUFS, then relative at -10 below the mean.
    keep = powers[loud > -70]
    if len(keep) == 0:
        return -70.0
    rel = -0.691 + 10 * np.log10(np.mean(keep)) - 10
    keep = powers[(-0.691 + 10 * np.log10(powers + 1e-12)) > rel]
    if len(keep) == 0:
        return -70.0
    return float(-0.691 + 10 * np.log10(np.mean(keep)))


def normalise(x: np.ndarray, target=-16.0, ceiling_db=-1.5) -> np.ndarray:
    gain = target - lufs(x)
    # In place: a copy of a twenty-eight-minute master is 330 MB that the
    # machine does not have while it is also filtering the signal for LUFS.
    x *= 10 ** (gain / 20)
    ceiling = 10 ** (ceiling_db / 20)
    peak = float(np.max(np.abs(x)))
    if peak > ceiling:
        # Soft knee rather than a hard clamp: a clamp on a voice sounds like a
        # fault. The knee's own slope at zero is 1/tanh(0.9) - about +3 dB - so
        # applying it blindly made the mix louder than the target it had just been
        # set to. Normalise again afterwards, then hard-clamp the last millivolt.
        x = np.tanh(x / ceiling * 0.9) * ceiling / math.tanh(0.9)
        x *= 10 ** ((target - lufs(x)) / 20)
        np.clip(x, -ceiling, ceiling, out=x)
    return x


# --------------------------------------------------------------------------
# Engines
# --------------------------------------------------------------------------

@dataclass
class Engine:
    name: str
    available: bool
    reason: str = ''


ENGINES = [
    Engine('kokoro', MODEL.exists() and VOICES.exists(),
           '' if MODEL.exists() else 'weights missing; run video_studio/kokoro_voice.py'),
    Engine('edge', False, 'needs speech.platform.bing.com, which is blocked here'),
    Engine('chatterbox', False, 'weights live on huggingface.co, which is blocked here'),
    Engine('piper', False, 'voice models live on huggingface.co, which is blocked here'),
]


def require_engine(name: str = 'kokoro') -> Engine:
    for engine in ENGINES:
        if engine.name == name:
            if not engine.available:
                raise SystemExit(f'engine {name!r} is unavailable: {engine.reason}')
            return engine
    raise SystemExit(f'no engine called {name!r}; known: {[e.name for e in ENGINES]}')


_kokoro = None


def _session():
    global _kokoro
    if _kokoro is None:
        from kokoro_onnx import Kokoro
        _kokoro = Kokoro(str(MODEL), str(VOICES))
    return _kokoro


def synth(text: str, voice: str, base_rate: float = 1.0) -> np.ndarray:
    """One line, phrased and paced, ready to be mastered."""
    k = _session()
    parts: list[np.ndarray] = []
    cuts = phrases(text)
    for i, (chunk, stop) in enumerate(cuts):
        audio, rate = k.create(chunk, voice=voice, speed=base_rate * shape_rate(i, len(cuts)), lang='en-us')
        audio = np.asarray(audio, dtype=np.float32)
        audio = resample(audio, rate, SR)
        # Trim the model's own leading and trailing silence so our pauses are the
        # only pauses - otherwise every gap is a comma plus a model artefact.
        audio = trim(audio)
        # A butt join between two chunks is a step discontinuity, and a step is a
        # click - broadband, in a place where nothing musical is happening. Six
        # milliseconds of fade at each end removes it without shortening the word.
        n = max(1, int(0.006 * SR))
        audio = audio.copy()
        audio[:n] *= np.linspace(0, 1, n)
        audio[-n:] *= np.linspace(1, 0, n)
        parts.append(audio)
        if stop != 'none':
            gap = PAUSE[stop] * PERFORMANCE[PROFILE]['pause']
            parts.append(np.zeros(int(gap * SR), dtype=np.float32))
    out = np.concatenate(parts) if parts else np.zeros(1, dtype=np.float32)
    return master(out)


def resample(x: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst:
        return x
    n = int(round(len(x) * dst / src))
    xp = np.linspace(0, len(x) - 1, n)
    return np.interp(xp, np.arange(len(x)), x).astype(np.float32)


def trim(x: np.ndarray, floor=0.012) -> np.ndarray:
    if len(x) == 0:
        return x
    loud = np.abs(x) > floor * max(1e-6, float(np.max(np.abs(x))))
    if not loud.any():
        return x
    first, last = np.argmax(loud), len(loud) - np.argmax(loud[::-1])
    pad = int(0.02 * SR)
    return x[max(0, first - pad):min(len(x), last + pad)]


def write_wav(path: Path, x: np.ndarray, stereo: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.stack([x, np.roll(x, int(0.011 * SR))], axis=1) if stereo else x[:, None]
    pcm = (np.clip(data, -1, 1) * 32767).astype('<i2')
    with wave.open(str(path), 'wb') as f:
        f.setnchannels(data.shape[1])
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(pcm.tobytes())


if __name__ == '__main__':
    for engine in ENGINES:
        state = 'ready' if engine.available else 'unavailable'
        print(f'{engine.name:<12} {state:<12} {engine.reason}')
    print(f'\nvoices: {", ".join(NARRATOR_VOICES)}')
