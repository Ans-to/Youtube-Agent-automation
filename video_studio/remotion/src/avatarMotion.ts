import { BPM } from './timing';

/** Frame- and beat-derived vector-character motion, so scrubbing and renders agree. */
export const avatarMotion = (frame: number, fps: number) => {
  const beat = frame * BPM / (fps * 60);
  return {
    beat,
    bob: Math.sin(beat * Math.PI * 2) * .025,
    typing: Math.sin(beat * Math.PI * 4),
    blink: Math.floor(frame) % Math.round(fps * 3.6) < 3,
  };
};
