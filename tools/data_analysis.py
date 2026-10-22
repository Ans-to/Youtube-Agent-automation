#!/usr/bin/env python3
"""Measured CSV analysis with no third-party dependencies.

The roadmap's second Phase 2 goal was "analyze this CSV and chart it", and the
system had no way to do it at all. This module is the measurement layer: it parses
a delimited text file, profiles every column, and renders a chart and a report
from the numbers it actually computed.

Three rules shape it:

* **Standard library only.** No pandas, no numpy, no plotting package. The whole
  point of this project is that it runs on a phone with nothing installed.
* **Deterministic.** Same input, same bytes out: columns in file order, keys
  sorted, floats rounded, chart bars in row order. A report that changes between
  runs cannot be reviewed.
* **No interpretation.** It reports counts, ranges and central tendency. It does
  not say whether a number is good, surprising, or a trend. The report says this
  out loud, because a statistical summary dressed as insight is the most common
  way a data tool lies.

Usage::

    from data_analysis import summarize, render_svg, render_markdown
    summary = summarize(csv_text, source_name="sales.csv")
    svg = render_svg(summary)
    report = render_markdown(summary)
"""
from __future__ import annotations

import csv
import io
import json
import math
import re
from collections import Counter
from xml.sax.saxutils import escape

#: Bounds that keep a hostile or accidental file from exhausting a phone.
MAX_CHARS = 2_000_000
MAX_ROWS = 20_000
MAX_COLUMNS = 60
MAX_LABEL_CHARS = 24
CHART_BARS = 12

#: Tokens treated as "no value". Kept small and explicit so a real category named
#: "None" is not silently discarded by accident — the column profile still counts
#: how many cells were treated as missing.
MISSING_TOKENS = frozenset({"", "na", "n/a", "null", "nil", "none", "nan", "-", "--"})

DEFAULT_TITLE = "Dataset summary"


class DataError(ValueError):
    """The input could not be read as a delimited table."""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def detect_delimiter(text: str) -> str:
    """Pick a delimiter from the header line, defaulting to a comma."""
    header = text.splitlines()[0] if text.splitlines() else ""
    counts = {delimiter: header.count(delimiter) for delimiter in (",", "\t", ";", "|")}
    best = max(counts, key=lambda key: (counts[key], key == ","))
    return best if counts[best] > 0 else ","


def parse_rows(text: str) -> tuple[list[str], list[list[str]]]:
    """Return (header, rows). Blank trailing rows are dropped, ragged rows padded."""
    if not isinstance(text, str):
        raise DataError("input must be text")
    text = text.lstrip("\ufeff")
    if len(text) > MAX_CHARS:
        raise DataError(f"input exceeds the {MAX_CHARS}-character analysis limit")
    if not text.strip():
        raise DataError("input is empty")

    reader = csv.reader(io.StringIO(text), delimiter=detect_delimiter(text))
    try:
        records = [row for row in reader if any(cell.strip() for cell in row)]
    except csv.Error as exc:
        raise DataError(f"input is not valid delimited text: {exc}") from exc
    if not records:
        raise DataError("input has no non-empty rows")

    header = [cell.strip() for cell in records[0]][:MAX_COLUMNS]
    if not header:
        raise DataError("header row is empty")
    # Duplicate or empty header cells get a stable, unique name so every column
    # can be addressed in the report and chart.
    seen: Counter[str] = Counter()
    columns: list[str] = []
    for index, name in enumerate(header):
        base = name or f"column_{index + 1}"
        seen[base] += 1
        columns.append(base if seen[base] == 1 else f"{base}_{seen[base]}")

    rows: list[list[str]] = []
    for record in records[1:MAX_ROWS + 1]:
        cells = [cell.strip() for cell in record[:len(columns)]]
        if len(cells) < len(columns):
            cells.extend([""] * (len(columns) - len(cells)))
        rows.append(cells)
    return columns, rows


# ---------------------------------------------------------------------------
# Column statistics
# ---------------------------------------------------------------------------

def _as_number(value: str):
    """Parse a plain number. Thousands separators are treated as text on purpose."""
    candidate = value.strip()
    if not candidate:
        return None
    try:
        number = float(candidate)
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    return number


def _round(value: float) -> float:
    return round(float(value), 3)


def _quantile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * fraction
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return sorted_values[int(position)]
    weight = position - low
    return sorted_values[low] * (1 - weight) + sorted_values[high] * weight


def profile_column(values: list[str]) -> dict:
    """Describe one column: completeness, type, and a summary appropriate to it."""
    missing = 0
    present: list[str] = []
    for value in values:
        if value.strip().lower() in MISSING_TOKENS:
            missing += 1
        else:
            present.append(value)

    numbers = [_as_number(value) for value in present]
    numeric = [number for number in numbers if number is not None]
    is_numeric = bool(present) and len(numeric) == len(present)

    profile: dict = {
        "count": len(present),
        "missing": missing,
        "unique": len({value for value in present}),
    }
    if is_numeric:
        ordered = sorted(numeric)
        mean = sum(ordered) / len(ordered)
        variance = (sum((value - mean) ** 2 for value in ordered) / (len(ordered) - 1)
                    if len(ordered) > 1 else 0.0)
        profile.update({
            "type": "number",
            "min": _round(ordered[0]),
            "max": _round(ordered[-1]),
            "mean": _round(mean),
            "median": _round(_quantile(ordered, 0.5)),
            "stdev": _round(math.sqrt(variance)),
            "sum": _round(sum(ordered)),
        })
    else:
        counts = Counter(present)
        # Sorted by count then value: a dict's insertion order would follow the
        # file and make two identical datasets serialise differently.
        top = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:5]
        profile.update({
            "type": "text" if present else "empty",
            "top_values": [{"value": value[:80], "count": count} for value, count in top],
        })
    return profile


def summarize(text: str, *, source_name: str = "", title: str = "") -> dict:
    """Profile every column and return a JSON-safe summary."""
    columns, rows = parse_rows(text)
    delimiter = detect_delimiter(text)
    profiles = {
        name: profile_column([row[index] for row in rows])
        for index, name in enumerate(columns)
    }
    numeric_columns = [name for name, profile in profiles.items() if profile["type"] == "number"]
    text_columns = [name for name, profile in profiles.items() if profile["type"] == "text"]
    cells = len(rows) * len(columns)
    return {
        "schema": 1,
        "title": (title or DEFAULT_TITLE)[:120],
        "source": source_name[:200],
        "delimiter": "tab" if delimiter == "\t" else delimiter,
        "rows": len(rows),
        "columns": list(columns),
        "numeric_columns": numeric_columns,
        "text_columns": text_columns,
        "missing_cells": sum(profile["missing"] for profile in profiles.values()),
        "total_cells": cells,
        "complete_percent": _round(100.0 * (cells - sum(p["missing"] for p in profiles.values())) / cells)
        if cells else 0.0,
        "columns_detail": profiles,
        "generated_by": "deterministic_scaffold",
        "ai_generated": False,
        "research_performed": False,
        "human_review_required": True,
        "interpretation_performed": False,
    }


def empty_summary(title: str = "", reason: str = "") -> dict:
    """A summary-shaped record for a run that had no input file.

    The keys match a real summary so a consumer does not have to special-case it,
    and the reasons are explicit so nobody can mistake it for measured data.
    """
    return {
        "schema": 1,
        "title": (title or DEFAULT_TITLE)[:120],
        "source": "",
        "delimiter": "",
        "rows": 0,
        "columns": [],
        "numeric_columns": [],
        "text_columns": [],
        "missing_cells": 0,
        "total_cells": 0,
        "complete_percent": 0.0,
        "columns_detail": {},
        "generated_by": "deterministic_scaffold",
        "ai_generated": False,
        "research_performed": False,
        "human_review_required": True,
        "interpretation_performed": False,
        "no_data_reason": (reason or "No CSV was supplied with this request.")[:300],
    }


# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------

def _short(value: str, limit: int = MAX_LABEL_CHARS) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def chart_series(summary: dict) -> dict:
    """Choose a deterministic series to plot from real data.

    Preference: the first numeric column, plotted against the first text column
    (or the row number). With no numeric column, the top value counts of the first
    column are plotted instead — a real distribution, not a placeholder.
    """
    detail = summary.get("columns_detail") or {}
    columns = summary.get("columns") or []
    rows = int(summary.get("rows") or 0)
    labels: list[str] = []
    values: list[float] = []
    label = ""

    numeric = summary.get("numeric_columns") or []
    if numeric and rows:
        # Four order statistics of one real column. Plotting individual rows would
        # make the image depend on row order and overflow the bar budget; these
        # four are stable, comparable, and all measured.
        column = numeric[0]
        profile = detail.get(column, {})
        label = f"{column}: min / median / max / mean"
        labels = ["min", "median", "max", "mean"]
        values = [float(profile.get("min", 0.0)), float(profile.get("median", 0.0)),
                  float(profile.get("max", 0.0)), float(profile.get("mean", 0.0))]
    elif columns:
        column = columns[0]
        top_values = detail.get(column, {}).get("top_values") or []
        label = f"{column} — most common values"
        labels = [_short(item["value"]) for item in top_values][:CHART_BARS]
        values = [float(item["count"]) for item in top_values][:CHART_BARS]

    return {"title": label or "No plottable column", "labels": labels, "values": values}


def render_svg(summary: dict, *, width: int = 720, height: int = 400) -> str:
    """A self-contained SVG bar chart. No scripts, no external references."""
    series = chart_series(summary)
    labels, values = series["labels"], series["values"]
    title = series["title"]
    pad_left, pad_right, pad_top, pad_bottom = 64, 24, 56, 72
    plot_width = max(1, width - pad_left - pad_right)
    plot_height = max(1, height - pad_top - pad_bottom)
    baseline = pad_top + plot_height
    top_value = max(values) if values else 0.0
    bottom_value = min(min(values), 0.0) if values else 0.0
    span = (top_value - bottom_value) or 1.0

    def y_for(value: float) -> float:
        return baseline - ((value - bottom_value) / span) * plot_height

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">',
        f'<rect width="{width}" height="{height}" fill="#0b0b0f"/>',
        f'<text x="{pad_left}" y="32" fill="#f4f2ec" font-family="system-ui,Segoe UI,sans-serif" '
        f'font-size="18" font-weight="600">{escape(_short(title, 70))}</text>',
        f'<text x="{pad_left}" y="52" fill="#a7a7b3" font-family="system-ui,Segoe UI,sans-serif" '
        f'font-size="12">{escape(summary.get("source") or "no source file")} · '
        f'{summary.get("rows", 0)} rows · {len(summary.get("columns") or [])} columns</text>',
        f'<line x1="{pad_left}" y1="{baseline}" x2="{pad_left + plot_width}" y2="{baseline}" '
        f'stroke="#353541" stroke-width="1"/>',
    ]

    if not values:
        parts.append(
            f'<text x="{pad_left}" y="{pad_top + plot_height / 2}" fill="#a7a7b3" '
            f'font-family="system-ui,Segoe UI,sans-serif" font-size="14">'
            f'No measured values to plot.</text>')
    else:
        count = len(values)
        slot = plot_width / count
        bar_width = max(8.0, min(64.0, slot * 0.6))
        for index, (label, value) in enumerate(zip(labels, values)):
            left = pad_left + slot * index + (slot - bar_width) / 2
            top = min(y_for(value), y_for(max(bottom_value, 0.0)))
            bar_height = max(1.0, abs(y_for(value) - y_for(max(bottom_value, 0.0))))
            parts.append(
                f'<rect x="{left:.2f}" y="{top:.2f}" width="{bar_width:.2f}" '
                f'height="{bar_height:.2f}" fill="#c8ff3d" rx="3"/>')
            parts.append(
                f'<text x="{left + bar_width / 2:.2f}" y="{top - 6:.2f}" fill="#f4f2ec" '
                f'text-anchor="middle" font-family="system-ui,Segoe UI,sans-serif" '
                f'font-size="11">{_format_number(value)}</text>')
            parts.append(
                f'<text x="{left + bar_width / 2:.2f}" y="{baseline + 18:.2f}" fill="#a7a7b3" '
                f'text-anchor="middle" font-family="system-ui,Segoe UI,sans-serif" '
                f'font-size="11">{escape(_short(label, 16))}</text>')

    parts.append(
        f'<text x="{pad_left}" y="{height - 14}" fill="#6f6f7d" '
        f'font-family="system-ui,Segoe UI,sans-serif" font-size="11">'
        f'Generated offline by Agent HQ from measured values. No interpretation was applied.</text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _format_number(value: float) -> str:
    if value == int(value) and abs(value) < 1e15:
        return f"{int(value):,}"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _table_row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def render_markdown(summary: dict) -> str:
    """A human-readable report built only from measured values."""
    title = summary.get("title") or DEFAULT_TITLE
    lines = [
        f"# {title}",
        "",
        "> Generated offline by Agent HQ from the numbers below. This is a",
        "> statistical profile, not an interpretation: it does not judge whether any",
        "> value is good, unusual, or a trend, and it contains no external research.",
        "",
    ]
    if summary.get("no_data_reason"):
        lines.extend([
            f"**No dataset was analysed.** {summary['no_data_reason']}",
            "",
            "Run `python analyze.py your-file.csv` in this folder to produce the real",
            "report, or re-submit the request naming a `.csv` file inside the project.",
            "",
        ])
    else:
        lines.extend([
            f"- Source: `{summary.get('source') or 'unspecified'}`",
            f"- Rows: {summary.get('rows', 0)}",
            f"- Columns: {len(summary.get('columns') or [])}",
            f"- Complete cells: {summary.get('complete_percent', 0.0)}%",
            "",
        ])

    lines.extend(["## Findings", ""])
    if summary.get("no_data_reason"):
        lines.append("Nothing was measured, so there are no findings to report.")
    else:
        numeric = summary.get("numeric_columns") or []
        text = summary.get("text_columns") or []
        lines.append(
            f"{len(summary.get('columns') or [])} columns were profiled: {len(numeric)} numeric, "
            f"{len(text)} text. "
            + (f"Missing values account for {summary.get('missing_cells', 0)} of "
               f"{summary.get('total_cells', 0)} cells." if summary.get("missing_cells")
               else "No cells were treated as missing.")
        )

    columns = summary.get("columns") or []
    detail = summary.get("columns_detail") or {}
    if detail:
        lines.extend(["", "## Columns", "",
                      _table_row(["Column", "Type", "Filled", "Missing", "Unique"]),
                      _table_row(["---", "---", "---", "---", "---"])])
        for name in columns:
            profile = detail.get(name, {})
            lines.append(_table_row([
                f"`{name}`", str(profile.get("type", "unknown")),
                str(profile.get("count", 0)), str(profile.get("missing", 0)),
                str(profile.get("unique", 0)),
            ]))

    numeric_rows = [(name, detail[name]) for name in columns
                    if detail.get(name, {}).get("type") == "number"]
    if numeric_rows:
        lines.extend(["", "## Numeric summary", "",
                      _table_row(["Column", "Min", "Median", "Max", "Mean", "Stdev"]),
                      _table_row(["---", "---", "---", "---", "---", "---"])])
        for name, profile in numeric_rows:
            lines.append(_table_row([
                f"`{name}`", _format_number(profile["min"]), _format_number(profile["median"]),
                _format_number(profile["max"]), _format_number(profile["mean"]),
                _format_number(profile["stdev"]),
            ]))

    text_rows = [(name, detail[name]) for name in columns
                 if detail.get(name, {}).get("type") == "text"]
    if text_rows:
        lines.extend(["", "## Most common values", ""])
        for name, profile in text_rows:
            top = profile.get("top_values") or []
            rendered = ", ".join(f"`{item['value']}` ({item['count']})" for item in top)
            lines.append(f"- **{name}**: {rendered or 'no values'}")

    lines.extend([
        "",
        "## Limits",
        "",
        "- These are counts and central tendency only. No correlation, trend,",
        "  significance, or causal claim is made, because none was computed.",
        "- Numbers are parsed as plain decimals. A value such as `1,234` or `12%` is",
        "  treated as text and excluded from numeric statistics.",
        f"- Analysis is bounded to {MAX_ROWS:,} rows, {MAX_COLUMNS} columns, and "
        f"{MAX_CHARS:,} characters; a larger file is truncated, not extrapolated.",
        "- Dates are treated as text. Ordering and gaps in time are not measured.",
        "- Reproduce this report with `python analyze.py <same file>` from the "
        "folder that contains it; nothing here depends on a model or a network.",
        "",
    ])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Reproducible runner
# ---------------------------------------------------------------------------

ANALYZE_SCRIPT = '''#!/usr/bin/env python3
"""Summarise a CSV file: summary.json, analysis.md and chart.svg.

Generated by Agent HQ. Standard library only, so it runs anywhere Python does.

    python analyze.py sales.csv
    python analyze.py sales.csv --out out --title "Q3 sales"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Profile a CSV file.")
    parser.add_argument("source", help="delimited text file to analyse")
    parser.add_argument("--out", default=".", help="output directory")
    parser.add_argument("--title", default="", help="report title")
    args = parser.parse_args(argv)

    source = Path(args.source)
    try:
        text = source.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # Find the project module by walking up from this file *and* from the current
    # directory, so the script works whether it is run from the artifact folder,
    # the repo root, or copied somewhere else and run from the project.
    script_dir, cwd = Path(__file__).resolve().parent, Path.cwd().resolve()
    search = [script_dir, *script_dir.parents, cwd, *cwd.parents]
    for parent in search:
        if (parent / "tools" / "data_analysis.py").is_file():
            sys.path.insert(0, str(parent))
            break
    try:
        from tools.data_analysis import render_markdown, render_svg, summarize
    except ImportError:
        print("error: run this from inside the Agent HQ project (tools/data_analysis.py missing)",
              file=sys.stderr)
        return 2

    try:
        summary = summarize(text, source_name=source.name, title=args.title)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\\n",
                                      encoding="utf-8")
    (out / "analysis.md").write_text(render_markdown(summary), encoding="utf-8")
    (out / "chart.svg").write_text(render_svg(summary), encoding="utf-8")
    print(f"{summary['rows']} rows x {len(summary['columns'])} columns -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''
