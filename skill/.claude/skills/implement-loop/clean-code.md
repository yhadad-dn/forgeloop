# Stage A.5: Clean-Code Pass

Runs after Stage A reports `DONE` and before the Stage B reviewer gate, on every
iteration. A fresh-context `refactorer` agent simplifies the code the developer just
wrote, without changing behavior. Reviewers and the run-proof then judge the cleaned
code.

Adapted from `code-simplification` (addyosmani/agent-skills, MIT) and `code-simplifier`
(anthropics/claude-plugins-official), with ForgeLoop gates added.

Stage A.5 cannot fail the loop. At worst it leaves the Stage A code unchanged.

## 1. Scope

Build the changed file list exactly as Stage B does (`implement-loop/review-gates.md`),
then keep only production files:

- exclude tests and fixtures (repo test patterns, e.g. `tests/`, `test_*.py`,
  `*_test.go`, `*.test.ts`, `conftest.py`);
- exclude generated/result paths forbidden by repo policy;
- on iterations after the first, keep only files the repair pass touched.

Empty scope → record `clean_code: skipped_no_prod_changes` and go to Stage B.

## 2. Snapshot Stage A

Snapshot the working tree, including untracked files, as a git tree object. A
throwaway index is used, so the real index is untouched and nothing is staged:

```bash
snapshot_tree() {
  local idx; idx="$(mktemp)"; rm -f "$idx"
  GIT_INDEX_FILE="$idx" git read-tree HEAD &&
  GIT_INDEX_FILE="$idx" git add -A &&
  GIT_INDEX_FILE="$idx" git write-tree
  rm -f "$idx"
}
TREE_A="$(snapshot_tree)"
```

Always diff snapshot against snapshot. `git diff ${TREE_A}` against the working tree
misreports untracked files as deleted.

Record hashes of every test file in the changed list, plus every test file in the repo
that imports an in-scope module:

```bash
sha256sum <test files> > /tmp/clean_code_tests_iter${ITER}.sha
```

## 3. Refactorer pass

Invoke the `refactorer` agent with:

- the in-scope production file list;
- task `CONTEXT` and the Stage 0.5 source-check summary (which code mirrors a source);
- the targeted test command per module and the full-suite command;
- this file.

Pattern table the refactorer scans (signals, not vague smells):

| Area | Pattern | Simplification |
|---|---|---|
| Structure | nesting 3+ levels | guard clauses, extracted helpers |
| Structure | function over ~50 lines with several responsibilities | split by responsibility |
| Structure | nested ternaries / dense one-liners | if/else, lookup table |
| Structure | boolean flag parameters | separate functions or named options |
| Structure | the same condition checked in several places | named predicate |
| Naming | generic (`data`, `tmp`, `res`) or abbreviated names | descriptive names |
| Naming | name that hides a side effect | rename to the real behavior |
| Comments | comment restating the code | delete (keep "why" comments) |
| Redundancy | duplicated 5+ line blocks | shared function |
| Redundancy | dead code, unused imports, commented-out blocks | remove after confirming unused |
| Redundancy | wrapper or abstraction with one trivial use | inline |

Do not touch:

- code that mirrors an authoritative source (equation order, notation, step structure);
- hot paths, unless the change is clearly no slower;
- blocks between `simplify-ignore-start` and `simplify-ignore-end` markers;
- error handling, public signatures, or anything outside the scope list.

## 4. Behavior gate

After the refactorer returns:

1. Test files unchanged: `sha256sum -c /tmp/clean_code_tests_iter${ITER}.sha` passes.
2. Scope respected: `TREE_A5="$(snapshot_tree)"`, then
   `git diff --name-only ${TREE_A} ${TREE_A5}` lists only in-scope files.
3. Full suite passes with the same pass/skip counts as Stage A's GREEN run.
4. Coverage for in-scope modules is not lower than Stage A's `TEST_COVERAGE`.

If any check fails and the offending change can be identified, restore only that
file from the snapshot (worktree only, nothing staged), take a fresh `TREE_A5`, and
rerun the checks:

```bash
git restore --source="${TREE_A}" --worktree -- <file>
```

If it cannot be isolated, restore every in-scope file from `TREE_A` and record
`clean_code: reverted_all`. Never repair a behavior change by editing tests.

## 5. Record

Save both diffs so the user can commit feature and refactor separately:

```bash
mkdir -p .claude/clean-code
TREE_A5="$(snapshot_tree)"
git diff --binary HEAD "${TREE_A}"      > .claude/clean-code/<task>-iter${ITER}-feature.patch
git diff --binary "${TREE_A}" "${TREE_A5}" > .claude/clean-code/<task>-iter${ITER}-refactor.patch
```

Never stage or commit these files.

Required output:

```text
CLEAN_CODE_RESULT:
  status: applied | no_changes | reverted_all | skipped_no_prod_changes
  files_in_scope: [...]
  applied_count: N
  reverted: [<file — change — failing check>]
  flagged_not_applied: [<file — suggestion — reason>]
  tests_unchanged: PASS | FAIL
  full_suite: pass | fail  (counts: <passed>/<skipped>, Stage A: <passed>/<skipped>)
  coverage_delta: <module: before -> after>
  refactor_patch: .claude/clean-code/<task>-iter<N>-refactor.patch
```

Pass `CLEAN_CODE_RESULT` and the refactor patch to Stage B, so reviewers can tell
feature changes from refactor changes.
