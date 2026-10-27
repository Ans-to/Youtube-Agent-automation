import React, { useEffect, useState } from 'react';
import { ThreeCanvas } from '@remotion/three';
import {
  AbsoluteFill, Audio, cancelRender, continueRender, delayRender, interpolate,
  staticFile, useCurrentFrame, useVideoConfig,
} from 'remotion';
import { GlitchOverlay } from './GlitchOverlay';
import { VoxelWorkspace } from './VoxelWorkspace';
import { frameAtBeat, glitchState, PALETTE, WIDTH, WORDS, wordImpact, wordIsVisible } from './timing';

export type StopCodingBlindProps = {
  /** A 120 BPM track with beat 0 at time 0. Null disables audio. */
  audioSrc?: string | null;
};

/** Wait for the locally bundled font before capturing a frame. */
const useHouseFont = () => {
  const [handle] = useState(() => delayRender('Loading Space Grotesk'));
  useEffect(() => {
    let active = true;
    const face = new FontFace('Space Grotesk',
      `url("${staticFile('fonts/space-grotesk-latin-700-normal.woff2')}")`,
      { weight: '700', style: 'normal' });
    face.load().then((loaded) => {
      if (!active) return;
      document.fonts.add(loaded);
      continueRender(handle);
    }).catch((error: unknown) => {
      if (active) cancelRender(error instanceof Error ? error : new Error(String(error)));
    });
    return () => { active = false; continueRender(handle); };
  }, [handle]);
};

/** 10-second portrait composition driven by the repository's Skill.md. */
export const StopCodingBlind: React.FC<StopCodingBlindProps> = ({ audioSrc }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  useHouseFont();
  const source = audioSrc === undefined ? staticFile('audio/stop-coding-blind-120bpm.wav') : audioSrc;
  const glitch = glitchState(frame, fps);
  const rule = interpolate(frame, [frameAtBeat(4, fps), frameAtBeat(4, fps) + 9], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill style={{ backgroundColor: PALETTE.background, overflow: 'hidden' }}>
      {source && <Audio src={source} />}
      <AbsoluteFill style={{
        background: 'radial-gradient(ellipse 70% 46% at 50% 68%, #211a28 0%, #0c1119 58%, #08090f 100%)',
      }} />

      {/* Frame-synchronized 3D workspace and camera-facing SVG character. */}
      <div style={{ position: 'absolute', top: 590, left: 0, width: WIDTH, height: 1280 }}>
        <ThreeCanvas width={WIDTH} height={1280} orthographic
          camera={{ position: [-8, 8, 9], zoom: 135, near: .1, far: 100 }}
          gl={{ antialias: false, alpha: true }}>
          <VoxelWorkspace frame={frame} fps={fps} />
        </ThreeCanvas>
      </div>

      {/* Each word snaps on a beat with spring overshoot and an RGB impact split. */}
      <div aria-label="Stop coding blind." style={{ position: 'absolute', left: 88, top: 122,
        width: WIDTH - 160, fontFamily: 'Space Grotesk, sans-serif', fontSize: 198,
        fontWeight: 700, letterSpacing: '-.045em', lineHeight: 1.02 }}>
        {WORDS.map((word) => {
          const visible = wordIsVisible(frame, word.beat, fps);
          const impact = wordImpact(frame, word.beat, fps);
          const split = glitch.active ? (glitch.elapsed % 2 ? -1 : 1) : 0;
          return <div key={word.text} style={{ height: 205, whiteSpace: 'nowrap', visibility: visible ? 'visible' : 'hidden' }}>
            <div style={{ color: word.accent ? PALETTE.red : PALETTE.foreground,
              transform: `translateY(${(1 - impact) * 48}px) scale(${.60 + .40 * impact})`,
              transformOrigin: 'left center',
              textShadow: split ? `${split * 10}px 0 ${PALETTE.cyan}, ${-split * 9}px 0 ${PALETTE.red}` : 'none' }}>
              {word.text}
            </div>
          </div>;
        })}
        <div style={{ marginTop: 10, width: 620, height: 8, backgroundColor: PALETTE.red,
          transform: `scaleX(${rule})`, transformOrigin: 'left center' }} />
      </div>

      <GlitchOverlay frame={frame} fps={fps} />
    </AbsoluteFill>
  );
};
