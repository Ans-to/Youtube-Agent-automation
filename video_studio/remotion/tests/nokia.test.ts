import assert from 'node:assert/strict';
import test from 'node:test';
import {
  NOKIA_DURATION_FRAMES, NOKIA_FPS, NOKIA_HEIGHT, NOKIA_SCENES,
  NOKIA_WIDTH, PROVISIONAL_WORD_CUES,
} from '../src/nokia/storyboard';

test('Nokia Evolution is a 30-second 9:16 Remotion composition', () => {
  assert.equal(NOKIA_FPS, 30);
  assert.equal(NOKIA_DURATION_FRAMES, 900);
  assert.deepEqual([NOKIA_WIDTH, NOKIA_HEIGHT], [1080, 1920]);
});

test('scene windows preserve the requested 8/10/12-second structure and VO', () => {
  assert.deepEqual(NOKIA_SCENES.map(({ startFrame, endFrame }) => [startFrame, endFrame]), [
    [0, 240], [240, 540], [540, 900],
  ]);
  assert.match(NOKIA_SCENES[0].voiceover, /^In 1865,/);
  assert.match(NOKIA_SCENES[1].voiceover, /rubber boots, cables, and electricity/);
  assert.match(NOKIA_SCENES[2].voiceover, /redefining what a mobile phone could be\.$/);
});

test('every supplied VO word has a monotonic word-level cue in its scene', () => {
  for (const scene of NOKIA_SCENES) {
    const cues = PROVISIONAL_WORD_CUES.filter((cue) => cue.sceneId === scene.id);
    assert.equal(cues.length, scene.voiceover.trim().split(/\s+/).length);
    assert.ok(cues.length > 0);
    for (let i = 0; i < cues.length; i++) {
      const cue = cues[i];
      assert.ok(cue.startFrame >= scene.startFrame && cue.endFrame <= scene.endFrame);
      assert.ok(cue.endFrame > cue.startFrame);
      if (i > 0) assert.ok(cue.startFrame >= cues[i - 1].endFrame);
    }
  }
});
