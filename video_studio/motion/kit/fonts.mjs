/**
 * Type, actually installed.
 *
 * The studio rendered in DejaVu Sans for five rounds because `assets/fonts` did
 * not exist and every `family:` call quietly fell back to the system default.
 * The files are in the repo now; this module is the one place they are loaded,
 * so a new renderer cannot forget to do it and a new family cannot be half
 * installed.
 *
 * Two things it gets right that a bare `registerFromPath` loop does not:
 *
 *   - **The alias matters.** @fontsource names the 400 weight of Space Grotesk
 *     "Space Grotesk Light", so registering the file as-is makes the family
 *     unresolvable as "Space Grotesk" and every call falls back again.
 *   - **Weights merge, if the alias is the same.** Registering 400 and 700 under
 *     one alias gives one family with both weights; registering them under two
 *     names gives two families and a bold that never appears.
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { GlobalFonts } from '@napi-rs/canvas';

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const FONT_DIR = path.resolve(HERE, '..', '..', 'assets', 'fonts');

/** family -> the weights that ship, and the file slug each one is spelled with */
export const FAMILIES = {
  Inter: { slug: 'inter', weights: [400, 500, 600, 700, 800, 900] },
  'Space Grotesk': { slug: 'space-grotesk', weights: [400, 500, 700] },
  Anton: { slug: 'anton', weights: [400] },
  'Instrument Serif': { slug: 'instrument-serif', weights: [400] },
  Archivo: { slug: 'archivo', weights: [800, 900] },
};

let loaded = 0;

/** Register everything, aliased by family. Safe to call more than once. */
export function loadFonts(dir = FONT_DIR) {
  if (loaded) return loaded;
  if (!fs.existsSync(dir)) return 0;
  for (const [family, { slug, weights }] of Object.entries(FAMILIES)) {
    for (const w of weights) {
      const file = path.join(dir, `${slug}-latin-${w}-normal.woff2`);
      if (fs.existsSync(file)) {
        GlobalFonts.registerFromPath(file, family);
        loaded += 1;
      }
    }
  }
  /* anything else in the folder that is a font file, under its own name */
  for (const f of fs.readdirSync(dir)) {
    if (!/\.(ttf|otf|woff2?)$/i.test(f)) continue;
    if (Object.values(FAMILIES).some(({ slug }) => f.startsWith(`${slug}-`))) continue;
    GlobalFonts.registerFromPath(path.join(dir, f));
    loaded += 1;
  }
  return loaded;
}

/** The families the renderer can actually resolve, for the tests to assert on. */
export function familyNames() {
  return GlobalFonts.families.map((f) => f.family);
}
