# Mobile bridge results

The branch-aware bridge writes sanitized result JSON files here. Results include request ID, action, completion timestamp, and a minimal success/status summary only. They intentionally exclude prompts, output contents, raw logs, local filesystem paths, and configuration values.

Keep this operational branch separate from `main` and PR #11.