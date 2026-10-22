#!/usr/bin/env python3
"""Decide how much work this machine should be asked to do at once.

The system has to run on a laptop with 4 GB of RAM and two cores without
crashing, swapping, or making the desktop unusable. It is allowed to be slow.
This module turns hardware facts into a **resource plan**: a small, explicit set
of limits that the rest of the system reads instead of hard-coding.

Three rules:

1. **Adapt the batch, never the artifact.** A smaller machine gets shorter
   timeouts, a smaller dataset ceiling, fewer repair attempts. It does not get a
   different resolution, frame rate, voice, or truncated report: output quality is
   the user's decision, and a silent downgrade is a lie about what was produced.
2. **One heavy job at a time, everywhere.** Every tier says one. The system is
   sequential by design, which is what keeps a 2-core machine responsive.
3. **Say what was chosen and why.** The plan records the detected facts, the tier,
   any downgrade under memory pressure, and every limit, so a slow run can be
   explained rather than guessed at.

Detection reuses `video_studio/capabilities.py` where it already does the awkward
platform work, and adds one thing it does not have: *available* memory right now,
not just installed memory.

Standard library only. No subprocess is started except the existing GPU probe.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SCHEMA = 1
TIERS = ("minimal", "low", "balanced", "high")
PROFILES = ("auto",) + TIERS

#: What each tier may ask of the machine. Every number here is a *batch* limit:
#: how long one step may run, how big a file may be read, how many repairs are
#: tried. None of them changes what an artifact looks like.
TIER_LIMITS = {
    "minimal": {
        "max_parallel_heavy_jobs": 1,
        "tool_loop_max_seconds": 300,
        "tool_loop_timeout_seconds": 60,
        "tool_max_repairs": 1,
        "model_timeout_seconds": 180,
        "model_max_tokens": 1_200,
        "dataset_max_bytes": 500_000,
        "test_timeout_seconds": 60,
        "test_max_attempts": 1,
        "min_free_disk_bytes": 200_000_000,
    },
    "low": {
        "max_parallel_heavy_jobs": 1,
        "tool_loop_max_seconds": 600,
        "tool_loop_timeout_seconds": 90,
        "tool_max_repairs": 2,
        "model_timeout_seconds": 240,
        "model_max_tokens": 1_600,
        "dataset_max_bytes": 1_000_000,
        "test_timeout_seconds": 90,
        "test_max_attempts": 2,
        "min_free_disk_bytes": 500_000_000,
    },
    "balanced": {
        "max_parallel_heavy_jobs": 1,
        "tool_loop_max_seconds": 900,
        "tool_loop_timeout_seconds": 120,
        "tool_max_repairs": 2,
        "model_timeout_seconds": 300,
        "model_max_tokens": 2_400,
        "dataset_max_bytes": 2_000_000,
        "test_timeout_seconds": 120,
        "test_max_attempts": 3,
        "min_free_disk_bytes": 1_000_000_000,
    },
    "high": {
        "max_parallel_heavy_jobs": 1,
        "tool_loop_max_seconds": 1_800,
        "tool_loop_timeout_seconds": 180,
        "tool_max_repairs": 2,
        "model_timeout_seconds": 600,
        "model_max_tokens": 4_000,
        "dataset_max_bytes": 8_000_000,
        "test_timeout_seconds": 180,
        "test_max_attempts": 3,
        "min_free_disk_bytes": 2_000_000_000,
    },
}

#: Stated positively so a reviewer can check that none of these moved.
NEVER_CHANGED_BY_TIER = (
    "requested video resolution and frame rate",
    "requested narration language and voice",
    "report and document content (numbers are measured, not sampled)",
    "chart values (every bar is a measured value)",
    "whether a run is marked complete",
)

#: What a smaller tier is honestly allowed to make smaller, in words a user can
#: read in the manifest. Kept separate from NEVER_CHANGED_BY_TIER so "this run
#: asked the model for less text" is never confused with "the artifact is worse".
DEGRADATIONS = {
    "minimal": [
        "one local-model call may wait at most 180s instead of 300s",
        "one generated section is capped at 1,200 tokens instead of 2,400",
        "datasets above 500 KB are refused instead of read (2 MB on balanced)",
        "one repair attempt per step instead of two",
    ],
    "low": [
        "one generated section is capped at 1,600 tokens instead of 2,400",
        "datasets above 1 MB are refused instead of read (2 MB on balanced)",
    ],
    "balanced": [],
    "high": [],
}


def available_memory_bytes():
    """Physical memory currently free, or None when it cannot be read cheaply."""
    if sys.platform == "win32":
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullAvailPhys)
        except Exception:  # noqa: BLE001 - a missing probe is not an error
            return None
        return None
    try:
        # Linux exposes MemAvailable, which accounts for reclaimable cache; using
        # MemFree would report a healthy desktop as "out of memory".
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _facts(cpu_count=None, ram_bytes=None, free_disk_bytes=None, gpu=None, base_path="."):
    """Hardware facts, reusing the video layer's detection where it exists."""
    if cpu_count is not None and ram_bytes is not None:
        return {
            "cpu_count": max(1, int(cpu_count)),
            "total_memory_bytes": int(ram_bytes) if ram_bytes else None,
            "free_disk_bytes": int(free_disk_bytes) if free_disk_bytes is not None else None,
            "gpu": dict(gpu or {"detected": False}),
            "source": "supplied",
        }
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from video_studio.capabilities import profile_device
        profile = profile_device(base_path)
        facts = {
            "cpu_count": int(profile.get("cpu_count") or os.cpu_count() or 1),
            "total_memory_bytes": profile.get("total_memory_bytes"),
            "free_disk_bytes": profile.get("free_disk_bytes"),
            "gpu": dict(profile.get("gpu") or {"detected": False}),
            "source": "video_studio.capabilities",
        }
    except Exception:  # noqa: BLE001 - profiling must never stop a task
        facts = {
            "cpu_count": max(1, os.cpu_count() or 1),
            "total_memory_bytes": None,
            "free_disk_bytes": None,
            "gpu": {"detected": False},
            "source": "fallback",
        }
    if cpu_count is not None:
        facts["cpu_count"] = max(1, int(cpu_count))
    if ram_bytes is not None:
        facts["total_memory_bytes"] = int(ram_bytes)
    if free_disk_bytes is not None:
        facts["free_disk_bytes"] = int(free_disk_bytes)
    if gpu is not None:
        facts["gpu"] = dict(gpu)
    return facts


def tier_for(ram_bytes, cpu_count):
    """Which tier this much memory and this many cores justifies.

    An unknown RAM figure is treated as *balanced*, not minimal: guessing low would
    silently cut a capable machine's limits, which is its own kind of wrong.
    """
    cores = max(1, int(cpu_count or 1))
    if not ram_bytes:
        return "balanced"
    gib = ram_bytes / (1024 ** 3)
    if gib < 4 or cores <= 1:
        return "minimal"
    if gib < 8:
        return "low"
    if gib < 16:
        return "balanced"
    return "high"


def _downgrade(tier):
    index = TIERS.index(tier)
    return TIERS[max(0, index - 1)]


def plan(profile="auto", *, cpu_count=None, ram_bytes=None, free_disk_bytes=None,
         available_bytes=None, gpu=None, base_path="."):
    """The resource plan for this machine. Deterministic given its arguments."""
    requested = str(profile or "auto").strip().lower()
    reasons = []
    if requested not in PROFILES:
        reasons.append(f"unknown profile '{requested[:20]}'; using auto")
        requested = "auto"

    facts = _facts(cpu_count=cpu_count, ram_bytes=ram_bytes,
                   free_disk_bytes=free_disk_bytes, gpu=gpu, base_path=base_path)
    detected = tier_for(facts["total_memory_bytes"], facts["cpu_count"])

    if requested == "auto":
        tier = detected
        reasons.append(
            f"detected {facts['cpu_count']} core(s) and "
            + (f"{facts['total_memory_bytes'] / (1024 ** 3):.1f} GiB RAM"
               if facts["total_memory_bytes"] else "an unknown amount of RAM"))
    else:
        tier = requested
        reasons.append(f"profile '{requested}' was requested explicitly")

    if available_bytes is None:
        available_bytes = available_memory_bytes()
    real = facts["total_memory_bytes"]
    pressure = None
    if available_bytes and real:
        ratio = max(0.0, min(1.0, available_bytes / real))
        if ratio < 0.15:
            pressure = "low"
            before = tier
            tier = _downgrade(tier)
            reasons.append(
                f"only {ratio * 100:.0f}% of RAM is available right now; "
                f"limits lowered from {before} to {tier} for this run")

    limits = dict(TIER_LIMITS[tier])
    # Disk is a warning, never a refusal: a run that cannot write its artifacts
    # should fail at the artifact with the reason intact, not refuse to start.
    warnings = []
    free_disk = facts["free_disk_bytes"]
    if free_disk is not None and free_disk < limits["min_free_disk_bytes"]:
        warnings.append(
            f"only {free_disk / 1_000_000:.0f} MB of disk is free "
            f"({limits['min_free_disk_bytes'] // 1_000_000} MB recommended); "
            "video rendering and large packages may fail part-way")
    return {
        "schema": SCHEMA,
        "requested": requested,
        "tier": tier,
        "detected_tier": detected,
        "pressure": pressure,
        "facts": {
            "cpu_count": facts["cpu_count"],
            "total_memory_bytes": facts["total_memory_bytes"],
            "available_memory_bytes": int(available_bytes) if available_bytes else None,
            "free_disk_bytes": facts["free_disk_bytes"],
            "gpu": facts["gpu"],
            "source": facts["source"],
        },
        "limits": limits,
        "degradations": list(DEGRADATIONS[tier]),
        "warnings": warnings,
        "never_changes": list(NEVER_CHANGED_BY_TIER),
        "reasons": reasons,
    }


def limits_from(cfg):
    """The limits carried by a config, or the balanced defaults.

    Every consumer reads through this, so a tool called directly (a test, a
    script, a dashboard action) behaves like the balanced tier instead of failing
    on a missing key. Unknown or non-integer values are ignored, which keeps a
    hand-edited config from being able to raise a limit above its tier.
    """
    plan_ = cfg.get("_resources") if isinstance(cfg, dict) else None
    merged = dict(TIER_LIMITS["balanced"])
    if isinstance(plan_, dict) and isinstance(plan_.get("limits"), dict):
        merged.update({k: v for k, v in plan_["limits"].items() if isinstance(v, int) and k in merged})
    return merged


def describe(resource_plan):
    """One short line for a human, or a console summary."""
    plan_ = resource_plan or {}
    limits = plan_.get("limits") or {}
    facts = plan_.get("facts") or {}
    ram = facts.get("total_memory_bytes")
    return (
        f"tier={plan_.get('tier', 'unknown')} "
        f"cores={facts.get('cpu_count', '?')} "
        f"ram={f'{ram / (1024 ** 3):.1f}GiB' if ram else 'unknown'} "
        f"heavy_jobs={limits.get('max_parallel_heavy_jobs', '?')} "
        f"tool_loop={limits.get('tool_loop_max_seconds', '?')}s "
        f"dataset={limits.get('dataset_max_bytes', '?')}B"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Show the resource plan for this machine.")
    parser.add_argument("--profile", default="auto", choices=list(PROFILES))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--path", default=".", help="path used to estimate free disk")
    args = parser.parse_args(argv)
    resource_plan = plan(args.profile, base_path=args.path)
    if args.json:
        print(json.dumps(resource_plan, indent=2))
    else:
        print(describe(resource_plan))
        for reason in resource_plan["reasons"]:
            print(" -", reason)
        for warning in resource_plan.get("warnings") or []:
            print(" ! warning:", warning)
        print("Never changed by tier:", "; ".join(resource_plan["never_changes"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
