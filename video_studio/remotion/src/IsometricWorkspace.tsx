import React from 'react';
import { BPM } from './timing';

const clamp01 = (value: number) => Math.max(0, Math.min(1, value));
const easeOut = (value: number) => 1 - Math.pow(1 - clamp01(value), 3);

/** All geometry is vector-drawn. There are no raster images or still backplates. */
export const IsometricWorkspace: React.FC<{ frame: number; fps: number }> = ({ frame, fps }) => {
  const framesPerBeat = fps * 60 / BPM;
  const beatPhase = ((frame % framesPerBeat) + framesPerBeat) % framesPerBeat / framesPerBeat;
  const beatGlow = Math.pow(1 - beatPhase, 4);
  const lineSpacing = Math.round(fps * 1.4);
  const lineDuration = Math.round(fps * 1.15);
  const code = [
    { indent: 0, width: 135, accent: false },
    { indent: 18, width: 169, accent: true },
    { indent: 18, width: 119, accent: false },
    { indent: 18, width: 179, accent: false },
    { indent: 0, width: 112, accent: true },
    { indent: 0, width: 145, accent: false },
  ];
  const current = Math.min(code.length - 1, Math.floor(frame / lineSpacing));
  const cursorProgress = easeOut((frame - current * lineSpacing) / lineDuration);
  const cursorX = 35 + code[current].indent + code[current].width * cursorProgress + 6;
  const cursorOpacity = beatPhase < .60 ? .95 : .25;
  // A slow, eased inspection pass keeps the terminal active without moving the
  // camera, jittering the layout or implying that code has been executed.
  const scanProgress = (1 - Math.cos(2 * Math.PI * frame / (fps * 6))) / 2;
  const scanY = 28 + 145 * scanProgress;

  const keys = [];
  for (let row = 0; row < 4; row++) {
    for (let column = 0; column < 9; column++) {
      const x = 455 + column * 19.5 - row * 18;
      const y = 441 + column * 9.1 + row * 9.6;
      keys.push(
        <path
          key={`${row}-${column}`}
          d={`M ${x} ${y} l 15 7 -13 7 -15 -7 z`}
          fill={row === 3 && column > 2 && column < 7 ? '#5b3338' : '#414149'}
          stroke="#77717a"
          strokeWidth=".7"
        />,
      );
    }
  }

  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 1000 800"
      width="100%"
      height="100%"
      style={{ overflow: 'visible' }}
    >
      <defs>
        <radialGradient id="workspace-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#ff3347" stopOpacity=".42" />
          <stop offset="52%" stopColor="#a7192a" stopOpacity=".12" />
          <stop offset="100%" stopColor="#a7192a" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="desk-top" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#29262b" />
          <stop offset="100%" stopColor="#121216" />
        </linearGradient>
        <linearGradient id="screen-face" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#28191f" />
          <stop offset="100%" stopColor="#0b1015" />
        </linearGradient>
        <clipPath id="screen-mask">
          <rect x="0" y="0" width="300" height="190" />
        </clipPath>
      </defs>

      {/* A low-contrast floor grid supplies depth; the camera stays locked. */}
      <ellipse cx="515" cy="479" rx="430" ry="260" fill="url(#workspace-glow)" opacity={.48 + .16 * beatGlow} />
      <g fill="none" stroke="#3c2830" strokeWidth="1.1" opacity=".42">
        <path d="M 40 587 L 504 354 L 968 586" />
        <path d="M 35 653 L 504 418 L 971 652" />
        <path d="M 70 721 L 504 503 L 938 720" />
        <path d="M 115 772 L 504 577 L 893 772" />
        <path d="M 116 620 L 500 813" />
        <path d="M 234 559 L 687 785" />
        <path d="M 358 495 L 815 723" />
        <path d="M 887 620 L 503 813" />
        <path d="M 769 559 L 316 785" />
        <path d="M 645 495 L 188 723" />
      </g>

      {/* Desk: top and exposed sides are separate isometric planes. */}
      <path d="M 84 489 L 476 688 L 476 734 L 84 534 Z" fill="#151418" stroke="#4a3035" strokeWidth="2" />
      <path d="M 476 688 L 900 470 L 900 517 L 476 734 Z" fill="#21191e" stroke="#4a3035" strokeWidth="2" />
      <path d="M 84 489 L 510 274 L 900 470 L 476 688 Z" fill="url(#desk-top)" stroke="#615055" strokeWidth="2.5" />
      <path d="M 102 489 L 510 284 L 881 470" fill="none" stroke="#9b6269" strokeOpacity=".34" strokeWidth="2" />
      <path d="M 476 688 L 900 470" fill="none" stroke="#ff4352" strokeOpacity=".55" strokeWidth="3" />

      {/* Stand and keyboard occupy the desk before the screen is drawn. */}
      <path d="M 409 378 L 455 398 L 455 492 L 409 472 Z" fill="#373139" stroke="#67525a" strokeWidth="2" />
      <path d="M 382 479 L 455 516 L 513 487 L 440 451 Z" fill="#302a30" stroke="#7c5b60" strokeWidth="2" />
      <path d="M 253 522 L 474 410 L 693 518 L 475 632 Z" fill="#15161a" stroke="#66575e" strokeWidth="2" />
      <path d="M 253 522 L 475 632 L 475 642 L 253 531 Z" fill="#0c0d10" />
      <g>{keys}</g>
      <path d="M 330 554 L 365 537 L 463 586 L 428 604 Z" fill="#2a272d" stroke="#5c5057" strokeWidth="1.4" />

      {/* Monitor bezel: three faces make the glowing terminal a solid object. */}
      <path d="M 257 98 L 276 87 L 617 239 L 598 250 Z" fill="#69505a" />
      <path d="M 598 250 L 617 239 L 617 477 L 598 488 Z" fill="#342b33" />
      <path d="M 257 98 L 598 250 L 598 488 L 257 336 Z" fill="#0d0d11" stroke="#8b646a" strokeWidth="3" />
      <path d="M 275 123 L 581 260 L 581 458 L 275 321 Z" fill="#141015" stroke="#ff4a55" strokeOpacity={.62 + .2 * beatGlow} strokeWidth="2.5" />

      {/* Code strokes type in order; the cursor and rim light follow the beat. */}
      <g transform="matrix(1 .4477 0 1 279 124)" clipPath="url(#screen-mask)">
        <rect width="300" height="190" fill="url(#screen-face)" />
        <rect x="0" y="0" width="300" height="22" fill="#33262b" />
        <circle cx="12" cy="11" r="3" fill="#ff5961" />
        <circle cx="23" cy="11" r="3" fill="#996b69" />
        <circle cx="34" cy="11" r="3" fill="#72595d" />
        {code.map((item, index) => {
          const progress = easeOut((frame - index * lineSpacing) / lineDuration);
          return (
            <g key={index}>
              <rect x={20 + item.indent} y={36 + index * 23} width="8" height="4" rx="2" fill="#a66c72" opacity={progress > 0 ? .65 : 0} />
              <rect x={35 + item.indent} y={36 + index * 23} width={item.width * progress} height="4" rx="2" fill={item.accent ? '#ff6570' : '#d8d5d0'} opacity=".9" />
            </g>
          );
        })}
        <rect x={cursorX} y={32 + current * 23} width="5" height="11" rx="1" fill="#ff616a" opacity={cursorOpacity} />
        <rect x="0" y={scanY} width="300" height="4" fill="#ff4b55" opacity=".18" />
      </g>
      <path d="M 275 123 L 581 260 L 581 458 L 275 321 Z" fill="none" stroke="#ff5965" strokeOpacity={.34 + .28 * beatGlow} strokeWidth="4" />

      {/* A quiet desk lamp of red light grounds the monitor without a photo. */}
      <ellipse cx="510" cy="531" rx="157" ry="49" fill="url(#workspace-glow)" opacity=".28" />
    </svg>
  );
};
