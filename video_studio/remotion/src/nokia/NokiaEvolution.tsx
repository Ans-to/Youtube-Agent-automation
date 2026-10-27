import React, { useEffect, useState } from 'react';
import {
  AbsoluteFill, Audio, cancelRender, continueRender, delayRender, interpolate, spring,
  staticFile, useCurrentFrame, useVideoConfig,
} from 'remotion';
import { NokiaArchivist, type ArchivistPose } from './NokiaArchivist';
import { NokiaSceneArt } from './NokiaSceneArt';
import {
  NOKIA_SCENES, PROVISIONAL_WORD_CUES,
  type NokiaSceneId, type NokiaWordCue,
} from './storyboard';

export type NokiaEvolutionProps = {
  /** Full-length VO mix, beginning at frame zero. Use the measured word cues below. */
  narrationSrc?: string | null;
  /** Global frame ranges from alignment of the final narration file. */
  wordCues?: NokiaWordCue[];
};

const SCENE_START: Record<NokiaSceneId, number> = { mill: 0, pivot: 240, world: 540 };
const SCENE_POSE: Record<NokiaSceneId, ArchivistPose> = {
  mill: 'inspect', pivot: 'point', world: 'present',
};
const SPRING_TEXT = { damping: 12, stiffness: 140, mass: 0.8 };

const useHouseFont = () => {
  const [handle] = useState(() => delayRender('Loading Space Grotesk for Nokia Evolution'));
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

const SceneEntrance: React.FC<{
  frame: number;
  fps: number;
  startFrame: number;
  children: React.ReactNode;
  style?: React.CSSProperties;
  config?: { damping?: number; stiffness?: number; mass?: number };
}> = ({ frame, fps, startFrame, children, style, config = SPRING_TEXT }) => {
  if (frame < startFrame) return null;
  const impact = spring({ frame: frame - startFrame + 1, fps, config });
  return <div style={{ ...style, opacity: Math.min(1, impact), transform: `translateY(${(1 - impact) * 26}px) scale(${0.94 + 0.06 * impact})` }}>{children}</div>;
};

const sceneFade = (frame: number, sceneId: NokiaSceneId) => {
  const [start, end] = sceneId === 'mill' ? [0, 240] : sceneId === 'pivot' ? [240, 540] : [540, 900];
  const fadeIn = sceneId === 'mill' ? 1 : interpolate(frame, [start - 16, start + 10], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const fadeOut = sceneId === 'world' ? 1 : interpolate(frame, [end - 10, end + 16], [1, 0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  return fadeIn * fadeOut;
};

const KaraokeCaption: React.FC<{
  frame: number;
  fps: number;
  sceneId: NokiaSceneId;
  cues: NokiaWordCue[];
}> = ({ frame, fps, sceneId, cues }) => {
  const scene = NOKIA_SCENES.find((item) => item.id === sceneId)!;
  const words = cues.filter((cue) => cue.sceneId === sceneId);
  const entrance = spring({ frame: Math.max(0, frame - SCENE_START[sceneId] + 1), fps,
    config: { damping: 16, stiffness: 120, mass: 0.85 } });
  return (
    <div style={{ position: 'absolute', left: 54, right: 54, bottom: 82, minHeight: 218,
      boxSizing: 'border-box', padding: '24px 30px', borderRadius: 16,
      background: 'linear-gradient(110deg,rgba(7,12,20,.92),rgba(10,17,27,.84))',
      border: '1px solid rgba(218,165,98,.38)', borderLeft: '5px solid #e74c3c',
      boxShadow: '0 18px 55px rgba(0,0,0,.30)',
      opacity: Math.min(1, entrance), transform: `translateY(${(1 - entrance) * 22}px)` }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10,
        font: '700 13px monospace', letterSpacing: '3px', color: '#d8aa69' }}>
        <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: '#e74c3c', boxShadow: '0 0 16px #e74c3c' }} />
        NARRATION / {sceneId.toUpperCase()}
      </div>
      <div aria-label={scene.voiceover} style={{ display: 'flex', flexWrap: 'wrap', columnGap: 10, rowGap: 0,
        alignItems: 'baseline', color: '#d6d8dd', fontFamily: 'Space Grotesk, sans-serif',
        fontSize: 29, fontWeight: 500, lineHeight: 1.38 }}>
        {words.map((cue, index) => {
          const spoken = frame >= cue.startFrame;
          const active = frame >= cue.startFrame && frame < cue.endFrame;
          const impact = spoken ? spring({ frame: frame - cue.startFrame + 1, fps,
            config: { damping: 12, stiffness: 180, mass: .65 } }) : 0;
          return (
            <span key={`${cue.sceneId}-${cue.index}-${index}`} style={{ display: 'inline-block',
              whiteSpace: 'pre', color: active ? '#ffc775' : spoken ? '#f1eee7' : '#77808d',
              textShadow: active ? '0 0 18px rgba(255,183,91,.42)' : 'none',
              transform: `translateY(${spoken ? (1 - impact) * 8 : 0}px) scale(${spoken ? .94 + .06 * impact : 1})`,
              transformOrigin: 'left center' }}>{cue.word}{index < words.length - 1 ? ' ' : ''}</span>
          );
        })}
      </div>
    </div>
  );
};

const SceneTypography: React.FC<{ frame: number; fps: number }> = ({ frame, fps }) => {
  const currentScene = frame < 240 ? 'mill' : frame < 540 ? 'pivot' : 'world';
  const start = SCENE_START[currentScene];
  const duration = frame - start;

  return (
    <>
      <div style={{ position: 'absolute', left: 72, right: 72, top: 116, display: 'flex', flexDirection: 'column', gap: 16 }}>
        {currentScene === 'mill' && <>
          <SceneEntrance frame={frame} fps={fps} startFrame={0} style={{ alignSelf: 'flex-start' }}>
            <div style={{ padding: '15px 21px', color: '#111722', background: 'linear-gradient(100deg,#f1bd6b,#d7954b)',
              borderRadius: 5, font: '700 24px monospace', letterSpacing: '2px', boxShadow: '0 0 28px rgba(231,158,76,.28)' }}>
              1865 <span style={{ color: '#a73b34' }}>•</span> ORIGINS
            </div>
          </SceneEntrance>
          <SceneEntrance frame={frame} fps={fps} startFrame={18} style={{ maxWidth: 760 }}>
            <div style={{ color: '#f4e8d6', font: '700 54px/1.05 "Space Grotesk", sans-serif', letterSpacing: '-1px' }}>
              A MILL IN THE<br/><span style={{ color: '#e7ad60' }}>FINNISH FOREST</span>
            </div>
            <div style={{ marginTop: 14, color: '#acb6c4', font: '500 21px monospace', letterSpacing: '2px' }}>A PAPER COMPANY BEGINS</div>
          </SceneEntrance>
        </>}
        {currentScene === 'pivot' && <SceneEntrance frame={frame} fps={fps} startFrame={240}>
          <div style={{ color: '#f4e8d6', font: '700 48px/1.05 "Space Grotesk", sans-serif', letterSpacing: '-.5px' }}>
            THE INDUSTRIAL<br/><span style={{ color: '#e7ad60' }}>PIVOT</span>
          </div>
          <div style={{ marginTop: 13, color: '#9cb4c5', font: '500 18px monospace', letterSpacing: '2px' }}>FROM RAW MATERIALS TO POWER</div>
        </SceneEntrance>}
        {currentScene === 'world' && <SceneEntrance frame={frame} fps={fps} startFrame={540}>
          <div style={{ color: '#f4e8d6', font: '700 48px/1.06 "Space Grotesk", sans-serif', letterSpacing: '-.5px' }}>
            CONNECTING<br/><span style={{ color: '#e7ad60' }}>THE WORLD</span>
          </div>
          <div style={{ marginTop: 13, color: '#9cb4c5', font: '500 17px monospace', letterSpacing: '2px' }}>A NEW ERA OF MOBILE COMMUNICATION</div>
        </SceneEntrance>}
      </div>

      {currentScene === 'pivot' && <div style={{ position: 'absolute', left: 66, top: 565, width: 463 }}>
        <SceneEntrance frame={frame} fps={fps} startFrame={252}>
          <div style={{ color: '#f1bd6b', font: '700 14px monospace', letterSpacing: '3px' }}>THE INDUSTRIAL SHIFT</div>
        </SceneEntrance>
        {['PAPER', 'RUBBER BOOTS', 'CABLES', 'ELECTRICITY'].map((item, index) => (
          <SceneEntrance key={item} frame={frame} fps={fps} startFrame={264 + index * 8}>
            <div style={{ marginTop: 15, display: 'flex', alignItems: 'center', gap: 16,
              color: '#f2eadd', font: '700 21px monospace', letterSpacing: '1px' }}>
              <span style={{ width: 22, height: 3, background: index === 3 ? '#e74c3c' : '#e4ac61', boxShadow: `0 0 12px ${index === 3 ? '#e74c3c' : '#e4ac61'}` }} />
              {item}
            </div>
          </SceneEntrance>
        ))}
      </div>}

      {currentScene === 'world' && duration >= 810 && <div style={{ position: 'absolute', left: 66, right: 66, top: 1320,
        textAlign: 'center', pointerEvents: 'none' }}>
        <SceneEntrance frame={frame} fps={fps} startFrame={810}
          config={{ stiffness: 150, damping: 8, mass: 1 }}>
          <div style={{ color: '#fff4e4', font: '700 66px/1.02 "Space Grotesk", sans-serif', letterSpacing: '-2px',
            textShadow: '0 0 28px rgba(231,76,60,.55), 0 8px 0 rgba(111,36,34,.8)' }}>
            CONNECTING<br/><span style={{ color: '#e74c3c' }}>PEOPLE.</span>
          </div>
        </SceneEntrance>
      </div>}
    </>
  );
};

const currentSceneId = (frame: number): NokiaSceneId => frame < 240 ? 'mill' : frame < 540 ? 'pivot' : 'world';

/** 30-second, 9:16 Remotion short with an aligned-word cue interface. */
export const NokiaEvolution: React.FC<NokiaEvolutionProps> = ({ narrationSrc, wordCues = PROVISIONAL_WORD_CUES }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  useHouseFont();
  const sceneId = currentSceneId(frame);

  return (
    <AbsoluteFill style={{ backgroundColor: '#0b0f19', overflow: 'hidden' }}>
      {narrationSrc && <Audio src={narrationSrc} />}
      <NokiaSceneArt frame={frame} />
      {NOKIA_SCENES.map((scene) => {
        const alpha = sceneFade(frame, scene.id);
        if (alpha <= 0.001) return null;
        const pose = scene.id === 'mill' ? 'inspect' : scene.id === 'pivot' ? 'point' : 'present';
        return <div key={scene.id} style={{ position: 'absolute', inset: 0, opacity: alpha, pointerEvents: 'none' }}>
          <NokiaArchivist frame={frame} fps={fps} sceneId={scene.id} pose={pose} />
        </div>;
      })}
      <SceneTypography frame={frame} fps={fps} />
      <KaraokeCaption frame={frame} fps={fps} sceneId={sceneId} cues={wordCues} />
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 4,
        background: 'linear-gradient(90deg,#e7ad60,#e74c3c,#51d8d5)', opacity: .88 }} />
      <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', opacity: .11,
        backgroundImage: 'repeating-linear-gradient(0deg,transparent 0px,transparent 5px,rgba(170,193,210,.16) 6px)' }} />
    </AbsoluteFill>
  );
};

/** Ready-to-use Remotion prop defaults for an authored timing preview. */
export const NOKIA_EVOLUTION_DEFAULT_PROPS: NokiaEvolutionProps = {
  narrationSrc: null,
  wordCues: PROVISIONAL_WORD_CUES,
};
