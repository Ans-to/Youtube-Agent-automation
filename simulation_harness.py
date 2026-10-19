#!/usr/bin/env python3
"""Deterministic property-style simulation of Agent HQ safety invariants.

This is a fast state-machine model, not a claim that one million full AI tasks,
network calls, or video renders were executed. It explores synthetic task
lifecycle cases with reproducible seeds and checks safety rules.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from dataclasses import dataclass, field

SEED_DEFAULT = 20261019


@dataclass
class TaskModel:
    status: str = "pending"
    attempt: int = 0
    artifacts: list[str] = field(default_factory=list)
    quality_passed: bool = False
    external_action: bool = False
    approval_granted: bool = False
    external_action_executed: bool = False
    history: list[str] = field(default_factory=list)

    def transition(self, new_status: str) -> None:
        allowed = {
            "pending": {"queued"},
            "queued": {"running"},
            "running": {"needs_human_action", "completed", "failed"},
            "needs_human_action": {"running"},
            "completed": set(),
            "failed": set(),
        }
        if new_status not in allowed.get(self.status, set()):
            raise ValueError(f"illegal task transition: {self.status} -> {new_status}")
        self.status = new_status
        self.history.append(new_status)


def action_gate(requested: bool, approved: bool) -> tuple[str, bool]:
    """Return the safe next status and whether the side effect may execute."""
    if not requested:
        return "running", False
    if not approved:
        return "needs_human_action", False
    return "running", True


def run_case(rng: random.Random, case_id: int) -> tuple[bool, str]:
    """Exercise a randomized lifecycle and return (passed, scenario label)."""
    del case_id  # reserved for richer failure reports without changing the API
    task = TaskModel()
    task.transition("queued")
    task.attempt = 1
    task.transition("running")

    task.external_action = rng.random() < 0.18
    task.approval_granted = rng.random() < 0.25
    next_status, may_execute = action_gate(
        task.external_action, task.approval_granted
    )
    task.external_action_executed = task.external_action and may_execute

    if task.external_action and not task.approval_granted:
        task.transition(next_status)
        if task.external_action_executed or task.status != "needs_human_action":
            return False, "external_action_gate"
        # An action-dependent task cannot proceed to completion while blocked.
        if task.status in {"completed", "failed"}:
            return False, "blocked_action_terminal_state"
        return True, "external_blocked"

    if task.external_action and not task.external_action_executed:
        return False, "approved_action_execution"

    # Simulate interruption after zero or more saved artifacts.
    saved = rng.randrange(0, 4)
    task.artifacts.extend(f"attempt-1-artifact-{i}" for i in range(saved))
    interrupted = rng.random() < 0.22
    if interrupted:
        previous_artifacts = list(task.artifacts)
        task.transition("needs_human_action")
        if task.artifacts != previous_artifacts or task.attempt != 1:
            return False, "recovery_preserves_state"
        if task.status == "running":
            return False, "interrupted_task_not_recovered"
        # Retry is explicit, increments attempt, and preserves earlier outputs.
        if rng.random() < 0.60:
            task.attempt += 1
            task.transition("running")
            if task.attempt != 2 or task.artifacts != previous_artifacts:
                return False, "retry_is_new_attempt"
            task.artifacts.append("attempt-2-output")

    task.quality_passed = rng.random() < 0.70
    task.transition("completed" if task.quality_passed else "failed")

    if task.status == "completed" and not task.quality_passed:
        return False, "completion_requires_quality_gate"
    if task.external_action and not task.approval_granted and task.external_action_executed:
        return False, "external_action_requires_approval"
    return True, "interrupted" if interrupted else ("external" if task.external_action else "normal")


def run_simulations(trials: int, seed: int) -> dict:
    if trials < 1:
        raise ValueError("trials must be at least 1")
    rng = random.Random(seed)
    counts: Counter[str] = Counter()
    for case_id in range(trials):
        try:
            ok, label = run_case(rng, case_id)
        except ValueError as exc:
            return {
                "ok": False,
                "seed": seed,
                "trials_requested": trials,
                "trials_completed": case_id + 1,
                "failure_case": case_id,
                "failure_invariant": "illegal_transition",
                "failure_detail": str(exc),
                "scenario_counts": dict(sorted(counts.items())),
            }
        counts[label] += 1
        if not ok:
            return {
                "ok": False,
                "seed": seed,
                "trials_requested": trials,
                "trials_completed": case_id + 1,
                "failure_case": case_id,
                "failure_invariant": label,
                "scenario_counts": dict(sorted(counts.items())),
            }
    return {
        "ok": True,
        "seed": seed,
        "trials_requested": trials,
        "trials_completed": trials,
        "failure_case": None,
        "failure_invariant": None,
        "scenario_counts": dict(sorted(counts.items())),
        "scope": "synthetic state-machine/property simulation; not full end-to-end AI/network/render execution",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=1_000_000)
    parser.add_argument("--seed", type=int, default=SEED_DEFAULT)
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args()
    try:
        result = run_simulations(args.trials, args.seed)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else
          f"Simulation {'PASS' if result['ok'] else 'FAIL'}: {result['trials_completed']:,}/{result['trials_requested']:,} cases; seed={result['seed']}; failures={0 if result['ok'] else 1}")
    if not result["ok"]:
        print(json.dumps(result, indent=2), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
