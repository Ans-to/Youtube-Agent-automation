# Specialist playbook and evaluation system

## What "training" means in this repository

The project does not fine-tune model weights. Instead, every role has a structured playbook in `skillbooks.json` and `dispatch.py` injects the applicable playbook into the configured local model prompt. Each playbook defines domain expertise, a workflow, quality gates, failure modes, a deliverable contract, and a practice drill. The specialist is instructed to report a concise status against those gates; the report itself is not proof that a gate passed.

This makes behavior more consistent and testable, but capability still depends on the local model, task quality, available evidence, context length, and human review. It is not honest to describe any model as guaranteed to be a master solely because a prompt says so.

## Structure

- `roster.json`: 52 role profiles. There are 51 specialist roles; `AGENT-50` is the human approval boundary and may not run automatically.
- `skillbooks.json`: one playbook per roster role, with workflow steps, quality gates, failure modes, deliverable contracts, and a practice drill.
- `dispatch.py`: injects the corresponding playbook into each role run. If model generation is disabled, it prints the playbook as a checklist and clearly marks that no AI work was performed.
- `orchestrate.py`: executes selected specialist roles sequentially. Prior outputs are passed along as unverified draft context, not as trusted facts.

## Run a role practice task

From the repository root:

    python agents/dispatch.py --agent AGENT-51 --task "Review this 60-second script and produce a motion-graphics art-direction brief"

For the motion systems specialist:

    python agents/dispatch.py --agent AGENT-52 --task "Design a deterministic 8-shot Canvas2D motion system with frame timing and QA limits"

Add `--context-file workspace/source-notes.md` when the role needs supplied evidence. Generated output is saved beneath `workspace/agent-runs/` unless a safe workspace path is supplied.

## Run the full default creative pipeline

    python agents/orchestrate.py --task "Create a source-checkable Urdu technology video plan, storyboard, motion design, and QA checklist" --context-file workspace/source-notes.md

The default sequence includes research/source roles, script/storyboard, both motion-design specialists, captions, render validation, visual QA, safety review, and release preparation. It is sequential, not 51 simultaneous models. With the model disabled, it writes role checklists rather than AI-generated work.

## Mastery evaluation loop

1. Supply a concrete task and relevant source material.
2. Run the appropriate specialist and record its artifact.
3. Score the artifact against each profile's quality gates: 0 = fail, 1 = partial, 2 = pass.
4. Test the output with a repeatable task-specific test or human review. Do not treat the model's self-rating as independent verification.
5. If the review identifies a repeatable failure mode, revise the corresponding playbook, add a regression test, and require CI to pass before using the change.
6. Keep external actions (publishing, payments, deletion, messaging, and approvals) outside automatic roles unless a separately tested and explicit approval mechanism exists.

There is no automatic weight update or unsupervised self-training loop. Changes to the playbooks should be reviewed, testable, and committed to GitHub.
