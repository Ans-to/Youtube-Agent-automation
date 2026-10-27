import { spring } from 'remotion';
import { GLITCH_BEATS, WORDS } from './storyboard';

export { GLITCH_BEATS, WORDS } from './storyboard';
export const BPM = 120;
export const FPS = 30;
export const DURATION_SECONDS = 10;
export const DURATION_FRAMES = DURATION_SECONDS * FPS;
export const WIDTH = 1080;
export const HEIGHT = 1920;
export const PALETTE = {
  background: '#08090f', foreground: '#f8f7f2', red: '#ff3f55', cyan: '#44edec',
} as const;

export const frameAtBeat = (beat: number, fps = FPS): number =>
  Math.round((beat * 60 * fps) / BPM);

/** A word first appears on its own beat, even on the first spring frame. */
export const wordIsVisible = (frame: number, beat: number, fps = FPS): boolean =>
  frame >= frameAtBeat(beat, fps);

/** A real spring with a visible first frame and an overshoot on impact. */
export const wordImpact = (frame: number, beat: number, fps = FPS): number => {
  if (!wordIsVisible(frame, beat, fps)) return 0;
  return spring({ frame: frame - frameAtBeat(beat, fps) + 1, fps,
    config: { damping: 10, stiffness: 220, mass: .8 } });
};

/** Deterministic, short RGB/pixel burst on word impacts and two-beat accents. */
export const glitchState = (frame: number, fps = FPS) => {
  for (const beat of GLITCH_BEATS) {
    const elapsed = frame - frameAtBeat(beat, fps);
    if (elapsed >= 0 && elapsed < Math.max(2, Math.round(fps * 0.10))) {
      return { active: true, beat, elapsed };
    }
  }
  return { active: false, beat: -1, elapsed: -1 };
};

export const cueFrames = (fps = FPS) => WORDS.map((word) => frameAtBeat(word.beat, fps));
