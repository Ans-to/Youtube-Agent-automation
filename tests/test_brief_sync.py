"""The picture may only print words the narration says.

The report that started this was blunt: "what we are seeing on screen and what
is actually happening or talking about are totally different". It was true. Each
section carried its own on-screen copy, written by hand next to the narration and
never compared with it, so the opening frame said "SHIP IT, OR STOP IT." while
the narrator was still saying "an agent just opened a pull request".

These tests hold the rule that fixed it: every word the film prints must be a
word of the narration, in the order it is spoken, in the section that says it.
"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIEFS = ROOT / "video_studio" / "briefs"
PLAN = ROOT / "docs" / "media" / "review-ai-code-plan.json"


def bare(word: str) -> str:
    return re.sub(r"[^a-z0-9']", "", str(word).lower())


ONES = {
    0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
    7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve",
    13: "thirteen", 14: "fourteen", 15: "fifteen", 16: "sixteen",
    17: "seventeen", 18: "eighteen", 19: "nineteen",
}
TENS = {20: "twenty", 30: "thirty", 40: "forty", 50: "fifty", 60: "sixty",
        70: "seventy", 80: "eighty", 90: "ninety"}


def spoken(token: str) -> list[str]:
    """What the voice says for a token the frame may print as a numeral.

    A rail prints "40" and the narrator says "forty" - that is correct film
    practice, not a mismatch, so the comparison reads both the same way.
    """
    if token.isdigit():
        value = int(token)
        if value in ONES:
            return [ONES[value]]
        if value in TENS:
            return [TENS[value]]
        if value < 100:
            tens, ones = divmod(value, 10)
            if tens * 10 in TENS and ones in ONES:
                return [TENS[tens * 10], ONES[ones]]
    return [token]


def tokens(text: str) -> list[str]:
    out = []
    for token in (bare(part) for part in str(text).split()):
        if token:
            out.extend(spoken(token))
    return out


def is_subsequence(phrase: str, spoken: list[str]) -> bool:
    want = tokens(phrase)
    if not want:
        return True
    cursor = 0
    for token in want:
        while cursor < len(spoken) and spoken[cursor] != token:
            cursor += 1
        if cursor >= len(spoken):
            return False
        cursor += 1
    return True


def authored_copy(section: dict) -> list[tuple[str, str]]:
    """Every phrase this section prints, labelled with the prop it came from."""
    props = section.get("props") or {}
    out = []
    for key in ("text", "left", "right", "label"):
        if isinstance(props.get(key), str) and props[key].strip():
            out.append((key, props[key]))
    for key in ("items", "lines"):
        for index, item in enumerate(props.get(key) or []):
            if isinstance(item, str) and item.strip():
                out.append((f"{key}[{index}]", item))
    for index, segment in enumerate(props.get("segments") or []):
        label = segment.get("label") if isinstance(segment, dict) else None
        if isinstance(label, str) and label.strip():
            out.append((f"segments[{index}]", label))
    return out


class BriefsOnlyPrintWhatIsSaid(unittest.TestCase):
    def briefs(self):
        paths = sorted(BRIEFS.glob("*.json"))
        self.assertTrue(paths, "no briefs found")
        return paths

    def test_every_on_screen_phrase_is_in_the_narration(self):
        failures = []
        for path in self.briefs():
            brief = json.loads(path.read_text(encoding="utf-8"))
            for section in brief.get("sections", []):
                spoken = tokens(" ".join(line.get("text", "") for line in section.get("lines", [])))
                for prop, phrase in authored_copy(section):
                    if not is_subsequence(phrase, spoken):
                        failures.append(
                            f"{path.name}: section {section.get('id')} prints {phrase!r} "
                            f"({prop}) but never says it")
        self.assertEqual(failures, [])

    def test_a_phrase_out_of_order_is_still_refused(self):
        spoken = tokens("One command runs every check npm test")
        self.assertTrue(is_subsequence("runs every check", spoken))
        self.assertFalse(is_subsequence("check every runs", spoken))

    def test_the_guard_is_not_vacuous(self):
        """A phrase nobody says must fail, or the test above proves nothing."""
        spoken = tokens("An agent just opened a pull request Do you ship it today")
        self.assertFalse(is_subsequence("Ship it, or stop it", spoken))


class TheDeliveredPlanMatchesTheNarration(unittest.TestCase):
    """The plan published with the film is checked, not the brief it came from."""

    def setUp(self):
        if not PLAN.is_file():
            self.skipTest("the delivered plan is not in the repository")
        self.plan = json.loads(PLAN.read_text(encoding="utf-8"))
        if not any("shows" in shot for shot in self.plan.get("shots", [])):
            self.skipTest("this plan predates the on-screen text record")

    def section_words(self, section_id: str) -> list[str]:
        windows = [(shot["start"], shot["end"]) for shot in self.plan["shots"]
                   if shot["section"] == section_id]
        first = min(start for start, _ in windows)
        last = max(end for _, end in windows)
        spoken = []
        for cue in self.plan["captions"]:
            if cue["start"] >= first - 0.5 and cue["end"] <= last + 0.5:
                spoken.extend(tokens(cue["text"]))
        return spoken

    def test_every_beat_shows_words_from_its_own_section(self):
        failures = []
        cache = {}
        for shot in self.plan["shots"]:
            shown = shot.get("shows") or ""
            if not shown:
                continue
            section = shot["section"]
            if section not in cache:
                cache[section] = self.section_words(section)
            for phrase in [part.strip() for part in shown.split("|") if part.strip()]:
                if not is_subsequence(phrase, cache[section]):
                    failures.append(f"{shot['id']} shows {phrase!r}")
        self.assertEqual(failures, [])

    def test_the_first_beat_is_on_screen_immediately(self):
        first = self.plan["shots"][0]
        self.assertLessEqual(first["start"], 0.2)
        self.assertTrue(first.get("shows"), "the opening beat has nothing on it")


if __name__ == "__main__":
    unittest.main()
