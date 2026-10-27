import { FPS } from '../timing';

export const NOKIA_FPS = FPS;
export const NOKIA_DURATION_FRAMES = 30 * NOKIA_FPS;
export const NOKIA_WIDTH = 1080;
export const NOKIA_HEIGHT = 1920;

export type NokiaSceneId = 'mill' | 'pivot' | 'world';
export type NokiaWordCue = {
  sceneId: NokiaSceneId;
  word: string;
  index: number;
  startFrame: number;
  endFrame: number;
};

export const NOKIA_SCENES = [
  {
    id: 'mill',
    startFrame: 0,
    endFrame: 8 * NOKIA_FPS,
    heading: 'THE TIMBER MILL',
    voiceover: 'Nokia began in 1865 at a Finnish timber mill. Paper was only the beginning.',
  },
  {
    id: 'pivot',
    startFrame: 8 * NOKIA_FPS,
    endFrame: 18 * NOKIA_FPS,
    heading: 'THE INDUSTRIAL PIVOT',
    voiceover: 'Nokia expanded beyond paper into rubber boots, cables, and electricity, helping Finland modernize before mobile phones arrived.',
  },
  {
    id: 'world',
    startFrame: 18 * NOKIA_FPS,
    endFrame: 30 * NOKIA_FPS,
    heading: 'CONNECTING THE WORLD',
    voiceover: 'When the digital age arrived, Nokia pivoted once more—redefining mobile phones and connecting people around the world.',
  },
] as const;

/**
 * Fallback editorial cues, distributed over the supplied scene windows. These
 * keep the composition previewable before narration alignment is supplied; they
 * are NOT forced-alignment results. Replace them with the measured word frames
 * for the final VO file. The component accepts that exact cue array as a prop.
 */
export const createProvisionalWordCues = (): NokiaWordCue[] => NOKIA_SCENES.flatMap((scene) => {
  const words = scene.voiceover.match(/[^\s]+/g) ?? [];
  const firstFrame = scene.startFrame + 9;
  const lastFrame = scene.endFrame - 9;
  const weights = words.map((word) => {
    const punctuation = /[.!?…—]$/.test(word) ? 7 : /[,;:]$/.test(word) ? 4 : 0;
    return Math.max(2, word.replace(/[^\p{L}\p{N}]/gu, '').length * 0.75) + punctuation;
  });
  const totalWeight = weights.reduce((sum, weight) => sum + weight, 0);
  let cursor = firstFrame;
  return words.map((word, index) => {
    const startFrame = cursor;
    cursor = index === words.length - 1
      ? lastFrame
      : cursor + (lastFrame - firstFrame) * weights[index] / totalWeight;
    return {
      sceneId: scene.id,
      word,
      index,
      startFrame: Math.round(startFrame),
      endFrame: Math.max(Math.round(startFrame) + 1, Math.round(cursor)),
    };
  });
});

export const PROVISIONAL_WORD_CUES = createProvisionalWordCues();
