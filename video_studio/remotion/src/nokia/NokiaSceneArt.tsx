import React from 'react';
import { interpolate } from 'remotion';
import { NokiaIndustrialSet } from './NokiaIndustrialSet';
import type { NokiaSceneId } from './storyboard';

const opacityFor = (frame: number, sceneId: NokiaSceneId) => {
  const [start, end] = sceneId === 'mill' ? [0, 240] : sceneId === 'pivot' ? [240, 540] : [540, 900];
  const fade = 16;
  const enter = interpolate(frame, [start - fade, start + fade], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const leave = sceneId === 'world' ? 1 : interpolate(frame, [end - fade, end + fade], [1, 0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  return enter * leave;
};

const Grid: React.FC<{ sceneId: NokiaSceneId }> = ({ sceneId }) => (
  <svg viewBox="0 0 1080 1920" preserveAspectRatio="none" width="100%" height="100%"
    style={{ position: 'absolute', inset: 0 }} aria-hidden="true">
    <defs>
      <pattern id={`nokia-iso-grid-${sceneId}`} width="144" height="84" patternUnits="userSpaceOnUse">
        <path d="M0 42 L72 0 L144 42 L72 84 Z M-72 42 L0 0 L72 42 L0 84 Z M72 0 V84"
          fill="none" stroke="#75829a" strokeOpacity=".14" strokeWidth="1.3" />
      </pattern>
      <radialGradient id={`amber-lamp-glow-${sceneId}`}>
        <stop offset="0" stopColor="#ffcc78" stopOpacity=".54" />
        <stop offset=".34" stopColor="#df8a3c" stopOpacity=".18" />
        <stop offset="1" stopColor="#e97c32" stopOpacity="0" />
      </radialGradient>
      <linearGradient id={`screen-glow-${sceneId}`} x1="0" x2="1" y1="0" y2="1">
        <stop offset="0" stopColor="#53e3df" stopOpacity=".45" />
        <stop offset="1" stopColor="#e74c3c" stopOpacity=".22" />
      </linearGradient>
    </defs>
    <rect width="1080" height="1920" fill={`url(#nokia-iso-grid-${sceneId})`} />
    <path d="M0 548 H1080" stroke="#8590a5" strokeOpacity=".20" />
    <path d="M0 1390 H1080" stroke="#8590a5" strokeOpacity=".14" />
  </svg>
);

const BaseBackdrop: React.FC<{ frame: number; sceneId: NokiaSceneId; children?: React.ReactNode }> = ({ frame, sceneId, children }) => (
  <div style={{ position: 'absolute', inset: 0, opacity: opacityFor(frame, sceneId), overflow: 'hidden' }}>
    <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(160deg,#101827 0%,#0b0f19 48%,#080c14 100%)' }} />
    <Grid sceneId={sceneId} />
    {children}
  </div>
);

const Blueprint: React.FC = () => (
  <svg viewBox="0 0 500 390" width="100%" height="100%" aria-hidden="true">
    <defs>
      <linearGradient id="blueprint-fill" x1="0" y1="0" x2="1" y2="1">
        <stop stopColor="#172738" /> <stop offset="1" stopColor="#0b1421" />
      </linearGradient>
    </defs>
    <rect width="500" height="390" rx="18" fill="url(#blueprint-fill)" stroke="#c98d4e" strokeOpacity=".75" strokeWidth="2" />
    <path d="M0 65 H500 M0 130 H500 M0 195 H500 M0 260 H500 M0 325 H500 M62 0 V390 M124 0 V390 M186 0 V390 M248 0 V390 M310 0 V390 M372 0 V390 M434 0 V390"
      stroke="#88b8cd" strokeOpacity=".11" strokeWidth="1" />
    <path d="M69 283 L69 160 L151 160 L151 111 L265 111 L265 157 L349 157 L349 260 L423 260 L423 312 L300 312 L300 226 L214 226 L214 283Z"
      fill="none" stroke="#e8b36a" strokeWidth="5" strokeLinejoin="round" />
    <path d="M84 175 H135 M169 126 H244 M282 173 H325 M365 276 H406 M83 268 H191" stroke="#65d5d4" strokeWidth="3" strokeLinecap="round" />
    <circle cx="69" cy="160" r="7" fill="#e74c3c" />
    <circle cx="265" cy="157" r="7" fill="#e74c3c" />
    <circle cx="349" cy="260" r="7" fill="#e74c3c" />
    <path d="M25 24 H42 M25 24 V41 M475 24 H458 M475 24 V41 M25 366 H42 M25 366 V349 M475 366 H458 M475 366 V349"
      fill="none" stroke="#f1cf99" strokeWidth="2" opacity=".75" />
  </svg>
);

const Lamp: React.FC<{ frame: number }> = ({ frame }) => {
  const pulse = 0.92 + 0.08 * Math.sin(frame / 18);
  return (
    <svg viewBox="0 0 1080 1920" preserveAspectRatio="none" width="100%" height="100%"
      style={{ position: 'absolute', inset: 0 }} aria-hidden="true">
      <ellipse cx="850" cy="540" rx="400" ry="520" fill="url(#amber-lamp-glow-mill)" opacity={pulse} />
      <path d="M931 0 V144 Q931 171 906 186 L859 215" fill="none" stroke="#637184" strokeWidth="13" />
      <path d="M837 210 Q865 188 895 203 L936 275 L810 275Z" fill="#3a4351" stroke="#e0a65d" strokeWidth="3" />
      <path d="M815 268 H930 L904 302 H839Z" fill="#f3c46f" opacity={pulse} />
      <path d="M824 305 L710 527 M918 305 L1010 527" stroke="#dc9c4c" strokeOpacity=".13" strokeWidth="4" />
    </svg>
  );
};

const IndustrialStage: React.FC<{ frame: number }> = ({ frame }) => {
  const flow = 0.58 + 0.35 * ((Math.sin(frame / 12) + 1) / 2);
  const rise = interpolate(frame, [240, 300, 480], [80, 0, -38], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  return (
    <svg viewBox="0 0 1080 1920" preserveAspectRatio="none" width="100%" height="100%"
      style={{ position: 'absolute', inset: 0 }} aria-hidden="true">
      <defs><linearGradient id="rise-chart" x1="0" y1="1" x2="0" y2="0"><stop stopColor="#e74c3c" stopOpacity="0"/><stop offset="1" stopColor="#f4bd69" stopOpacity=".48"/></linearGradient></defs>
      <path d="M64 1215 L225 1134 L360 1095 L485 990 L620 955 L760 809 L955 758 L955 1240 L64 1240Z" fill="url(#rise-chart)" opacity=".72" transform={`translate(0 ${rise})`} />
      <path d="M64 1215 L225 1134 L360 1095 L485 990 L620 955 L760 809 L955 758" fill="none" stroke="#e74c3c" strokeWidth="8" strokeLinecap="round" strokeLinejoin="round" opacity={flow} transform={`translate(0 ${rise})`} />
      <path d="M82 1280 H986" stroke="#c6a477" strokeOpacity=".38" strokeWidth="2" />
      <path d="M119 1018 C302 933 384 938 498 860 S730 782 880 688" fill="none" stroke="#4fd7d6" strokeWidth="5" strokeDasharray="12 17" opacity={flow} />
      <path d="M135 1068 C320 987 405 994 514 916 S749 836 898 742" fill="none" stroke="#e74c3c" strokeWidth="4" strokeDasharray="6 22" opacity={1 - flow * .5} />
      {[0,1,2,3].map((i) => <circle key={i} cx={140 + i * 224} cy={1048 - i * 112 + rise * (0.7 - i * .13)} r="10" fill={i % 2 ? '#e74c3c' : '#68eeee'} />)}
    </svg>
  );
};

const MobileInterface: React.FC<{ frame: number }> = ({ frame }) => {
  const zoom = interpolate(frame, [540, 900], [1, 1.15], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const pulse = 0.58 + 0.32 * ((Math.sin(frame / 11) + 1) / 2);
  return (
    <svg viewBox="0 0 1080 1920" preserveAspectRatio="none" width="100%" height="100%"
      style={{ position: 'absolute', inset: 0 }} aria-hidden="true">
      <path d="M540 480 V1390" stroke="#d9a362" strokeOpacity=".35" strokeWidth="2" strokeDasharray="8 14" />
      <g transform={`translate(${(1 - zoom) * 260} ${(1 - zoom) * 250}) scale(${zoom})`}>
        <ellipse cx="320" cy="1010" rx="310" ry="430" fill="url(#screen-glow-world)" opacity=".45" />
        <rect x="105" y="538" width="414" height="816" rx="55" fill="#080d15" stroke="#8896a8" strokeWidth="9" />
        <rect x="124" y="576" width="376" height="735" rx="35" fill="#0e1a28" stroke="#33475b" strokeWidth="3" />
        <rect x="258" y="554" width="110" height="11" rx="5" fill="#657487" />
        <circle cx="454" cy="560" r="6" fill="#e74c3c" />
        <path d="M161 653 H463" stroke="#d9a362" strokeOpacity=".58" strokeWidth="3" />
        <circle cx="312" cy="849" r="123" fill="#112436" stroke="#61ded8" strokeWidth="3" strokeOpacity=".72" />
        <circle cx="312" cy="849" r="84" fill="none" stroke="#e74c3c" strokeOpacity={pulse} strokeWidth="4" />
        <path d="M250 849 H374 M312 787 V911" stroke="#9bb4c3" strokeOpacity=".55" strokeWidth="2" />
        <circle cx="312" cy="849" r="13" fill="#e74c3c" />
        <g fill="#f0c078">
          <circle cx="257" cy="808" r="6"/><circle cx="370" cy="822" r="6"/><circle cx="273" cy="892" r="6"/><circle cx="357" cy="900" r="6"/>
        </g>
        <path d="M174 1038 H445 M174 1074 H416 M174 1110 H430" stroke="#5b778b" strokeWidth="8" strokeLinecap="round" />
        <path d="M174 1170 H445" stroke="#e74c3c" strokeWidth="5" strokeLinecap="round" />
      </g>
      <g fill="none" stroke="#e5aa5c" strokeOpacity={pulse}>
        <circle cx="545" cy="758" r="34" strokeWidth="3"/><circle cx="545" cy="758" r="62" strokeWidth="2" opacity=".55"/><circle cx="545" cy="758" r="91" strokeWidth="1.5" opacity=".35"/>
      </g>
    </svg>
  );
};

export const NokiaSceneArt: React.FC<{ frame: number }> = ({ frame }) => (
  <>
    <BaseBackdrop frame={frame} sceneId="mill">
      <Lamp frame={frame} />
      <div style={{ position: 'absolute', left: 54, top: 688, width: 470, height: 365,
        filter: 'drop-shadow(0 22px 34px rgba(0,0,0,.38))' }}><Blueprint /></div>
    </BaseBackdrop>
    <BaseBackdrop frame={frame} sceneId="pivot">
      <NokiaIndustrialSet frame={frame} />
      <IndustrialStage frame={frame} />
    </BaseBackdrop>
    <BaseBackdrop frame={frame} sceneId="world">
      <MobileInterface frame={frame} />
      <div style={{ position: 'absolute', right: 58, top: 552, width: 3, height: 830,
        background: 'linear-gradient(transparent,rgba(222,166,91,.42),transparent)' }} />
      <div style={{ position: 'absolute', left: 86, top: 1382, width: 908, height: 2,
        background: 'linear-gradient(90deg,transparent,rgba(218,161,87,.55),transparent)' }} />
    </BaseBackdrop>
  </>
);
