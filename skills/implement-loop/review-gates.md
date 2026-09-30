# Review Gates

## Stage B: Internal Reviewer Gate

Build the authoritative changed file list from git:

```bash
git diff --name-only > /tmp/files_tracked.txt
git diff --cached --name-only >> /tmp/files_tracked.txt
sort -u /tmp/files_tracked.txt -o /tmp/files_tracked.txt
git ls-files --others --exclude-standard > /tmp/files_untracked.txt
cat /tmp/files_tracked.txt /tmp/files_untracked.txt | sort -u > /tmp/files_authoritative.txt
```

Reject any path your repo marks as a generated result or forbidden artifact.

Capture:

- task context and checklist;
- source-check summary;
- developer summary;
- RED/GREEN evidence;
- TEST_COVERAGE;
- `CLEAN_CODE_RESULT` and the Stage A.5 refactor patch (so reviewers can tell
  feature changes from refactor changes);
- tracked diff;
- untracked file contents.

Review with these focuses:

| Reviewer | Focus |
|---|---|
| correctness | logic, edge cases, regressions, source/spec alignment |
| security | unsafe subprocess, filesystem, network, secrets |
| performance | hot-path allocations and avoidable recomputation |
| standards | repo conventions, constants, generated artifact guards, Stage A.5 stayed in scope and left tests untouched |
| slop | dead code, shallow tests, empty comments, premature abstractions |

Reviewer fan-out is proportional to the diff:

- docs-only diffs under ~50 changed lines (no code, config, CI, or permission
  changes — config edits can carry auth/deploy/secret risk and keep the full
  gate): one combined correctness+standards reviewer;
- small scoped code diffs (under ~50 lines) whose design already passed a
  review gate (e.g. an approved debug-loop handoff): correctness plus slop at
  minimum;
- new code surfaces or larger diffs: all five reviewers.

Classify:

- `BLOCKING`: correctness issue, security issue, violated acceptance criterion, wrong
  source claim, or missing regression coverage for a correctness-sensitive change.
- `DEFERRED`: a non-blocking finding that is correctness-relevant on code
  introduced in this loop — a plausible failure mode, misclassification, or
  hang that simply falls outside the current acceptance criteria.
- `NON_BLOCKING`: style, minor maintainability, minor performance.

Blocking findings become `FIX_BRIEF`. Do not proceed to Stage C until Stage B passes.

`DEFERRED` handling: every `DEFERRED` finding must be resolved before
convergence, in exactly one of two ways:

- **Fix it in this loop**: the fix is a code change and re-enters the loop like
  any other — another Stage A pass and a rerun of the review gates. Never
  patch code at Stage D; a fix applied after the gates passed is unreviewed.
- **Emit a follow-up task file** under `.claude/plans/followups/<task>-<n>.md`
  using the canonical `CONTEXT`/`WHAT_TO_DO`/`TESTS`/`VERIFY`/`RUN_PROOF`/`CHECKLIST`
  schema, so it is one `/implement-loop` invocation away from landing.

Stage D only verifies that each `DEFERRED` finding has an already-reviewed fix
or a follow-up file. Findings may not be dropped in report prose — the
convergence report lists each one under "Carried-forward findings".

## Stage C: Run-Proof Gate

After Stage B passes, run the task's `RUN_PROOF` on its CPU or GPU target. The full
protocol — target setup, GPU pre-run checks, log capture, and PASS/FAIL/ERROR
handling — is in `run-proof.md`.
