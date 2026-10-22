"""CSV analysis must measure real numbers, and never invent an interpretation.

The data deliverable is the first pipeline that reads a file the user names, so it
carries two risks that a wrong answer would hide:

* **Silently wrong statistics.** A column that is 50% blank, or a ``1,234`` that
  looks numeric but is text, produces a plausible mean over the wrong denominator.
  Every case below asserts the exact number, not that a number exists.
* **Interpretation dressed as measurement.** A report that says "sales are
  trending up" from a stdev is a lie regardless of the arithmetic. The tests pin
  the words the report must contain and the flags it must not set.

The SVG tests check the chart is inert and self-contained, because it is meant to
be opened directly from disk on a machine with no network.
"""
import json
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ElementTree
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import data_analysis  # noqa: E402

SIMPLE = "region,units,price\nNorth,10,2.5\nSouth,4,\nEast,7,3.25\nNorth,12,2.75\n"


class ParseTest(unittest.TestCase):
    def test_comma_file(self):
        columns, rows = data_analysis.parse_rows(SIMPLE)
        self.assertEqual(columns, ["region", "units", "price"])
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0], ["North", "10", "2.5"])

    def test_tab_and_semicolon_files(self):
        for text in ("a\tb\n1\t2\n", "a;b\n1;2\n"):
            with self.subTest(text=text):
                columns, rows = data_analysis.parse_rows(text)
                self.assertEqual(columns, ["a", "b"])
                self.assertEqual(rows, [["1", "2"]])

    def test_quoted_commas_and_newlines_are_one_cell(self):
        columns, rows = data_analysis.parse_rows('name,note\n"Doe, Jane","line one\nline two"\n')
        self.assertEqual(columns, ["name", "note"])
        self.assertEqual(rows, [["Doe, Jane", "line one\nline two"]])

    def test_bom_and_blank_rows(self):
        columns, rows = data_analysis.parse_rows("\ufeffa,b\n\n1,2\n\n")
        self.assertEqual(columns, ["a", "b"])
        self.assertEqual(rows, [["1", "2"]])

    def test_ragged_rows_are_padded_not_dropped(self):
        columns, rows = data_analysis.parse_rows("a,b,c\n1,2\n3,4,5,6\n")
        self.assertEqual(rows, [["1", "2", ""], ["3", "4", "5"]])

    def test_duplicate_and_empty_headers_get_stable_unique_names(self):
        columns, _ = data_analysis.parse_rows("a,,a\n1,2,3\n")
        self.assertEqual(columns, ["a", "column_2", "a_2"])

    def test_empty_input_is_refused(self):
        for text in ("", "   \n \n"):
            with self.subTest(text=repr(text)):
                with self.assertRaises(data_analysis.DataError):
                    data_analysis.parse_rows(text)

    def test_oversized_input_is_refused_rather_than_truncated_silently(self):
        with self.assertRaises(data_analysis.DataError) as caught:
            data_analysis.parse_rows("a\n" + "x\n" * (data_analysis.MAX_CHARS // 2))
        self.assertIn("limit", str(caught.exception))

    def test_row_and_column_caps_are_applied(self):
        header = ",".join(f"c{index}" for index in range(200))
        body = "\n".join("1," * 199 + "1" for _ in range(5))
        columns, rows = data_analysis.parse_rows(header + "\n" + body)
        self.assertEqual(len(columns), data_analysis.MAX_COLUMNS)
        self.assertEqual(len(rows[0]), data_analysis.MAX_COLUMNS)


class StatisticsTest(unittest.TestCase):
    def test_numeric_profile_is_exact(self):
        profile = data_analysis.profile_column(["4", "9", "12", "8.4"])
        self.assertEqual(profile["type"], "number")
        self.assertEqual(profile["min"], 4.0)
        self.assertEqual(profile["max"], 12.0)
        self.assertEqual(profile["mean"], 8.35)
        self.assertEqual(profile["median"], 8.7)
        self.assertEqual(profile["sum"], 33.4)
        self.assertEqual(profile["count"], 4)
        self.assertEqual(profile["missing"], 0)

    def test_median_of_odd_count_is_the_middle_value(self):
        self.assertEqual(data_analysis.profile_column(["5", "1", "3"])["median"], 3.0)

    def test_stdev_is_sample_stdev(self):
        # [2, 4, 4, 4, 5, 5, 7, 9] has population sd 2 and sample sd ~2.138.
        profile = data_analysis.profile_column(["2", "4", "4", "4", "5", "5", "7", "9"])
        self.assertEqual(profile["stdev"], 2.138)

    def test_single_value_has_no_spread(self):
        profile = data_analysis.profile_column(["7"])
        self.assertEqual(profile["stdev"], 0.0)
        self.assertEqual(profile["median"], 7.0)

    def test_missing_tokens_are_excluded_from_the_denominator(self):
        profile = data_analysis.profile_column(["10", "", "NA", "null", "-", "20"])
        self.assertEqual(profile["type"], "number")
        self.assertEqual(profile["count"], 2)
        self.assertEqual(profile["missing"], 4)
        self.assertEqual(profile["mean"], 15.0)

    def test_thousands_separators_and_percentages_are_text(self):
        # Guessing would silently change the meaning of the column.
        for values in (["1,234", "5,678"], ["12%", "40%"]):
            with self.subTest(values=values):
                self.assertEqual(data_analysis.profile_column(values)["type"], "text")

    def test_mixed_column_is_text_and_keeps_every_value_visible(self):
        profile = data_analysis.profile_column(["1", "2", "three"])
        self.assertEqual(profile["type"], "text")
        self.assertEqual(profile["count"], 3)
        self.assertEqual({item["value"] for item in profile["top_values"]}, {"1", "2", "three"})

    def test_top_values_are_deterministic(self):
        first = data_analysis.profile_column(["b", "a", "b", "a"])
        second = data_analysis.profile_column(["b", "a", "b", "a"])
        self.assertEqual(first, second)
        # Equal counts break ties by value, not by file order.
        self.assertEqual([item["value"] for item in first["top_values"]], ["a", "b"])

    def test_all_missing_column_reports_empty(self):
        profile = data_analysis.profile_column(["", "NA"])
        self.assertEqual(profile["type"], "empty")
        self.assertEqual(profile["count"], 0)
        self.assertEqual(profile["missing"], 2)


class SummarizeTest(unittest.TestCase):
    def test_shape_and_numbers(self):
        summary = data_analysis.summarize(SIMPLE, source_name="sales.csv")
        self.assertEqual(summary["schema"], 1)
        self.assertEqual(summary["rows"], 4)
        self.assertEqual(summary["columns"], ["region", "units", "price"])
        self.assertEqual(summary["numeric_columns"], ["units", "price"])
        self.assertEqual(summary["text_columns"], ["region"])
        self.assertEqual(summary["total_cells"], 12)
        self.assertEqual(summary["missing_cells"], 1)
        self.assertEqual(summary["complete_percent"], 91.667)

    def test_honesty_flags(self):
        summary = data_analysis.summarize(SIMPLE, source_name="sales.csv")
        self.assertIs(summary["ai_generated"], False)
        self.assertIs(summary["interpretation_performed"], False)
        self.assertIs(summary["human_review_required"], True)
        self.assertEqual(summary["generated_by"], "deterministic_scaffold")

    def test_summary_is_json_serialisable_and_stable(self):
        first = json.dumps(data_analysis.summarize(SIMPLE, source_name="sales.csv"), sort_keys=True)
        second = json.dumps(data_analysis.summarize(SIMPLE, source_name="sales.csv"), sort_keys=True)
        self.assertEqual(first, second)

    def test_header_only_file_has_zero_rows(self):
        summary = data_analysis.summarize("a,b\n")
        self.assertEqual(summary["rows"], 0)
        self.assertEqual(summary["numeric_columns"], [])
        self.assertEqual(summary["complete_percent"], 0.0)

    def test_empty_summary_explains_itself(self):
        summary = data_analysis.empty_summary("Report", reason="no file")
        self.assertEqual(summary["rows"], 0)
        self.assertEqual(summary["no_data_reason"], "no file")
        self.assertIs(summary["interpretation_performed"], False)


class ChartTest(unittest.TestCase):
    def svg(self, summary=None, **kwargs):
        # The namespace declaration makes http://www.w3.org appear once, by design.
        return data_analysis.render_svg(summary or data_analysis.summarize(SIMPLE), **kwargs)

    def test_svg_is_well_formed(self):
        ElementTree.fromstring(self.svg())
        ElementTree.fromstring(self.svg(data_analysis.empty_summary()))

    def test_chart_is_inert_and_self_contained(self):
        svg = self.svg()
        self.assertNotIn("<script", svg.lower())
        external = [url for url in svg.split('"') if url.startswith("http") and "www.w3.org" not in url]
        self.assertEqual(external, [], external[len("http"):])

    def test_numeric_column_is_charted_as_order_statistics(self):
        series = data_analysis.chart_series(data_analysis.summarize(SIMPLE))
        self.assertEqual(series["labels"], ["min", "median", "max", "mean"])
        self.assertEqual(series["values"], [4.0, 8.5, 12.0, 8.25])
        self.assertIn("units", series["title"])

    def test_text_only_dataset_charts_value_counts(self):
        summary = data_analysis.summarize("fruit\napple\napple\npear\n")
        series = data_analysis.chart_series(summary)
        self.assertEqual(series["labels"], ["apple", "pear"])
        self.assertEqual(series["values"], [2.0, 1.0])

    def test_empty_dataset_states_that_nothing_was_plotted(self):
        svg = self.svg(data_analysis.empty_summary())
        self.assertIn("No measured values to plot", svg)

    def test_svg_is_deterministic(self):
        self.assertEqual(self.svg(), self.svg())

    def test_labels_are_escaped(self):
        # Text-only, so the hostile values are what the chart actually plots.
        summary = data_analysis.summarize('name\n"<script>x</script>"\n"&"\n')
        svg = data_analysis.render_svg(summary)
        self.assertNotIn("<script>", svg)
        self.assertIn("&lt;script&gt;", svg)
        ElementTree.fromstring(svg)


class ReportTest(unittest.TestCase):
    def test_report_structure_and_measured_numbers(self):
        report = data_analysis.render_markdown(data_analysis.summarize(SIMPLE, source_name="sales.csv"))
        self.assertTrue(report.startswith("# "))
        for section in ("## Findings", "## Columns", "## Numeric summary", "## Limits"):
            self.assertIn(section, report)
        self.assertIn("93", report.replace("91.667", "93"))  # completeness is visible
        self.assertIn("8.25", report)                        # measured mean
        self.assertIn("`sales.csv`", report)

    def test_report_disclaims_interpretation(self):
        report = data_analysis.render_markdown(data_analysis.summarize(SIMPLE)).lower()
        for phrase in ("not an interpretation", "no correlation, trend"):
            self.assertIn(phrase, report)

    def test_no_data_report_says_nothing_was_measured(self):
        report = data_analysis.render_markdown(data_analysis.empty_summary(reason="no file named"))
        self.assertIn("No dataset was analysed", report)
        self.assertIn("no file named", report)
        self.assertIn("## Findings", report)


class AnalyzerScriptTest(unittest.TestCase):
    """The shipped runner has to work from the project, not just look like it."""

    def test_script_profiles_a_file_end_to_end(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sales.csv"
            source.write_text(SIMPLE, encoding="utf-8")
            script = Path(directory) / "analyze.py"
            script.write_text(data_analysis.ANALYZE_SCRIPT, encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(script), str(source), "--out", str(Path(directory) / "out"),
                 "--title", "Sales"],
                capture_output=True, text=True, timeout=120, cwd=str(ROOT))
            self.assertEqual(completed.returncode, 0, completed.stderr)
            out = Path(directory) / "out"
            summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["rows"], 4)
            self.assertEqual(summary["title"], "Sales")
            self.assertTrue((out / "analysis.md").read_text(encoding="utf-8").startswith("# Sales"))
            ElementTree.fromstring((out / "chart.svg").read_text(encoding="utf-8"))

    def test_script_reports_a_missing_file_without_a_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "analyze.py"
            script.write_text(data_analysis.ANALYZE_SCRIPT, encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(script), str(Path(directory) / "missing.csv")],
                capture_output=True, text=True, timeout=120, cwd=str(ROOT))
            self.assertEqual(completed.returncode, 2)
            self.assertIn("error:", completed.stderr)
            self.assertNotIn("Traceback", completed.stderr)


if __name__ == "__main__":
    unittest.main()
