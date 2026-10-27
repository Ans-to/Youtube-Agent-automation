/** Data charts must not show a final number over an unfinished bar. */
export function chartBarState(value, maximum, progress) {
  if (!Number.isFinite(value) || value < 0 || !Number.isFinite(maximum) || maximum <= 0 ||
      !Number.isFinite(progress)) throw new Error('invalid chart bar state');
  const shown = Math.max(0, Math.min(1, progress));
  return { relativeHeight: value / maximum * shown, labelVisible: shown >= .999, started: shown > .001 };
}
