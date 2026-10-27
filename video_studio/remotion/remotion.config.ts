import { Config } from '@remotion/cli/config';

// Three.js needs a WebGL-capable Chromium renderer. Use `--gl=swangle` on
// GPU-less machines if ANGLE cannot access hardware acceleration.
Config.setChromiumOpenGlRenderer('angle');
