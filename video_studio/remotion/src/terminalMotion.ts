import { frameAtBeat } from './timing';

/** Type the six rows, then keep revising one row every two beats. */
export const terminalLineState = (frame: number, index: number, fps: number) => {
  const initialStart = Math.round(fps * (14 + index * 19) / 30);
  const typeDuration = Math.max(1, Math.round(fps * .6));
  const initial = Math.max(0, Math.min(1, (frame - initialStart + 1) / typeDuration));
  const editingStart = frameAtBeat(9, fps);
  if (frame < editingStart) return { progress: initial, active: false };
  const cycleFrames = frameAtBeat(2, fps);
  const elapsed = frame - editingStart;
  const row = Math.floor(elapsed / cycleFrames) % 6;
  if (index !== row) return { progress: 1, active: false };
  const typed = Math.min(1, (elapsed % cycleFrames + 1) / Math.max(1, Math.round(cycleFrames * .7)));
  return { progress: .25 + .75 * typed, active: true };
};
