# Stage 1: Symptom Validation

Run before any evidence mapping or reproduction work.

## Questions to Ask

Collect the following in one batch — do not ask piecemeal:

1. **Observed behavior**: What exactly happens? Include output, error messages, stack
   traces if available.
2. **Expected behavior**: What should happen instead?
3. **Environment**: Version, OS, runtime, configuration, dependency versions.
4. **Reproduction inputs**: Exact steps, commands, or inputs needed to trigger the
   symptom.
5. **Constraints**: What cannot be changed as part of the fix? What must remain
   compatible?
6. **Success criteria**: What does "fixed" look like? How will you confirm it?

Do not ask follow-up questions that the user's answers already cover. If an answer is
ambiguous, ask one targeted clarifying question per ambiguity in a second pass.

## Required Output

```text
SYMPTOM_VALIDATION:
  status: COMPLETE | PENDING
  observed_behavior: <description>
  expected_behavior: <description>
  environment: <version, OS, config, dependency versions>
  reproduction_inputs: <exact steps or inputs>
  constraints:
    - <constraint, or "none">
  success_criteria:
    - <criterion>
  user_answers_summary: <verbatim summary of user answers>
```

## Gate

- Do not proceed to Stage 2 until `status: COMPLETE`.
- Record every user answer verbatim in `user_answers_summary`.
- If the user cannot reproduce the symptom, record that as a constraint and note it
  as a risk in Stage 2.
- If the user declines to answer a question, record `user declined` for that field
  and note it as a risk.
