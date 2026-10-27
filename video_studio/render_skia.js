#!/usr/bin/env node
/**
 * No-browser renderer: draws the same render.html code through Skia.
 *
 * The primary renderer (render.js + Puppeteer) needs a Chromium binary. This
 * fallback needs only Node and the optional @napi-rs/canvas package, so the
 * pipeline can produce real frames on machines and CI images with no browser.
 * It executes render.html itself; it does not re-implement the visuals.
 *
 *   node render_skia.js storyboard.pro.json --out frames --format jpeg --quality 90
 *
 * Options: --out <dir> --format jpeg|png --quality 1-100 --scale 0.25-1 --max-frames N
 *
 * Limits are identical to render.js so a storyboard cannot render differently
 * depending on which path produced it.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const { contentProblem } = require("./visual_content.cjs");

let canvasLib;
try {
  canvasLib = require("@napi-rs/canvas");
} catch (error) {
  console.error(
    "RENDER ERROR: @napi-rs/canvas is not installed. This fallback renderer is optional.\n" +
    "Install it with: npm install --no-save @napi-rs/canvas\n" +
    "The primary renderer (render.js) uses Puppeteer and does not need it."
  );
  process.exit(3);
}
const { createCanvas, GlobalFonts } = canvasLib;

const BASE = __dirname;
const FONT_DIR = path.join(BASE, "fonts");
const VISUAL_TYPES = new Set(["hero", "stat", "timeline", "diagram", "comparison", "code",
  "quote", "waveform", "kinetic-type", "bar-chart"]);
const TRANSITIONS = new Set(["none", "cut", "whip-pan", "masked-reveal", "morph", "glitch",
  "match-cut", "fade", "wipe-left", "wipe-right", "slide-left", "slide-right", "zoom", "push", "dissolve"]);
const CAMERA_MOVES = new Set(["static", "push-in", "pull-out", "pan-left", "pan-right", "drift",
  "crane-up", "tilt-down", "handheld"]);
const EASINGS = new Set(["editorial", "entrance", "exit", "settle", "snap", "glide", "dramatic"]);
const TONES = new Set(["corporate", "edgy", "minimalist", "cinematic", "playful"]);
const MAX_FRAMES = 30000;
const MAX_SECONDS = 1000;

function fail(message) {
  console.error("RENDER ERROR: " + message);
  process.exit(1);
}

function parseArgs(argv) {
  const options = { storyboard: null, out: "skia-frames", format: "jpeg", quality: 90, scale: 1, maxFrames: MAX_FRAMES };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--out") options.out = argv[++index];
    else if (value === "--format") options.format = String(argv[++index] || "").toLowerCase();
    else if (value === "--quality") options.quality = Number(argv[++index]);
    else if (value === "--scale") options.scale = Number(argv[++index]);
    else if (value === "--max-frames") options.maxFrames = Number(argv[++index]);
    else if (value.startsWith("--")) fail("unknown option " + value);
    else options.storyboard = value;
  }
  if (!options.storyboard) fail("storyboard path is required");
  if (!["jpeg", "png"].includes(options.format)) fail("format must be jpeg or png");
  if (!Number.isFinite(options.quality) || options.quality < 1 || options.quality > 100) fail("quality must be 1..100");
  if (!Number.isFinite(options.scale) || options.scale < 0.25 || options.scale > 1) fail("scale must be 0.25..1");
  return options;
}

function applyFonts() {
  if (!fs.existsSync(FONT_DIR)) fail("font directory is missing: " + FONT_DIR);
  const families = {};
  for (const file of fs.readdirSync(FONT_DIR)) {
    if (!file.endsWith(".woff2")) continue;
    const family = file.startsWith("inter") ? "Inter" : file.startsWith("space-grotesk") ? "Space Grotesk" : null;
    if (!family) continue;
    try {
      GlobalFonts.registerFromPath(path.join(FONT_DIR, file), family);
      families[family] = (families[family] || 0) + 1;
    } catch (error) {
      fail("could not register font " + file + ": " + error.message);
    }
  }
  if (!families.Inter || !families["Space Grotesk"]) fail("bundled fonts did not register: " + JSON.stringify(families));
  return families;
}

function validate(storyboard) {
  if (!storyboard || typeof storyboard !== "object" || Array.isArray(storyboard)) fail("storyboard root must be an object");
  const width = Number(storyboard.width === undefined ? 1920 : storyboard.width);
  const height = Number(storyboard.height === undefined ? 1080 : storyboard.height);
  const fps = Number(storyboard.fps === undefined ? 30 : storyboard.fps);
  if (!Number.isInteger(width) || width < 320 || width > 3840) fail("width must be 320..3840");
  if (!Number.isInteger(height) || height < 180 || height > 3840) fail("height must be 180..3840");
  if (!Number.isInteger(fps) || fps < 1 || fps > 60) fail("fps must be 1..60");
  if (!Array.isArray(storyboard.scenes) || storyboard.scenes.length < 1 || storyboard.scenes.length > 100) {
    fail("scenes must contain 1..100 entries");
  }
  let total = 0;
  for (const [index, scene] of storyboard.scenes.entries()) {
    if (!scene || typeof scene !== "object") fail("scene " + index + " must be an object");
    const kind = String(scene.visual_type || "hero").toLowerCase();
    if (!VISUAL_TYPES.has(kind)) fail("scene " + index + " has unsupported visual_type: " + kind);
    const contentError = contentProblem(scene, kind);
    if (contentError) fail("scene " + index + ": " + contentError + "; the renderer will not invent missing content");
    const transition = String(scene.transition_in || "none").toLowerCase();
    if (!TRANSITIONS.has(transition)) fail("scene " + index + " has unsupported transition_in: " + transition);
    const move = String(scene.camera_motion || "static").toLowerCase();
    if (!CAMERA_MOVES.has(move)) fail("scene " + index + " has unsupported camera_motion: " + move);
    if (scene.easing !== undefined && !EASINGS.has(String(scene.easing).toLowerCase())) {
      fail("scene " + index + " has unsupported easing: " + scene.easing);
    }
    const duration = Number(scene.duration_seconds);
    if (!Number.isFinite(duration) || duration <= 0 || duration > 600) fail("scene " + index + " duration must be 0..600 seconds");
    total += duration;
  }
  if (total > MAX_SECONDS) fail("storyboard exceeds the " + MAX_SECONDS + "-second limit");
  if (storyboard.style !== undefined && storyboard.style !== null) {
    if (typeof storyboard.style !== "object" || Array.isArray(storyboard.style)) fail("style must be an object");
    if (storyboard.style.tone !== undefined && !TONES.has(String(storyboard.style.tone).toLowerCase())) {
      fail("unsupported style.tone: " + storyboard.style.tone);
    }
    const grade = storyboard.style.grade;
    if (grade !== undefined) {
      for (const [key, min, max] of [["vignette", 0, 0.4], ["grain", 0, 0.08], ["bloom", 0, 0.3], ["contrast", 0.9, 1.2]]) {
        if (grade[key] === undefined) continue;
        const value = Number(grade[key]);
        if (!Number.isFinite(value) || value < min || value > max) fail("style.grade." + key + " must be " + min + ".." + max);
      }
    }
  }
  return { width, height, fps };
}

function installEnvironment(width, height) {
  const frame = createCanvas(width, height);
  const scratch = createCanvas(160, 160);

  class SnapshotImage {
    constructor() {
      this._canvas = null;
    }
    set src(_value) {
      // render.html builds each transition from canvas.toDataURL(); capture the
      // pixels that exist at that instant instead of decoding a data URI.
      const copy = createCanvas(frame.width, frame.height);
      copy.getContext("2d").drawImage(frame, 0, 0);
      this._canvas = copy;
    }
    async decode() {}
  }

  const context = frame.getContext("2d", { alpha: false });
  const drawImage = context.drawImage.bind(context);
  context.drawImage = function patchedDrawImage(source, ...rest) {
    if (source instanceof SnapshotImage) return drawImage(source._canvas, ...rest);
    return drawImage(source, ...rest);
  };

  global.document = {
    getElementById: () => frame,
    createElement: (tag) => (String(tag).toLowerCase() === "canvas" ? createCanvas(160, 160) : scratch),
    fonts: { ready: Promise.resolve(), check: () => true },
  };
  global.window = global;
  global.Image = SnapshotImage;
  return frame;
}

function loadRenderer() {
  const html = fs.readFileSync(path.join(BASE, "render.html"), "utf8");
  const start = html.indexOf("<script>");
  const end = html.indexOf("</script>", start);
  if (start < 0 || end < 0) fail("render.html does not contain a script block");
  // eslint-disable-next-line no-eval
  (0, eval)(html.slice(start + 8, end));
  if (typeof window.drawFrame !== "function") fail("render.html did not expose drawFrame()");
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const storyboardPath = path.resolve(options.storyboard);
  if (!fs.existsSync(storyboardPath)) fail("storyboard not found: " + storyboardPath);
  const storyboard = JSON.parse(fs.readFileSync(storyboardPath, "utf8"));
  const { width, height, fps } = validate(storyboard);

  const renderWidth = Math.max(320, Math.round(width * options.scale));
  const renderHeight = Math.max(180, Math.round(height * options.scale));
  if (!Number.isInteger(renderWidth) || !Number.isInteger(renderHeight)) fail("scaled canvas is not integral");
  if ((renderWidth % 2) || (renderHeight % 2)) fail("H.264 requires even canvas dimensions");

  const families = applyFonts();
  const frame = installEnvironment(renderWidth, renderHeight);
  loadRenderer();
  window.setCanvasSize(renderWidth, renderHeight);
  window.setFrameRate(fps);
  if (storyboard.style) window.setStyle(storyboard.style);

  const outDir = path.resolve(options.out);
  fs.mkdirSync(outDir, { recursive: true });
  for (const file of fs.readdirSync(outDir)) {
    if (/^frame-\d{6}\.(jpg|png)$/.test(file)) fs.unlinkSync(path.join(outDir, file));
  }

  const extension = options.format === "png" ? "png" : "jpg";
  const transitions = [];
  let total = 0;
  for (const [sceneIndex, scene] of storyboard.scenes.entries()) {
    if (total >= options.maxFrames) break;
    const seconds = Number(scene.duration_seconds);
    const count = Math.max(1, Math.round(seconds * fps));
    const previous = sceneIndex > 0 ? storyboard.scenes[sceneIndex - 1] : null;
    const previousCount = previous ? Math.max(1, Math.round(Number(previous.duration_seconds) * fps)) : 0;
    const requested = Number(scene.transition_frames) || 12;
    const kind = String(scene.transition_in || "none").toLowerCase();
    const transitionFrames = previous && kind !== "none"
      ? Math.min(count, Math.max(1, Math.min(60, Math.round(requested))))
      : 0;
    transitions.push({ scene: sceneIndex + 1, type: kind, frames: transitionFrames });

    for (let localFrame = 0; localFrame < count && total < options.maxFrames; localFrame += 1) {
      if (transitionFrames && localFrame < transitionFrames) {
        const progress = transitionFrames <= 1 ? 1 : localFrame / (transitionFrames - 1);
        await window.drawTransitionFrame(
          previous, previousCount - 1, previousCount, Math.max(0, total - 1),
          scene, localFrame, count, total, kind, progress
        );
      } else {
        window.drawFrame(scene, localFrame, count, total);
      }
      const pixels = options.format === "png"
        ? frame.encode("png")
        : frame.encode("jpeg", options.quality);
      const data = await pixels;
      fs.writeFileSync(path.join(outDir, "frame-" + String(total).padStart(6, "0") + "." + extension), data);
      total += 1;
    }
    console.log("Rendered scene " + (sceneIndex + 1) + "/" + storyboard.scenes.length + " (" + count + " frames)");
  }

  const manifest = {
    title: String(storyboard.title || "Offline Agent HQ video"),
    width: renderWidth,
    height: renderHeight,
    source_width: width,
    source_height: height,
    scale: options.scale,
    fps,
    frame_count: total,
    duration_seconds: Number((total / fps).toFixed(3)),
    scene_count: storyboard.scenes.length,
    transitions,
    style: storyboard.style || null,
    tone: (storyboard.style && storyboard.style.tone) || null,
    renderer: "@napi-rs/canvas (no browser)",
    fonts: families,
    generated_at: new Date().toISOString(),
  };
  fs.writeFileSync(path.join(BASE, "render-manifest.json"), JSON.stringify(manifest, null, 2) + "\n");
  fs.writeFileSync(path.join(outDir, "manifest.json"), JSON.stringify(manifest, null, 2) + "\n");
  console.log("Rendered " + total + " frames at " + renderWidth + "x" + renderHeight + " to " + outDir);
}

main().catch((error) => fail(error && error.message ? error.message : String(error)));
