# Stage 5: Debug Handoff Format

The debug handoff is an `implement-loop` task file using the canonical task schema.
All five sections — `CONTEXT`, `WHAT_TO_DO`, `TESTS`, `VERIFY`, and `CHECKLIST` —
are required. Omitting any section blocks Stage 6 self-check.

---

````markdown
## CONTEXT

Bug: {one-sentence symptom description}

Environment: {version, OS, config, dependency versions}

RED evidence: {type and reference — test name, command, or log location}

Root cause: {selected root cause from Stage 4}

Trace: {evidence type and location — file:line, config key, log reference,
dependency version, or data boundary}

Confidence: {high | medium | low}

Residual uncertainty: {any remaining unknown, or "none"}

## WHAT_TO_DO

Fix the traced root cause. Do not change behavior beyond what is needed to correct
the defect.

- {fix description, scoped strictly to the traced root cause}
- {any additional constraint from symptom validation}

## TESTS

Write or update tests that:

- Prove the bug is fixed (RED before fix, GREEN after fix).
- Guard against recurrence (regression tests committed alongside the fix).

Tests to write:
- {test name}: {what it verifies} — cite RED evidence and root-cause trace.

## VERIFY

```bash
{targeted test command that exercises the fix}
{full suite command}
{repro command to confirm the original symptom is gone}
```

## CHECKLIST

- [ ] Source check completed using evidence sources in this report
- [ ] RED evidence was present before fix
- [ ] GREEN evidence captured after fix
- [ ] Coverage evidence reported
- [ ] Regression tests committed alongside fix
- [ ] Reviewer gate passed
- [ ] Codex gate passed or repo policy fallback applied
- [ ] User approved commit
````

---

## Section Guidance

- **CONTEXT** must include the RED evidence reference and root-cause trace. An
  implementor reading only `CONTEXT` should know exactly what broke and where.
- **WHAT_TO_DO** must be scoped to the traced root cause only. Speculative or
  unrelated changes are a blocking finding at Stage 6.
- **TESTS** must name the regression test that would have caught the bug and prove
  the fix. "Add tests" is not sufficient — test names and what they verify are required.
- **VERIFY** must include the full-suite command in addition to targeted commands.
  A targeted test passing alone is not convergence evidence.
- **CHECKLIST** must include the regression test item. An implement-loop run that
  omits regression tests is not complete.
