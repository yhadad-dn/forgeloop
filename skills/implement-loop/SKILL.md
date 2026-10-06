---
name: implement-loop
description: >
  Automated TDD implementation loop with reliable-source checks, bounded repair
  planning, a behavior-preserving clean-code pass, reviewer gates, coverage evidence,
  and a real CPU/GPU run-proof gate.
  Invoke with: /implement-loop <task-file-or-description>.
---

# Implement Loop

## Goal

Implement one task through a disciplined loop:

```text
load task -> source check -> TDD implementation -> coverage gate
          -> clean-code pass -> reviewer gate -> run-proof gate (CPU/GPU) -> approval
```

The reviewer gate and the run-proof gate must both pass before convergence. After the first iteration, every failed
gate becomes a bounded repair plan before another implementation pass. Stop after
`MAX_ITERATIONS`.

## Principle: Correctness Only Goes Up

implement-loop exists to strengthen correctness, never to harm it. Every stage adds
evidence or removes defects; none may weaken what is already true:

- Never weaken a test, assertion, threshold, coverage bar, `RUN_PROOF` criterion, or
  source correspondence to get a gate to pass.
- A clean-code (A.5) or repair change that cannot be shown to be behavior-preserving
  and in scope is reverted, not argued for.
- A gate that cannot run (tool missing, cluster unreachable) is reported as not run,
  never counted as passed.
- Never switch ForgeLoop versions in the middle of a task: finish a task under the
  version it started with; new rules apply from the next task.
- When following a rule would harm correctness, stop and ask the user.

Reference files (relative to this skill's directory):

- `source-check.md`
- `stage-r.md`
- `coverage-gate.md`
- `clean-code.md`
- `review-gates.md`
- `run-proof.md`
- `reports.md`
- `../cluster-loop/srun-inside.md` (GPU runs)

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
- `RUN_PROOF` (see `run-proof.md`)

## Paths, Agents, and Repo Configuration

- File references in this skill are relative to this skill's directory; `../<skill>/`
  points at a sibling ForgeLoop skill.
- ForgeLoop agents (`developer`, `refactorer`, `source-check`,
  `reviewer-*`) are named `forgeloop:<agent>` when ForgeLoop is installed as a plugin,
  and `<agent>` when installed into a repo's `.claude/`.
- Paths like `.claude/plans/` refer to the target repo, never the plugin directory.
- Before Stage 0, read `.claude/forgeloop.md` in the target repo if it exists. Its
  values (test commands, coverage threshold, test-file patterns, forbidden paths,
  Codex policy, declared sources) override the defaults in this skill's files.

## Constants

- `MAX_ITERATIONS = 5`
- Divergence reports should be written near the task file or under
  `.claude/plans/divergence-reports/`.

## Stage 0: Load Task

1. Resolve the task.
2. Extract context, work items, tests, verification, and checklist.
3. Warn on missing dependencies mentioned by the task; block only when the task says the
   dependency is mandatory.
4. Validate `RUN_PROOF` per `run-proof.md`. If it is missing or
   incomplete, stop and ask the user for it — never invent a command or criteria.
   For `device: gpu`, get an active SLURM job ID from the user or offer
   `/cluster-loop` to allocate one; record it as `RUN_JOBID`.
5. Assert a clean working tree. `HEAD` is the baseline for iteration 1's scope, Stage R's
   N=2 fallback and Stage B's file list, which is only valid if nothing was dirty at
   invocation. Run from inside the target repo:

```bash
# Returns 0 if the tree is clean outside ForgeLoop artifact paths; otherwise prints
# the offending `git status --porcelain` lines to stdout and returns 1.
assert_clean_tree() {
  local top out
  top="$(git rev-parse --show-toplevel)" || return 2
  out="$(git -C "$top" status --porcelain --untracked-files=all -- . \
    ':(exclude,glob)**/.claude/clean-code/**' ':(exclude,glob)**/.claude/run-proofs/**' \
    ':(exclude,glob)**/.claude/plans/**' ':(exclude,glob)**/.claude/debug-reports/**')" || return 2
  [ -z "$out" ] && return 0
  printf '%s\n' "$out"
  return 1
}
```

   If it returns 1, hard-block: stop, show the listed paths, and ask the user to commit
   or stash them. This step is read-only: never auto-commit, never auto-stash, never
   alter the user's tree. The pathspec excludes ForgeLoop's own artifact directories (glob
   form, so nested `**/.claude/...` dirs under a subdirectory cwd are covered too), so a
   prior run's leftovers never block, even in repos that do not gitignore them.
6. Run Stage 0.5 before implementation.

Initialize:

```text
iteration = 0
converged = false
fix_brief = ""
fix_source = ""
repair_plan = ""
source_check = ""
iteration_log = []
run_proof = {}
RUN_JOBID = ""
```

## Stage 0.5: Reliable-Source Check

Read `source-check.md`.

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
    Stage A.5: clean-code pass (never fails the loop)
    Stage B: reviewer gate
        if blocking findings: continue
    Stage C: run-proof gate
        if FAIL: continue
        if ERROR: stop and ask the user
    Stage D: converged
```

## Stage R: Repair Plan

Read `stage-r.md`.

Convert the latest failed review's `FIX_BRIEF` into an in-scope repair plan. Preserve all
blocking findings. If the repair requires scope expansion or conflicts with the task,
report `PLAN_AMENDMENT_REQUIRED` and stop.

## Stage A: Developer TDD Pass

Dispatch `explorer` first when `WHAT_TO_DO` does not already name an exact file:line or
a single named file to change; skip it when the task already pinpoints the location.
On a repair iteration, a non-empty "Previous-iteration file list" in the repair plan also counts as already pinpointing the location, so explorer dispatch is skipped there too.
Treat its citations as a starting point, not exhaustive — the developer should
Read/Grep further itself when they don't resolve the question.

First iteration prompt:

```text
Acceptance criteria:
[WHAT_TO_DO verbatim]

Reliable-source check:
[source_check summary]

TDD protocol:
1. RED: write tests from TESTS, run targeted pytest, and show expected failures.
2. GREEN: implement the minimum code and run the full suite.
3. COVERAGE: report TEST_COVERAGE using coverage-gate.md.

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

## Stage A.5: Clean-Code Pass

Read `clean-code.md`.

After Stage A reports `DONE`, snapshot the working tree and run the `refactorer`
agent (fresh context) over the changed production files only — on later iterations,
only the files the repair touched. It simplifies without changing behavior: test files
must stay byte-identical, the full suite must pass with Stage A's counts, and coverage
must not drop. Any change that breaks a check is restored from the snapshot. Code that
mirrors an authoritative source, hot paths, and `simplify-ignore` blocks are left alone.

Stage A.5 never fails the loop. Record `CLEAN_CODE_RESULT` and hand the refactor patch
to Stage B.

## Stage B: Reviewer Gate

Read `review-gates.md`.

Use the authoritative changed file list from git, include untracked files, reject forbidden
result/artifact paths configured by the repo, run the coverage threshold gate, then review
the captured diff with focused reviewers:

- correctness;
- security;
- hygiene (conventions, scope, dead code, and performance — one dispatch).

Blocking findings produce a `FIX_BRIEF` and another loop iteration.

## Stage C: Run-Proof Gate

Read `run-proof.md`.

Run the task's `RUN_PROOF` command for real: locally for `device: cpu`, inside the
SLURM allocation `RUN_JOBID` via `srun --jobid` for `device: gpu`. Before a GPU run,
confirm the allocation is `R`, a GPU is visible, and the node sees the current
working tree. Capture the full log and judge every `pass_criteria` entry with quoted
log evidence.

- `FAIL` (code ran, criteria not met) produces a `FIX_BRIEF` and another iteration.
- `ERROR` (allocation, environment, or tree-sync problem) is never a pass and never a
  reason to change code: stop, ask the user, then rerun the same proof.
- Changing the proof command or loosening its criteria is `PLAN_AMENDMENT_REQUIRED`.

## Stage D: Decision

When Stage B and Stage C pass, set `converged = true` and use
`reports.md` for the user approval gate.

Every `DEFERRED` finding must be fixed or emitted as a follow-up task file
before convergence (see `review-gates.md`); the convergence
report lists each one under "Carried-forward findings".

Before every commit: plan, code, and docs must stay in sync. If this change
invalidates a plan file, an ADR, or a README section that describes the behavior just
changed, update it as part of this task — a commit that leaves them out of sync is
incomplete, not merely untidy, and belongs on the checklist like any other gate.

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
  coverage_decision: measured_pass|measured_below_threshold_repair_run|unavailable_review_required|not_applicable_no_prod_changes
  suite_result: pass|fail
  clean_code_status: applied|no_changes|reverted_all|skipped_no_prod_changes
  clean_code_applied_count: N
  clean_code_reverted_count: N
  clean_code_refactor_patch: <path or n/a>
  stage_b_overall: PASS|FAIL
  stage_b_blocking_count: N
  stage_b_nonblocking_count: N
  run_proof_overall: PASS|FAIL|ERROR|not_applicable
  run_proof_device: cpu|gpu|not_applicable
  run_proof_target: local|job <RUN_JOBID> on <nodelist>|n/a
  run_proof_exit_code: <n or n/a>
  run_proof_log_path: <path or n/a>
  run_proof_error_reason: <if ERROR>
  fix_source: stage_b|stage_c|none
  converged: true|false
```
