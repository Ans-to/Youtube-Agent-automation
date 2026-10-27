import React from 'react';
import { spring } from 'remotion';
import type { NokiaSceneId } from './storyboard';

export type ArchivistPose = 'inspect' | 'point' | 'present';

export const NokiaArchivist: React.FC<{
  frame: number;
  fps: number;
  sceneId: NokiaSceneId;
  pose: ArchivistPose;
}> = ({ frame, fps, sceneId, pose }) => {
  const sceneStart = sceneId === 'mill' ? 0 : sceneId === 'pivot' ? 8 * fps : 18 * fps;
  const appear = spring({ frame: Math.max(0, frame - sceneStart + 1), fps,
    config: { damping: 14, stiffness: 100, mass: 0.9 } });
  const bob = Math.sin((frame - sceneStart) / (fps * 0.7)) * 5;

  const leftArm = pose === 'point'
    ? 'M116 265 C87 276 69 305 47 337 L16 352 Q7 357 15 366 L43 371 Q57 371 66 360 L133 319Z'
    : pose === 'present'
      ? 'M116 265 C88 276 76 304 61 335 L39 351 Q31 359 42 365 L68 362 Q82 358 88 346 L141 309Z'
      : 'M116 265 C91 274 74 302 58 327 L42 344 Q35 352 46 359 L72 355 Q83 350 89 339 L141 309Z';
  const rightArm = pose === 'point'
    ? 'M244 265 C273 276 293 302 313 321 L338 322 Q350 322 349 334 L342 355 Q337 364 325 358 L292 347 L228 313Z'
    : pose === 'present'
      ? 'M244 265 C274 274 290 298 305 327 L329 344 Q340 352 330 361 L304 358 Q291 356 283 344 L220 310Z'
      : 'M244 265 C272 276 286 301 300 328 L317 345 Q324 353 313 360 L289 355 Q278 350 271 339 L219 309Z';

  return (
    <div style={{ position: 'absolute', left: 640, top: 570, width: 410, height: 850,
      opacity: appear, transform: `translateY(${(1 - appear) * 36 + bob}px) scale(${0.92 + 0.08 * appear})`,
      transformOrigin: 'bottom center', pointerEvents: 'none' }}>
      <svg width="100%" height="100%" viewBox="0 0 360 700" role="img"
        aria-label="A vector archivist in a fedora and trench coat">
        <defs>
          <linearGradient id={`coatShade-${sceneId}`} x1="0" x2="1" y1="0" y2="1">
            <stop offset="0" stopColor="#384457" />
            <stop offset="1" stopColor="#141d2b" />
          </linearGradient>
          <linearGradient id={`faceShade-${sceneId}`} x1="0" x2="1" y1="0" y2="1">
            <stop offset="0" stopColor="#edc29a" />
            <stop offset="1" stopColor="#ae775d" />
          </linearGradient>
          <radialGradient id={`archivistAccentGlow-${sceneId}`}>
            <stop offset="0" stopColor="#f6b85d" stopOpacity=".45" />
            <stop offset="1" stopColor="#f6b85d" stopOpacity="0" />
          </radialGradient>
        </defs>
        <ellipse cx="181" cy="654" rx="126" ry="23" fill="#030711" opacity=".55" />
        <ellipse cx="180" cy="393" rx="183" ry="172" fill={`url(#archivistAccentGlow-${sceneId})`} opacity=".26" />

        {/* Trench-coat silhouette and tailored front panels. */}
        <path d="M119 250 Q78 262 68 303 L41 493 Q36 531 59 559 L82 629 Q181 659 280 629 L302 559 Q324 531 319 493 L292 303 Q282 262 241 250 L216 232 L144 232Z"
          fill="#0b111b" stroke="#070b12" strokeWidth="11" strokeLinejoin="round" />
        <path d="M122 258 Q91 270 84 307 L64 491 L92 535 L113 447 L106 616 Q180 638 254 616 L247 447 L268 535 L296 491 L276 307 Q269 270 238 258 L211 245 L149 245Z"
          fill={`url(#coatShade-${sceneId})`} stroke="#667384" strokeWidth="4" strokeLinejoin="round" />
        <path d="M145 246 L180 270 L215 246 L237 315 L213 351 L180 326 L147 351 L123 315Z" fill="#e1dbcf" />
        <path d="M144 247 L180 271 L155 329 L126 292Z" fill="#647082" />
        <path d="M216 247 L180 271 L205 329 L234 292Z" fill="#465367" />
        <path d="M173 286 L180 293 L187 286 L195 317 L180 336 L165 317Z" fill="#d85b4e" />
        <path d="M180 336 L196 317 L209 559 L180 575 L151 559 L164 317Z" fill="#a73d3b" />
        <path d="M180 336 L196 317 L209 559 L180 575Z" fill="#7d3031" opacity=".8" />
        <path d="M111 421 Q180 437 249 421 L247 443 Q180 460 113 443Z" fill="#111a27" />
        <rect x="169" y="426" width="22" height="22" rx="3" fill="none" stroke="#d7ad69" strokeWidth="5" />
        <path d="M101 370 L132 375 L126 408 L96 403Z M228 375 L259 370 L264 403 L234 408Z" fill="#1d2938" stroke="#697687" strokeWidth="3" />
        <path d="M98 370 L134 375 L130 385 L97 381Z M226 375 L261 370 L262 381 L230 385Z" fill="#788494" />
        <path d="M119 292 L94 487 M240 292 L266 487" fill="none" stroke="#8190a1" strokeWidth="3" opacity=".68" />
        <circle cx="180" cy="373" r="5" fill="#d7ad69" />
        <circle cx="180" cy="399" r="5" fill="#d7ad69" />

        {/* Arms shift between inspection, pointing, and open presentation. */}
        <path d={leftArm} fill="#303d50" stroke="#111a27" strokeWidth="9" strokeLinejoin="round" />
        <path d={rightArm} fill="#303d50" stroke="#111a27" strokeWidth="9" strokeLinejoin="round" />
        <path d={pose === 'inspect' ? 'M39 340 L64 350 L54 373 L30 362Z' : 'M14 348 L43 348 L42 371 L13 371Z'} fill="#e1dbcf" />
        <path d={pose === 'point' ? 'M339 320 Q356 311 361 322 L353 332 L365 338 L360 349 L343 345Z' : 'M315 342 Q332 343 338 354 L329 366 L314 361 L303 355Z'} fill="#d5a17d" />
        <path d={pose === 'present' ? 'M34 353 L67 350' : 'M31 356 L58 364'} stroke="#f0bf91" strokeWidth="5" strokeLinecap="round" />

        {/* Head, expressive face and fedora. */}
        <path d="M139 105 Q180 82 221 105 L228 182 Q221 226 180 242 Q139 226 132 182Z" fill="#101723" />
        <path d="M137 119 Q144 98 180 96 Q216 98 223 119 L217 187 Q210 219 180 228 Q150 219 143 187Z" fill={`url(#faceShade-${sceneId})`} stroke="#885c4b" strokeWidth="3" />
        <path d="M180 100 Q214 100 221 120 L216 184 Q210 211 180 221Z" fill="#f1c79b" opacity=".47" />
        <path d="M139 143 Q128 133 125 150 Q126 170 143 173Z M221 143 Q232 133 235 150 Q234 170 217 173Z" fill="#bd8968" />
        <path d="M151 158 Q163 151 174 158 L172 164 Q162 160 152 166Z M186 158 Q197 151 209 158 L207 166 Q197 160 187 164Z" fill="#20202a" />
        <path d="M154 175 Q164 169 174 175 L173 180 Q163 178 155 182Z M187 175 Q197 169 206 175 L205 182 Q197 178 188 180Z" fill="#121a25" />
        <path d="M179 176 L173 198 Q180 203 189 197 L183 176Z" fill="#a8735a" />
        <path d="M163 207 Q180 216 197 207 Q191 224 180 223 Q169 223 163 207Z" fill="#28202a" />
        <path d="M170 230 L180 237 L190 230 L194 256 L180 269 L166 256Z" fill="#bc8968" />
        <path d="M82 111 Q113 79 158 72 Q211 66 259 97 L269 112 Q181 95 77 121Z" fill="#090e17" stroke="#05080e" strokeWidth="8" />
        <path d="M124 99 Q126 38 150 22 Q184 5 218 24 Q244 44 244 99 Q185 88 124 99Z" fill="#1b2534" stroke="#080d15" strokeWidth="8" />
        <path d="M127 84 Q184 73 242 84 L244 100 Q184 89 124 101Z" fill="#873a37" />
        <path d="M138 47 Q161 18 198 23 Q217 25 232 42 Q196 33 169 37Z" fill="#536174" opacity=".8" />

        {pose === 'inspect' && (
          <g transform="translate(32 337) rotate(-13)">
            <circle cx="19" cy="18" r="24" fill="#0b0f19" fillOpacity=".34" stroke="#f3bd67" strokeWidth="7" />
            <circle cx="19" cy="18" r="16" fill="#67d7d6" fillOpacity=".14" stroke="#f6dda9" strokeWidth="2" />
            <path d="M37 37 L63 68" stroke="#b47c3f" strokeWidth="10" strokeLinecap="round" />
            <path d="M15 7 A13 13 0 0 1 29 16" fill="none" stroke="#fff2ca" strokeWidth="3" strokeLinecap="round" />
          </g>
        )}
      </svg>
    </div>
  );
};
