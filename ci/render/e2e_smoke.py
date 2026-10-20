#!/usr/bin/env python3
"""Exercise the real local queue/CEO pipeline using isolated synthetic data."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
AGENTS = ROOT / "agents"
if str(AGENTS) not in sys.path:
    sys.path.insert(0, str(AGENTS))

import agent
import dispatch


def require(condition, message):
    if not condition:
        raise SystemExit("E2E CHECK FAILED: " + message)


def main():
    work = ROOT / "workspace" / "render-ci"
    work.mkdir(parents=True, exist_ok=True)
    notes = work / "synthetic-source-notes.md"
    notes.write_text(
        "# Synthetic CI notes\n\n"
        "This is artificial smoke-test content used only to test orchestration and rendering. "
        "It is not factual research and must never be published.\n",
        encoding="utf-8",
    )
    config = work / "config.json"
    config.write_text(
        json.dumps({"model": {"enabled": False}, "runner": {"max_tasks_per_cycle": 1}}),
        encoding="utf-8",
    )
    queue = work / "tasks.json"
    queue.write_text(json.dumps([{
        "id": "CI-VIDEO-E2E",
        "kind": "youtube_package",
        "title": "CI synthetic demo render",
        "input": (
            "Create a template demo render MP4 for a faceless YouTube video about "
            "CI pipeline smoke testing. Generate the video package and render it. "
            "This is synthetic test content, not publication content."
        ),
        "context_file": str(notes.relative_to(ROOT)),
        "status": "pending",
    }], indent=2), encoding="utf-8")

    # Redirect task state into the isolated synthetic workspace. No API key or
    # local-model endpoint is configured; this check intentionally tests fallback mode.
    agent.TASKS = queue
    agent.CONFIG = config
    agent.OUTPUTS = work / "results"
    dispatch.collect_web_research = None

    processed = agent.cycle("CI-VIDEO-E2E")
    require(processed == 1, "queue runner did not process the synthetic task")

    tasks = json.loads(queue.read_text(encoding="utf-8"))
    require(len(tasks) == 1, "test queue unexpectedly changed task count")
    require(tasks[0].get("status") in {"needs_human_action", "completed"},
            "synthetic task ended in unexpected status: " + str(tasks[0].get("status")))

    task_result = work / "results" / "CI-VIDEO-E2E.md"
    require(task_result.is_file() and task_result.stat().st_size > 0,
            "queue task result is missing or empty")

    destination = ROOT / "workspace" / "orchestration" / "task-CI-VIDEO-E2E"
    manifest_path = destination / "pipeline-status.json"
    require(manifest_path.is_file(), "CEO pipeline manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    video_tool = next((item for item in manifest.get("tool_runs", [])
                       if item.get("tool") == "video_studio"), None)
    require(video_tool is not None, "CEO did not select the video builder")
    require(video_tool.get("status") == "completed",
            "video builder failed: " + repr(video_tool))

    package = destination / "video-production"
    required = ["script.md", "storyboard.json", "package-status.json", "video.mp4"]
    missing = [name for name in required if not (package / name).is_file()]
    require(not missing, "video package artifacts missing: " + ", ".join(missing))
    require((package / "video.mp4").stat().st_size > 0, "rendered MP4 is empty")

    status = json.loads((package / "package-status.json").read_text(encoding="utf-8"))
    storyboard = json.loads((package / "storyboard.json").read_text(encoding="utf-8"))
    require(status.get("generated_by") == "deterministic_template",
            "test must exercise the transparent no-model template path")
    require(status.get("publishable") is False and status.get("published") is False,
            "synthetic test output must never be marked publishable or published")
    require((storyboard.get("width"), storyboard.get("height")) == (1920, 1080),
            "test render must use the landscape format")
    require(len(storyboard.get("scenes", [])) == 4,
            "expected the four-scene deterministic smoke-test storyboard")
    require(manifest.get("external_actions_performed") is False,
            "test pipeline must not report external actions")

    print("PASS: synthetic task queue -> CEO delegation -> specialist stages")
    print("PASS: generated script -> storyboard -> validated landscape MP4")
    print("Pipeline status:", manifest.get("status"),
          "| final quality gate:", manifest.get("quality_gate"))
    print("Note: this is a template smoke test, not AI-written or publication-ready content.")


if __name__ == "__main__":
    main()
