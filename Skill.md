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



# UNIVERSAL STUDIO-LEVEL VIDEO ENGINE (MASTER DIRECTIVE)

## 1. Dynamic Topic-to-Scene Pipeline
When given *any* script, topic, or outline (whether it's historical, technical, or exploratory), the agent must execute these 4 phases before writing code:
1. **Script Breakdown:** Divide the narrative into 10-15 second modular scenes, mapping each scene to a specific core visual metaphor.
2. **Contextual Character & Prop Selection:** Dynamically assign a 2D vector character role based on the topic:
   - *History/Ancient Topics:* An archivist/explorer vector avatar.
   - *Tech/AI/Software Topics:* A modern developer/analyst vector avatar.
   - *Science/Cosmos:* A researcher/astronomer vector avatar.
3. **Theming & Color Grading:** Establish a dominant dark-mode palette (`#0b0f19` base) with a topic-specific neon accent (e.g., Cyan for tech, Amber for history, Emerald for finance/nature).

## 2. Universal Component Architecture (Remotion Template)
Every scene across *any* video must be built using this reusable, decoupled React component structure:
- **Root.tsx:** Manages global state, audio tracks, and master timing offsets using `<Series>`.
- **`BaseSceneTemplate.tsx`:** A standardized wrapper providing:
  - **Layer 0 (Background):** Isometric grid, atmospheric radial gradients, and topic-specific ambient lighting.
  - **Layer 1 (Environment/Data):** Dynamic 3D/Isometric elements (desks, servers, ancient ruins, charts) built via Three.js/R3F.
  - **Layer 2 (Kinetic Typography):** Remotion spring-driven text blocks with real-time audio word sync.
  - **Layer 3 (Vector Character/Prop):** Clean 2D SVG vector avatars with procedural `Math.sin()` idle animations.
  - **Layer 4 (UI Overlays/HUD):** Floating data cards, glowing code blocks, or map callouts.

## 3. Non-Negotiable Studio Quality Rules (Applied to Every Topic)
- **Zero Copyright / Zero Raster:** Absolutely no stock images, PNGs, or 3D voxel blocks. Everything must be pure code-driven vectors, SVGs, and Three.js primitives.
- **Spring Physics Mandate:** Never use linear CSS transitions. All UI entrances, zoom levels, and card expansions must use Remotion's `spring({ damping: 12, stiffness: 100 })`.
- **Dynamic Camera Orchestration:** No static shots lasting over 3 seconds. The camera must smoothly push in, pan, or track narrative beats using mathematical interpolation.
- **Micro-Detail Polish:** Every UI window must feature subtle glassmorphism (`backdrop-blur`, semi-transparent borders), glowing drop shadows, and high-contrast typography (Inter/JetBrains Mono).
- 

[MANDATORY VISUAL REDESIGN DIRECTIVE: STUDIO-GRADE POLISH]

1. BANISH CLIPART: All 2D vector assets and characters must be replaced with high-end, modern vector geometry. Use rich multi-stop SVG gradients, subtle inner shadows, and clean geometric proportions (resembling high-end motion design studios like Buck or Kurzgesagt).
2. CINEMATIC 3D/ISOMETRIC DEPTH: Stop using flat background grids. Every scene must utilize Three.js / React Three Fiber to build rich isometric environments featuring dynamic point lights, soft shadows, rim lighting, and atmospheric depth of field.
3. GLASSMORPHIC UI & HUD PANELS: All data cards, text boxes, and UI containers must feature advanced glassmorphism: `backdrop-blur-md`, semi-transparent frosted glass backgrounds (`rgba(255,255,255,0.03)`), ultra-thin 1px glowing borders (`rgba(255,255,255,0.1)`), and multi-layered drop shadows.
4. TYPOGRAPHIC HIERARCHY: Body text and titles must use premium font pairings (e.g., Inter / JetBrains Mono) with precise letter-spacing (`tracking-tight`, `tracking-widest`), smooth gradient text fills, and professional kinetic pacing.

