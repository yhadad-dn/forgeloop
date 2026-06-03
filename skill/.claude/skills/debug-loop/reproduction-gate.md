# Stage 3: Reproduction Gate

Run after Stage 2. Run before Stage 4.

## Acceptable RED Evidence

At least one of the following is required:

- A **failing automated test** (most preferred — becomes a committed regression test).
- A **failing command** with captured stdout/stderr output.
- A **captured log snippet or stack trace** that deterministically appears when the
  symptom triggers.
- A **deterministic manual repro sequence** that a second person could follow and
  observe the same symptom.

## Required Output

```text
REPRODUCTION: CONFIRMED | UNCONFIRMED | FLAKY
RED_EVIDENCE:
  type: failing_test | failing_command | log_trace | manual_repro
  description: <what was done>
  output: <captured output or path to captured file>
  deterministic: true | false | unknown
```

## Gate

- Do not proceed to Stage 4 until RED evidence exists.
- `REPRODUCTION: CONFIRMED` with `deterministic: true` is required to proceed to
  Stage 4. No other outcome qualifies.
- `FLAKY`: `FLAKY` does not qualify as confirmed RED evidence. Ask the user to choose
  one of:
  1. Gather additional evidence to achieve `REPRODUCTION: CONFIRMED`.
  2. Record the flakiness as a risk and stop (write a divergence note).
  3. Return to Stage 3 with a modified reproduction strategy.
  Stage 4 requires `REPRODUCTION: CONFIRMED` with `deterministic: true` regardless of
  the user's choice. No path through `FLAKY` proceeds directly to Stage 4.
- `UNCONFIRMED`: stop. Ask the user to provide reproduction steps or additional context.

## Notes

A test that was already passing before the alleged bug is not RED evidence.
RED evidence must show the symptom is present before any fix attempt.
"The symptom appeared once and then stopped" is `FLAKY`, not `CONFIRMED`.
