/**
 * Print the house timing table, so the Python checks can read it.
 *
 * The table is the one place a duration lives, and it is JavaScript. Rather than
 * keep a second copy of it in Python - which is how two sources of truth start -
 * this prints the table and its own audit as JSON, and the check reads that.
 *
 *   node video_studio/motion/timings_cli.mjs
 *   node video_studio/motion/timings_cli.mjs --check     # exit 1 if an entry breaks its ceiling
 */
import { DURATIONS, ARRIVAL_MAX, LIGHT_MAX, CYCLE_MAX, audit } from './timings.mjs';

const payload = {
  arrivalMax: ARRIVAL_MAX,
  lightMax: LIGHT_MAX,
  cycleMax: CYCLE_MAX,
  entries: DURATIONS,
  problems: audit(),
};

process.stdout.write(JSON.stringify(payload, null, 2) + '\n');

if (process.argv.includes('--check') && payload.problems.length) {
  process.exitCode = 1;
}
