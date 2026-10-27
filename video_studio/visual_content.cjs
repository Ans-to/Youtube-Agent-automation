"use strict";
// Minimum authored content for legacy storyboard graphics. This prevents the
// renderer from inventing a quote, number, process or comparison when a model
// omits its graphic metadata. It does NOT prove that provided content matches
// the narration or is factually correct.
function contentProblem(scene, kind) {
  const text = key => typeof scene[key] === "string" && scene[key].trim().length > 0;
  const list = key => Array.isArray(scene[key]) && scene[key].length > 0 &&
    scene[key].every(value => typeof value === "string" && value.trim().length > 0);
  if (kind === "stat" && (!text("stat_value") || !text("stat_label"))) return "stat requires an explicit stat_value and stat_label";
  if (kind === "diagram" && !list("visual_nodes")) return "diagram requires explicit visual_nodes";
  if (kind === "timeline" && !list("timeline_events")) return "timeline requires explicit timeline_events";
  if (kind === "comparison" && (!text("comparison_left_title") || !text("comparison_right_title") ||
      !list("comparison_left") || !list("comparison_right"))) return "comparison requires explicit titles and content for both sides";
  if (kind === "code" && !list("code_lines")) return "code requires explicit code_lines";
  if (kind === "quote" && !text("quote")) return "quote requires an explicit quote";
  if (kind === "bar-chart" && (!Array.isArray(scene.chart_values) || scene.chart_values.length < 2 ||
      scene.chart_values.length > 6 || !scene.chart_values.every(value => typeof value === "number" && Number.isFinite(value) && value >= 0) ||
      !Array.isArray(scene.chart_labels) || scene.chart_labels.length !== scene.chart_values.length ||
      !scene.chart_labels.every(value => typeof value === "string" && value.trim()))) {
    return "bar-chart requires 2–6 explicit non-negative values and a label for each";
  }
  return null;
}
module.exports = { contentProblem };
