# Offline Agent HQ Motion Design System

This is the implementation contract for the motion-design specialist roles, storyboard generator, and Canvas2D renderer. Treat it as a reusable visual language, not a guarantee that every output automatically reaches professional-studio quality. Review actual renders at final resolution.

## 1. Visual grammar

Every scene chooses one visual type based on its information purpose:

| Type | Best use | Supported scene fields |
|---|---|---|
| \`hero\` | Establish the idea, make a dramatic pause, or reset visual rhythm | \`graphic_label\` |
| \`stat\` | Emphasize one supported, source-backed measurement | \`stat_value\`, \`stat_label\` |
| \`diagram\` | Explain a process or relationship in ordered steps | \`visual_nodes\` (2–4 short labels) |
| \`timeline\` | Show stages, sequence, or progress | \`timeline_events\` (2–4 short labels) |
| \`comparison\` | Make a well-founded before/after or A/B comparison | \`comparison_left_title\`, \`comparison_right_title\`, \`comparison_left\`, \`comparison_right\` |
| \`code\` | Show the mechanism, a code concept, or a technical example | \`code_lines\` (up to 6 lines) |
| \`quote\` | Give a supported, attributed quotation or a short principle | \`quote\`, \`quote_source\` |
| \`waveform\` | Add a restrained audio/energy motif or sound-related visual | no required extra fields |
| kinetic-type | Animate a short headline with staggered, readable word reveals | short headline; optional show_orbit |
| bar-chart | Animate a compact comparison of supplied, source-backed numeric values | chart_values (2–6 numbers), matching chart_labels (2–6 strings) |

Chart labels/values must match one-to-one. A chart is an explanatory visual, not permission to invent a metric; include a source note in the script or scene metadata when values are factual.

The storyboard field `transition_in` accepts \`none\` (deliberate hard cut), \`whip-pan\`, \`masked-reveal\`, \`morph\`, \`glitch\`, and \`match-cut\`. Legacy names (\`fade\`, \`wipe-left\`, \`wipe-right\`, \`slide-left\`, \`slide-right\`, \`zoom\`) still render but fail the professional audit; `motion_director.py` upgrades them. Never use Push, Wipe, or Dissolve. \`transition_frames\` must be from 1 to 60. Transitions are deterministic frame-by-frame.

## 2. Shot design rules

For an existing film or series, treat its user-selected/approved visual reference
and motion-graphics-only constraints as the controlling style contract. Preserve
its shot builders, typography, palette, framing, and transition grammar unless
the user requests a redesign. The defaults below are not permission to replace
an established look while fixing content. If the reference is genuinely unclear,
confirm it before a full render.

1. Start with the viewer's question, not decoration. Give each shot one purpose, one focal point, and one key takeaway.
2. Change visual grammar when the idea changes: typography, diagram, code, timeline, comparison, data card, quote, or a held hero frame. Avoid showing the same generic orbit/card on every scene.
3. Build a rhythm: controlled entrance, time to understand, an explanatory build, then a readable hold. Motion should clarify the meaning, not compete with narration.
4. Keep landscape non-hero text in the left content zone and its visual card in the right zone. In portrait, use a vertically sequenced layout with text, graphic, and captions separated.
5. Keep text short and high contrast. Headline, subhead, captions, and micro-labels have distinct size/weight roles. Long text must wrap; no content should rely on a tiny footer.
6. Use a consistent palette: base \`#0b0b0f\`, foreground \`#f4f2ec\`, accent \`#c8ff3d\`, muted \`#a7a7b3\`, grid \`#24242c\`. Only add colors with a clear semantic function.
7. For facts, numbers, comparisons, and quotations, use only supplied or verified evidence. The renderer must never turn a placeholder/example metric into a factual claim.
8. Use the same visual thesis, palette, type scale, and easing logic across a video, but vary shot composition in service of the story.

### Semantic fidelity is a release requirement

Before rendering, divide the narration into spoken ideas. For each idea record
its exact source span, time range, visible subject, action, relationship and the
reason that visual means the same thing. Preserve who did what, negation,
qualifiers, time period and the denominators of comparisons and figures. A
related topic, generic icon, factory for "people carrying phones", or animated
text alone does not establish the intended relationship. Use drawings and motion
that explain the specific idea; do not invent a fact to make a graphic work.

After encoding, a named reviewer must watch **and listen** to every beat of the
actual video, including transitions, checking the pictured claim against the
spoken claim. Log mismatches with timestamps and fix/rerender them; a matching
keyword, contiguous timeline, character coverage, or moving pixels cannot prove
semantic correctness or word-level sync. A partial review is **unverified**.

## 3. Implementation and resource limits

- The output Canvas drawing buffer must be set to the actual storyboard \`width\` and \`height\`, not only the browser viewport.
- Supported canvas dimensions: 320–3840 px wide, 180–3840 px high (4K portrait is 2160×3840); frame rate: 1–60 fps.
- A storyboard may carry a `style` block (`tone`, `palette`, `grade`, `easing`, `typography`). It is validated before rendering and applied to every frame; `motion_director.py` generates it.
- Global cap: 1,000 seconds and 30,000 frames. Do not bypass the cap by splitting a job into unexpectedly huge scenes.
- Renderer frame functions receive the scene, local frame, scene frame count, and global frame index. Use those values for deterministic timing; do not call randomness or read wall-clock time inside \`drawFrame\`.
- Validate storyboard types before rendering, validate contiguous PNG numbering and exact PNG dimensions before encoding, and verify final MP4 metadata after encoding.
- Prefer simple vector operations and bounded arrays over expensive per-frame text reflow or unbounded particles on low-resource devices. Clean frame and audio intermediates only after output validation succeeds.

## 4. Handoff contracts for the two motion specialists

### AGENT-51 — Motion Graphics Creative Director

Deliver: visual thesis, selected visual type per scene, composition rules, palette/type rules, transition rationale, rhythm map, and a short creative QA checklist. Require meaningful variation across scenes without introducing unsupported facts or unlicensed assets.

### AGENT-52 — Motion Systems & Compositing Specialist

Deliver: exact scene fields, layer order, frame counts, easing/reveal behavior, transition type, safe-area rules for 16:9 and 9:16, render-budget estimate, and regression checks. Designs must map to the implemented visual types and deterministic renderer; call out unsupported effects instead of claiming they are implemented.

## 5. Review checklist

Before accepting a render, inspect the actual opening, at least one middle scene, the final scene, and any dense diagram/code/caption scene in each requested aspect ratio. Check:
- no clipped, colliding, unreadable, or misleading text;
- non-hero landscape graphics do not overlap copy;
- portrait layout is composed for portrait, not a landscape crop;
- each scene's graphic fits its script meaning and scene-to-scene rhythm;
- transitions have no sudden hidden content or long blank hold;
- frame count, dimensions, frame rate, video codec, and requested audio pass machine checks;
- a human review confirms visual quality. CI rendering alone does not prove aesthetics.

## 6. The template library, and choosing by situation

The generic visual types in section 1 are the grammar. The actual motion is drawn
from our own template library in `video_studio/motion/library.mjs`, and the agent
does not invent a template at the call site.

**Why ours, not stock.** The owner asked whether to use copyright-free stock
templates. Three reasons we do not: stock packs are mostly After Effects projects
that this renderer cannot open; their licences split into CC0, attribution, and
"free for personal use" — and the third kind is a claims risk on a monetised
channel; and a template's text boxes are fixed, so its type collides with ours.
Our own library keeps the visual language consistent across every film and
carries no licence at all.

**The agent's map is generated, not written.** `agents/motion_templates.json` is
the output of `node video_studio/motion/library_cli.mjs --write-agent-map`. Never
edit it by hand: a hand-kept catalogue drifts, and an agent acting on a stale
catalogue is worse than no catalogue. `tools/check_motion_library.py` fails the
build when the file and the code disagree.

**Pick by situation.** Every template declares the situations it serves and the
ones it must not be used for. The situation is the beat's purpose, not its look:

| Situation | What the beat is for | First choice |
|---|---|---|
| `opening-claim` | state the premise in one sentence | `kinetic-headline` |
| `name-the-thing` | put a name or key figure on the frame | `kinetic-headline` |
| `state-the-thesis` | state the idea the section argues for | `kinetic-headline` |
| `punchline` | land a short line with nothing else on screen | `kinetic-headline` |
| `explain-a-number` | show a figure the script claims | `count-up` |
| `show-a-sequence` | walk through steps in spoken order | `list-build` |
| `show-criteria` | list the conditions something must meet | `list-build` |
| `make-a-comparison` | put two options against each other | `compare-pair` |
| `before-and-after` | show the same thing before and now | `compare-pair` |
| `show-the-mechanism` | reveal how it works with real commands | `code-typing` |
| `show-the-command` | one command, typed | `code-typing` |
| `build-an-argument` | add one more reason to a stack | `stack-push` |
| `recap` | bring a section back to a short list | `list-build` |
| `hold-a-beat` | fill a short pause with real motion | `sweep-rule` |
| `punctuation` | mark a change of section | `sweep-rule` |

**How the choice is made.** `rankTemplates` in `video_studio/motion/choose.mjs`
scores every template against the beat it has to fill and returns the reasons:

1. *Situation.* Named for it `+3`, second choice `+2`, not called for `0`.
2. *Duration.* Inside the template's own band `+1.5`; outside it the score
   falls, and past 1.35× the band the template is refused outright.
3. *Region.* A template can only be used where it owns the space. If the free
   region is not one of its own, it is refused with that reason.
4. *Props.* Missing required props are a refusal, never a default.
5. *Novelty.* The previous beat's template is penalised `-2.5`, anything used in
   the last three beats `-1.0`.
6. *Weight.* Under 1.2 seconds, cheap templates are preferred.

**The region rule is the anti-overlap rule.** Every template owns named regions
of the frame (`title`, `hero`, `stage`, `floor`, `band`, `split`, `ledger`), and
none of them may touch the live column on the right or the caption band at the
foot. `drawTemplate` throws if a call asks for a region the template does not
own, or a beat the template cannot carry. The self-check renders every template
on a real canvas and measures the ink against its box, so "it stays inside its
region" is a measurement, not a comment.

**Nothing shakes.** No template translates or rotates the camera. Motion is one
direction, eased, then still.

**The camera is locked.** Not "subtle" — locked. There is no scene camera, no
beat push, no roll and no hand-held noise layer in any film. It kept coming back
because each version was defensible on its own: a reframe that settles like an
operator, a two percent push on every beat, a slow drift so that no frame is
identical to the last. On screen it is a picture that will not sit still, and the
owner named it as shake twice.

Measured on the background of the 0-30 s chunk, between consecutive frames:

| Version | Worst movement of a background patch | Mean |
|---|---|---|
| Camera moving (reframe + push + drift) | 8.0 px per frame at 1280 wide | 0.31 px |
| Camera locked (now) | **0.0 px** | **0.00 px** |

Everything that moves now moves inside the frame: type, slabs, the live column,
the cursor. `tools/check_motion_library.py` rule `M7 CAMERA` fails the build if a
hand-held offset, a `shakeX`/`shakeY` pair or a noise-driven rotation returns to
any film.
