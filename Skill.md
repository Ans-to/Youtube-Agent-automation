# Video Production Skill

Shared standards for motion design and rendered video in this repository. The task brief and any user-approved references define the content, format, aspect ratio, tone, and voice; follow those choices without adding fixed layout or style constraints that the task does not need.

## 1. Core Tech Stack & Architecture

- Use the renderer already selected for the task: Remotion with React/TypeScript and React Three Fiber/Three.js for Remotion compositions, or the repository's existing Canvas2D/FFmpeg pipeline where that is the established workflow.
- Keep reusable concerns modular: composition/storyboard, frame timing, character artwork and motion, audio, and rendering/validation should have clear boundaries.
- Make animation deterministic and frame-driven. The same inputs and frame must produce the same output; do not use wall-clock timing or uncontrolled randomness in frame rendering.
- Use the requested aspect ratio and dimensions throughout layout and rendering. Keep essential text and action within the relevant safe area without imposing a universal left/right or portrait layout.
- Ground factual visuals, numbers, quotations, and comparisons in supplied or verified evidence. Preserve meaning, uncertainty, attribution, and context; do not turn placeholders into claims.
- Use only effects supported by the selected renderer. Identify proposed or unsupported features honestly rather than claiming they are implemented.

## 2. Visual & 2D Vector Character Standards

- Make visual choices serve the brief and the meaning of each scene. Preserve an approved visual reference unless the user asks for a redesign.
- When a character is requested or useful to the story, use a clean, detailed 2D vector illustration, preferably layered SVG, presented as a camera-facing plane. Match its identity, clothing, expression, and gesture to the brief.
- Keep character silhouettes, faces, and important details legible at the final delivery size. Organize movable parts so intended gestures remain coherent; use licensed or original artwork.
- Use a restrained, high-contrast palette with consistent semantic accents. Keep typography readable, hierarchy clear, and negative space purposeful; do not force a particular color, grid, or placement when the brief calls for another treatment.
- Use diagrams, interfaces, charts, and other graphics only when they clarify the scene. Keep factual graphics accurate and legible, and avoid decorative interface detail that cannot be read or understood.

## 3. Motion, Physics & Pacing

- Story comes before effects. Give each shot a clear purpose and focal point; motion should explain, emphasize, or transition—not compete with comprehension.
- Pace reveals to meaning, narration, and emphasis. Use word- or phrase-level typography when it remains readable; let important information hold long enough to understand.
- Derive animation from the composition's frame and frame rate. Use Remotion `interpolate()` for frame-based timing and `spring()` when a responsive, physical impact suits the material; tune easing, overshoot, and follow-through rather than applying one motion preset everywhere.
- Synchronize significant text, cuts, and accents to clear audio beats or spoken stresses when appropriate. Keep transitions editorial and varied where the story warrants it; do not add camera motion or effects by default.
- Use deliberate stillness and readable holds. Avoid both accidental dead air and constant movement that distracts from the message.
- Keep secondary motion subordinate to the focal action. Use glitch, flashes, or rapid movement sparingly, with accessibility and visual comfort in mind.

## 4. Audio & Rendering Pipeline

- Follow the task's explicit language and the repository's configured, licensed voice/audio backend. Do not silently switch language, voice, or provider. When synthesizing speech, write for natural cadence and preserve meaningful pauses and the approved wording.
- Fit scene timing to the produced audio rather than trimming words or phonemes to fit arbitrary durations. Use measured timing when available; do not describe approximate energy-based cues as phoneme-accurate lip-sync.
- Mix narration, music, ambience, and effects intentionally. Keep speech intelligible, duck backing audio as needed, and avoid clipping, silence, or effects that mask speech.
- Before handoff, validate the rendered file's dimensions, frame rate, duration, video and audio streams, and relevant black-frame/freeze/audio checks. Render success alone does not establish visual, factual, or audio quality.
- Review the exact final output at normal playback speed with sound. Check scene meaning, text legibility, transitions, audio synchronization, and defects; report limitations and do not claim human approval unless the reviewed file is the delivered file.
