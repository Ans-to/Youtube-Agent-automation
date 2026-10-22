# Changes — every write, shown as a change

`tools/review.py` implements the last item of Phase 3: a run should be reviewable
by looking at what it changed, not by reading whole files back.

## What a run produces

Two artifacts per builder, beside the files it wrote:

| File | What it is |
| --- | --- |
| `changes.json` | machine-readable: every touched path, whether it was created, modified, deleted or binary, the added/removed line counts, and the diff lines |
| `changes.md` | the same, rendered for a person, with fenced diffs |

And one index per run:

```
workspace/orchestration/run/review/changes.md
```

It names each builder, the artifact directory, the file list and the counts, with
a pointer to that builder's full diff. It deliberately does **not** restate file
content — an index that reprints the artifact is not a review, it is a second
copy.

## How the diff is taken

Before the first step that writes a path, the tool loop reads the file's current
content into a baseline. After the run, each baseline path is compared with what
is on disk:

```
--- a/index.html
+++ b/index.html
@@ -1 +1,2 @@
 <h1>Bakery</h1>
+<p>Fresh bread daily</p>
```

The **first** capture wins. If a failed attempt writes a file and a repair writes
it again, the diff still runs from what the run found to what it left behind —
never from a half-finished attempt.

Test repair uses the same module: each attempted patch carries its own diff in
`test-report.json` and `fix-plan.md`, including patches that were reverted, because
"what it tried and undid" is exactly what a reviewer needs to see.

## Bounds

- 80 diff lines per file, 40 files per report.
- A binary file is named, not rendered.
- A manifest carries names and counts only, never file bodies.

Generated files can be large; a review that is a second copy of the artifact is
not reviewable.

## What verification checks

`agents/orchestrate.py` refuses a tool-loop artifact without a valid change report:

- `changes.json` and `changes.md` must exist;
- the report must declare schema 1 and its `files_changed` count must match its
  own file list;
- every path must be relative and stay inside the artifact directory;
- a `created` or `modified` entry must carry diff lines unless it is binary.

For test repair, a `model_patch` record without a diff fails verification, as does
a record that is both `verified` and `reverted`.

## Honest limits

- A diff shows what changed in a file; it does not say the change is good, and it
  does not show *why*. Intent lives in the plan and the report, not the diff.
- Renames are seen as a deletion plus a creation.
- Only files the builder wrote are diffed. A file changed by a subprocess the
  builder ran (a formatter, a code generator) appears only if the builder also
  wrote it.
- `changes.json` for a large generated file is still a real file; it is bounded,
  but it is not free.
