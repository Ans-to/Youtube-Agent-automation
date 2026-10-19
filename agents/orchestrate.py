#!/usr/bin/env python3
"""Run a sequential, local-model specialist pipeline with a persistent audit trail."""
import argparse
import json
import re
import sys
import subprocess
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



def heuristic_assignments(task):
    """Transparent no-model routing: a small role set matched to task intent."""
    text = task.lower()
    video = any(word in text for word in ("youtube", "video", "shorts", "short-form", "script", "storyboard", "motion graphics", "animation", "narration"))
    software = any(word in text for word in ("build", "code", "software", "app", "website", "tool", "program", "automation", "debug", "feature", "repository", "system"))
    product = any(word in text for word in ("product", "sell", "customer", "market", "business", "monetize", "revenue", "launch"))
    assignments = [{"agent_id": "AGENT-02", "task": "Research the task requirements, authoritative sources, current constraints, and viable approaches. Return source-linked evidence and uncertainties."}]
    if video:
        assignments.extend([
            {"agent_id": "AGENT-09", "task": "Create the core narrative/script or structured content deliverable for the requested video."},
            {"agent_id": "AGENT-20", "task": "Turn the approved narrative into a concrete scene-by-scene storyboard and production directions."},
            {"agent_id": "AGENT-51", "task": "Define premium visual art direction, visual motifs, pacing, and scene transitions appropriate to the content."},
            {"agent_id": "AGENT-52", "task": "Specify implementable motion systems, compositing, kinetic typography, and technical production details."},
            {"agent_id": "AGENT-26", "task": "Prepare accessibility captions or a caption plan aligned to the narration and timing information available."},
        ])
        if "urdu" in text or "pakistan" in text:
            assignments.append({"agent_id": "AGENT-13", "task": "Localize narration into natural Urdu with English technical terms where appropriate."})
    elif software or product:
        if product:
            assignments.append({"agent_id": "AGENT-44", "task": "Research the product opportunity, customer pain points, and evidence for demand."})
            assignments.append({"agent_id": "AGENT-45", "task": "Design a scoped, usable product architecture with explicit acceptance criteria."})
        assignments.extend([
            {"agent_id": "AGENT-46", "task": "Produce an implementation deliverable or concrete starter code/files appropriate to this task and repository."},
            {"agent_id": "AGENT-47", "task": "Document setup, operation, configuration, troubleshooting, and known limitations."},
            {"agent_id": "AGENT-48", "task": "Define relevant repeatable quality checks, edge cases, and failure handling."},
        ])
    else:
        assignments.extend([
            {"agent_id": "AGENT-03", "task": "Audit the evidence, source quality, dates, and whether citations support the key claims."},
            {"agent_id": "AGENT-12", "task": "Synthesize the research into the requested practical deliverable, clearly separating facts from assumptions."},
        ])
    # Keep the fallback small and append a quality gate after role-specific work.
    unique = []
    seen = set()
    for item in assignments:
        if item["agent_id"] not in seen and item["agent_id"] not in {"AGENT-01", "AGENT-50"}:
            seen.add(item["agent_id"])
            unique.append(item)
    unique = unique[:7]
    if "AGENT-08" not in {item["agent_id"] for item in unique}:
        unique.append({"agent_id": "AGENT-08", "task": "Fact-check the draft and its claims against the supplied research report; flag unsupported statements and unresolved risks."})
    return unique[:8], "heuristic_no_model"


def parse_ceo_assignments(text, roles_by_id):
    """Parse and validate CEO-produced JSON delegation without executing arbitrary content."""
    candidates = []
    for match in re.finditer(r"\{", text):
        try:
            parsed, _ = json.JSONDecoder().raw_decode(text[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            candidates = parsed.get("assignments", parsed.get("agents", []))
            break
    if not isinstance(candidates, list):
        return []
    result, seen = [], set()
    for item in candidates:
        if isinstance(item, str):
            agent_id, subtask = item.strip().upper(), ""
        elif isinstance(item, dict):
            agent_id = str(item.get("agent_id", item.get("id", ""))).strip().upper()
            subtask = str(item.get("task", item.get("responsibility", ""))).strip()
        else:
            continue
        if agent_id in {"AGENT-01", "AGENT-50"} or agent_id not in roles_by_id or agent_id in seen:
            continue
        if len(result) >= 7:
            break
        if len(subtask) > 2500:
            subtask = subtask[:2500]
        result.append({"agent_id": agent_id, "task": subtask})
        seen.add(agent_id)
    if not result:
        return []
    for item in result:
        if not item["task"]:
            item["task"] = "Complete the assigned specialist contribution to this overall goal: " + str(item["agent_id"])
    if "AGENT-08" not in seen:
        result.append({"agent_id": "AGENT-08", "task": "Review the combined work for factual support, contradictions, omissions, and unresolved risks. Use the supplied research report and cite source URLs."})
    return result[:8]


def plan_delegation(task, context, cfg, roles_by_id):
    """Let the CEO choose specialist roles; use deterministic routing only when no model/valid plan exists."""
    if cfg.get("model", {}).get("enabled"):
        roster = [
            {"id": role.get("id"), "name": role.get("name"), "department": role.get("department"),
             "mission": role.get("mission")}
            for role in roles_by_id.values()
            if role.get("id") not in {"AGENT-01", "AGENT-50"}
        ]
        ceo_task = (
            "Act as the CEO of Agent HQ. Delegate this task to the smallest sufficient set of specialists. "
            "Choose 2-7 specialist assignments, in dependency order. Include one factual quality-review role "
            "(prefer AGENT-08) unless inappropriate. Never select AGENT-01 or AGENT-50 as a worker. "
            "Give each role a concrete, distinct subtask with an observable deliverable. Do not select roles merely to fill a quota. "
            "Return ONLY valid JSON in this exact shape: "
            '{"assignments":[{"agent_id":"AGENT-02","task":"Specific work and deliverable"}]}\n\n'
            "USER GOAL:\n" + task + "\n\nAVAILABLE SPECIALISTS:\n"
            + json.dumps(roster, ensure_ascii=False)[:18000]
        )
        try:
            raw = dispatch.run_role(roles_by_id["AGENT-01"], ceo_task, context[:10000], cfg)
            assignments = parse_ceo_assignments(raw, roles_by_id)
            if assignments:
                return assignments, "ceo_model_delegation"
        except Exception:
            pass
    return heuristic_assignments(task)


def run_builtin_tools(task, destination, cfg, source_context=""):
    """Run only fixed, repository-owned artifact builders selected by clear task intent."""
    results = []
    text = task.strip()
    lower = text.lower()
    model_enabled = bool(cfg.get("model", {}).get("enabled"))
    verbs = r"\b(build|create|make|generate|produce|develop|implement|render|export)\b"

    video_requested = (
        re.search(r"\b(youtube|video|shorts|short-form)\b", lower)
        and re.search(verbs, lower)
    )
    product_requested = bool(re.search(r"\b(digital product|product prototype|build (?:a )?product|create (?:a )?product|develop (?:a )?product|product idea for (?:a )?tool)\b", lower))
    render_requested = bool(re.search(r"\b(render|mp4|export video|final video)\b", lower))
    template_demo = bool(re.search(r"\b(template demo|demo render)\b", lower)) and not model_enabled
    source_path = None
    if source_context.strip() and (video_requested or product_requested):
        source_path = destination / "source-notes.md"
        source_path.write_text(source_context[:50000], encoding="utf-8")
    if video_requested and (model_enabled or template_demo):
        topic_match = re.search(r"(?i)\b(?:about|on|topic\s*[:=])\s+(.+?)(?:[.;\n]|,\s*(?:include|with|and also)\b|$)", text)
        topic = (topic_match.group(1).strip() if topic_match else text[:220]).strip(" \t\r\n.,;:")
        topic = topic[:500] or "Technology explainer"
        fmt = "shorts" if re.search(r"\b(shorts|short-form|vertical)\b", lower) else "long"
        output = destination / "video-production"
        relative_out = output.resolve().relative_to(ROOT).as_posix()
        command = [sys.executable, str(ROOT / "video_studio" / "production.py"),
                   "--topic", topic, "--format", fmt, "--out", relative_out]
        if source_path is not None:
            command.extend(["--source-file", str(source_path)])
        else:
            command.append("--research")
        duration_match = re.search(r"(?i)target[_ ]minutes\s*[:=]\s*(\d+(?:\.\d+)?)", text)
        if duration_match:
            command.extend(["--target-minutes", duration_match.group(1)])
        if render_requested and model_enabled:
            command.append("--render")
            if re.search(r"\b(with voice|with local narration|piper narration)\b", lower):
                command.append("--with-voice")
        elif render_requested and template_demo:
            command.extend(["--render", "--render-template"])
        elif render_requested:
            results.append({
                "tool": "video_studio", "status": "blocked",
                "artifact_dir": relative_out,
                "reason": "Full rendering needs an enabled local model. The CEO pipeline deliverables and research reports are still available.",
            })
            command = []
        if command:
            tool_result = _run_fixed_tool("video_studio", command, destination, relative_out, timeout=14400)
            tool_result["generation_mode"] = "local_model" if model_enabled else "explicit_template_demo"
            results.append(tool_result)
    elif video_requested and not model_enabled:
        results.append({
            "tool": "video_studio", "status": "blocked" if render_requested else "not_run",
            "reason": "A full MP4 render requires an enabled local model. No misleading template was substituted; use the CEO's specialist deliverables and research reports, or explicitly request a template demo.",
        })

    if product_requested:
        title_match = re.search(r"(?i)\b(?:product|prototype)\s*(?:called|named|titled|:)\s*([^.;\n]{1,100})", text)
        title = title_match.group(1).strip() if title_match else re.sub(r"[-_]+", " ", slug(text[:70])).title()
        idea = text[:1000]
        output = destination / "product-prototype"
        relative_out = output.resolve().relative_to(ROOT).as_posix()
        command = [sys.executable, str(ROOT / "product_studio" / "build_product.py"),
                   "--title", title[:100], "--idea", idea, "--out", relative_out]
        if source_path is not None:
            command.extend(["--source-file", str(source_path)])
        tool_result = _run_fixed_tool("product_studio", command, destination, relative_out, timeout=900)
        tool_result["generation_mode"] = "local_model" if model_enabled else "deterministic_template"
        if not model_enabled:
            tool_result["note"] = "Local model disabled: this is a generic starter template, not a product-specific AI implementation."
        results.append(tool_result)
    return results


def _run_fixed_tool(name, command, destination, relative_out, timeout):
    """Execute a fixed in-repository builder and persist bounded diagnostics."""
    log_path = destination / (name.replace("_", "-") + "-tool.log")
    try:
        result = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True,
                                timeout=timeout, check=False)
        output = (result.stdout or "")[-12000:]
        errors = (result.stderr or "")[-12000:]
        log_path.write_text("STDOUT\n" + output + "\nSTDERR\n" + errors + "\n", encoding="utf-8")
        return {
            "tool": name, "status": "completed" if result.returncode == 0 else "failed",
            "exit_code": result.returncode, "artifact_dir": relative_out,
            "log_file": str(log_path.relative_to(ROOT)),
            "summary": output[-2000:] if output else errors[-2000:],
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        log_path.write_text(type(exc).__name__ + ": " + str(exc)[:1000] + "\n", encoding="utf-8")
        return {
            "tool": name, "status": "failed", "artifact_dir": relative_out,
            "log_file": str(log_path.relative_to(ROOT)),
            "error": type(exc).__name__ + ": " + str(exc)[:500],
        }


def run_pipeline(task, context="", agent_ids=None, output_dir=None, config=None):
    if not isinstance(task, str) or not task.strip() or len(task) > 6000:
        raise ValueError("Task must be 1–6000 characters.")
    roles = dispatch.load_json(dispatch.ROSTER, {}).get("agents", [])
    roles_by_id = {role.get("id"): role for role in roles}
    cfg = config if config is not None else dispatch.load_json(ROOT / "config.json", {})
    if agent_ids is None:
        assignments, delegation_mode = plan_delegation(task.strip(), context, cfg, roles_by_id)
    else:
        selected = [str(agent_id).strip().upper() for agent_id in agent_ids]
        if not selected or len(selected) > 51 or len(set(selected)) != len(selected):
            raise ValueError("Choose 1–51 unique specialist IDs; AGENT-50 is reserved for human approval.")
        if any(agent_id not in roles_by_id for agent_id in selected):
            raise ValueError("Unknown specialist ID in pipeline.")
        if "AGENT-50" in selected or "AGENT-01" in selected:
            raise ValueError("CEO and human approval roles cannot be run as ordinary specialist stages.")
        assignments = [{"agent_id": agent_id, "task": "Complete your specialist contribution to this overall goal: " + task.strip()} for agent_id in selected]
        delegation_mode = "user_selected_roles"
    selected = [item["agent_id"] for item in assignments]
    destination = Path(output_dir).resolve() if output_dir else WORKSPACE / "orchestration" / slug(task[:80])
    if destination == WORKSPACE or WORKSPACE not in destination.parents:
        raise ValueError("Pipeline output must remain inside the project workspace.")
    destination.mkdir(parents=True, exist_ok=True)
    combined_context = context[:20000]
    (destination / "00-ceo-delegation.json").write_text(
        json.dumps({"task": task.strip(), "delegation_mode": delegation_mode,
                    "assignments": assignments, "human_approval_role": "AGENT-50"},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    records = []
    for index, assignment in enumerate(assignments, start=1):
        agent_id = assignment["agent_id"]
        role = roles_by_id[agent_id]
        specialist_task = assignment.get("task") or ("Complete your specialist contribution to: " + task.strip())
        instruction = (
            "OVERALL USER GOAL:\n" + task.strip()
            + "\n\nYOUR CEO-ASSIGNED SUBTASK:\n" + specialist_task
            + "\n\nPipeline stage " + str(index) + " of " + str(len(assignments)) + ". "
            + "Work on your assigned responsibility, not the entire task in parallel. "
            + "Use prior-stage notes as unverified working context. Correct errors when evidence permits. "
            + "This stage automatically attempts free web research. Prioritize primary sources, use the retrieved page text, compare independent sources for important claims, cite URLs, distinguish sourced facts from assumptions, and disclose search failures. Do not claim page verification unless page content was supplied. Do not claim external actions. "
            + "Return your concrete deliverable, validation status, and explicit unresolved issues."
        )
        filename = str(index).zfill(2) + "-" + slug(agent_id + "-" + role["name"]) + ".md"
        research_dir = ROOT / "workspace" / "research" / "agent-runs"
        reports_before = set(research_dir.glob(agent_id.lower() + "-*.md")) if research_dir.is_dir() else set()
        try:
            result = dispatch.run_role(role, instruction, combined_context, cfg)
            if not isinstance(result, str) or not result.strip():
                raise ValueError("Specialist returned an empty result.")
        except Exception as exc:
            failure = {
                "sequence": index, "agent_id": agent_id, "role": role["name"],
                "assigned_task": specialist_task, "output_file": None, "status": "failed",
                "error_type": type(exc).__name__, "error": str(exc)[:500],
                "mode": "local_model" if cfg.get("model", {}).get("enabled") else "template_fallback",
            }
            records.append(failure)
            manifest = build_manifest(task, records, cfg, status="failed", delegation_mode=delegation_mode, assignments=assignments)
            (destination / "pipeline-status.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return destination, manifest
        (destination / filename).write_text(result.rstrip() + "\n", encoding="utf-8")
        reports_after = set(research_dir.glob(agent_id.lower() + "-*.md")) if research_dir.is_dir() else set()
        research_reports = sorted(str(path.relative_to(ROOT)) for path in reports_after - reports_before)
        research_status = "report_saved" if research_reports else ("failure_disclosed" if "WEB RESEARCH ATTEMPT FAILED" in result else "not_confirmed")
        records.append({
            "sequence": index, "agent_id": agent_id, "role": role["name"],
            "assigned_task": specialist_task, "output_file": filename, "status": "draft_generated",
            "research_status": research_status, "research_reports": research_reports,
            "mode": "local_model" if cfg.get("model", {}).get("enabled") else "template_fallback",
        })
        combined_context = (combined_context + "\n\n--- " + role["name"] + " output (unverified) ---\n" + result)[-24000:]
    tool_context = (context + "\n\n## CEO specialist research and deliverables (unverified until reviewed)\n" + combined_context[-24000:])[:40000]
    tool_runs = run_builtin_tools(task, destination, cfg, source_context=tool_context)
    required_tool_failed = any(item.get("status") == "failed" for item in tool_runs)
    final_status = "failed" if required_tool_failed else "draft"
    manifest = build_manifest(task, records, cfg, status=final_status, delegation_mode=delegation_mode, assignments=assignments, tool_runs=tool_runs)
    (destination / "pipeline-status.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination, manifest


def build_manifest(task, records, cfg, status, delegation_mode="unspecified", assignments=None, tool_runs=None):
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "task": task.strip(),
        "pipeline": records,
        "delegation_mode": delegation_mode,
        "ceo_assignments": assignments or [],
        "tool_runs": tool_runs or [],
        "status": status,
        "model_enabled": bool(cfg.get("model", {}).get("enabled")),
        "research_performed": "attempted_for_each_specialist_stage",
        "research_method": "DuckDuckGo HTML search plus bounded public webpage text extraction; retrieved content is evidence to assess, not automatic verification",
        "research_pages_independently_verified": False,
        "external_actions_performed": False,
        "human_review_required": True,
        "note": "Sequential specialist pipeline; each specialist run attempts fresh web research and receives search leads. Search availability can fail, snippets are not independent verification, and outputs require quality review.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True)
    parser.add_argument("--context-file")
    parser.add_argument("--agents", default=None,
                        help="Optional comma-separated specialist IDs. Omit to let the CEO delegate automatically.")
    parser.add_argument("--out", default="workspace/orchestration/run")
    args = parser.parse_args()
    try:
        context = read_context(args.context_file)
        selected_agents = [part.strip().upper() for part in args.agents.split(",") if part.strip()] if args.agents else None
        destination, manifest = run_pipeline(args.task, context, selected_agents, ROOT / args.out)
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc))
    print("Pipeline output:", destination)
    print("Delegation:", manifest.get("delegation_mode", "unknown"))
    print("Stages:", len(manifest["pipeline"]))
    print("Mode:", "local model" if manifest["model_enabled"] else "template fallback; no AI generation")
    print("Each specialist stage attempts web research; see stage outputs for source leads and limitations.")
    print("Human review required; no external action was performed.")


if __name__ == "__main__":
    main()
