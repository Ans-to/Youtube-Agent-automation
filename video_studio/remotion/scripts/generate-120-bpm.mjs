#!/usr/bin/env node
/**
 * Original, deterministic 120 BPM instrumental bed for StopCodingBlind.
 * No samples or outside assets: a soft synth, kick, snare and hi-hats are
 * synthesized on an exact 48 kHz sample grid. Beat zero is at sample zero.
 * Usage: node scripts/generate-120-bpm.mjs [output.wav]
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const OUT = path.resolve(process.argv[2] ?? path.join(ROOT, 'public/audio/stop-coding-blind-120bpm.wav'));
const RATE = 48_000, DURATION = 10, BPM = 120;
const BEAT = Math.round(RATE * 60 / BPM), SAMPLES = DURATION * RATE;
const mix = new Float64Array(SAMPLES);
const TAU = 2 * Math.PI;

// Integer hash instead of Math.random: repeated renders are bit-for-bit equal.
function noise(seed) {
  let x = (seed ^ 0x9e3779b9) >>> 0;
  x = Math.imul(x ^ (x >>> 16), 0x7feb352d);
  x = Math.imul(x ^ (x >>> 15), 0x846ca68b);
  return ((x ^ (x >>> 16)) >>> 0) / 0x7fffffff - 1;
}
function add(start, length, sample) {
  const begin = Math.round(start), end = Math.min(SAMPLES, begin + Math.round(length * RATE));
  for (let i = begin; i < end; i++) mix[i] += sample((i - begin) / RATE, i - begin);
}

// A restrained four-on-the-floor pulse anchors every exact half-second beat.
for (let beat = 0; beat < DURATION * BPM / 60; beat++) {
  const start = beat * BEAT;
  add(start, .36, (t) => {
    const phase = TAU * (49 * t + 94 * (1 - Math.exp(-38 * t)) / 38);
    return .50 * Math.exp(-14 * t) * Math.sin(phase);
  });
  if (beat % 4 === 1 || beat % 4 === 3) {
    add(start, .24, (t, n) => {
      const transient = noise(n + beat * 8317) - .72 * noise(n - 1 + beat * 8317);
      return .11 * Math.exp(-20 * t) * transient + .055 * Math.exp(-22 * t) * Math.sin(TAU * 180 * t);
    });
  }
  const bassNotes = [55, 55, 65.406, 48.999, 55, 55, 82.407, 65.406];
  const note = bassNotes[beat % bassNotes.length];
  add(start, .44, (t) => {
    const attack = Math.min(1, t / .008);
    const release = Math.min(1, (.44 - t) / .08);
    return .13 * attack * Math.max(0, release) * Math.exp(-2.8 * t) *
      (Math.sin(TAU * note * t) + .18 * Math.sin(TAU * 2 * note * t));
  });
  const notes = [220, 261.626, 329.628, 293.665, 220, 261.626, 391.995, 329.628];
  const pitch = notes[beat % notes.length];
  add(start, .40, (t) => .047 * Math.min(1, t / .012) * Math.exp(-6.5 * t) * Math.sin(TAU * pitch * t));
}
for (let eighth = 0; eighth < DURATION * BPM / 30; eighth++) {
  add(eighth * BEAT / 2, .08, (t, n) => {
    const high = noise(n + eighth * 337) - .86 * noise(n - 1 + eighth * 337);
    return (eighth % 2 ? .025 : .033) * Math.exp(-52 * t) * high;
  });
}
// Dark, low pad and a short tail fade keep the ten-second cut clean.
for (let i = 0; i < SAMPLES; i++) {
  const t = i / RATE;
  const fade = Math.min(1, t / .18, (DURATION - t) / .32);
  const pad = .022 * (Math.sin(TAU * 110 * t) + .45 * Math.sin(TAU * 164.814 * t));
  // Gentle saturation controls drum transients while lifting the musical bed;
  // keep headroom for the later AAC encode and check the actual true peak.
  mix[i] = .70 * Math.tanh((mix[i] + pad) * 5.2) * Math.max(0, fade);
}

// Suppress sharp ultrasonic edges from saturation before measuring headroom.
// This FIR delays the signal by one sample (0.021 ms), well below one frame.
let previous = 0, previous2 = 0;
for (let i = 0; i < SAMPLES; i++) {
  const next = mix[i];
  mix[i] = .25 * next + .5 * previous + .25 * previous2;
  previous2 = previous; previous = next;
}

// PCM avoids compressed-audio encoder delay: the video and track share zero.
let peak = 0;
for (const value of mix) peak = Math.max(peak, Math.abs(value));
const gain = Math.min(1, .82 / Math.max(peak, 1e-9));
const wav = Buffer.alloc(44 + SAMPLES * 2);
wav.write('RIFF', 0); wav.writeUInt32LE(wav.length - 8, 4); wav.write('WAVE', 8);
wav.write('fmt ', 12); wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20);
wav.writeUInt16LE(1, 22); wav.writeUInt32LE(RATE, 24); wav.writeUInt32LE(RATE * 2, 28);
wav.writeUInt16LE(2, 32); wav.writeUInt16LE(16, 34); wav.write('data', 36);
wav.writeUInt32LE(SAMPLES * 2, 40);
for (let i = 0; i < SAMPLES; i++) wav.writeInt16LE(Math.round(Math.max(-1, Math.min(1, mix[i] * gain)) * 32767), 44 + i * 2);
fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, wav);
console.log(`Wrote ${OUT}: ${DURATION}s, ${RATE} Hz PCM, ${BPM} BPM, beat interval ${BEAT} samples.`);
