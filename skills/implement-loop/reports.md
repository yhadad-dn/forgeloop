# Reports

## Convergence Report

Use when all gates pass:

```text
=== TASK [{task_name}] — CONVERGED in {iteration} iteration(s) ===

Stage B: PASS
Stage C: PASS

Non-blocking findings:
  Stage B: {items or none}

Carried-forward findings:
  {each DEFERRED finding with its follow-up task file under
   .claude/plans/followups/, or none — DEFERRED findings may not be dropped}

Source truth:
  captured_at_utc: {timestamp}
  authoritative: {sources}
  context_only: {sources}

Coverage:
  decision: {coverage_decision}
  changed production modules: {modules or none}
  coverage repair: {summary}

Clean-code pass:
  status: {applied | no_changes | reverted_all | skipped_no_prod_changes}
  applied: {count, one line per change}
  reverted: {changes restored from the snapshot, or none}
  flagged, not applied: {judgment calls left for the user, or none}
  feature patch: {.claude/clean-code/<task>-iter<N>-feature.patch}
  refactor patch: {.claude/clean-code/<task>-iter<N>-refactor.patch}
  (commit feature and refactor separately if you want split history)

Run proof:
  device: {cpu | gpu | not_applicable}
  target: {local | job <RUN_JOBID> on <nodelist>}
  command: {exact command}
  exit_code: {n}
  duration: {HH:MM:SS}
  log: {.claude/run-proofs/<task>-iter<N>.log}
  criteria:
    {each pass criterion with its quoted log evidence}

VERIFY:
{verification commands}

Wait for user approval before staging or committing.
```

## Divergence Report

Write when the loop cannot converge:

```markdown
# Divergence Report: {task_name}

**Status:** Not converged
**Task:** {task reference}
**Date:** {date}

## Summary

{one paragraph}

## Iteration Log

| # | Stage A change | Stage B | Stage C (run proof) | Converged? |
|---|---|---|---|---|
{rows}

## Persistent Blockers

{blockers}

## Scope / Plan Conflicts

{conflicts}

## Recommended Next Action

1. Adjust task scope
2. Run prerequisite task
3. Resolve conflicting requirements manually
4. Retry with fresh context
```

