#!/usr/bin/env python3
"""Run a sequential, local-model specialist pipeline with a persistent audit trail."""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
WORKSPACE = (ROOT / "workspace").resolve()
sys.path.insert(0, str(BASE))
import dispatch

DEFAULT_PIPELINE = [
    "AGENT-02", "AGENT-03", "AGENT-09", "AGENT-20",
    "AGENT-51", "AGENT-52", "AGENT-26", "AGENT-32", "AGENT-33", "AGENT-37", "AGENT-49",
]


def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:48] or "project"


def read_context(path):
    if not path:
        return ""
    source = Path(path).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() not in {".txt", ".md", ".json"}:
        raise ValueError("Context must be an existing .txt, .md, or .json file.")
    return source.read_text(encoding="utf-8", errors="replace")[:50000]


def run_pipeline(task, context="", agent_ids=None, output_dir=None, config=None):
    if not isinstance(task, str) or not task.strip() or len(task) > 6000:
        raise ValueError("Task must be 1–6000 characters.")
    roles = dispatch.load_json(dispatch.ROSTER, {}).get("agents", [])
    roles_by_id = {role.get("id"): role for role in roles}
    selected = DEFAULT_PIPELINE if agent_ids is None else agent_ids
    if not selected or len(selected) > 51 or len(set(selected)) != len(selected):
        raise ValueError("Choose 1–51 unique specialist IDs; AGENT-50 is reserved for human approval.")
    if any(agent_id not in roles_by_id for agent_id in selected):
        raise ValueError("Unknown specialist ID in pipeline.")
    if "AGENT-50" in selected:
        raise ValueError("AGENT-50 is a human approval role and cannot be run as an automatic specialist.")
    destination = Path(output_dir).resolve() if output_dir else WORKSPACE / "orchestration" / slug(task[:80])
    if destination == WORKSPACE or WORKSPACE not in destination.parents:
        raise ValueError("Pipeline output must remain inside the project workspace.")
    destination.mkdir(parents=True, exist_ok=True)
    cfg = config if config is not None else dispatch.load_json(ROOT / "config.json", {})
    combined_context = context[:20000]
    records = []
    for index, agent_id in enumerate(selected, start=1):
        role = roles_by_id[agent_id]
        instruction = (
            task.strip()
            + "\n\nPipeline stage " + str(index) + " of " + str(len(selected)) + ". "
            + "Use prior-stage notes as unverified working context. Correct errors when evidence permits. "
            + "Do not claim external research or external actions. Flag facts that require independent sourcing. "
            + "Return this stage's deliverable and explicit unresolved issues."
        )
        filename = str(index).zfill(2) + "-" + slug(agent_id + "-" + role["name"]) + ".md"
        try:
            result = dispatch.run_role(role, instruction, combined_context, cfg)
            if not isinstance(result, str) or not result.strip():
                raise ValueError("Specialist returned an empty result.")
        except Exception as exc:
            failure = {
                "sequence": index, "agent_id": agent_id, "role": role["name"],
                "output_file": None, "status": "failed",
                "error_type": type(exc).__name__, "error": str(exc)[:500],
                "mode": "local_model" if cfg.get("model", {}).get("enabled") else "template_fallback",
            }
            records.append(failure)
            manifest = build_manifest(task, records, cfg, status="failed")
            (destination / "pipeline-status.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return destination, manifest
        (destination / filename).write_text(result.rstrip() + "\n", encoding="utf-8")
        records.append({
            "sequence": index, "agent_id": agent_id, "role": role["name"],
            "output_file": filename, "status": "draft_generated",
            "mode": "local_model" if cfg.get("model", {}).get("enabled") else "template_fallback",
        })
        combined_context = (combined_context + "\n\n--- " + role["name"] + " output (unverified) ---\n" + result)[-20000:]
    manifest = build_manifest(task, records, cfg, status="draft")
    (destination / "pipeline-status.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination, manifest


def build_manifest(task, records, cfg, status):
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "task": task.strip(),
        "pipeline": records,
        "status": status,
        "model_enabled": bool(cfg.get("model", {}).get("enabled")),
        "research_performed": False,
        "external_actions_performed": False,
        "human_review_required": True,
        "note": "Sequential specialist pipeline; roles share one configured local model. Outputs are drafts, not verified facts.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True)
    parser.add_argument("--context-file")
    parser.add_argument("--agents", default=",".join(DEFAULT_PIPELINE),
                        help="Comma-separated role IDs; AGENT-50 is reserved for actual human approval.")
    parser.add_argument("--out", default="workspace/orchestration/run")
    args = parser.parse_args()
    try:
        context = read_context(args.context_file)
        destination, manifest = run_pipeline(args.task, context,
            [part.strip().upper() for part in args.agents.split(",") if part.strip()],
            ROOT / args.out)
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc))
    print("Pipeline output:", destination)
    print("Stages:", len(manifest["pipeline"]))
    print("Mode:", "local model" if manifest["model_enabled"] else "template fallback; no AI generation")
    print("Human review required; no web research or external action was performed.")


if __name__ == "__main__":
    main()
