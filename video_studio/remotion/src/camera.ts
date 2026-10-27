import { interpolate } from 'remotion';
import { BPM, DURATION_SECONDS } from './timing';

export type CameraPose = {
  position: [number, number, number];
  target: [number, number, number];
  zoom: number;
};

/**
 * Frame-derived orthographic camera move: a continuous push/orbit with a very
 * small beat-synchronous ease. No real-time clocks or random motion are used.
 */
export const cameraPose = (frame: number, fps: number): CameraPose => {
  const p = interpolate(frame, [0, DURATION_SECONDS * fps], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const beat = frame * BPM / (fps * 60);
  const angle = interpolate(p, [0, 1], [-0.72, -0.55]) + 0.009 * Math.sin(beat * Math.PI * 2);
  const radius = interpolate(p, [0, 1], [12.5, 11.2]);
  return {
    position: [radius * Math.sin(angle), 7.6 - p * .30, radius * Math.cos(angle)],
    target: [0, 1.27 + p * .08, -.15],
    zoom: interpolate(p, [0, 1], [135, 150]) + 0.9 * Math.sin(beat * Math.PI * 2),
  };
};
