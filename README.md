# ForgeLoop

**Gated workflow skills for agentic planning, implementation, review, and repair.**

ForgeLoop is a portable Claude/Codex workflow pack for teams that want agentic coding
to behave like a disciplined engineering process: source checks first, test-driven
implementation, reviewer gates, external review, bounded repair loops, and explicit
approval before commit.

The first shipped workflow is **`implement-loop`**. More workflow skills, such as
`plan-loop`, can live beside it under the same structure.

---

## Why ForgeLoop

Agentic coding fails when it skips the boring parts: verifying the source of truth,
writing real regression tests, checking coverage, reviewing the actual diff, and stopping
when requirements conflict.

ForgeLoop turns those steps into a repeatable loop:

```text
source check -> TDD implementation -> coverage gate -> reviewer gate
             -> Codex review -> repair plan -> approval gate
```

It is designed for high-stakes repos where "looks good" is not enough.

## What You Get

- **`implement-loop` skill**: a bounded TDD implementation loop with up to five repair
  iterations.
- **Reliable-source check**: blocks implementation when the plan conflicts with the
  paper, spec, official docs, or repo contracts.
- **Developer handoff contract**: requires RED, GREEN, full-suite, and coverage evidence.
- **Five reviewer roles**: correctness, security, performance, standards, and slop.
- **Codex outer gate**: required by default, configurable only through explicit repo
  policy.
- **Repair discipline**: failed review findings become scoped repair plans before code
  changes continue.
- **Convergence reports**: clear approval gate before staging or committing.

## Repo Layout

```text
forgeloop/
  skill/.claude/                  # installable Claude payload
    skills/implement-loop.md
    skills/implement-loop/
    agents/
    AGENTS.template.md
    CLAUDE.template.md
  templates/                      # copyable task/report templates
  docs/                           # adaptation and setup notes
  examples/                       # tiny examples for learning the loop
  scripts/install.sh              # copies the payload into another repo
```

## Quick Start

From a target repo:

```bash
git clone https://github.com/<your-user>/forgeloop.git /tmp/forgeloop
/tmp/forgeloop/scripts/install.sh .
```

The installer refuses to overwrite existing `.claude` files by default. Run with
`--dry-run` first if you want to inspect what would be copied.

Then ask Claude:

```text
Use the implement-loop skill.

Implement this task:
<task file or acceptance criteria>
```

For best results, give the loop a task file with context, acceptance criteria, test
expectations, and verification commands. Start from `templates/task-plan.md`.

## The Implement Loop

`implement-loop` follows six stages:

1. **Stage 0: Load Task**  
   Resolve the task file or inline criteria and extract context, tests, verification,
   and checklist.

2. **Stage 0.5: Reliable-Source Check**  
   A read-only source-check pass compares the plan to authoritative sources and repo
   contracts. Conflicts stop the loop.

3. **Stage A: Developer TDD Pass**  
   Write failing tests, implement the smallest passing change, run the full suite, and
   report coverage.

4. **Stage B: Reviewer Gate**  
   Review the actual changed files with focused reviewers. Blocking findings produce a
   repair brief.

5. **Stage C: Codex Gate**  
   Run an outer review using Codex CLI. A failed verdict enters the repair loop.
   If your repo cannot use Codex, explicitly edit the policy before treating the loop as
   converged.

6. **Stage D: Approval Gate**  
   When all gates pass, ForgeLoop reports exactly what changed and waits for human
   approval before commit.

## Philosophy

ForgeLoop is intentionally strict:

- Plans are context, not truth.
- Generated docs and prior AI reviews are not algorithm authority.
- Test evidence is part of the deliverable.
- Repair iterations must stay inside scope.
- Results and generated artifacts are never edited by hand unless your repo policy says
  otherwise.
- The human chooses when to commit.

## Requirements

- Claude Code or a compatible Claude workflow that can read `.claude/skills/`.
- A repo with tests runnable from the command line.
- Codex CLI for the default outer review gate.

If Codex CLI is unavailable, keep the loop's Stage C policy explicit for your team. Do not
silently treat an unavailable outer review as a pass.

## What Gets Installed

```text
.claude/
  skills/implement-loop.md
  skills/implement-loop/*.md
  agents/developer.md
  agents/source-check.md
  agents/tester.md
  agents/reviewer-*.md
  AGENTS.template.md
  CLAUDE.template.md
```

## Before First Use

Adapt these repo-specific settings:

- authoritative specs, papers, and official docs;
- full-suite and targeted test commands;
- forbidden generated artifact paths;
- Codex model and command;
- coverage threshold;
- reviewer notes for your domain.

## Limitations

ForgeLoop is not a CI system and does not replace human approval. It is a workflow
contract for an agent. It needs repo-specific tuning before it should be trusted on
large or high-risk changes.

## Add More Loops

ForgeLoop is meant to grow:

```text
skill/.claude/skills/
  implement-loop.md
  plan-loop.md
  review-loop.md
  debug-loop.md
```

Keep each loop small, explicit, and gate-driven. Put reusable stage details in a sibling
folder, just like `implement-loop/`.

## Status

Early release extracted from internal engineering workflows. The packaged skill is
intentionally plain Markdown so it is easy to audit, fork, and adapt.
