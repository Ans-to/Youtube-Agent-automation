"""Tests for the thirty-second render test: its plan, its frames, its sound.

The film's timeline lives in one JavaScript file and is read here through
``--cues`` rather than copied. A copy would be the second source of truth that
the plan exists to remove, and the two would drift the first time a beat moved.

Three of these tests are regression tests for faults that shipped in this session
and that nothing else caught:

* the frames, which were blank for every still after the first because a panel
  opened a canvas save and never closed it;
* the keystrokes, which sat inside the music bed and could not be heard;
* the transitions, which repeated the same device on adjacent shots.
"""
import array
import json
import math
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "video_studio"
FILM = STUDIO / "films" / "render_test.mjs"
sys.path.insert(0, str(STUDIO))

import audio_design  # noqa: E402 - path set up above

NODE = shutil.which("node")
TYPED = "fix the login page"


def read_plan() -> dict:
    completed = subprocess.run([NODE, str(FILM), "--cues"], cwd=ROOT,
                               capture_output=True, text=True, timeout=120)
    if completed.returncode != 0:
        raise AssertionError("the film could not describe itself: " + completed.stderr[-1500:])
    return json.loads(completed.stdout)


@unittest.skipUnless(NODE, "node is not installed; the film cannot be read")
class PlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = read_plan()

    def test_shots_cover_the_film_exactly_once(self):
        shots = self.plan["shots"]
        self.assertGreaterEqual(len(shots), 6)
        self.assertEqual(shots[0]["start"], 0.0)
        self.assertAlmostEqual(shots[-1]["end"], self.plan["duration"], places=6)
        for before, after in zip(shots, shots[1:]):
            self.assertAlmostEqual(before["end"], after["start"], places=6,
                                   msg="%s and %s leave a gap" % (before["id"], after["id"]))

    def test_no_two_neighbouring_shots_use_the_same_device(self):
        # "don't always use the same transition" is a standing note. A cut is the
        # absence of a device, so two cuts in a row are allowed; two wipes are not.
        shots = self.plan["shots"]
        for before, after in zip(shots, shots[1:]):
            if before["arrive"] == after["arrive"] and before["arrive"] != "cut":
                self.fail("%s and %s both arrive with %r"
                          % (before["id"], after["id"], before["arrive"]))

    def test_every_shot_has_its_own_device_or_justifies_a_cut(self):
        devices = {shot["arrive"] for shot in self.plan["shots"]}
        self.assertGreaterEqual(len(devices), 4, msg="the film uses %r" % devices)
        self.assertTrue(devices <= {"cut", "wipe", "iris", "push", "focus", "flash"})

    def test_cues_are_inside_the_film_and_within_their_limits(self):
        duration = self.plan["duration"]
        for cue in self.plan["cues"]:
            self.assertGreaterEqual(cue["at"], 0.0)
            self.assertLess(cue["at"], duration)
            self.assertGreaterEqual(cue["length"], 0.02)
            self.assertLessEqual(cue["length"], 2.0)
            self.assertGreaterEqual(cue["gain"], 0.0)
            self.assertLessEqual(cue["gain"], 1.0)

    def test_cues_are_ordered_and_every_kind_is_synthesisable(self):
        cues = self.plan["cues"]
        ats = [cue["at"] for cue in cues]
        self.assertEqual(ats, sorted(ats), "the sheet is not in time order")
        for cue in cues:
            self.assertIn(cue["kind"], audio_design.SFX_KINDS,
                          msg="%r has no synthesiser" % cue["kind"])

    def test_one_keystroke_per_typed_character(self):
        strokes = [cue for cue in self.plan["cues"] if cue["kind"] == "key" and cue["gain"] > 0.4]
        self.assertEqual(len(strokes), len(TYPED))
        # Typing is a rhythm, not a machine: the gaps are uneven but never wild.
        gaps = [b["at"] - a["at"] for a, b in zip(strokes, strokes[1:])]
        self.assertGreater(min(gaps), 0.08)
        self.assertLess(max(gaps), 0.20)
        self.assertGreater(len({round(gap, 3) for gap in gaps}), 3,
                           "evenly spaced keystrokes read as a metronome")

    def test_no_sound_arrives_after_the_picture_stops(self):
        tips = [cue["at"] + cue["length"] for cue in self.plan["cues"]]
        self.assertLessEqual(max(tips), self.plan["duration"])

    def test_the_film_is_light_only(self):
        completed = subprocess.run([NODE, str(FILM), "--cues", "--look", "dark"], cwd=ROOT,
                                   capture_output=True, text=True, timeout=120)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("light only", completed.stderr)


@unittest.skipUnless(NODE, "node is not installed; the film cannot be rendered")
class FrameTests(unittest.TestCase):
    def test_several_stills_in_one_process_are_all_drawn(self):
        """The bug this keeps dead: the second still in a process came out black.

        The prompt panel opened a save and never closed it, and its alpha was
        multiplied by an arrival that is zero for the first second, so the context
        came back with globalAlpha at zero and every frame after it was empty.
        Rendering one still per process hid it completely - the first render is
        always fine - so this test renders several in a row and checks every one.
        """
        with tempfile.TemporaryDirectory() as tmp:
            seconds = [0.6, 2.6, 6.9, 13.0]
            completed = subprocess.run(
                [NODE, str(FILM), "--out", tmp, "--width", "320", "--quiet",
                 "--still", ",".join(str(s) for s in seconds)],
                cwd=ROOT, capture_output=True, text=True, timeout=300,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr[-1500:])
            for seconds_at in seconds:
                path = Path(tmp) / ("still-%.2f.jpg" % seconds_at)
                self.assertTrue(path.is_file(), msg=str(path))
                data = path.read_bytes()
                self.assertGreater(len(data), 4000,
                                   "still at %.1fs is %.0f bytes - an empty frame"
                                   % (seconds_at, len(data)))

    def test_a_leak_is_reported_rather_than_drawn(self):
        """The guard, not just the fix: a context that comes back changed throws."""
        source = FILM.read_text(encoding="utf-8")
        self.assertIn("globalAlpha leaked", source)
        self.assertIn("guard(ctx", source)


class SoundTests(unittest.TestCase):
    def _render(self, cues, duration=1.0, sample_rate=24000, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cue.wav"
            audio_design.render_motion_sfx(path, duration, cues, sample_rate=sample_rate)
            with wave.open(str(path)) as wav:
                samples = array.array("h")
                samples.frombytes(wav.readframes(wav.getnframes()))
            return samples

    def test_key_is_a_short_bright_transient(self):
        """A keystroke is a click with a body, not a beep.

        It has to be over quickly - a stroke that rings for a tenth of a second
        reads as a synth blip - and it has to be brightest at the start, which is
        what makes it read as a plastic key rather than a tone.
        """
        rate = 24000
        samples = self._render([{"at": 0.1, "kind": "key", "gain": 0.6, "length": 0.05}], sample_rate=rate)
        start = int(0.1 * rate)
        stroke = samples[start:start + int(0.05 * rate)]
        peak = max(abs(value) for value in stroke)
        self.assertGreater(peak, 0)

        def crossings(segment):
            return sum(1 for i in range(1, len(segment)) if (segment[i - 1] < 0) != (segment[i] < 0))

        head = stroke[:int(0.010 * rate)]
        tail = stroke[-int(0.010 * rate):]
        self.assertGreater(crossings(head), crossings(tail) * 2,
                           "the stroke does not decay from bright to dull")

    def test_keystrokes_are_not_a_machine_gun(self):
        """Twelve strokes in a row must not be twelve copies of one sample."""
        rate = 24000
        cues = [{"at": 0.05 + i * 0.1, "kind": "key", "gain": 0.5, "length": 0.05} for i in range(12)]
        samples = self._render(cues, duration=1.4, sample_rate=rate)
        windows = []
        for i in range(12):
            start = int((0.05 + i * 0.1) * rate)
            windows.append(samples[start:start + int(0.03 * rate)])
        peaks = {max(abs(value) for value in window) for window in windows}
        self.assertGreater(len(peaks), 1, "every stroke has the same peak")
        first, second = windows[0], windows[1]
        numerator = sum(a * b for a, b in zip(first, second))
        energy = math.sqrt(sum(a * a for a in first) * sum(b * b for b in second))
        self.assertLess(numerator / energy, 0.95, "two strokes are the same sound")

    def test_bed_gain_scales_the_bed_and_only_the_bed(self):
        with tempfile.TemporaryDirectory() as tmp:
            levels = {}
            for gain in (1.0, 0.4):
                path = Path(tmp) / ("bed-%.1f.wav" % gain)
                audio_design.render_sound_design(path, 2.0, [2.0], bed_gain=gain)
                with wave.open(str(path)) as wav:
                    samples = array.array("h")
                    samples.frombytes(wav.readframes(wav.getnframes()))
                levels[gain] = math.sqrt(sum(v * v for v in samples) / len(samples))
            self.assertLess(levels[0.4], levels[1.0] * 0.75,
                            "bed gain barely moved the bed")

    def test_bed_gain_is_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            for bad in (-0.1, 1.6, "loud"):
                with self.assertRaisesRegex(ValueError, "bed gain"):
                    audio_design.render_sound_design(Path(tmp) / "x.wav", 1.0, [1.0], bed_gain=bad)

    def test_key_stays_above_the_bed(self):
        """The fault this keeps dead: typing you cannot hear.

        Measured on the delivered mix, the strokes sat 1.6 dB above the kick on
        average with the bed at unity. A typing shot with no typing in it is not a
        mixing preference, it is a bug, so it is checked rather than listened for.
        """
        rate = 24000
        bed = Path(tempfile.mkdtemp()) / "mix.wav"
        plan = json.loads(subprocess.run([NODE, str(FILM), "--cues"], cwd=ROOT,
                                         capture_output=True, text=True, timeout=120).stdout)
        audio_design.render_sound_design(bed, 6.0, [6.0], sample_rate=rate,
                                         sfx_cues=plan["cues"], bed_gain=0.85)
        with wave.open(str(bed)) as wav:
            samples = array.array("h")
            samples.frombytes(wav.readframes(wav.getnframes()))

        def rms(at, window=0.03):
            start = int(at * rate)
            segment = samples[start:start + int(window * rate)]
            return math.sqrt(sum(v * v for v in segment) / max(1, len(segment))) if segment else 0.0

        strokes = [cue["at"] for cue in plan["cues"] if cue["kind"] == "key" and cue["gain"] > 0.4]
        self.assertTrue(strokes)
        floor = sorted(rms(t / 1000.0) for t in range(4200, 5200, 20))[len(range(4200, 5200, 20)) // 2]
        lifts = [20 * math.log10(max(rms(at), 1e-9) / max(floor, 1e-9)) for at in strokes]
        lifts.sort()
        self.assertGreater(lifts[len(lifts) // 2], 8.0,
                           "median keystroke is only %.1f dB above the bed" % lifts[len(lifts) // 2])


if __name__ == "__main__":
    unittest.main()
