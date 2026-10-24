# The thirty-second render test

A short film whose only job is to be wrong cheaply. It is not a scene from the
long film and it is not a trailer: it is thirty seconds that exercise the parts
of the pipeline that are expensive to discover late — a typing beat that has to
land on a character, a pointer that has to press something and be answered,
kinetic type at its largest, every transition device, and sound that is caused
by the picture instead of laid over it.

    docs/media/render-test-30s.mp4        1280x720, 30 fps, 30.0 s, stereo-ready mono
    python tools/render_test_film.py      rebuild it, picture and sound
    node video_studio/films/render_test.mjs --cues    the plan, as JSON

## The script, in full

| time | picture | sound |
| --- | --- | --- |
| 0.0–5.4 | You type "fix the login page" and press enter. The request lifts out of the field and travels up, shrinking, to where the next card will be. | 17 keystrokes, one per character; a click on the press; a whoosh as it leaves |
| 5.4–9.8 | The agent writes the fix, one banded line of diff at a time, then commits. | a soft tick per line, a click, a pop for the commit |
| 9.8–12.0 | **NO CODE** | whoosh, pop |
| 12.0–14.2 | **ONE KEY** | pop |
| 14.2–16.4 | **A WORKING PAGE** | pop |
| 16.4–20.4 | The test suite reports, six rows, then the receipt. | a pop per result |
| 20.4–25.2 | **PRESS ENTER**, and the key arrives and is pressed. | impact, pop, click |
| 25.2–30.0 | **SHIPPED.** and out. | impact, swell |

Eight shots, six devices: `push`, `wipe`, `cut`, `push`, `focus`, `cut`, `wipe`.
No two neighbouring shots use the same one — `check_plan` in the tool refuses a
film where they do.

## One timeline, two media

The film emits a single JSON document with its shots and its cue sheet
(`--cues`). The picture is drawn from it and `tools/render_test_film.py`
synthesises the sound from it, so a click cannot drift away from the press that
caused it: `EV.enterPress` is one constant that both the drawn key and the
written cue read.

## The sound

Everything is arithmetic. `video_studio/audio_design.py` gained one cue kind,
`key`, and one control, `bed_gain`:

* `key` is three things at once — a broadband contact tick, the plastic click of
  the switch, and a low body resonance from the case. No envelope on top: the
  decays are the envelope, and a release ramp softens the transient that makes it
  read as a key at all. Each cue detunes a little from its own deterministic seed,
  so twelve strokes in a row are a rhythm and not a machine gun.
* `bed_gain` sets the underscore against the cues, and only the underscore.
  Measured with the bed at unity, the keystrokes sat 1.6 dB above the kick on
  average and sometimes below it: a typing shot with no typing in it. The bed now
  sits at 0.85 and the strokes at 0.52, and the strokes measure 12.4 dB above the
  bed in the mix.

Delivery: −20 LUFS integrated, −1.8 dBTP true peak. The long film's −14 LUFS is
the right target for a film with a voice in it; this one has no voice, and its
energy is sparse transients. Reaching −14 would have taken about 10 dB of limiter
on every click. `--lufs` still forces any target, and the report writes down how
much limiting it cost.

## What this film caught

Every one of these was a real fault in the work, not a hypothetical:

* **Frames that were blank after the first.** The prompt panel opened a canvas
  `save()` and never closed it, and its alpha was multiplied by an arrival that is
  zero for the first second. `globalAlpha` came back at zero and every later frame
  in that process was empty. Rendering one still per process hid it completely;
  only the contact sheet, where a dozen stills share a process, showed the black
  frames. There is now a `guard()` that throws if a draw hands the context back
  changed, and a test that renders four stills in one process.
* **Type off the right edge.** The stage settles every phrase from 1.35× down to
  1× across its beat, so a phrase fitted to the column at rest is 35 percent too
  wide for its first second. "A WORKING PAGE" ran out of frame; the stills at the
  end of the beat were perfectly inside it.
* **A request that flew through the title.** Two lines of type in the same place
  for a fifth of a second — the one thing that has been rejected twice. The title
  now leaves before the request starts to travel.
* **Two chapter labels on the same words** for the length of a transition. The
  incoming label now arrives after the change has finished.
* **An empty field after every hard cut.** The word schedule started at zero, so
  the frame after a cut had nothing on it for 0.2 s. It now starts slightly before
  zero, and the cut lands with the first letters already coming up.
* **A limiter that measured a silence.** `ebur128` prints one line per moment of
  audio and the first is always `-70.0 LUFS`. Reading the whole log instead of the
  summary block made the mastering tool believe a good mix was silent and apply
  +56 dB to it.
* **Card shots that could not pass the motion gate.** Text on a card is three
  pixels tall at the checker's 320×180, and three pixels of new text is not a
  change anyone can see. Every row now arrives as a filled band that wipes open —
  which is also what a diff looks like being written.

## The gate it clears

    tools/check_second_layers.py   30/30 seconds, mean 4.3 live regions, worst 2
    tools/check_determinism.py     identical across processes and chunk windows
    python -m unittest discover    1335 tests
    tools/check_structure.py       PASSED
    tools/check_motion_library.py  PASSED
