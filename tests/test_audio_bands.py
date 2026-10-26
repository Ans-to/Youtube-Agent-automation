"""The gate the rejected film would have failed.

A film whose sound is called "irritating" passed every check we had, because none
of them listened. This one does: it renders the score and refuses broadband
brightness.
"""
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCORE = ROOT / 'video_studio' / 'score.py'


def _band_profile(path):
    with wave.open(str(path)) as f:
        n, sr = f.getnframes(), f.getframerate()
        data = np.frombuffer(f.readframes(n), dtype='<i2')
        data = data.reshape(-1, f.getnchannels()).astype(np.float32)
        data = data.mean(axis=1) / 32768
    win = int(0.25 * sr)
    centroids, share = [], []
    for i in range(0, len(data) - win, win):
        seg = data[i:i + win]
        if np.sqrt((seg ** 2).mean()) < 0.004:
            continue
        spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        freqs = np.fft.rfftfreq(len(seg), 1 / sr)
        centroids.append((spec * freqs).sum() / (spec.sum() + 1e-9))
        share.append(spec[freqs > 4000].sum() / (spec.sum() + 1e-9))
    return centroids, share


SECTIONS = ('calm:0:3,warm:3:6,moving:6:9,tense:9:12,'
            'sparse:12:15,history:15:18,build:18:21,resolve:21:24')


class AudioBandTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp()) / 'gate.wav'
        subprocess.run([sys.executable, str(SCORE), '--seconds', '24',
                        '--sections', SECTIONS, '--out', str(cls.out)],
                       check=True, capture_output=True)

    def test_no_window_is_dominated_by_hiss(self):
        """The old score hit 81 % above 4 kHz. Twelve percent is already bright."""
        _, share = _band_profile(self.out)
        self.assertLess(max(share), 0.15, f'worst window {max(share):.1%} above 4 kHz')

    def test_score_sits_in_the_low_mids(self):
        centroids, _ = _band_profile(self.out)
        self.assertLess(max(centroids), 3000, f'worst centroid {max(centroids):.0f} Hz')

    def test_unknown_section_is_rejected(self):
        """A misspelt section must fail loudly, not fall back to a default."""
        bad = Path(tempfile.mkdtemp()) / 'bad.wav'
        result = subprocess.run([sys.executable, str(SCORE), '--seconds', '4',
                                 '--sections', 'calm:0:2,nonsense:2:4', '--out', str(bad)],
                                capture_output=True)
        self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
