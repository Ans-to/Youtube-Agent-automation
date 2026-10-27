import React, { useEffect, useState } from 'react';
import {
  AbsoluteFill,
  Audio,
  cancelRender,
  continueRender,
  delayRender,
  Easing,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import { IsometricWorkspace } from './IsometricWorkspace';
import { focusState, frameAtBeat, PALETTE, WORDS, wordState } from './timing';

export type StopCodingBlindProps = {
  /** A 120 BPM track with beat 0 at time 0. Null disables audio. */
  audioSrc?: string | null;
};

/** Wait for the bundled house font instead of rendering with a system fallback. */
const useHouseFont = () => {
  const [handle] = useState(() => delayRender('Loading the bundled Space Grotesk font'));
  useEffect(() => {
    let active = true;
    const face = new FontFace(
      'Space Grotesk',
      `url("${staticFile('fonts/space-grotesk-latin-700-normal.woff2')}")`,
      { weight: '700', style: 'normal' },
    );
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

/**
 * 10-second portrait motion graphic. Word entrances use the same 120 BPM clock
 * as the bundled, zero-offset instrumental. No image or photograph is used.
 */
export const StopCodingBlind: React.FC<StopCodingBlindProps> = ({ audioSrc }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  useHouseFont();

  const source = audioSrc === undefined ? staticFile('audio/stop-coding-blind-120bpm.wav') : audioSrc;
  const focus = focusState(frame, fps);
  const rule = interpolate(frame, [frameAtBeat(4, fps), frameAtBeat(4, fps) + Math.round(fps * .3)], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.quad),
  });

  return (
    <AbsoluteFill style={{ backgroundColor: PALETTE.background, overflow: 'hidden' }}>
      {source && <Audio src={source} />}
      <AbsoluteFill
        style={{
          background: 'radial-gradient(ellipse 75% 50% at 56% 73%, #241419 0%, #101014 53%, #0b0b0f 100%)',
        }}
      />

      {/* Portrait-safe title: each word has its own mask and fixed line box. */}
      <div
        aria-label="Stop coding blind."
        style={{ position: 'absolute', left: 88, top: 166, width: 900, fontFamily: 'Space Grotesk, sans-serif',
          fontSize: 198, fontWeight: 700, letterSpacing: '-0.045em', lineHeight: 1.02,
          transform: `translateY(${-30 * focus.title}px) scale(${1 - .25 * focus.title})`,
          transformOrigin: 'left top' }}
      >
        {WORDS.map((word) => {
          const state = wordState(frame, word.beat, fps);
          return (
            <div key={word.text} style={{ height: 205, overflow: 'hidden', whiteSpace: 'nowrap' }}>
              <div
                style={{ color: word.accent ? PALETTE.accent : PALETTE.foreground, opacity: state.opacity,
                  transform: `translate3d(0, ${(1 - state.progress) * 48}px, 0) scale(${.96 + .04 * state.progress})`,
                  transformOrigin: 'left bottom' }}
              >
                {word.text}
              </div>
            </div>
          );
        })}
        <div style={{ marginTop: 12, height: 8, width: 620, backgroundColor: PALETTE.accent,
          transform: `scaleX(${rule})`, transformOrigin: 'left center' }} />
      </div>

      {/* Drawn 3D-like desk, terminal, keyboard and floor; no camera shake. */}
      <div style={{ position: 'absolute', left: 0, top: 934, width: 1080, height: 864,
        transform: `translateY(${-58 * focus.terminal}px) scale(${1 + .10 * focus.terminal})`,
        transformOrigin: '50% 50%' }}>
        <IsometricWorkspace frame={frame} fps={fps} />
      </div>
    </AbsoluteFill>
  );
};
