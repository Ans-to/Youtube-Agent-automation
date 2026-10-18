#!/usr/bin/env python3
"""Build a source-aware, scene-by-scene video package with a local model."""
import argparse
import json
import math
import subprocess
import sys
import urllib.error
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
sys.path.insert(0, str(ROOT))
from agent import post_local_model


VISUAL_TYPES = {"hero", "stat", "timeline", "diagram", "comparison", "code", "quote", "waveform"}


def load_config():
    try:
        return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def read_source(path):
    if not path:
        return ""
    source = Path(path).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() not in {".txt", ".md", ".json"}:
        raise ValueError("Source file must be an existing .txt, .md, or .json file.")
    if source.stat().st_size > 2_000_000:
        raise ValueError("Source file exceeds the 2 MB limit.")
    return source.read_text(encoding="utf-8", errors="replace")[:50000]


def parse_json_response(content, label):
    text = str(content or "").strip()
    fence = chr(96) * 3
    if text.startswith(fence):
        text = text.split("\n", 1)[-1]
        if text.endswith(fence):
            text = text[:-3]
        text = text.strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(label + " response was not valid JSON: " + str(exc)) from exc
    if not isinstance(value, dict):
        raise ValueError(label + " response must be a JSON object.")
    return value


def model_json(prompt, cfg, max_tokens):
    model = cfg.get("model", {})
    if not model.get("enabled"):
        return None
    body = {
        "model": model.get("model", "local-model"),
        "messages": [
            {"role": "system", "content": "You are a rigorous faceless-video producer. Use only supplied source evidence; never pretend to browse or verify outside facts. Mark unsupported claims for verification. Return JSON only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.25,
        "max_tokens": min(int(model.get("max_output_tokens", 1800)), max_tokens),
    }
    response = post_local_model(model.get("base_url", ""), body, model.get("timeout_seconds", 120))
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("Local model response did not contain choices[0].message.content.") from exc
    return parse_json_response(content, "Local model")


def create_outline(topic, source_notes, cfg, target_minutes, scene_count, fmt):
    prompt = (
        "Create the outline for a faceless YouTube narration package. Return JSON with keys "
        "title, description, thesis, sections. sections must contain 4–8 objects with name, purpose, "
        "key_points (array), and visual_direction. No full script yet. "
        "Topic: " + topic + "\nFormat: " + fmt + "\nTarget duration minutes: " + str(target_minutes)
        + "\nPlanned scene count: " + str(scene_count)
        + "\nNarration language: Urdu with natural English technical terms.\n"
        "Quality rules: create a coherent narrative arc; avoid filler, clickbait, invented numbers, unsupported certainty, "
        "and repeated talking points. Explain what evidence is needed. If source notes are present, use only what they support; "
        "otherwise clearly mark factual claims for later verification.\n"
        "SUPPLIED SOURCE NOTES (not independently verified):\n"
        + (source_notes[:12000] if source_notes else "(No source notes supplied.)")
    )
    outline = model_json(prompt, cfg, 1800)
    sections = outline.get("sections")
    if not isinstance(sections, list) or not 4 <= len(sections) <= 8:
        raise ValueError("Local model outline must contain 4–8 sections; no package was finalized.")
    cleaned = []
    for index, section in enumerate(sections):
        if not isinstance(section, dict) or not isinstance(section.get("name"), str) or not isinstance(section.get("purpose"), str):
            raise ValueError("Outline section " + str(index + 1) + " is missing required text fields.")
        points = section.get("key_points", [])
        if not isinstance(points, list) or not all(isinstance(point, str) for point in points):
            raise ValueError("Outline section key_points must be an array of strings.")
        cleaned.append({
            "name": section["name"][:100],
            "purpose": section["purpose"][:400],
            "key_points": points[:8],
            "visual_direction": str(section.get("visual_direction", ""))[:500],
        })
    outline["sections"] = cleaned
    outline["title"] = str(outline.get("title") or topic)[:100]
    outline["description"] = str(outline.get("description") or "")[:5000]
    outline["thesis"] = str(outline.get("thesis") or topic)[:1000]
    return outline


def create_scene(topic, outline, section, source_notes, cfg, index, total, target_words, previous_scene):
    visual_list = ", ".join(sorted(VISUAL_TYPES))
    prompt = (
        "Write exactly one production-ready scene for a faceless technology explainer. Return a JSON object with keys "
        "eyebrow, headline, subhead, narration, visual_type, and any appropriate visual data fields. "
        "visual_type must be one of: " + visual_list + ".\n"
        "Topic: " + topic + "\nVideo thesis: " + outline["thesis"] + "\n"
        "Scene " + str(index) + " of " + str(total) + "\n"
        "Section: " + json.dumps(section, ensure_ascii=False) + "\n"
        "Target narration length: approximately " + str(target_words) + " whitespace-separated words. "
        "Use natural Urdu with English technical terms. Keep headline compact and subhead informative. "
        "Narration should move the argument forward, not repeat prior scenes. Use pauses and plain language, not stage directions. "
        "Do not invent citations, dates, measurements, attributed quotations, or claims of web research. "
        "If evidence is missing, explicitly say what needs verification within narration or unresolved_notes. "
        "Visual metadata rules: diagram -> visual_nodes array; timeline -> timeline_events array; stat -> stat_value and stat_label; "
        "comparison -> comparison_left_title, comparison_right_title, comparison_left and comparison_right arrays; "
        "code -> code_lines array; quote -> quote and quote_source only when supplied evidence supports the quote; "
        "waveform needs no extra data; hero may use graphic_label. Add unresolved_notes as an array of strings.\n"
        "Previous scene for continuity (unverified draft): " + json.dumps(previous_scene, ensure_ascii=False)
        + "\nSUPPLIED SOURCE NOTES (not independently verified):\n"
        + (source_notes[:5000] if source_notes else "(No source notes supplied. Flag important claims for fact-checking.)")
    )
    scene = model_json(prompt, cfg, int(cfg.get("model", {}).get("scene_output_tokens", 700)))
    for key in ("eyebrow", "headline", "subhead", "narration"):
        if not isinstance(scene.get(key), str) or not scene[key].strip():
            raise ValueError("Scene " + str(index) + " is missing required text field: " + key)
        scene[key] = scene[key].strip()[:12000 if key == "narration" else 240]
    visual_type = str(scene.get("visual_type", "hero")).lower()
    if visual_type not in VISUAL_TYPES:
        raise ValueError("Scene " + str(index) + " uses unsupported visual_type: " + visual_type)
    scene["visual_type"] = visual_type
    for key in ("visual_nodes", "timeline_events", "comparison_left", "comparison_right", "code_lines", "unresolved_notes"):
        if key in scene and (not isinstance(scene[key], list) or not all(isinstance(v, str) for v in scene[key])):
            raise ValueError("Scene " + str(index) + " field " + key + " must be an array of strings.")
        if key in scene:
            scene[key] = [item[:120] for item in scene[key][:8]]
    return scene


def fallback(topic):
    scenes = [
        {"duration_seconds": 5, "eyebrow": "THE QUESTION", "headline": topic[:80],
         "subhead": "A topic package created with the offline template.", "narration": topic,
         "visual_type": "hero", "graphic_label": "THE CORE IDEA"},
        {"duration_seconds": 5, "eyebrow": "THE CONTEXT", "headline": "What we know",
         "subhead": "Add trusted source notes before presenting factual claims.",
         "narration": "Known context se shuru karein aur factual claims ko reliable sources se verify karein.",
         "visual_type": "diagram", "visual_nodes": ["EVIDENCE", "EXPLANATION", "TAKEAWAY"]},
        {"duration_seconds": 5, "eyebrow": "THE EXPLANATION", "headline": "How it works",
         "subhead": "Use one concept per scene, with a simple visual metaphor.",
         "narration": "Core idea ko step by step explain karein, har scene mein ek concept rakhein.",
         "visual_type": "code", "code_lines": ["input = evidence;", "process = explain(input);", "output = clear_idea;"]},
        {"duration_seconds": 5, "eyebrow": "THE TAKEAWAY", "headline": "What to remember",
         "subhead": "Review, fact-check, and edit before publication.",
         "narration": "Practical takeaway summarize karein. Yeh sirf template hai, researched ya fact-checked content nahi.",
         "visual_type": "timeline", "timeline_events": ["QUESTION", "EVIDENCE", "EXPLAIN", "REVIEW"]},
    ]
    return {"title": topic[:90],
            "description": "Offline template package. Research and verify factual claims before publication.",
            "thesis": topic,
            "script": "Template only: no local model was enabled and no web research was performed. Add trustworthy sources and verify claims before publishing.",
            "scenes": scenes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--out", default="workspace/generated")
    parser.add_argument("--format", choices=["long", "shorts"], default="long")
    parser.add_argument("--target-minutes", type=float, help="Requested narration length; default 15 minutes for long, 1 minute for Shorts.")
    parser.add_argument("--source-file", help="Local .txt, .md, or .json source notes to ground claims.")
    parser.add_argument("--scenes", type=int, help="Override scene count (1–100); defaults to about 3 scenes per minute.")
    parser.add_argument("--render", action="store_true", help="Render final storyboard to MP4.")
    parser.add_argument("--render-template", action="store_true", help="Explicitly permit a short, clearly labelled template demo without AI generation.")
    parser.add_argument("--with-voice", action="store_true", help="Add local Piper narration (requires --render and PIPER_MODEL).")
    args = parser.parse_args()
    topic = args.topic.strip()
    if not topic or len(topic) > 500:
        raise SystemExit("Topic must be 1–500 characters.")
    target_minutes = args.target_minutes if args.target_minutes is not None else (1.0 if args.format == "shorts" else 15.0)
    if not math.isfinite(target_minutes) or target_minutes < 0.25 or target_minutes > 16.0:
        raise SystemExit("Target minutes must be between 0.25 and 16 to stay within renderer resource limits.")
    if args.with_voice and not args.render:
        raise SystemExit("--with-voice requires --render.")
    target_seconds = target_minutes * 60
    default_scenes = max(4, math.ceil(target_minutes * 3))
    scene_count = args.scenes if args.scenes is not None else default_scenes
    if scene_count < 1 or scene_count > 100 or scene_count > 30000:
        raise SystemExit("Scene count must be between 1 and 100.")
    if target_seconds > 1000 or round(target_seconds * 30) > 30000:
        raise SystemExit("Target duration exceeds the renderer's supported limits.")
    cfg = load_config()
    source_notes = read_source(args.source_file)
    model_enabled = bool(cfg.get("model", {}).get("enabled"))
    if args.render and not model_enabled and not args.render_template:
        raise SystemExit("No local model is enabled. This produces only a 20-second template, not the requested full video. Use --render-template only for a demo.")
    if args.render_template and model_enabled:
        raise SystemExit("--render-template is only for the deterministic no-model demo. Use --render for model-generated content.")

    if model_enabled:
        if source_notes:
            outline = create_outline(topic, source_notes, cfg, target_minutes, scene_count, args.format)
        else:
            outline = create_outline(topic, "", cfg, target_minutes, scene_count, args.format)
        section_list = outline["sections"]
        scenes = []
        previous = {"headline": "", "summary": "Opening scene; no previous scene."}
        words_per_scene = max(12, round(target_minutes * 125 / scene_count))
        for index in range(1, scene_count + 1):
            section = section_list[min(len(section_list) - 1, (index - 1) * len(section_list) // scene_count)]
            scene = create_scene(topic, outline, section, source_notes, cfg, index, scene_count, words_per_scene, previous)
            words = len(scene["narration"].split())
            if words < max(8, int(words_per_scene * 0.45)):
                scene = create_scene(topic, outline, section, source_notes, cfg, index, scene_count,
                                     words_per_scene * 2, previous)
                if len(scene["narration"].split()) < max(8, int(words_per_scene * 0.45)):
                    raise ValueError("Scene " + str(index) + " narration remained too short after retry; no final package was marked ready.")
            scene["duration_seconds"] = target_seconds / scene_count
            scene.setdefault("caption", scene["narration"])
            scenes.append(scene)
            previous = {"headline": scene["headline"], "summary": scene["narration"][-800:]}
        script_text = "\n\n".join("[" + str(i + 1) + "] " + scene["narration"] for i, scene in enumerate(scenes))
        required_words = max(80, int(target_minutes * 85))
        if len(script_text.split()) < required_words:
            raise ValueError("Generated script is below the minimum narration-length check; increase scene count or model output capacity.")
        content = {"title": outline["title"], "description": outline["description"],
                   "thesis": outline["thesis"], "script": script_text, "scenes": scenes}
        generated_by = "local_model_multi_pass"
        actual_target_seconds = target_seconds
    else:
        content = fallback(topic)
        scenes = content["scenes"]
        generated_by = "deterministic_template"
        actual_target_seconds = sum(float(scene["duration_seconds"]) for scene in scenes)

    workspace_root = (ROOT / "workspace").resolve()
    output_dir = (ROOT / args.out).resolve()
    if output_dir == workspace_root or workspace_root not in output_dir.parents:
        raise SystemExit("Output directory must remain inside the project workspace.")
    output_dir.mkdir(parents=True, exist_ok=True)
    script_body = str(content.get("script", ""))
    title = str(content.get("title", topic))[:100]
    desc = str(content.get("description", ""))
    source_section = "\n\n## Source notes supplied by user\n" + source_notes[:50000] if source_notes else "\n\n## Source verification\nNo source notes were supplied. Verify factual claims before publication."
    script_md = "# " + title + "\n\n" + desc + "\n\n## Narration draft\n" + script_body + source_section + "\n"
    (output_dir / "script.md").write_text(script_md, encoding="utf-8")
    storyboard = {
        "title": title, "width": 1080 if args.format == "shorts" else 1920,
        "height": 1920 if args.format == "shorts" else 1080, "fps": 30,
        "scenes": scenes,
    }
    (output_dir / "storyboard.json").write_text(json.dumps(storyboard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    actual_words = len(script_body.split())
    status = {
        "status": "draft" if model_enabled else "template_demo",
        "format": args.format, "topic": topic, "target_minutes": target_minutes,
        "target_seconds": target_seconds, "storyboard_seconds": sum(float(s["duration_seconds"]) for s in scenes),
        "narration_words": actual_words, "generated_by": generated_by,
        "source_notes_provided": bool(source_notes), "web_research_performed": False,
        "human_review_required": True, "published": False,
        "note": "Model output is a draft. This code does not independently research or verify claims.",
    }
    (output_dir / "package-status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Draft package:", output_dir)
    print("Mode:", generated_by)
    print("Narration words:", actual_words, "| target minutes:", target_minutes, "| storyboard seconds:", status["storyboard_seconds"])
    print("Web research performed: no. Verify factual claims before publishing.")
    if args.render:
        command = [sys.executable, str(BASE / "studio.py"), "--storyboard",
                   str(output_dir / "storyboard.json"), "--output", str(output_dir / "video.mp4")]
        if args.with_voice:
            command.append("--with-voice")
        subprocess.run(command, check=True)
    elif args.render_template:
        command = [sys.executable, str(BASE / "studio.py"), "--storyboard",
                   str(output_dir / "storyboard.json"), "--output", str(output_dir / "video.mp4")]
        subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
