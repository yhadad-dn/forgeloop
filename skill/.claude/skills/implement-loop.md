---
name: implement-loop
description: >
  Automated TDD implementation loop with reliable-source checks, bounded repair
  planning, reviewer gates, Codex CLI review, and coverage evidence.
  Invoke with: /implement-loop <task-file-or-description>.
---

# Implement Loop

## Goal

Implement one task through a disciplined loop:

```text
load task -> source check -> TDD implementation -> coverage gate
          -> reviewer gate -> Codex gate -> approval
```

Both review gates must pass before convergence. After the first iteration, every failed
gate becomes a bounded repair plan before another implementation pass. Stop after
`MAX_ITERATIONS`.

Reference files:

- `codex-model-check.md`
- `implement-loop/source-check.md`
- `implement-loop/stage-r.md`
- `implement-loop/coverage-gate.md`
- `implement-loop/review-gates.md`
- `implement-loop/reports.md`

## Inputs

The task can be:

- a file path;
- a short identifier that resolves to a task file;
- inline acceptance criteria.

Extract or derive:

- `CONTEXT`
- `WHAT_TO_DO`
- `TESTS`
- `VERIFY`
- `CHECKLIST`

## Constants

- `MAX_ITERATIONS = 5`
- Divergence reports should be written near the task file or under
  `.claude/plans/divergence-reports/`.

## Stage 0: Load Task

1. Resolve the task.
2. Extract context, work items, tests, verification, and checklist.
3. Warn on missing dependencies mentioned by the task; block only when the task says the
   dependency is mandatory.
4. Run Stage 0.5 before implementation.

Initialize:

```text
iteration = 0
converged = false
fix_brief = ""
fix_source = ""
repair_plan = ""
source_check = ""
iteration_log = []
CODEX_MODEL = ""
CODEX_BASE_COMMAND = ""
```

## Stage 0.1: Codex Model Check

Read `codex-model-check.md`.

Follow the protocol in `codex-model-check.md`: probe `gpt-5.5` locally first; only
run a web-search sub-agent if the probe fails. Record `CODEX_MODEL` and
`CODEX_BASE_COMMAND` in loop state. Use these values at Stage C.

## Stage 0.5: Reliable-Source Check

Read `implement-loop/source-check.md`.

Run a read-only source-check pass comparing the task against authoritative sources:

- published paper/spec/official docs explicitly referenced by the task;
- the repo's own source files for implementation contracts;
- generated docs and plans only as context.

If the result is `CONFLICT`, `NO_SOURCE_BLOCKED`, malformed, or unavailable, stop and ask
the user for a decision. Do not choose a side autonomously.

## Main Loop

```text
while iteration < MAX_ITERATIONS and not converged:
    iteration += 1
    if iteration > 1:
        Stage R: build repair plan from latest fix brief
    Stage A: developer implementation
    Stage B: reviewer gate
        if blocking findings: continue
    Stage C: Codex gate
        if fail: continue
    Stage D: converged
```

## Stage R: Repair Plan

Read `implement-loop/stage-r.md`.

Convert the latest failed review's `FIX_BRIEF` into an in-scope repair plan. Preserve all
blocking findings. If the repair requires scope expansion or conflicts with the task,
report `PLAN_AMENDMENT_REQUIRED` and stop.

## Stage A: Developer TDD Pass

First iteration prompt:

```text
Acceptance criteria:
[WHAT_TO_DO verbatim]

Reliable-source check:
[source_check summary]

TDD protocol:
1. RED: write tests from TESTS, run targeted pytest, and show expected failures.
2. GREEN: implement the minimum code and run the full suite.
3. COVERAGE: report TEST_COVERAGE using implement-loop/coverage-gate.md.

Tests to write:
[TESTS verbatim]

Do not mark done until RED_OUTPUT, GREEN_OUTPUT, and TEST_COVERAGE are present.
```

Subsequent iteration prompt:

```text
Make only the changes listed in the repair plan.

Repair plan:
[repair_plan verbatim]

Original fix brief:
[fix_brief verbatim]

Original acceptance criteria:
[WHAT_TO_DO verbatim]

After changes, run the full suite and report TEST_COVERAGE.
```

Require:

- status `DONE`;
- RED evidence on iteration 1;
- GREEN evidence showing the relevant suite passed;
- TEST_COVERAGE with coverage decision and residual risks.

## Stage B: Reviewer Gate

Read `implement-loop/review-gates.md`.

Use the authoritative changed file list from git, include untracked files, reject forbidden
result/artifact paths configured by the repo, run the coverage threshold gate, then review
the captured diff with focused reviewers:

- correctness;
- security;
- performance;
- standards;
- dead-code/slop.

Blocking findings produce a `FIX_BRIEF` and another loop iteration.

## Stage C: Codex CLI Gate

Read `implement-loop/review-gates.md`.

Invoke Codex through the shell CLI by default and require an exact `OVERALL: PASS` or
`OVERALL: FAIL` verdict. A failed verdict produces a `FIX_BRIEF`.

Codex availability or authentication errors are not passes. If your repo cannot use Codex,
write an explicit local fallback policy before running the loop.

## Stage D: Decision

When Stage B and Stage C pass, set `converged = true` and use
`implement-loop/reports.md` for the user approval gate.

Do not commit automatically.

## Iteration Log

Record one entry per iteration:

```yaml
- iteration: N
  developer_summary: <one sentence>
  files_changed: [list]
  red_evidence: present|n/a
  green_evidence: present|missing
  test_coverage: present|missing
  coverage_decision: measured_pass|measured_below_threshold_tester_run|unavailable_review_required|not_applicable_no_prod_changes
  suite_result: pass|fail
  stage_b_overall: PASS|FAIL
  stage_b_blocking_count: N
  stage_b_nonblocking_count: N
  codex_overall: PASS|FAIL|ERROR
  codex_error_reason: <if ERROR>
  codex_command: <exact command or n/a>
  codex_verdict_path: <path or n/a>
  fix_source: stage_b|stage_c|none
  converged: true|false
```
