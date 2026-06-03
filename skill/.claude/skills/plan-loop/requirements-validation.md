# Stage 1: Requirements Validation

Run before any source mapping or plan generation.

## Questions to Ask

Collect the following in one batch — do not ask piecemeal:

1. **Goal**: What should the finished work do or produce? What is the single measurable
   outcome?
2. **Non-goals**: What is explicitly out of scope for this plan?
3. **Constraints**: Language, library, architecture, performance, deadline, or team
   constraints?
4. **Success criteria**: How will you know the plan succeeded? What would make you reject
   the implementation?
5. **Known risks**: What might make this plan fail or need revision?

Do not ask follow-up questions that the user's answers already cover. If an answer is
ambiguous, ask one targeted clarifying question per ambiguity in a second pass.

## Required Output

```text
REQUIREMENTS_VALIDATION:
  status: COMPLETE | PENDING
  goal: <one sentence>
  non_goals:
    - <item, or "none">
  constraints:
    - <item, or "none">
  success_criteria:
    - <item>
  known_risks:
    - <item, or "none">
  user_answers_summary: <verbatim summary of user answers>
```

## Gate

- Do not proceed to Stage 2 until `status: COMPLETE`.
- Record every user answer verbatim in `user_answers_summary`.
- If the user declines to answer a question, record `user declined` for that field and
  note it as a risk.
