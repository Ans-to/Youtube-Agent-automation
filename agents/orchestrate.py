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
    if source.stat().st_size > 2_000_000:
        raise ValueError("Context file must not exceed 2 MB.")
    return source.read_text(encoding="utf-8", errors="replace")[:50000]



def heuristic_assignments(task):
    """Transparent no-model routing: a small role set matched to task intent."""
    text = task.lower()
    explicit_video = bool(re.search(r"\b(video|shorts|short-form|storyboard|motion graphics|video production|youtube script|video script|youtube content package|faceless channel video)\b", text))
    # Creative screenplay/fight requests often do not say "video" or "YouTube".
    # Route them to script/storyboard/motion roles without misclassifying code scripts.
    creative_scene_request = bool(
        re.search(r"\b(fight|battle|screenplay|superhero|anime|animation|animated sequence|scene[- ]by[- ]scene)\b", text)
        and re.search(r"\b(script|screenplay|scene|sequence|storyboard|create|write|draft)\b", text)
    )
    video = explicit_video or creative_scene_request
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
    reviewer = next((item for item in result if item["agent_id"] == "AGENT-08"), None)
    result = [item for item in result if item["agent_id"] != "AGENT-08"]
    if reviewer is None:
        reviewer = {"agent_id": "AGENT-08", "task": "Review the combined work for factual support, contradictions, omissions, and unresolved risks. Use the supplied research report and cite source URLs."}
    reviewer["task"] = "FINAL QUALITY GATE: " + reviewer["task"]
    result.append(reviewer)
    return result[:8]


def plan_delegation(task, context, cfg, roles_by_id):
    """Let the CEO choose specialist roles; use deterministic routing only when no valid model plan exists."""
    model_enabled = bool(cfg.get("model", {}).get("enabled"))
    ceo_error = False
    if model_enabled:
        skill_profiles = {
            profile.get("agent_id"): profile
            for profile in dispatch.load_json(dispatch.SKILLBOOK, {}).get("profiles", [])
        }
        roster = []
        for role in roles_by_id.values():
            agent_id = role.get("id")
            if agent_id in {"AGENT-01", "AGENT-50"}:
                continue
            skill = skill_profiles.get(agent_id, {})
            roster.append({
                "id": agent_id,
                "name": role.get("name"),
                "department": role.get("department"),
                "mission": str(role.get("mission", ""))[:180],
                "expertise": str(skill.get("expertise", ""))[:140],
                "deliverable": str(skill.get("deliverable_contract", ""))[:120],
            })
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
            # Delegation is a lightweight planning call. Specialist stages perform
            # their own task-specific research; searching before the CEO can route work
            # adds latency and can time out CPU-only local models.
            raw = dispatch.run_role(
                roles_by_id["AGENT-01"], ceo_task, context[:6000], cfg,
                perform_research=False,
            )
            assignments = parse_ceo_assignments(raw, roles_by_id)
            if assignments:
                return assignments, "ceo_model_delegation"
        except Exception:
            ceo_error = True
    assignments, _ = heuristic_assignments(task)
    if model_enabled:
        return assignments, "heuristic_fallback_after_ceo_error" if ceo_error else "heuristic_fallback_invalid_ceo_plan"
    return assignments, "heuristic_no_model"


def run_builtin_tools(task, destination, cfg, source_context=""):
    """Run only fixed, repository-owned artifact builders selected by clear task intent."""
    results = []
    text = task.strip()
    request_match = re.search(r"(?is)USER REQUEST:\s*(.+?)(?:\n\nREQUIRED OUTCOME:|$)", text)
    intent_text = request_match.group(1).strip() if request_match else text
    lower = text.lower()
    intent_lower = intent_text.lower()
    model_enabled = bool(cfg.get("model", {}).get("enabled"))
    verbs = r"\b(build|create|make|generate|produce|develop|implement|render|export)\b"

    # "Build a YouTube automation studio" is a software task, not a request to render a video.
    video_intent = re.search(
        r"\b(video|shorts|short-form|storyboard|motion graphics|video production|youtube script|video script|youtube content package|faceless channel video)\b",
        intent_lower,
    )
    video_requested = bool(video_intent and re.search(verbs, intent_lower))
    product_requested = bool(re.search(
        r"\b(?:build|create|make|develop|implement)\s+(?:(?:me|a|an|the)\s+)?(?:(?:simple|small|local|offline|responsive|basic|functional|custom|tiny|working|digital)\s+){0,3}(?:product|app|website|web app|software tool|tool|utility|prototype|calculator|dashboard)\b",
        intent_lower,
    ) or re.search(r"\bproduct idea for (?:a )?tool\b", intent_lower))
    render_requested = bool(re.search(r"\b(render|mp4|export video|final video)\b", intent_lower))
    template_demo = bool(re.search(r"\b(template demo|demo render)\b", intent_lower)) and not model_enabled
    source_path = None
    if source_context.strip() and (video_requested or product_requested):
        source_path = destination / "source-notes.md"
        source_path.write_text(source_context[:50000], encoding="utf-8")
    if video_requested:
        topic_match = re.search(r"(?i)\b(?:about|on|topic\s*[:=])\s+(.+?)(?:[.;\n]|,\s*(?:include|with|and also)\b|$)", intent_text)
        topic = (topic_match.group(1).strip() if topic_match else intent_text[:220]).strip(" \t\r\n.,;:")
        topic = topic[:500] or "Technology explainer"
        fmt = "shorts" if re.search(r"\b(shorts|short-form|vertical)\b", intent_lower) else "long"
        output = destination / "video-production"
        relative_out = output.resolve().relative_to(ROOT).as_posix()
        command = [sys.executable, str(ROOT / "video_studio" / "production.py"),
                   "--topic", topic, "--format", fmt, "--out", relative_out]
        if source_path is not None:
            command.extend(["--source-file", str(source_path)])
        else:
            command.append("--research")
        duration_match = re.search(r"(?i)target[_ ]minutes\s*[:=]\s*(\d+(?:\.\d+)?)", intent_text)
        if duration_match:
            command.extend(["--target-minutes", duration_match.group(1)])
        if render_requested and model_enabled:
            command.append("--render")
            if re.search(r"\b(with voice|with local narration|piper narration)\b", intent_lower):
                command.append("--with-voice")
        elif render_requested and template_demo:
            command.extend(["--render", "--render-template"])
        elif render_requested and not model_enabled:
            results.append({
                "tool": "video_render", "status": "blocked",
                "artifact_dir": relative_out,
                "reason": "Full-length MP4 rendering is blocked because no local model is enabled. A separate deterministic template package will be generated and clearly labelled; it is not a substitute for the requested final video.",
            })
        tool_result = _run_fixed_tool("video_studio", command, destination, relative_out, timeout=14400)
        tool_result["generation_mode"] = "local_model" if model_enabled else ("explicit_template_demo" if template_demo and render_requested else "deterministic_template")
        if not model_enabled:
            tool_result["note"] = "No local model is enabled: script and storyboard are deterministic scaffolding, not a researched or AI-written final video."
        results.append(tool_result)

    if product_requested:
        title_match = re.search(r"(?i)\b(?:product|prototype|app|tool|website)\s*(?:called|named|titled|:)\s*([^.;\n]{1,100})", intent_text)
        title_seed = re.sub(r"(?i)^\s*(?:please\s+)?(?:build|create|make|generate|develop|implement)\s+(?:a|an|the)?\s*", "", intent_text).strip()
        title = title_match.group(1).strip() if title_match else re.sub(r"[-_]+", " ", slug(title_seed[:70])).title()
        idea_match = re.search(r"(?is)user problem and product idea:\s*(.+?)(?:\.\s*research the user need|$)", intent_text)
        idea = (idea_match.group(1).strip() if idea_match else intent_text[:1000])[:1000]
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
    if not isinstance(task, str) or not task.strip() or len(task) > 20000:
        raise ValueError("Task must be 1–20,000 characters.")
    roles = dispatch.load_json(dispatch.ROSTER, {}).get("agents", [])
    roles_by_id = {role.get("id"): role for role in roles}
    cfg = config if config is not None else dispatch.load_json(ROOT / "config.json", {})
    destination = Path(output_dir).resolve() if output_dir else WORKSPACE / "orchestration" / slug(task[:80])
    if destination == WORKSPACE or WORKSPACE not in destination.parents:
        raise ValueError("Pipeline output must remain inside the project workspace.")
    destination.mkdir(parents=True, exist_ok=True)
    progress_path = destination / "pipeline-progress.json"

    def save_progress(status, phase, message, completed_stages=0, total_stages=0, agent_id=None, role_name=None):
        snapshot = {
            "status": status, "phase": phase, "message": message,
            "completed_stages": completed_stages, "total_stages": total_stages,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if agent_id:
            snapshot["agent_id"] = agent_id
        if role_name:
            snapshot["role"] = role_name
        temporary = progress_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(progress_path)

    save_progress("running", "CEO delegation", "CEO is planning the task and selecting specialist responsibilities.")
    ceo_research_dir = ROOT / "workspace" / "research" / "agent-runs"
    ceo_reports_before = set(ceo_research_dir.glob("agent-01-*.md")) if ceo_research_dir.is_dir() else set()
    if agent_ids is None:
        assignments, delegation_mode = plan_delegation(task.strip(), context, cfg, roles_by_id)
    else:
        selected = [str(agent_id).strip().upper() for agent_id in agent_ids]
        if not selected or len(selected) > 50 or len(set(selected)) != len(selected):
            raise ValueError("Choose 1–50 unique worker IDs; AGENT-01 is the CEO and AGENT-50 is reserved for human approval.")
        if any(agent_id not in roles_by_id for agent_id in selected):
            raise ValueError("Unknown specialist ID in pipeline.")
        if "AGENT-50" in selected or "AGENT-01" in selected:
            raise ValueError("CEO and human approval roles cannot be run as ordinary specialist stages.")
        assignments = [{"agent_id": agent_id, "task": "Complete your specialist contribution to this overall goal: " + task.strip()} for agent_id in selected]
        assignments = [item for item in assignments if item["agent_id"] != "AGENT-08"]
        assignments.append({
            "agent_id": "AGENT-08",
            "task": "FINAL QUALITY GATE: Review the combined deliverables, research evidence, factual claims, contradictions, omissions, and unresolved risks. Cite source URLs and end with OVERALL QUALITY GATE: PASS, PARTIAL, or FAIL.",
        })
        delegation_mode = "user_selected_roles"
    ceo_reports_after = set(ceo_research_dir.glob("agent-01-*.md")) if ceo_research_dir.is_dir() else set()
    ceo_research_reports = sorted(str(path.relative_to(ROOT)) for path in ceo_reports_after - ceo_reports_before)
    selected = [item["agent_id"] for item in assignments]
    save_progress("running", "Specialist work", "CEO assigned " + str(len(assignments)) + " stages; starting specialist execution.", 0, len(assignments))
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
        save_progress("running", "Specialist stage " + str(index) + "/" + str(len(assignments)), agent_id + " / " + role["name"] + " is researching and producing its assigned deliverable.", index - 1, len(assignments), agent_id, role["name"])
        instruction = (
            "OVERALL USER GOAL:\n" + task.strip()
            + "\n\nYOUR CEO-ASSIGNED SUBTASK:\n" + specialist_task
            + "\n\nPipeline stage " + str(index) + " of " + str(len(assignments)) + ". "
            + "Work on your assigned responsibility, not the entire task in parallel. "
            + "Use prior-stage notes as unverified working context. Correct errors when evidence permits. "
            + "This stage automatically attempts free web research. Prioritize primary sources, use the retrieved page text, compare independent sources for important claims, cite URLs, distinguish sourced facts from assumptions, and disclose search failures. Do not claim page verification unless page content was supplied. Do not claim external actions. "
            + "Return your concrete deliverable, validation status, and explicit unresolved issues."
        )
        if agent_id == "AGENT-08":
            instruction += (
                "\n\nMACHINE-READABLE FINAL GATE: End your deliverable with exactly one line in this format: "
                "OVERALL QUALITY GATE: PASS, PARTIAL, or FAIL. Use PASS only when critical claims are supported; "
                "PARTIAL when material evidence is missing; FAIL when material claims are unsupported, contradictory, or unsafe. "
                "Do not mark PASS merely because the draft is well formatted."
            )
        filename = str(index).zfill(2) + "-" + slug(agent_id + "-" + role["name"]) + ".md"
        research_dir = ROOT / "workspace" / "research" / "agent-runs"
        reports_before = set(research_dir.glob(agent_id.lower() + "-*.md")) if research_dir.is_dir() else set()
        try:
            result = dispatch.run_role(role, instruction, combined_context, cfg)
            if not isinstance(result, str) or not result.strip():
                raise ValueError("Specialist returned an empty result.")
        except Exception as exc:
            # Preserve research files created before a model timeout, then continue to
            # downstream specialists and the final quality gate.
            reports_after_failure = set(research_dir.glob(agent_id.lower() + "-*.md")) if research_dir.is_dir() else set()
            failed_stage_reports = sorted(reports_after_failure - reports_before)
            failed_stage_report_names = [str(path.relative_to(ROOT)) for path in failed_stage_reports]
            research_pages_attempted = 0
            research_pages_fetched = 0
            evidence_sections = []
            for report_path in failed_stage_reports:
                structured_path = report_path.with_suffix(".json")
                try:
                    report_data = json.loads(structured_path.read_text(encoding="utf-8"))
                    metadata = report_data.get("metadata", {})
                    research_pages_attempted += int(metadata.get("pages_attempted", 0))
                    research_pages_fetched += int(metadata.get("pages_fetched", 0))
                except (OSError, ValueError, TypeError):
                    pass
                try:
                    evidence_sections.append(
                        "\n\n## Research saved before specialist failure — "
                        + str(report_path.relative_to(ROOT)) + "\n"
                        + report_path.read_text(encoding="utf-8", errors="replace")[:5000]
                    )
                except OSError:
                    pass
            if research_pages_fetched:
                failure_research_status = "pages_fetched"
            elif research_pages_attempted:
                failure_research_status = "search_leads_only"
            elif failed_stage_reports:
                failure_research_status = "failure_disclosed"
            else:
                failure_research_status = "not_recorded"

            failure_filename = str(index).zfill(2) + "-" + slug(agent_id + "-" + role["name"] + "-failure") + ".md"
            report_listing = "\n".join("- " + item for item in failed_stage_report_names) or "- None recorded"
            failure_text = (
                "# Specialist stage failed: " + role["name"] + "\n\n"
                + "- Agent: " + agent_id + "\n"
                + "- Stage: " + str(index) + " of " + str(len(assignments)) + "\n"
                + "- Error type: " + type(exc).__name__ + "\n"
                + "- Error: " + str(exc)[:1000] + "\n"
                + "- Research status before failure: " + failure_research_status + "\n"
                + "- Research pages fetched before failure: " + str(research_pages_fetched) + "\n"
                + "- Research reports: \n" + report_listing + "\n\n"
                + "No specialist deliverable was confirmed. Any saved research below is source evidence to assess, "
                  "not proof of the final claims. Downstream stages may continue, but missing work remains unresolved.\n"
                + "".join(evidence_sections)
            )
            (destination / failure_filename).write_text(failure_text, encoding="utf-8")
            failure = {
                "sequence": index, "agent_id": agent_id, "role": role["name"],
                "assigned_task": specialist_task, "output_file": failure_filename, "status": "failed",
                "research_status": failure_research_status,
                "research_reports": failed_stage_report_names,
                "research_pages_attempted": research_pages_attempted,
                "research_pages_fetched": research_pages_fetched,
                "error_type": type(exc).__name__, "error": str(exc)[:500],
                "mode": "local_model" if cfg.get("model", {}).get("enabled") else "template_fallback",
            }
            records.append(failure)
            save_progress("running", "Recovering from specialist failure", agent_id + " failed; the failure and available research were saved, and later stages will continue.", index, len(assignments), agent_id, role["name"])
            combined_context = (
                combined_context + "\n\n--- " + role["name"] + " stage failure and preserved research ---\n"
                + failure_text
            )[-24000:]
            continue
        (destination / filename).write_text(result.rstrip() + "\n", encoding="utf-8")
        quality_gate = "unconfirmed"
        if agent_id == "AGENT-08":
            gate_match = re.search(r"(?im)^\s*OVERALL QUALITY GATE:\s*(PASS|PARTIAL|FAIL)\s*[.!]?\s*$", result)
            if gate_match:
                quality_gate = gate_match.group(1).lower()
        reports_after = set(research_dir.glob(agent_id.lower() + "-*.md")) if research_dir.is_dir() else set()
        new_report_paths = reports_after - reports_before
        research_reports = sorted(str(path.relative_to(ROOT)) for path in new_report_paths)
        pages_attempted = 0
        pages_fetched = 0
        for report_path in new_report_paths:
            structured_path = report_path.with_suffix(".json")
            try:
                report_data = json.loads(structured_path.read_text(encoding="utf-8"))
                metadata = report_data.get("metadata", {})
                pages_attempted += int(metadata.get("pages_attempted", 0))
                pages_fetched += int(metadata.get("pages_fetched", 0))
            except (OSError, ValueError, TypeError):
                continue
        if pages_fetched:
            research_status = "pages_fetched"
        elif pages_attempted:
            research_status = "search_leads_only"
        elif research_reports:
            research_status = "failure_disclosed"
        else:
            result_lower = result.lower()
            research_status = "failure_disclosed" if ("web research attempt failed" in result_lower or "web research module unavailable" in result_lower) else "not_confirmed"
        records.append({
            "sequence": index, "agent_id": agent_id, "role": role["name"],
            "assigned_task": specialist_task, "output_file": filename, "status": "draft_generated",
            "research_status": research_status, "research_reports": research_reports,
            "research_pages_attempted": pages_attempted, "research_pages_fetched": pages_fetched,
            "quality_gate": quality_gate if agent_id == "AGENT-08" else None,
            "mode": "local_model" if cfg.get("model", {}).get("enabled") else "template_fallback",
        })
        combined_context = (combined_context + "\n\n--- " + role["name"] + " output (unverified) ---\n" + result)[-24000:]
    save_progress("running", "Specialist stage complete", "All specialist stages have returned; assembling research evidence and preparing artifact tools.", len(assignments), len(assignments))
    research_sections = []
    research_budget = 18000
    research_root = (ROOT / "workspace" / "research" / "agent-runs").resolve()
    for record in records:
        for report in record.get("research_reports", []):
            if research_budget <= 0:
                break
            report_path = (ROOT / report).resolve()
            if research_root not in report_path.parents or report_path.suffix.lower() != ".md" or not report_path.is_file():
                continue
            try:
                report_text = report_path.read_text(encoding="utf-8", errors="replace")[:min(5000, research_budget)]
            except OSError:
                continue
            research_sections.append("\n\n## Source-linked research report — " + str(record.get("role", record.get("agent_id", "specialist"))) + "\n" + report_text)
            research_budget -= len(report_text)
        if research_budget <= 0:
            break
    tool_context = (
        (context or "")[:10000]
        + "\n\n## Retrieved specialist research reports (unverified until reviewed)\n"
        + "".join(research_sections)
        + "\n\n## CEO specialist deliverables (unverified until reviewed)\n"
        + combined_context[-10000:]
    )[:40000]
    save_progress("running", "Artifact generation", "Specialist stages finished; building selected artifacts and preparing the final quality status.", len(assignments), len(assignments))
    tool_runs = run_builtin_tools(task, destination, cfg, source_context=tool_context)
    required_tool_failed = any(item.get("status") == "failed" for item in tool_runs)
    required_tool_blocked = any(item.get("status") == "blocked" for item in tool_runs)
    reviewer_record = next((item for item in records if item.get("agent_id") == "AGENT-08"), {})
    reviewer_gate = reviewer_record.get("quality_gate", "unconfirmed")
    specialist_failed = any(item.get("status") == "failed" for item in records)
    final_status = "failed" if required_tool_failed else (
        "blocked" if required_tool_blocked else (
            "review_failed" if reviewer_gate == "fail" else (
                "partial" if specialist_failed or reviewer_gate in {"partial", "unconfirmed"} else "draft"
            )
        )
    )
    manifest = build_manifest(task, records, cfg, status=final_status, delegation_mode=delegation_mode, assignments=assignments, tool_runs=tool_runs, ceo_research_reports=ceo_research_reports)
    (destination / "pipeline-status.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    progress_status = "completed" if final_status == "draft" else ("failed" if final_status == "failed" else "needs_human_action")
    save_progress(progress_status, "Pipeline complete", "Pipeline ended with status: " + final_status + "; final quality gate: " + str(manifest.get("quality_gate", "unconfirmed")) + ".", len(assignments), len(assignments))
    return destination, manifest


def build_manifest(task, records, cfg, status, delegation_mode="unspecified", assignments=None, tool_runs=None, ceo_research_reports=None):
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "task": task.strip(),
        "pipeline": records,
        "delegation_mode": delegation_mode,
        "ceo_assignments": assignments or [],
        "ceo_research_reports": ceo_research_reports or [],
        "tool_runs": tool_runs or [],
        "quality_gate": next((item.get("quality_gate") for item in records if item.get("agent_id") == "AGENT-08"), "unconfirmed"),
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
    if manifest.get("status") == "failed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
