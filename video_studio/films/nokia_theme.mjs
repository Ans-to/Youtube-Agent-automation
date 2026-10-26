/**
 * The film's two inks.
 *
 * This started as one palette - cream paper, navy ink - applied to every shot,
 * which is why eight shots in a row looked like the same poster. A documentary
 * needs a tonal rhythm: dark where the film is intimate or cold, paper where it
 * is factual. So there are two palettes now, and a shot picks one.
 *
 * PALETTE is the live object every shot reads while it draws. Swapping a shot's
 * palette is one Object.assign in the stage hook, which means none of the forty
 * or so places that paint with PALETTE.text had to change.
 */
import { setShotPrepare } from '../motion/kit/stage.mjs';

export const PAPER = {
  text: '#16283C',
  caption: '#A85F12',   // amber, dark enough to hold 4.5:1 on cream
  dim: '#5C6472',
  land: '#16283C',
  landEdge: '#0B1420',
  paper: '#F1E7D4',
};

export const INK = {
  text: '#F1E7D4',
  caption: '#E8A64E',   // the same amber, lit for a dark ground
  dim: '#8C97A6',
  land: '#F1E7D4',
  landEdge: '#0B1420',
  paper: '#0C1622',
};

export const PALETTE = { ...PAPER };

/** Point the live palette at whatever ink this shot is printed in. */
export function applyShotPalette(shot) {
  if (!shot || !shot.palette) return;
  Object.assign(PALETTE, shot.palette);
  // Shots were authored as `background: PALETTE.paper`, which is read once when
  // the module loads - so a shot that switched to ink still painted cream behind
  // itself. The background follows the palette now.
  shot.background = shot.palette.paper;
}

// Registered here, at import time, so a caller cannot forget it. The stage calls
// this before every shot draws, which is the moment the ink changes.
setShotPrepare(applyShotPalette);

export default PALETTE;
