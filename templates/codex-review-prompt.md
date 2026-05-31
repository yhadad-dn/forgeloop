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

