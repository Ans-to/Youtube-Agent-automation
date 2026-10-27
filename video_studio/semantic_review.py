"""Evidence schema for a human visual-to-narration review.

The checks here establish coverage and provenance, not semantic truth. A person
must watch/listen to the encoded file and judge whether the depicted subject,
action, relationship, chronology and qualifiers match what is actually spoken.
"""
from __future__ import annotations

import math
import re


class SemanticMismatch(ValueError):
    """The reviewer explicitly reported a mismatch in the finished video."""


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('visual cue timestamps must be finite numbers')
    return float(value)


def expected_beats(storyboard, shots, timing, tolerance=0.05):
    """Build expected review rows from a contiguous, narration-linked storyboard.

    Each first cue begins with the line; subsequent cue labels must be literal,
    ordered substrings of the line. This maps text to picture intervals, but the
    result is not word-level alignment or evidence that the interval actually
    contains the intended sound.
    """
    if (not isinstance(storyboard, dict) or not isinstance(storyboard.get('scenes'), list)
            or not isinstance(shots, list) or not shots or not isinstance(timing, list)
            or len(shots) != len(timing)):
        raise ValueError('a complete storyboard, shot clock and narration timing are required')
    flattened = []
    for scene in storyboard['scenes']:
        if not isinstance(scene, dict) or not isinstance(scene.get('shots'), list):
            raise ValueError('storyboard scenes must contain shot objects')
        for shot in scene['shots']:
            if not isinstance(shot, dict) or shot.get('scene') != scene.get('scene'):
                raise ValueError('storyboard shot scene does not match its parent')
            flattened.append(shot)
    if len(flattened) != len(shots):
        raise ValueError('storyboard must cover every shot exactly once')

    result = []
    for expected, narration, depicted in zip(shots, timing, flattened):
        if not isinstance(expected, dict) or not isinstance(narration, dict):
            raise ValueError('shot clock and narration rows must be objects')
        ident, text = expected.get('id'), narration.get('text')
        if (not isinstance(ident, str) or not isinstance(text, str) or not text
                or narration.get('shot') != ident or depicted.get('id') != ident
                or depicted.get('scene') != expected.get('scene') or depicted.get('narration') != text):
            raise ValueError('storyboard must use the exact narration and ordered shot IDs')
        cues = depicted.get('visualCues')
        if not isinstance(cues, list) or not cues:
            raise ValueError(f'{ident}: a visual cue is required for every narrated shot')
        shot_start, shot_end = _number(expected.get('start')), _number(expected.get('end'))
        if shot_start < 0 or shot_end <= shot_start:
            raise ValueError(f'{ident}: invalid shot duration')
        previous_end = shot_start
        char_starts = []
        for index, cue in enumerate(cues):
            if not isinstance(cue, dict) or not isinstance(cue.get('visual'), str) or not cue['visual'].strip():
                raise ValueError(f'{ident}: cue {index} needs a named visual')
            start, end = _number(cue.get('start')), _number(cue.get('end'))
            if end <= start or abs(start - previous_end) > tolerance or start < shot_start - tolerance or end > shot_end + tolerance:
                raise ValueError(f'{ident}: visual cues have a gap, overlap or invalid duration')
            previous_end = end
            needle = cue.get('cue')
            if not isinstance(needle, str):
                raise ValueError(f'{ident}: cue {index} must quote the narration')
            if index == 0:
                if needle != '':
                    raise ValueError(f'{ident}: first visual cue must start with the line')
                position = 0
            else:
                if not needle.strip():
                    raise ValueError(f'{ident}: interior cue must quote a non-empty word or phrase')
                match = re.compile(re.escape(needle), re.IGNORECASE).search(text, char_starts[-1] + 1)
                if match is None:
                    raise ValueError(f'{ident}: visual cue does not occur in narration in order')
                position = match.start()
            char_starts.append(position)
        if abs(previous_end - shot_end) > tolerance:
            raise ValueError(f'{ident}: visual cues do not cover the full shot')
        for index, cue in enumerate(cues):
            start_char = char_starts[index]
            end_char = char_starts[index + 1] if index + 1 < len(char_starts) else len(text)
            excerpt = text[start_char:end_char]
            if not excerpt.strip():
                raise ValueError(f'{ident}: cue {index} has no spoken content')
            result.append({'shot': ident, 'cue_index': index, 'start': cue['start'], 'end': cue['end'],
                           'visual': cue['visual'], 'spoken_span': excerpt})
    return result


def blank_beat_reviews(storyboard, shots, timing):
    """Create a blank checklist; no row is accepted or interpreted as approval."""
    return [{**item, 'status': 'unverified', 'subject': '', 'action': '',
             'relationship': '', 'evidence': ''}
            for item in expected_beats(storyboard, shots, timing)]


def validate_beat_reviews(storyboard, shots, timing, reviews):
    """Require one explicit human assessment per actual planned visual cue."""
    expected = expected_beats(storyboard, shots, timing)
    if not isinstance(reviews, list) or len(reviews) != len(expected):
        raise ValueError('the reviewer must assess every visual cue, not just each scene')
    keys = ('shot', 'cue_index', 'start', 'end', 'visual', 'spoken_span')
    for wanted, row in zip(expected, reviews):
        if (not isinstance(row, dict) or type(row.get('cue_index')) is not int
                or any(row.get(key) != wanted[key] for key in keys)):
            raise ValueError(f"{wanted['shot']}: the beat review does not match the current storyboard and narration")
        if row.get('status') == 'fail':
            raise SemanticMismatch(f"{wanted['shot']} cue {wanted['cue_index']}: reviewer reported semantic mismatch")
        if row.get('status') != 'pass':
            raise ValueError(f"{wanted['shot']} cue {wanted['cue_index']}: semantic review is unverified")
        for field in ('subject', 'action', 'relationship', 'evidence'):
            value = row.get(field)
            if not isinstance(value, str) or len(value.strip()) < 5:
                raise ValueError(f"{wanted['shot']} cue {wanted['cue_index']}: describe {field} from the encoded video")
    return len(expected)
