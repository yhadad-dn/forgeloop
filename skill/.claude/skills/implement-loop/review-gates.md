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
- tracked diff;
- untracked file contents.

Review with these focuses:

| Reviewer | Focus |
|---|---|
| correctness | logic, edge cases, regressions, source/spec alignment |
| security | unsafe subprocess, filesystem, network, secrets |
| performance | hot-path allocations and avoidable recomputation |
| standards | repo conventions, constants, generated artifact guards |
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
  using the canonical `CONTEXT`/`WHAT_TO_DO`/`TESTS`/`VERIFY`/`CHECKLIST`
  schema, so it is one `/implement-loop` invocation away from landing.

Stage D only verifies that each `DEFERRED` finding has an already-reviewed fix
or a follow-up file. Findings may not be dropped in report prose — the
convergence report lists each one under "Carried-forward findings".

## Stage C: Codex CLI Gate

Run an independent Codex review after Stage B passes. This gate is required by default.
If your repo cannot use Codex, document an explicit fallback policy before running
ForgeLoop; do not silently treat Codex as optional.

Prompt contract:

```text
OVERALL: PASS | FAIL
BLOCKING_FINDINGS:
  - <severity>: <file:line> — <issue> — <required fix>
NON_BLOCKING_FINDINGS:
  - <severity>: <file:line> — <issue>
CHECKLIST_RESULTS:
  - Check N: PASS | FAIL — <reason>
FIX_BRIEF:
  - <exact change, or "none">
```

Suggested command:

```bash
codex exec review \
  -m "${CODEX_MODEL}" \
  --output-last-message ".claude/codex_verdicts/verdict_iter${ITER}.md" \
  - < /tmp/codex_prompt_iter${ITER}.txt
```

`CODEX_MODEL` is set in Stage 0.1 of the loop by the Codex model check sub-agent.
See `codex-model-check.md` for the verification protocol and fallback behavior.

Verdict handling — accept a verdict in either of two forms:

1. **Contract form**: first line is `OVERALL: PASS` or `OVERALL: FAIL`, with a
   `FIX_BRIEF` section.
2. **Codex-native review form** (`codex exec review` post-processes output into
   its own summary nondeterministically; do not fight it): map any P1/P2
   finding to `OVERALL: FAIL` with `FIX_BRIEF` taken verbatim from the
   findings; map an explicit no-blocking statement (e.g. "No blocking issues
   were found") to `OVERALL: PASS`.

Safety rules:

- Absence of output — or output with neither findings nor an explicit
  no-blocking statement — is never a pass. Retry once, then treat as
  `codex_overall = ERROR`.
- Treat unavailable CLI, authentication failure, unsupported model, or denied approval as
  `codex_overall = ERROR`.
- If retry also errors, write a divergence report.
