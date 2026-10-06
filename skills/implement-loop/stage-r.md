# Stage R: Repair Plan

Stage R runs only for iterations after the first.

Before building the plan, compute the previous iteration's touched-file list using the
same persisted-tree mechanism as `clean-code.md` Section "Snapshot and Scope" (REQ-3):

- read `TREE_A5_prev2` from `.claude/clean-code/<task>-iter$((N-2))-tree.txt`, or use
  `HEAD` when `N-1 == 1` (iteration 1 always starts from `HEAD`, a valid baseline because
  Stage 0 enforced a clean tree);
- read `TREE_A5_prev1` from `.claude/clean-code/<task>-iter$((N-1))-tree.txt`;
- the previous-iteration file list is `git diff --name-only ${TREE_A5_prev2}
  ${TREE_A5_prev1}` — exactly what the previous repair pass touched. No "plus
  untracked files" step here: `snapshot_tree()` already folds untracked content into
  both trees via `git add -A`, so re-adding untracked files on top would pull back in
  unchanged leftovers regardless of whether they changed between the two snapshots;
- then keep only production files, the same filter `clean-code.md` Section 1 applies:
  exclude tests and fixtures (repo test patterns, e.g. `tests/`, `test_*.py`,
  `*_test.go`, `*.test.ts`, `conftest.py`), and exclude generated/result paths
  forbidden by repo policy (e.g. everything under `.claude/` — ForgeLoop's own
  run-proofs, clean-code patches, plans, and follow-up artifacts);
- if `TREE_A5_prev1` is missing, or (for N > 2) `TREE_A5_prev2` is missing, record
  `clean_code_scope_fallback: true` and leave the list empty rather than guessing —
  never guess, never crash.

This list is a soft starting point, never a hard restriction: it informs "Allowed
files" below but cannot silently block a file the fix brief genuinely needs.

Convert the failed gate's `FIX_BRIEF` into this plan before any developer writes code:

```text
Repair Plan — iteration {N}

Source: {stage_b|stage_c}

Blocking findings to fix:
{copy every blocking finding verbatim}

Root cause:
{why the implementation missed each finding; cite files/functions/tests}

Exact fix scope:
Previous-iteration file list (read-only, informational):
- {the computed list above, or "none (fallback: tree file missing)"}
Allowed files:
- {paths needed by blocking findings; cross-reference the previous-iteration file list}
Additional files beyond the previous-iteration list:
- {file}: {one-line reason it is genuinely needed by the fix brief} — or "none"
Forbidden files:
- Any unrelated file
- Generated result artifacts
- Later-batch files unless explicitly allowed
Edits:
- {file}: {exact intended edit}

Scope check:
IN_SCOPE | PLAN_AMENDMENT_REQUIRED

Verification:
{exact commands}
```

Rules:

- Do not drop or soften any blocking finding.
- Do not include non-blocking cleanup.
- Every entry in "Additional files beyond the previous-iteration list" needs a
  one-line reason; an empty list is written as "none".
- Stop with `PLAN_AMENDMENT_REQUIRED` if scope expands or requirements conflict.

