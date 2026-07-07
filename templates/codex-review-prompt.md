# Codex Review Prompt Template

```text
Review this implementation against the task. Return exactly:

OVERALL: PASS | FAIL
BLOCKING_FINDINGS:
  - <severity>: <file:line> — <issue> — <required fix>
NON_BLOCKING_FINDINGS:
  - <severity>: <file:line> — <issue>
CHECKLIST_RESULTS:
  - Check N: PASS | FAIL — <reason>
FIX_BRIEF:
  - <exact change, or "none">

=== TASK ===
...

=== ACCEPTANCE CRITERIA ===
...

=== TEST EVIDENCE ===
...

=== DIFF ===
...
```

## Verdict Acceptance

`codex exec review` may replace the requested contract with its native summary
format nondeterministically. Both forms are acceptable:

- Contract form: first line `OVERALL: PASS | FAIL` plus `FIX_BRIEF`.
- Native form: any P1/P2 finding maps to `OVERALL: FAIL` (FIX_BRIEF verbatim
  from the findings); an explicit no-blocking statement maps to `OVERALL: PASS`.

Never treat absence of output — or output with neither findings nor an explicit
no-blocking statement — as a pass.

