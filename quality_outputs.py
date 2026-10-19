"""Offline templates that produce evidence-safe work packages."""
from textwrap import dedent

def youtube_package(title, request):
    topic = (request or title or "Your topic").strip()[:1000]
    return dedent(f"""\
    # YouTube Production Package: {title}

    **Mode: offline scaffold.** No model or web research was used. Replace every [VERIFY] item with evidence before publishing.

    ## Creative brief
    - Topic: {topic}
    - Audience: curious non-specialists; explain technical terms on first use.
    - Narration default: natural Urdu with English technical terms.
    - Promise: one clear question, a step-by-step explanation, evidence, limitations, and a practical takeaway.

    ## Scene-by-scene script and motion plan

    ### 01 — Cold open (0:00–0:15)
    **Narration:** “Ek simple sawal: {topic}. Is ke peeche asal mein kya ho raha hai—and is se aap ko kya farq parta hai? Aaj hum isay step by step decode karenge.”
    **Visual:** near-black frame, 3–6 word headline, one accent keyword, short push-in, hard cut on final word.
    **Motion/audio:** reveal headline words 3–4 frames apart; one impact, then music ducks under speech.

    ### 02 — Define the problem (0:15–0:45)
    **Narration scaffold:** “Aam assumption [VERIFY] hai, lekin important difference [VERIFY] hai. Is distinction ko samajhna zaroori hai kyun ke [evidence-backed reason].”
    **Visual:** split screen labelled ASSUMPTION / WHAT TO CHECK; highlight one difference.
    **Motion:** 8–12 frame wipe; labels remain pinned.

    ### 03 — Explain the mechanism (0:45–1:30)
    **Narration scaffold:** “Step one input hai: [verified input]. Step two processing hai: [verified operation]. Step three output hai: [verified output].”
    **Visual:** three-stage pipeline with accurate labels, connectors, and one failure path.
    **Motion:** draw connectors first, reveal nodes sequentially, pause before output.
    **Evidence gate:** [VERIFY: official documentation or reproducible test].

    ### 04 — Demonstration (1:30–2:15)
    **Narration scaffold:** “Input [real input] tha, expected result [expected], aur observed result [measured]. In teen cheezon ko alag rakhein.”
    **Visual:** screen recording or deterministic mock labelled ILLUSTRATION; show source, date, units, and test conditions.
    **Gate:** if evidence is unavailable, leave this as a research task rather than inventing a result.

    ### 05 — Limitations (2:15–3:00)
    **Narration scaffold:** “Har approach ki limits hoti hain. Is ka benefit [verified benefit] hai, magar limitation [verified limitation] hai. Is liye yeh har situation mein best choice nahi.”
    **Visual:** benefit/limit comparison; warning color only for an actual risk.
    **Motion:** freeze ideal path, reveal edge case, then show mitigation.

    ### 06 — Takeaway and close (3:00–3:30)
    **Narration scaffold:** “Main takeaway yeh hai: [evidence-backed answer]. Agar aap khud test karna chahte hain, [safe next step] karein aur result ko [measurement] se compare karein.”
    **Visual:** three takeaways, one CTA, safe margins for platform UI.
    **Audio:** resolve music after speech; hold final card 0.5–1 second.

    **Duration integrity:** this is a short structural example, not a finished 15-minute script. Expand long-form scenes with sourced examples and enough narration. Shorts should keep one question, one explanation, one takeaway.

    ## Professional motion-graphics direction
    - Use a design system: dark neutral base, one primary accent, one warning color, readable type scale.
    - Hierarchy: headline first, evidence/diagram second, supporting labels third.
    - Motion verbs: establish → reveal → emphasize → resolve. Every movement must communicate a relationship.
    - Use hard cuts for argument changes, wipes for process, match cuts for comparisons.
    - Composite background, subject/diagram, labels, and accents on separate layers.
    - Keep one key message per frame, large mobile-safe text, and consistent camera logic.
    - Prefer deterministic Canvas2D/SVG graphics and reusable components; test on the target phone.
    - Audio priority: narration > music > effects. Duck music under speech and use licensed assets only.

    ## Research register
    | Claim | Required evidence | Status |
    |---|---|---|
    | Definition/mechanism | Official documentation or primary source | [VERIFY] |
    | Numbers/performance | Original report or reproducible test with units/date | [VERIFY] |
    | Example/case study | Source or reproducible demo | [VERIFY] |
    | Limitation/counterpoint | Primary evidence and corroboration where possible | [VERIFY] |
    | Quote/attribution | Exact source, speaker, date, context | [VERIFY] |

    No sources were consulted in this fallback. Record URL, publisher, publication date, claim supported, and access date when research is performed.

    ## Packaging
    - Title A: {title}: How It Actually Works
    - Title B: The Simple Explanation of {topic[:70]}
    - Title C: What Most Explanations Miss About {topic[:60]}
    - Thumbnail: one focal diagram/object and 2–4 words; no unverified numbers or misleading imagery.
    - Description opening: “We break down {topic} step by step, examine the evidence, and explain key limitations.”
    - Add only real sources and final timestamps after editing; never invent chapters or citations.

    ## Shorts cutdown
    - 0–2s: state the question visually and verbally.
    - 2–12s: explain the mechanism with one animated diagram.
    - 12–25s: show verified evidence or a labelled illustration.
    - 25–35s: state the limitation and takeaway.
    - End with one CTA; reframe to 9:16 and check platform UI overlaps.

    ## Release QA
    - [ ] Claims are sourced or labelled as illustrative/hypothetical.
    - [ ] Numbers, dates, quotes, and names are verified against primary evidence.
    - [ ] Script matches final visuals and narration.
    - [ ] Captions are accurate, timed, and readable on a phone.
    - [ ] Audio is intelligible on phone speakers and headphones.
    - [ ] Footage, music, logos, and text have appropriate rights.
    - [ ] Render dimensions, frame rate, duration, audio, and file are validated.
    - [ ] Metadata accurately represents the video; a human reviews before upload.

    ## Next actions
    1. Supply trusted source notes or enable a compatible local model for a tailored script.
    2. Replace [VERIFY] placeholders with evidence or remove the claim.
    3. Expand to the requested duration without filler.
    4. Render a 20–30 second proof of concept and inspect it on the phone.
    5. Complete QA. This package does not research, render, upload, or publish by itself.
    """).strip() + "\n"

def structured_plan(title, request):
    return dedent(f"""\
    # {title}\n\n    ## Execution Plan

    ## Outcome
    {request}

    ## Definition of done
    - Deliverable exists at a named path or in a usable view.
    - Each requirement maps to a visible acceptance check.
    - Assumptions, dependencies, and exclusions are explicit.
    - Tests cover success, invalid input, and a boundary case.
    - No external action is claimed without service confirmation.

    ## Work breakdown
    | Stage | Work | Acceptance evidence |
    |---|---|---|
    | Define | Extract goal, user, constraints, format, deadline | Requirements checklist |
    | Design | Choose the smallest sufficient solution | Design and trade-offs |
    | Build | Produce the deliverable, not just instructions | Files/output exist |
    | Verify | Test normal, empty, invalid, boundary input | Test log with results |
    | Review | Check correctness, security, accessibility, usability | Findings by severity |
    | Handoff | Explain run, inspect, troubleshooting | Exact commands and limits |

    ## Risk controls
    - Do not invent data, sources, credentials, or successful tool results.
    - Keep private configuration out of source control.
    - Require human approval for publication, payments, messages, destructive changes, and account actions.
    - Stop at missing dependency gates and name the dependency.

    **Status:** offline structured plan; no model reasoning or external research was run.
    """).strip() + "\n"

def structured_draft(title, request):
    return dedent(f"""\
    # Deliverable Draft: {title}

    ## Request
    {request}

    ## Draft quality requirements
    1. Identify the intended reader/viewer and the single outcome they need.
    2. Put useful information first; remove filler and repetition.
    3. Use supplied examples or label illustrative examples clearly.
    4. Mark unsupported factual claims under VERIFY BEFORE USE.
    5. Match requested format, language, sections, and length.
    6. End with a concrete next action.
    7. Check completeness, specificity, accuracy, voice, and formatting.

    **Status:** structured drafting scaffold only. No local model is enabled, so this is not finished prose. Enable a compatible local model for a tailored draft.
    """).strip() + "\n"

def structured_review(title, context):
    excerpt = context or "(No readable workspace text files were found.)"
    return dedent(f"""\
    # Review Report: {title}

    ## Scope
    The runner supplied this workspace excerpt. This fallback cannot semantically judge correctness or execute tests.

    {excerpt}

    ## Review gates
    | Gate | Pass criteria | Status |
    |---|---|---|
    | Requirements | Acceptance criteria have evidence | NOT VERIFIED |
    | Correctness | Representative cases match expected behavior | NOT VERIFIED |
    | Evidence | Claims link to sources or reproducible tests | NOT VERIFIED |
    | Error handling | Missing/invalid/boundary inputs fail safely | NOT VERIFIED |
    | Security/privacy | No secrets, unsafe paths, or uncontrolled actions | NOT VERIFIED |
    | Usability | Mobile readability and accessible controls | NOT VERIFIED |
    | Release | Build/test logs and handoff exist | NOT VERIFIED |

    ## Findings
    - Checks above have not been executed by this template.
    - Test results cannot be inferred from file names.
    - Run project-specific tests, record actual results, and compare them with requirements.

    **Status:** checklist only; no semantic review or tests were performed. Treat all gates as open until evidence is attached.
    """).strip() + "\n"
