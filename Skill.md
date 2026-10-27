AI Video Director & Pipeline Rules
​This document outlines the mandatory rules your AI agent must follow when generating scripts, code, voiceovers, and motion graphics for high-retention cinematic videos.
​1. Voiceover & Audio Pipeline Rules
​Tooling: Use Microsoft Edge TTS (edge-tts) as the primary free, programmatic TTS engine. Do not use generic or paid third-party APIs unless explicitly overridden.
​Voice Selection:
​For serious, dramatic, or corporate documentary content, default to:
​en-US-ChristopherNeural (Deep, authoritative, commanding)
​en-US-SteffanNeural (Analytical, steady, professional)
​Cadence & Pacing Prevention:
​Never pass raw, unformatted text blocks to the TTS engine.
​Automatically inject micro-pauses (..., comma breaks, or em-dashes —) into sentences to prevent the AI voice from rushing.


​2. Background Score & Audio Mixing Rules
​Track Selection: Default to low-frequency cinematic ambient drones, subtle electronic pulses, or minimalist piano ostinatos for documentary and tech-failure videos.
​Volume Levels: Background music must always be set to a low volume threshold (e.g., volume={0.15}) to ensure the voiceover remains the primary focal point.
​File Management: All background tracks must be referenced dynamically from the public/sounds/ directory using Remotion's staticFile() helper.


​3. Contextual FX & Transition Rules
​Selective Accents: Do not apply constant glitch effects or heavy filters globally. Use glitches, RGB chromatic aberration, or pixel dissolves only as transitional punctuation during high-tension moments (e.g., market crashes, software shifts, or dramatic scene transitions).
​Clean Baseline: Normal narrative sections, historical overviews, or calm analytical explanations should have clean, crisp, high-end rendering with smooth camera pans and elegant typography.
​4. Automated Visual Storyboarding & Metaphor Matching
​Emotional & Keyword Analysis:
​Triumphant/Growth: Use upward camera pans, green/cyan accent lighting, world maps, or expanding grids.
​Tense/Crisis: Use dark isometric rooms, selective red glitch overlays, closing camera angles, and dramatic shadows.
​Technical/Analytical: Use glowing monitors, terminal windows, line charts, and floating UI elements.
​The 3-Second Rule (Pacing):
​Never keep the same visual state for more than 3 to 5 seconds. Introduce micro-visual shifts (camera zooms, text pops, lighting changes) to maintain viewer retention.


​5. 100% Code-Based Procedural Asset Protocol (Zero Copyright Risk)
​Strictly No External Raster Images: Never download, fetch, or reference external JPEGs, PNGs, or stock footage. Every single visual element must be rendered programmatically.
​Visual Rendering Toolkit:
​3D Environments & Objects: Use Three.js / React Three Fiber to build 3D voxel models, isometric rooms, abstract shapes, and lighting using geometric primitives.
​UI, Icons & Historical/Product Metaphors: Use Programmatic SVGs or Canvas vectors drawn mathematically using path coordinates.


​6. Automated Karaoke Subtitles Engine
​Subtitle Styling: Every video must feature burnt-in captions at the lower-third or center-screen position.
​Word-Level Highlighting: Using Remotion or subtitle parsers, words must animate in sync with the .mp3 voiceover timing. The currently spoken word must be highlighted in high-contrast accent color (e.g., neon red), while past words remain white and future words remain dimmed.


​7. Quality Assurance & Safe-Zone Rules
​Platform Safe Zones: For vertical videos (9:16), ensure all critical text, titles, and UI elements stay within the central safe zone—avoiding the bottom 15% (platform UI) and top 10% (profile headers).
​Responsive Layering Math: Code must calculate positioning dynamically using Remotion's useCurrentFrame() and interpolate() to prevent element clipping or static overflow.


​8. Audio-Visual Timestamp & Forced Alignment Protocol
​Dynamic Subtitle JSON: When generating voiceover audio via edge-tts, the code must capture or generate a corresponding word-level timestamp array (Start time, End time, Word).
​Remotion Frame Mapping: Subtitle and visual cut components must calculate their active state dynamically using real-time audio timestamp data, ensuring zero drift between voice and visuals.


​9. Multi-Scene Composition Orchestration
​Modular File Structure: Every scene must be built as an isolated, self-contained Remotion composition (Scene1.tsx, Scene2.tsx, etc.) accepting props for duration and data.
​Master Composition (Root.tsx): Orchestrate the final video inside Root.tsx using <Series> or calculated durationInFrames offsets, ensuring seamless audio and visual transitions across scene boundaries.


​10. Code-Based Detailed 2D Vector Characters (Zero Copyright Risk)
​Strictly No Pixel/Voxel Art or Raster Images: Characters must be rendered as high-end, modern 2D vector illustrations (clean vector lines, smooth geometric curves, and multi-tone color gradients for professional depth).
​Technical Construction (Modular SVGs):
​Build characters as React components using native SVG elements (<path>, <g>, <circle>, <linearGradient>).
​Structure characters in modular layers (Body, Head, Eyes, Mouth, Arms, Clothing/Accessories) so individual parts can be animated independently.
​Procedural Animation:
​Use mathematical interpolation (interpolate(), Math.sin()) to animate vector groups—such as subtle torso breathing, head nods, arm gestures, or changing mouth shapes for script sync—driven purely by code.

## Strict Layer Separation Rule (2D Vector vs 3D Environment)
- **Environment:** Can be 3D isometric (Three.js / R3F) for desks, grids, and monitors.
- **Characters:** Must **never** be blocky voxels or 3D models. Characters must be rendered as **flat-faced or layered 2D vector SVGs** positioned inside the 3D space as crisp billboard planes, ensuring they always look like high-end vector illustrations (like the detective style) regardless of the background grid.
- 
