#!/usr/bin/env node
/**
 * The motion library's own command line.
 *
 * Three jobs, all of them things that must be measured rather than believed:
 *
 *   ``--selfcheck``        render every template on its own, measure where the
 *                          ink actually landed, and fail if it left its region or
 *                          if it is not animating. This is how the library proves
 *                          the "type never leaves its box" rule instead of
 *                          asserting it in a comment.
 *
 *   ``--agent-map``        print the map the motion agent reads: templates,
 *                          situations, limits and regions, as JSON.
 *   ``--write-agent-map``  write that map to ``agents/motion_templates.json``.
 *                          The map is generated from the code on purpose - a
 *                          hand-maintained copy drifts, and a motion agent acting
 *                          on a stale catalogue is worse than no catalogue.
 *
 *   ``--choose``           run the chooser for one beat and print the decision and
 *                          its reasons.
 *
 *   node video_studio/motion/library_cli.mjs --selfcheck
 *   node video_studio/motion/library_cli.mjs --write-agent-map
 *   node video_studio/motion/library_cli.mjs --choose --situation recap --seconds 2.4 --region stage
 */
import fs from 'fs';
import path from 'path';
import process from 'process';
import { fileURLToPath } from 'url';

import { createCanvas, GlobalFonts } from '@napi-rs/canvas';

import { TEMPLATES, REGIONS, RESERVED, regionRect, drawTemplate, describeLibrary } from './library.mjs';
import { SITUATIONS, rankTemplates, chooseTemplate, explainChoice } from './choose.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const STUDIO = path.resolve(HERE, '..');
const ROOT = path.resolve(STUDIO, '..');

const W = 640;
const H = 360;

function registerFonts() {
  const faces = [
    ['Inter', 'inter-latin-400-normal.woff2'],
    ['Inter', 'inter-latin-600-normal.woff2'],
    ['Inter', 'inter-latin-700-normal.woff2'],
    ['Space Grotesk', 'space-grotesk-latin-600-normal.woff2'],
    ['Space Grotesk', 'space-grotesk-latin-700-normal.woff2'],
  ];
  for (const [family, file] of faces) {
    GlobalFonts.registerFromPath(path.join(STUDIO, 'fonts', file), family);
  }
}

/** The ink bounding box of the canvas, or null when nothing was drawn. */
function inkBox(ctx) {
  const { data } = ctx.getImageData(0, 0, W, H);
  let minX = W;
  let minY = H;
  let maxX = -1;
  let maxY = -1;
  let ink = 0;
  for (let y = 0; y < H; y += 1) {
    for (let x = 0; x < W; x += 1) {
      if (data[(y * W + x) * 4 + 3] > 8) {
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
        ink += 1;
      }
    }
  }
  return maxX < 0 ? null : { x: minX, y: minY, right: maxX, bottom: maxY, ink };
}

/** How many pixels differ between two renders of the same template. */
function differing(a, b) {
  let count = 0;
  for (let i = 3; i < a.length; i += 4) {
    if (Math.abs(a[i] - b[i]) > 6) count += 1;
  }
  return count;
}

function selfcheck() {
  registerFonts();
  const canvas = createCanvas(W, H);
  const ctx = canvas.getContext('2d');
  const results = [];
  const failures = [];

  for (const template of TEMPLATES) {
    // A beat inside the template's own band, so the check tests the template and
    // not the caller's arithmetic.
    const seconds = Math.min(template.maxSeconds, Math.max(template.minSeconds, 2.0));
    for (const region of template.regions) {
      const box = regionRect(region, W, H);
      const shots = [];
      const times = [0.15, 0.45, 0.9].map((f) => f * seconds);
      for (const local of times) {
        ctx.clearRect(0, 0, W, H);
        try {
          drawTemplate(ctx, template.id, { w: W, h: H, region, seconds, local, ...template.sample });
        } catch (error) {
          failures.push(`${template.id}/${region} threw at ${local.toFixed(2)}s: ${error.message}`);
          shots.push(null);
          continue;
        }
        const box2 = inkBox(ctx);
        shots.push({ box: box2, data: ctx.getImageData(0, 0, W, H).data.slice() });
      }
      const drawn = shots.filter(Boolean);
      if (!drawn.length) continue;
      const middle = drawn[Math.floor(drawn.length / 2)];
      if (!middle.box) {
        failures.push(`${template.id}/${region}: drew nothing`);
        continue;
      }
      const tolerance = 4;
      for (const shot of drawn) {
        if (!shot.box) continue;
        if (shot.box.x < box.x - tolerance || shot.box.y < box.y - tolerance
          || shot.box.right > box.x + box.w + tolerance
          || shot.box.bottom > box.y + box.h + tolerance) {
          failures.push(
            `${template.id}/${region}: ink [${shot.box.x},${shot.box.y}..${shot.box.right},${shot.box.bottom}] `
            + `left its box [${box.x},${box.y}..${box.x + box.w},${box.y + box.h}]`,
          );
        }
      }
      const moved = drawn.length > 1 ? differing(drawn[0].data, drawn[drawn.length - 1].data) : 0;
      if (moved < 200) {
        failures.push(`${template.id}/${region}: barely animates (${moved} pixels changed between first and last frame)`);
      }
      results.push({
        id: template.id,
        region,
        seconds,
        ink: middle.box.ink,
        coverage: +(middle.box.ink / (W * H)).toFixed(4),
        moved,
      });
    }
  }

  const report = { canvas: `${W}x${H}`, cases: results.length, checks: results, failures };
  console.log(JSON.stringify(report, null, 2));
  return failures.length ? 1 : 0;
}

function agentMap() {
  return {
    version: 1,
    generated_by: 'video_studio/motion/library_cli.mjs --write-agent-map',
    notice: 'Generated from the code. Do not edit by hand: edit the templates or the situations and regenerate.',
    rules: {
      pick_by_situation: 'Choose the template from the situation the beat is for, never from habit or from what the last beat used.',
      one_region_each: 'A template owns one region. Two templates may not share a region on the same frame.',
      type_never_overlaps_type: 'Every word is masked to its own box; the self-check measures this.',
      no_shake: 'No template translates or rotates the camera. Motion is one direction, eased, then still.',
      beat_length: 'A template refuses a beat outside its band; pick another template rather than stretching it.',
    },
    reserved: RESERVED,
    regions: REGIONS,
    situations: SITUATIONS,
    templates: describeLibrary(),
  };
}

function choose(args) {
  const situation = args.situation;
  const seconds = Number(args.seconds);
  const region = args.region || null;
  const ranked = rankTemplates({ situation, seconds, region, have: {} });
  const withProps = rankTemplates({
    situation, seconds, region,
    have: Object.fromEntries(TEMPLATES.flatMap((t) => t.needs.map((need) => [need, true]))),
  });
  console.log(JSON.stringify({
    situation,
    seconds,
    region,
    needs_a_prop: explainChoice(ranked, { situation, seconds }),
    assuming_props: explainChoice(withProps, { situation, seconds }),
    ranked: withProps,
  }, null, 2));
  return 0;
}

function main(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith('--')) continue;
    const key = token.slice(2);
    const next = argv[i + 1];
    if (next && !next.startsWith('--')) {
      args[key] = next;
      i += 1;
    } else {
      args[key] = true;
    }
  }

  if (args.selfcheck) return selfcheck();
  if (args['agent-map']) {
    console.log(JSON.stringify(agentMap(), null, 2));
    return 0;
  }
  if (args['write-agent-map']) {
    const target = path.resolve(ROOT, 'agents', 'motion_templates.json');
    fs.writeFileSync(target, JSON.stringify(agentMap(), null, 2) + '\n', 'utf8');
    console.log(`wrote ${path.relative(ROOT, target)}`);
    return 0;
  }
  if (args.choose) return choose(args);
  console.error('nothing to do: use --selfcheck, --agent-map, --write-agent-map or --choose');
  return 2;
}

process.exit(main(process.argv.slice(2)));
