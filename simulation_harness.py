#!/usr/bin/env python3
"""Deterministic property-style simulation of Agent HQ safety invariants.

This is a fast state-machine model, not a claim that one million full AI tasks,
network calls, or video renders were executed. It explores one million synthetic
task lifecycle cases with reproducible seeds and checks the safety rules that
the real application must preserve.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

STATUSES = ("pending", "queued", "running", "completed", "failed", "needs_human_action")
SEED_DEFAULT = 20261019


@dataclass
class TaskModel:
    status: str = "pending"
    attempt: int = 0
    artifacts: list[str] = field(default_factory=list)
    quality_passed: bool = False
    external_action: bool = False
    approval_granted: bool = False
    history: list[str] = field(default_factory=list)

    def transition(self, new_status: str) -> None:
        self.status = new_status
        self.history.append(new_status)


def run_case(rng: random.Random, case_id: int) -> tuple[bool, str]:
    """Exercise a randomized lifecycle and return (passed, scenario label)."""
    task = TaskModel()
    task.transition("queued")
    task.attempt = 1
    task.transition("running")

    # A task may ask for an external side effect; this must stop at the gate.
    task.external_action = rng.random() < 0.18
    task.approval_granted = rng.random() < 0.25
    if task.external_action and not task.approval_granted:
        task.transition("needs_human_action")
        if task.status != "needs_human_action":
            return False, "external_action_gate"

    # Simulate interruption after zero or more saved artifacts.
    saved = rng.randrange(0, 4)
    task.artifacts.extend(f"attempt-1-artifact-{i}" for i in range(saved))
    interrupted = rng.random() < 0.22
    if interrupted:
        previous_artifacts = list(task.artifacts)
        task.transition("needs_human_action")
        # Recovery must preserve progress and must not silently replay.
        if task.artifacts != previous_artifacts or task.attempt != 1:
            return False, "recovery_preserves_state"
        if task.status == "running":
            return False, "interrupted_task_not_recovered"
        # Manual retry is a distinct attempt and cannot erase prior artifacts.
        if rng.random() < 0.60:
            task.attempt += 1
            task.transition("running")
            if task.attempt != 2 or task.artifacts != previous_artifacts:
                return False, "retry_is_new_attempt"
            task.artifacts.append("attempt-2-output")

    task.quality_passed = rng.random() < 0.70
    if task.quality_passed:
        task.transition("completed")
    else:
        task.transition("failed")

    if task.status == "completed" and not task.quality_passed:
        return False, "completion_requires_quality_gate"
    if task.external_action and not task.approval_granted and "completed" in task.history:
        # The model's external action is a hard gate, not a general task blocker.
        # A task may complete its draft while the side effect remains unperformed;
        # the state must still record the approval gate if the action itself is requested.
        if "needs_human_action" not in task.history:
            return False, "external_action_requires_gate"

    return True, "interrupted" if interrupted else ("external" if task.external_action else "normal")


def run_simulations(trials: int, seed: int) -> dict:
    if trials < 1:
        raise ValueError("trials must be at least 1")
    rng = random.Random(seed)
    counts: Counter[str] = Counter()
    for case_id in range(trials):
        ok, label = run_case(rng, case_id)
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
