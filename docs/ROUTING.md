# Task routing — which pipeline runs, and why

`agents/routing.py` decides what work a goal needs. `agents/orchestrate.py`
executes the decision. The split exists because the previous arrangement — a
handful of regular expressions sitting next to the code that ran the builders —
had two problems that no amount of extra patterns would fix:

1. A goal the patterns did not match could not reach a builder at all, and
   nothing recorded that the goal had been considered and rejected.
2. There was no place to put a routing policy that had to hold for *every* chooser
   once a model started choosing.

## The catalog

Six pipelines exist. The catalog is the single source of truth: it is what the
model is shown, what validation checks against, and what the tests read.

| Pipeline | Executor | Deliverable | What it produces |
| --- | --- | --- | --- |
| `video_production` | `video_studio/production.py` | `video_package` | research, script, storyboard, metadata, QA; MP4 only when the guards allow |
| `web_build` | `tools/tool_agent.py` | `web` | a complete offline page or small web app, CSP-locked, no external assets |
| `document_deliverable` | `tools/tool_agent.py` | `document` | `deliverable.md` plus `deliverable.json` metadata |
| `cli_tool` | `tools/tool_agent.py` | `cli` | `tool.py` (stdlib, `--self-test`) plus a README |
| `data_deliverable` | `tools/tool_agent.py` + `tools/data_analysis.py` | `data` | `summary.json`, `analysis.md`, `chart.svg`, and a re-runnable `analyze.py` |
| `product_prototype` | `product_studio/build_product.py` | `product_prototype` | a draft prototype package with an archive and status file |

Each pipeline declares the argument keys it accepts, with types and bounds, and
the phrasings it must never claim.

## How a decision is made

```
task ──► deterministic router ──► compare ──► route record
   │            (patterns)            │            │
   └──────► model router ─────────────┘            ▼
              (catalog only)               execution (orchestrate)
```

* **Deterministic router (no model).** Explicit patterns choose a pipeline. This
  is the behaviour that existed before the router, moved rather than improved: if
  the old code built a page for a goal, it still does. It also runs as a
  comparison whenever a model is available.
* **Model router (local model enabled).** The model sees the pipeline catalog, the
  tool catalog the tool-loop pipelines may use, and the task. It answers with a
  JSON list of pipeline ids and arguments — or an empty list, which is a valid and
  frequently correct answer. It is choosing among existing code paths. It cannot
  name a new pipeline, pass shell text, widen an argument's bounds, or write files.
* **Validation, not trust.** Unknown ids, duplicate ids, a second tool-loop
  pipeline, unknown argument keys, wrong types, and out-of-range values are
  dropped with a recorded reason. A response that is not JSON at all falls back to
  the deterministic router rather than failing the task.
* **Vetoes, for both.** A veto encodes a decision that is about policy, not
  preference, so it applies to model choices too:

  | Veto | Why it exists |
  | --- | --- |
  | Advisory request (`explain`, `how do I`, `what is`, `review`, `summarise` …) with no first-person produce marker | The offline path cannot answer a question or summarise a source; returning a scaffold as though it had would be a false completion |
  | No build verb or measurement verb in the goal | Nothing was asked to be produced |
  | Measurement request with no dataset behind it | "Analyse my landing page" is advice; "analyse sales.csv" is work |
  | "YouTube automation studio / software / system / platform" for `video_production` | That is a software request; it was previously mis-rendered as a video |

## Measurement requests are work, questions are not

"Analyse sales.csv" and "explain how to analyse survey data" share a verb but not
an intent. The router separates them on two independent signals:

- **a dataset is named** (a `.csv`/`.tsv` reference), or a measurement verb sits
  within one clause of `data`, `dataset`, `csv`, `table` or `numbers`;
- **the request opens with a question** (`how do I`, `what is`, `explain`,
  `review`, `compare`…). A question opening wins unless the request also asks in
  the first person (`write me`, `I need`, `please build`).

A named dataset is only carried into the arguments when it is a relative path. An
absolute path, a drive letter, a `..` segment, or a dot-directory is dropped
before execution, and the reader in `agents/orchestrate.py` refuses the same
shapes independently — so neither layer alone is load-bearing.

## The record

Every run writes `routing.json` beside `pipeline-status.json`, and the same object
appears as `manifest["routing"]`:

```json
{
  "mode": "model",
  "pipelines": ["document_deliverable"],
  "requests": [{"pipeline": "document_deliverable", "args": {"title": "Q3 ops review"}, "why": "..."}],
  "heuristic_pipelines": [],
  "agreement": "model_only",
  "advisory": false,
  "vetoed": [],
  "rejected": ["entry 0 (document_deliverable): unknown argument 'shell'"],
  "notes": "clear"
}
```

`mode` is one of `heuristic`, `model`, `heuristic_after_model_error`, or
`heuristic_after_rejected_plan`. `agreement` is `match`, `differs`,
`model_only`, `model_chose_nothing`, or `not_applicable`. `heuristic_pipelines` is
kept on purpose: when the model reaches a pipeline the patterns miss, the gap is
visible and can be closed later instead of being lost.

## What execution still owns

Routing is a decision, not a permission. The executor keeps the guards that must
hold regardless of who chose the pipeline:

- `--render` is added only when a local model is enabled; otherwise the render is
  reported as `blocked` and the package is still built.
- A template demo is only used for an explicitly labelled demo request.
- `run_command` inside the tool loop stays opt-in (`AGENT_HQ_ALLOW_EXEC=1`).
- Publishing, payment, deletion, and messaging remain outside automatic execution.

## Limits

- **The deterministic router is conservative on purpose.** It does not catch
  "build me a landing page" (the article is not adjacent to the verb) or "make a
  data report"; with a model enabled those route correctly, and the record shows
  the disagreement.
- **A route is not a result.** `web_build`, `document_deliverable`, and `cli_tool`
  produce labelled deterministic scaffolds without a model. The document scaffold
  carries structure and acceptance criteria, not research. The CLI scaffold
  carries working plumbing and a self-test, not the task's algorithm. Both say so
  in the artifact.
- **Three of the roadmap's ten held-out goals are reachable** ("write a
  changelog", "build a CLI that dedupes photos", "analyse this CSV and chart
  it"). The CLI goal is routed but its scaffold is plumbing, not a working
  deduplicator. Test-and-fix tasks still have no pipeline.
- **The data pipeline measures; it does not interpret.** It reports counts,
  ranges, central tendency and a chart of order statistics. No trend, correlation
  or causal claim is computed, and the report says so.
- **One tool-loop pipeline per task.** Multi-artifact plans are not implemented;
  the router returns a list, but the loop runs once.
