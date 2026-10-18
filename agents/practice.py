#!/usr/bin/env python3
"""Run specialist practice tasks and record human-scored, role-specific feedback.

This is prompt-level practice and evaluation scaffolding; it does not fine-tune model weights.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
WORKSPACE = (ROOT / "workspace").resolve()
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(ROOT))
import dispatch
from queue_store import task_queue_lock


def utc_stamp():
    return datetime.now(timezone.utc).isoformat()


def is_within(path, parent):
    path = Path(path).expanduser().resolve()
    parent = Path(parent).expanduser().resolve()
    return path != parent and parent in path.parents


def load_config():
    try:
        return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def read_context(path):
    if not path:
        return ""
    source = Path(path).expanduser()
    source = source.resolve() if source.is_absolute() else (ROOT / source).resolve()
    if not is_within(source, WORKSPACE):
        raise ValueError("Training context must be inside the local workspace.")
    if not source.is_file() or source.suffix.lower() not in {".txt", ".md", ".json"}:
        raise ValueError("Training context must be an existing .txt, .md, or .json file.")
    if source.stat().st_size > 2_000_000:
        raise ValueError("Training context file exceeds the 2 MB limit.")
    return source.read_text(encoding="utf-8", errors="replace")[:50000]


def get_role_and_skill(agent_id):
    role = dispatch.find_role(str(agent_id).upper())
    if not role:
        raise ValueError("Unknown specialist ID.")
    role = dispatch.ensure_executable_role(role)
    skill = dispatch.find_skill(role["id"])
    if not skill:
        raise ValueError("No skillbook profile exists for " + role["id"])
    return role, skill


def create_attempt(agent_id, task=None, context="", config=None, run_root=None):
    role, skill = get_role_and_skill(agent_id)
    if task is None:
        task = (
            "Complete a concrete practice assignment for your specialty. Follow the practice drill and deliverable contract in your skillbook. "
            "Use a small illustrative example; label any invented example data as hypothetical. "
            "Apply every quality gate and report pass/partial/fail against visible evidence. Do not claim external research or actions."
        )
    if not isinstance(task, str) or not task.strip() or len(task) > 6000:
        raise ValueError("Practice task must be 1–6000 characters.")
    if len(context) > 50000:
        context = context[:50000]
    cfg = config if config is not None else load_config()
    root = Path(run_root).expanduser().resolve() if run_root else WORKSPACE / "training" / "runs"
    if root == WORKSPACE or WORKSPACE not in root.parents:
        raise ValueError("Training run output must remain inside the project workspace.")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    run_dir = root / role["id"] / run_id
    if not is_within(run_dir, WORKSPACE):
        raise ValueError("Unsafe training output path.")
    run_dir.mkdir(parents=True, exist_ok=False)
    artifact = dispatch.run_role(role, task, context, cfg)
    if not isinstance(artifact, str) or not artifact.strip():
        raise ValueError("Specialist returned an empty practice artifact.")
    artifact_path = run_dir / "artifact.md"
    artifact_path.write_text(artifact.rstrip() + "\n", encoding="utf-8")
    model_enabled = bool(cfg.get("model", {}).get("enabled"))
    gates = [
        {"gate": str(gate), "score": None, "evidence": ""}
        for gate in skill.get("quality_gates", [])
    ]
    report = {
        "created_at": utc_stamp(),
        "agent_id": role["id"],
        "role": role["name"],
        "department": role.get("department", ""),
        "task": task,
        "artifact_file": str(artifact_path),
        "mode": "local_model" if model_enabled else "template_only",
        "status": "pending_human_assessment" if model_enabled else "template_only_not_assessed",
        "quality_gates": gates,
        "model_weight_training_performed": False,
        "human_review_required": True,
        "notes": (
            "The artifact is AI-generated and unverified. Human scoring is required before treating this as a mastery result."
            if model_enabled else
            "No AI generation occurred because the model is disabled. This is a playbook/checklist template, not evidence of skill mastery."
        ),
    }
    report_path = run_dir / "assessment.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return run_dir, report


def record_human_assessment(report_path, scores, improvement_notes="", feedback_dir=None):
    path = Path(report_path).expanduser().resolve()
    if not is_within(path, WORKSPACE) or not path.is_file() or path.name != "assessment.json":
        raise ValueError("Assessment report must be an existing assessment.json inside the project workspace.")
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("status") not in {"pending_human_assessment", "template_only_not_assessed"}:
        raise ValueError("This assessment has already been reviewed or is not scorable.")
    gates = report.get("quality_gates")
    if not isinstance(gates, list) or not gates:
        raise ValueError("Assessment has no quality gates.")
    normalized = {}
    for index, item in enumerate(gates):
        name = item.get("gate")
        if not isinstance(name, str) or not name:
            raise ValueError("Quality gate " + str(index) + " has no name.")
        value = scores.get(name)
        if isinstance(value, bool) or value not in {0, 1, 2}:
            raise ValueError("Each quality gate must have a human score: 0 (fail), 1 (partial), or 2 (pass).")
        normalized[name] = value
        item["score"] = value
    notes = str(improvement_notes or "").strip()[:3000]
    total = sum(normalized.values())
    maximum = 2 * len(normalized)
    all_pass = all(value == 2 for value in normalized.values())
    report.update({
        "status": "human_reviewed_pass" if all_pass else "human_reviewed_needs_improvement",
        "human_reviewed": True,
        "human_reviewed_at": utc_stamp(),
        "human_scores": normalized,
        "score_total": total,
        "score_maximum": maximum,
        "score_percent": round(100 * total / maximum, 1) if maximum else 0,
        "improvement_notes": notes,
        "human_review_required": False,
        "model_weight_training_performed": False,
    })
    temp = path.with_name(path.name + ".tmp-" + str(os.getpid()))
    temp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)

    if notes:
        out_dir = Path(feedback_dir).resolve() if feedback_dir else WORKSPACE / "training" / "feedback"
        if out_dir == WORKSPACE or WORKSPACE not in out_dir.parents:
            raise ValueError("Feedback output must remain inside the project workspace.")
        out_dir.mkdir(parents=True, exist_ok=True)
        feedback_file = out_dir / (report["agent_id"] + ".jsonl")
        record = {
            "human_reviewed": True,
            "agent_id": report["agent_id"],
            "assessed_at": report["human_reviewed_at"],
            "scores": normalized,
            "improvement_notes": notes,
            "assessment_path": str(path),
            "score_percent": report["score_percent"],
        }
        with task_queue_lock(feedback_file):
            with feedback_file.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    practice = sub.add_parser("practice", help="Run practice tasks for one or all specialist roles")
    pick = practice.add_mutually_exclusive_group(required=True)
    pick.add_argument("--agent", help="One role ID such as AGENT-51")
    pick.add_argument("--all", action="store_true", help="Run a practice task for all executable specialist roles")
    practice.add_argument("--limit", type=int, help="Optional limit when --all is used (1–51)")
    practice.add_argument("--task", help="One practice task applied to each selected role (max 6000 characters)")
    practice.add_argument("--context-file", help="Optional local context file inside workspace")
    practice.add_argument("--out", default="workspace/training/runs", help="Output root, which must remain inside workspace")

    assess = sub.add_parser("assess", help="Record a human review for an assessment.json")
    assess.add_argument("--report", required=True)

    args = parser.parse_args()
    if args.command == "practice":
        if args.limit is not None and (not args.all or not 1 <= args.limit <= 51):
            raise SystemExit("--limit is valid only with --all and must be between 1 and 51.")
        if args.task is not None and (not args.task.strip() or len(args.task) > 6000):
            raise SystemExit("--task must be 1–6000 characters.")
        try:
            context = read_context(args.context_file)
            cfg = load_config()
            if args.all:
                roles = [r for r in dispatch.load_json(dispatch.ROSTER, {}).get("agents", []) if r.get("id") != "AGENT-50"]
                roles = roles[:args.limit] if args.limit else roles
                if not roles:
                    raise ValueError("No executable specialist roles were found.")
            else:
                role, _ = get_role_and_skill(args.agent)
                roles = [role]
            root = Path(args.out).expanduser()
            root = root.resolve() if root.is_absolute() else (ROOT / root).resolve()
            if root == WORKSPACE or WORKSPACE not in root.parents:
                raise ValueError("Training output root must remain inside workspace.")
            for role in roles:
                out_dir, report = create_attempt(
                    role["id"], args.task, context, cfg,
                    root,
                )
                print(role["id"], role["name"], "->", out_dir, "[" + report["status"] + "]")
            print("Human scoring is required. Use: python agents/practice.py assess --report <assessment.json>")
            if not cfg.get("model", {}).get("enabled"):
                print("The local model is disabled: outputs are template-only and do not train or assess capability.")
        except (ValueError, OSError) as exc:
            raise SystemExit(str(exc))
    else:
        path = Path(args.report).expanduser()
        path = path.resolve() if path.is_absolute() else (ROOT / path).resolve()
        if not is_within(path, WORKSPACE):
            raise SystemExit("Assessment report must be inside the project workspace.")
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            if report.get("status") not in {"pending_human_assessment", "template_only_not_assessed"}:
                raise ValueError("This assessment has already been reviewed or is not scorable.")
            scores = {}
            print("Human assessment:", report.get("agent_id"), report.get("role"))
            print("Score each gate: 0 = fail, 1 = partial, 2 = pass.")
            for item in report.get("quality_gates", []):
                while True:
                    raw = input("\n" + item["gate"] + "\nScore (0/1/2): ").strip()
                    if raw in {"0", "1", "2"}:
                        scores[item["gate"]] = int(raw)
                        break
                    print("Enter 0, 1, or 2.")
            notes = input("\nLesson to carry into future runs (optional): ").strip()
            result = record_human_assessment(path, scores, notes)
        except (ValueError, OSError, json.JSONDecodeError, KeyError) as exc:
            raise SystemExit(str(exc))
        print("Assessment status:", result["status"])
        print("Score:", str(result["score_total"]) + "/" + str(result["score_maximum"]) + " (" + str(result["score_percent"]) + "%)")
        print("Human-reviewed notes stored locally; model weights were not updated.")


if __name__ == "__main__":
    main()
