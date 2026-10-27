import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { execFileSync } from 'node:child_process';
import test from 'node:test';
import { BPM, DURATION_FRAMES, DURATION_SECONDS, FPS, GLITCH_BEATS, HEIGHT, PALETTE, WIDTH, WORDS, frameAtBeat, glitchState, wordImpact, wordIsVisible } from '../src/timing';
import { cameraPose } from '../src/camera';
import { avatarMotion } from '../src/avatarMotion';
import { terminalLineState } from '../src/terminalMotion';

const root = resolve(import.meta.dirname, '..');

test('composition is exactly ten seconds in portrait', () => {
  assert.equal(BPM, 120);
  assert.equal(FPS, 30);
  assert.equal(DURATION_SECONDS, 10);
  assert.equal(DURATION_FRAMES, 300);
  assert.deepEqual([WIDTH, HEIGHT], [1080, 1920]);
});

test('literal words appear in order on successive half-second beats', () => {
  assert.equal(WORDS.map((item) => item.text).join(' '), 'Stop coding blind.');
  assert.deepEqual(WORDS.map((item) => frameAtBeat(item.beat)), [15, 30, 45]);
  assert.deepEqual(WORDS.map((item) => frameAtBeat(item.beat, 24)), [12, 24, 36]);
  for (const word of WORDS) {
    const at = frameAtBeat(word.beat);
    assert.equal(wordIsVisible(at - 1, word.beat), false);
    assert.equal(wordIsVisible(at, word.beat), true);
    assert.equal(wordImpact(at - 1, word.beat), 0);
    assert.ok(wordImpact(at, word.beat) > 0);
    assert.ok(wordImpact(at + 5, word.beat) > 1, 'the impact spring should overshoot');
  }
});

test('glitches land on every word and two-beat accent, then clear', () => {
  assert.deepEqual(GLITCH_BEATS, [1, 2, 3, 4, 6, 8, 10, 12, 14, 16, 18]);
  for (const beat of GLITCH_BEATS) {
    const at = frameAtBeat(beat);
    assert.equal(glitchState(at - 1).active, false);
    assert.deepEqual(glitchState(at), { active: true, beat, elapsed: 0 });
    assert.equal(glitchState(at + 2).active, true);
    assert.equal(glitchState(at + 3).active, false);
  }
});

test('camera moves every frame and vector-character motion is beat-derived', () => {
  for (let frame = 1; frame < DURATION_FRAMES; frame++) {
    const before = cameraPose(frame - 1, FPS);
    const after = cameraPose(frame, FPS);
    assert.notDeepEqual(after, before, `camera held at frame ${frame}`);
    for (const n of [...after.position, ...after.target, after.zoom]) assert.ok(Number.isFinite(n));
  }
  assert.notEqual(avatarMotion(0, FPS).typing, avatarMotion(2, FPS).typing);
  assert.ok(avatarMotion(2, FPS).typing * avatarMotion(6, FPS).typing < 0);
  assert.notEqual(avatarMotion(0, FPS).bob, avatarMotion(2, FPS).bob);
  assert.deepEqual(avatarMotion(101, FPS), avatarMotion(101, FPS));
});

test('the terminal keeps editing after its initial type-on', () => {
  assert.equal(terminalLineState(0, 0, FPS).progress, 0);
  const first = frameAtBeat(9);
  assert.equal(terminalLineState(first, 0, FPS).active, true);
  assert.ok(terminalLineState(first + 10, 0, FPS).progress > terminalLineState(first, 0, FPS).progress);
  assert.equal(terminalLineState(first + frameAtBeat(2), 1, FPS).active, true);
});

function luminance(hex: string) {
  const values = hex.slice(1).match(/../g)!.map((v) => parseInt(v, 16) / 255);
  const rgb = values.map((v) => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
  return .2126 * rgb[0] + .7152 * rgb[1] + .0722 * rgb[2];
}

test('white, red and cyan have strong contrast on the dark background', () => {
  for (const color of [PALETTE.foreground, PALETTE.red, PALETTE.cyan]) {
    const contrast = (luminance(color) + .05) / (luminance(PALETTE.background) + .05);
    assert.ok(contrast >= 4.5, `${color}: ${contrast}`);
  }
});

test('bundled audio is reproducible 48 kHz PCM with an attack on every beat', () => {
  const file = resolve(root, 'public/audio/stop-coding-blind-120bpm.wav');
  const audio = readFileSync(file);
  assert.equal(audio.toString('ascii', 0, 4), 'RIFF');
  assert.equal(audio.readUInt16LE(20), 1); // PCM
  assert.equal(audio.readUInt16LE(22), 1); // mono
  assert.equal(audio.readUInt32LE(24), 48_000);
  assert.equal(audio.readUInt16LE(34), 16);
  assert.equal(audio.readUInt32LE(40), DURATION_SECONDS * 48_000 * 2);
  const level = (start: number, duration: number) => {
    let power = 0;
    const count = Math.floor(duration * 48_000);
    for (let i = Math.round(start * 48_000); i < Math.round(start * 48_000) + count; i++) {
      power += (audio.readInt16LE(44 + i * 2) / 32768) ** 2;
    }
    return Math.sqrt(power / count);
  };
  for (let beat = 1; beat < 20; beat++) {
    const time = beat * 60 / BPM;
    assert.ok(level(time, .04) > level(time - .06, .04) * 3, `beat ${beat} is not audible at ${time}s`);
  }
  const temp = mkdtempSync(resolve(tmpdir(), 'studio-audio-'));
  try {
    const regenerated = resolve(temp, 'bed.wav');
    execFileSync(process.execPath, [resolve(root, 'scripts/generate-120-bpm.mjs'), regenerated]);
    const sha = (data: Buffer) => createHash('sha256').update(data).digest('hex');
    assert.equal(sha(readFileSync(regenerated)), sha(audio));
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});
