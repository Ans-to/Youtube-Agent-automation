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

1. Start with the viewer's question, not decoration. Give each shot one purpose, one focal point, and one key takeaway.
2. Change visual grammar when the idea changes: typography, diagram, code, timeline, comparison, data card, quote, or a held hero frame. Avoid showing the same generic orbit/card on every scene.
3. Build a rhythm: controlled entrance, time to understand, an explanatory build, then a readable hold. Motion should clarify the meaning, not compete with narration.
4. Keep landscape non-hero text in the left content zone and its visual card in the right zone. In portrait, use a vertically sequenced layout with text, graphic, and captions separated.
5. Keep text short and high contrast. Headline, subhead, captions, and micro-labels have distinct size/weight roles. Long text must wrap; no content should rely on a tiny footer.
6. Use a consistent palette: base \`#0b0b0f\`, foreground \`#f4f2ec\`, accent \`#c8ff3d\`, muted \`#a7a7b3\`, grid \`#24242c\`. Only add colors with a clear semantic function.
7. For facts, numbers, comparisons, and quotations, use only supplied or verified evidence. The renderer must never turn a placeholder/example metric into a factual claim.
8. Use the same visual thesis, palette, type scale, and easing logic across a video, but vary shot composition in service of the story.

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
