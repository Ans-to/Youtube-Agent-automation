"""Guards for the two failures that were invisible for five rounds.

The film was rejected over and over and the reasons given were about look and
voice, but two of the faults underneath it were silent:

1.  `assets/fonts/` did not exist, so every `family: 'Inter'` and
    `family: 'Space Grotesk'` call rendered in DejaVu Sans - the Linux default -
    and nobody could see that it had happened. The type was wrong and the code
    said it was right.
2.  The director reads `shot.transitionRole`. The new film set `shot.role`, so
    every join fell through to the default and the film cut on the same
    fallback eight times while the log cheerfully printed "something changes".

Both are the same class of bug: a name that does not resolve, and a library that
helps by guessing. These tests make the next one fail loudly.
"""
from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "video_studio"
FONTS = STUDIO / "assets" / "fonts"
KIT = STUDIO / "motion"


def registered_families() -> list[str]:
    """Every family the renderer can actually resolve.

    This asks the kit's own loader, not a copy of it: a test that registered the
    files its own way would pass while the renderers stayed in DejaVu.
    """
    script = (
        "import { loadFonts, familyNames } from './motion/kit/fonts.mjs';"
        "loadFonts();"
        "console.log(JSON.stringify(familyNames()));"
    )
    out = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=STUDIO, capture_output=True, text=True, timeout=120,
    )
    if out.returncode != 0:
        raise AssertionError(out.stderr[:2000])
    return json.loads(out.stdout.strip().splitlines()[-1])


class TestTypeIsReallyInstalled(unittest.TestCase):
    def test_font_files_ship_with_the_repo(self):
        self.assertTrue(FONTS.is_dir(), "assets/fonts is missing; every named family silently falls back")
        files = [p for p in FONTS.iterdir() if p.suffix.lower() in ('.woff2', '.woff', '.ttf', '.otf')]
        self.assertGreaterEqual(len(files), 8, f"only {len(files)} font files")

    def test_every_family_the_code_asks_for_can_be_resolved(self):
        families = set(registered_families())
        generic = {
            'sans-serif', 'serif', 'monospace', 'system-ui', 'cursive', 'fantasy',
            'ui-sans-serif', 'ui-serif', 'ui-monospace',
            # `family:` is also the key shapes.mjs uses for a *category of
            # drawing* - geometry, object, data, diagram, prop, chart. Those are
            # not typefaces and must not be held to being installed.
            'geometry', 'object', 'data', 'diagram', 'prop', 'chart',
        }
        asked: dict[str, set[str]] = {}
        for path in list(KIT.rglob('*.mjs')) + list((STUDIO / 'films').rglob('*.mjs')):
            for m in re.finditer(r"family:\s*'([^']+)'", path.read_text()):
                asked.setdefault(m.group(1), set()).add(path.name)
            for m in re.finditer(r'font\s*=\s*[`"\'][^`"\']*?px\s+"?([A-Za-z][A-Za-z0-9 ]*)"?', path.read_text()):
                asked.setdefault(m.group(1).strip(), set()).add(path.name)
        missing = {k: sorted(v) for k, v in asked.items() if k not in families and k not in generic}
        self.assertEqual(missing, {}, f"these families are asked for but not installed: {missing}")


def _starts() -> list[dict]:
    path = Path('/tmp/st-test.json')
    if not path.exists():
        out = subprocess.run(
            ['node', 'films/nokia_atlas.mjs', '--starts', str(path)],
            cwd=STUDIO, capture_output=True, text=True, timeout=300,
        )
        if out.returncode != 0:
            raise AssertionError(out.stderr[-2000:])
    return json.loads(path.read_text())


class TestTheDirectorIsActuallyDriving(unittest.TestCase):
    """A role the director does not know is a role that silently becomes `beat`."""

    ROLES = {'beat', 'time', 'chapter', 'era', 'motion', 'rack', 'momentum'}

    def test_every_shot_declares_a_known_role(self):
        src = (STUDIO / 'films' / 'nokia_atlas.mjs').read_text()
        roles = re.findall(r"^\s{4}role:\s*'([^']+)'", src, re.M)
        self.assertEqual(len(roles), 8, f"expected eight shots, found {len(roles)}")
        unknown = [r for r in roles if r not in self.ROLES]
        self.assertEqual(unknown, [], f"unknown roles: {unknown}")

    def test_the_film_publishes_a_clock_that_the_mixer_can_use(self):
        rows = _starts()
        self.assertEqual(len(rows), 8)
        at = 0.0
        for row in rows:
            self.assertAlmostEqual(row['start'], at, places=2)
            self.assertGreater(row['voStart'], row['start'], 'the picture must lead the voice')
            self.assertLess(row['voStart'], row['end'], 'a line may not start after its own cut')
            if row['vo'] is not None:
                self.assertLessEqual(row['voStart'] + row['vo'], row['end'] + 1e-6,
                                     f"{row['id']}: the line runs past the cut")
            at = row['end']

    def test_no_two_joins_use_the_same_technique(self):
        rows = _starts()
        kinds = [r['transition'] for r in rows[1:]]
        self.assertEqual(len(kinds), len(set(kinds)), f"a technique repeats: {kinds}")
        for row in rows[1:]:
            self.assertTrue(row['transitionWhy'], f"{row['id']} has a join with no reason")


class TestVoiceLinesFitTheFilm(unittest.TestCase):
    def test_every_line_fits_inside_its_shot(self):
        import sys
        sys.path.insert(0, str(STUDIO))
        import narrate

        timing = json.loads((STUDIO / 'films' / 'vo-timing.json').read_text())
        rows = _starts()
        placed = narrate.place_in_film(timing, rows)
        self.assertEqual(len(placed), len(timing))
        for row in placed:
            self.assertGreater(row['end'], row['start'])


if __name__ == '__main__':
    unittest.main()
