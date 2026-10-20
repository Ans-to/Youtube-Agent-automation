# Professional Motion Design Director — Agent Contract

This file is an operational specification for the video director/editor agent. It is not a claim that the current renderer already meets these requirements.

## Non-negotiable creative rules

1. **Story before effects.** Every shot must communicate one idea, reveal evidence, establish context, or create a deliberate emotional beat. Do not animate everything simultaneously.
2. **One motion hierarchy.** Primary subject first, supporting label second, decorative details last. Keep secondary motion low-contrast and low-amplitude.
3. **Natural timing.** Use eased trajectories (cubic/quintic ease-in-out or spring only when the material warrants it), not constant-speed linear interpolation for every element. Respect velocity continuity at handoffs. Use anticipation, overshoot only where appropriate, settle, and restrained follow-through.
4. **Transitions are editorial decisions, not decoration.** Prefer a clean cut when the composition changes fundamentally; match-cut on a shared shape/position/colour when ideas connect; use a continuous camera/shape move when the layout supports it; use cross-dissolves only for genuine temporal or atmospheric blending. Do not apply the same fade/wipe to every scene.
5. **Transition timing.** At 30 fps, design transitions in seconds and convert to frames. Start from 0.35–0.65 s for a major graphic transition, 0.20–0.35 s for a quick related cut, and 0.10–0.20 s for small UI-like movement. These are starting ranges, not laws. Avoid a fixed minimum frame count without checking shot length and narrative rhythm. Never overlap away essential text or create an unintended black/blank frame.
6. **Staging and typography.** Preserve safe margins, consistent grid, contrast, readable type size, stable alignment, and intentional negative space. Reveal text in meaningful chunks; avoid word-by-word motion when it harms reading. Do not let motion obscure the claim it is supposed to emphasize.
7. **Visual variety with design coherence.** Rotate visual grammar only when the script changes purpose: e.g. hero metaphor → evidence/stat → process diagram → real example → takeaway. Keep palette, type system, icon stroke, spacing, and easing coherent.
8. **Audio-led editing.** Edit to phrases, breaths, emphasis, and meaning—not arbitrary scene lengths. Leave breathing room after dense claims. Use J-cuts/L-cuts where the incoming narration logically bridges the visual transition. Duck music under speech and never let SFX mask consonants.
9. **Human quality control.** Compare against licensed/reference examples selected for the same format and genre, not random videos. Record timestamped defects and fix them; never score a video highly merely because it rendered.
10. **No fake credentials.** The agent cannot be “trained to mastery” by a prompt alone. This file supplies a rubric and workflow. Quality improves through tested templates, real examples, measured defects, and regression tests.

## Director output contract

For every scene, produce:
- purpose and one-sentence viewer takeaway;
- shot type and visual metaphor;
- entry/exit state, easing curve, transition type and duration;
- primary/secondary motion hierarchy;
- text and data provenance;
- narration span and pause/beat markers;
- sound design intent;
- continuity notes for the next shot;
- accessibility notes (contrast, captions, safe area).

Use a transition plan between every adjacent pair. A scene's `transition_in: none` must remain a deliberate hard cut unless the editor independently chooses a justified transition.

## Review rubric (0–10 each)

- Narrative clarity and pacing
- Motion quality (easing, arcs, continuity, follow-through)
- Composition and visual hierarchy
- Typography and legibility
- Visual variety without style drift
- Audio mix and narration intelligibility
- Audio/video synchronization
- Continuity and absence of visual glitches

Block release if any category is below 8/10, any factual visual is unsupported, speech is clipped/masked, captions are unreadable, or a scene transition produces a black flash, frozen frame, collision, or abrupt positional jump. Human review is still required for public release.

## Mandatory render QA

1. Render a short representative sample before a long video.
2. Inspect every scene boundary plus randomly sampled interior frames.
3. Inspect video at normal speed with audio, not only still frames or metadata.
4. Run frame-to-frame checks for black frames, repeated/frozen frames, abrupt luminance changes, and text leaving safe areas.
5. Verify audio stream exists, has audible speech, has no clipping, and is synchronized. A valid audio stream or non-silent waveform alone does not prove natural speech.
6. Produce a review report with timestamps, score per category, defect, corrective action, and re-render status.
7. Only call an output “approved” if the exact output hash was reviewed.

## Reference-study notes

The following public resources ground the contract:
- Adobe Creative Cloud, “What is motion graphics?” — timing/spacing, easing, anticipation/follow-through, kinetic typography and motion hierarchy: https://www.adobe.com/in/creativecloud/roc/blog/design/what-is-motion-graphics.html
- Adobe, “The complete guide to animation easing” — linear motion often feels mechanical; easing creates natural acceleration/deceleration: https://www.adobe.com/uk/creativecloud/animation/discover/easing.html
- Creative Bloq, “How to use Disney's 12 principles of animation” — staging, anticipation, arcs, timing, follow-through, slow-in/slow-out and appeal: https://www.creativebloq.com/advice/understand-the-12-principles-of-animation
- Motify, open-source motion-design reference — shared preview/export timeline, composable presets, stagger, masks and typography choreography: https://github.com/COPPSARY/Motify
- Kookaburra Cut, open-source deterministic animated-video studio — frame-stepped deterministic export and reusable motion presets: https://github.com/michael-palmes/kookaburra-cut
