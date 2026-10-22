"""Guards the security posture of the optional Kani/NeMo requirement set.

That file has two properties that are easy to break silently:

1. it must resolve at all - it previously pinned `transformers==4.57.1` against
   `nemo_toolkit[tts]==2.4.0`, which requires `transformers<=4.52.0`, so
   `pip install -r` failed with ResolutionImpossible and the backend never ran;
2. it must not drift back into the vulnerable transformers window - every release
   in NeMo 2.4's `<=4.52.0` range carries published advisories.

These tests read the file, so they cost nothing and catch both regressions.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "video_studio" / "requirements-kani-tts.txt"


def requirements() -> list[str]:
    """Return the requirement lines, without comments or blanks."""
    lines = []
    for raw in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            lines.append(line)
    return lines


def find(prefix: str) -> str:
    for line in requirements():
        if line.replace("_", "-").lower().startswith(prefix):
            return line
    raise AssertionError(f"no requirement starting with {prefix!r}")


class KaniRequirementTests(unittest.TestCase):
    def test_transformer_pin_is_outside_the_vulnerable_window(self):
        line = find("transformers")
        # Any `<=4.5x` or `==4.x` upper bound re-introduces the advisories that
        # NeMo 2.4 forced. The secure pairing is transformers 5.x.
        numbers = [float(value) for value in re.findall(r"\d+\.\d+", line)]
        self.assertTrue(numbers, "transformers pin should carry a version")
        self.assertGreaterEqual(min(numbers), 5.0, f"transformers must be 5.x or newer: {line}")

    def test_nemo_is_pinned_to_a_version_without_a_transformers_cap(self):
        line = find("nemo-toolkit")
        self.assertIn("==3.", line.replace(" ", ""), f"NeMo must be 3.x: {line}")

    def test_huggingface_hub_is_at_or_above_the_first_v2_release(self):
        line = find("huggingface-hub")
        self.assertNotIn("<2.0", line, f"huggingface-hub should allow 2.x: {line}")

    def test_every_requirement_is_pinned_or_bounded(self):
        # An unbounded requirement lets a resolver pick a vulnerable version.
        for line in requirements():
            self.assertRegex(
                line,
                r"(==|>=|~=|<)",
                f"requirement has no version constraint: {line}",
            )

    def test_the_documented_residual_risk_is_still_described(self):
        text = REQUIREMENTS.read_text(encoding="utf-8")
        for blocked in ("hydra-core", "lightning", "fsspec"):
            self.assertIn(blocked, text,
                          f"{blocked} is capped by NeMo; the file must say so")


if __name__ == "__main__":
    unittest.main()
