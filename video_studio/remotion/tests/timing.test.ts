import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { execFileSync } from 'node:child_process';
import test from 'node:test';
import { BPM, DURATION_FRAMES, DURATION_SECONDS, FPS, HEIGHT, PALETTE, WIDTH, WORDS, focusState, frameAtBeat, wordState } from '../src/timing';

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
    assert.equal(wordState(at - 1, word.beat).opacity, 0);
    assert.ok(wordState(at, word.beat).opacity > 0);
    assert.equal(wordState(at + 5, word.beat).progress, 1);
    assert.equal(wordState(at + 15, word.beat).progress, 1);
  }
});

test('focus shifts to the terminal and returns to the final phrase on the beat grid', () => {
  assert.deepEqual(focusState(0), { title: 0, terminal: 0 });
  assert.equal(focusState(frameAtBeat(11)).title, 1);
  assert.equal(focusState(frameAtBeat(12)).terminal, 1);
  assert.equal(focusState(frameAtBeat(18)).terminal, 0);
  assert.equal(focusState(frameAtBeat(19)).title, 0);
  for (let frame = 0; frame < DURATION_FRAMES; frame++) {
    const state = focusState(frame);
    assert.ok(state.title >= 0 && state.title <= 1);
    assert.ok(state.terminal >= 0 && state.terminal <= 1);
  }
});

function luminance(hex: string) {
  const values = hex.slice(1).match(/../g)!.map((v) => parseInt(v, 16) / 255);
  const rgb = values.map((v) => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
  return .2126 * rgb[0] + .7152 * rgb[1] + .0722 * rgb[2];
}

test('white and red headline have strong contrast on the dark background', () => {
  for (const color of [PALETTE.foreground, PALETTE.accent]) {
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
