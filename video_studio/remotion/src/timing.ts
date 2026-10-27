// One clock for both the score and the typography. The supplied audio starts
// on beat zero; at 120 BPM each beat is 0.5 s (15 frames at 30 fps).
export const BPM = 120;
export const FPS = 30;
export const DURATION_SECONDS = 10;
export const DURATION_FRAMES = DURATION_SECONDS * FPS;
export const WIDTH = 1080;
export const HEIGHT = 1920;
export const PALETTE = { background: '#0b0b0f', foreground: '#f4f2ec', accent: '#ff4b55' } as const;

export const WORDS = [
  { text: 'Stop', beat: 1, accent: false },
  { text: 'coding', beat: 2, accent: false },
  { text: 'blind.', beat: 3, accent: true },
] as const;

export const frameAtBeat = (beat: number, fps = FPS): number =>
  Math.round((beat * 60 * fps) / BPM);

const ease = (t: number) => {
  const n = Math.max(0, Math.min(1, t));
  return n * n * (3 - 2 * n);
};

/** Give the terminal a turn as the focal point, then restore the full claim. */
export const focusState = (frame: number, fps = FPS) => {
  const beat = frame * BPM / (fps * 60);
  const title = beat < 11 ? ease((beat - 5) / 6) : 1 - ease((beat - 11) / 8);
  const terminal = beat < 12 ? ease((beat - 8) / 4) : 1 - ease((beat - 12) / 6);
  return { title, terminal };
};

/** A masked, one-direction reveal that begins on its beat and settles in 0.2 s. */
export const wordState = (frame: number, beat: number, fps = FPS) => {
  const start = frameAtBeat(beat, fps);
  if (frame < start) return { opacity: 0, progress: 0 };
  const duration = Math.max(1, Math.round(fps * 0.2));
  const t = Math.min(1, (frame - start + 1) / duration);
  const progress = 1 - Math.pow(1 - t, 4);
  return { opacity: Math.min(1, t * 3), progress };
};
