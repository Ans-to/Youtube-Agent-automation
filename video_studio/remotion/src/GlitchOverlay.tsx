import React from 'react';
import { AbsoluteFill } from 'remotion';
import { glitchState } from './timing';

/** Pixel-block and RGB accent bursts on word hits / two-beat accents. */
export const GlitchOverlay: React.FC<{ frame: number; fps: number }> = ({ frame, fps }) => {
  const glitch = glitchState(frame, fps);
  return (
    <AbsoluteFill style={{ pointerEvents: 'none', overflow: 'hidden' }}>
      {/* Constant, very light CRT scanlines: the 3D action remains readable. */}
      <AbsoluteFill style={{ opacity: .23,
        background: 'repeating-linear-gradient(to bottom, transparent 0px, transparent 5px, rgba(0,0,0,.30) 6px, transparent 7px)' }} />
      {glitch.active && Array.from({ length: 9 }, (_, index) => {
        // All positions are deterministic integer pixels, not Math.random().
        const seed = glitch.beat * 83 + index * 67 + glitch.elapsed * 31;
        const x = 28 + (seed * 73 % 940);
        const y = 115 + (seed * 113 % 1530);
        const width = 18 + (seed % 5) * 16;
        return <div key={index} style={{ position: 'absolute', left: x, top: y, width, height: 4 + (seed % 3) * 3,
          backgroundColor: index % 2 ? '#55f6f0' : '#ff405a', opacity: .48, mixBlendMode: 'screen' }} />;
      })}
    </AbsoluteFill>
  );
};
