---
name: debug-loop
description: >
  Gated bug investigation loop with symptom validation, evidence source mapping,
  mandatory reproduction gate, trace-backed root-cause analysis, handoff generation,
  reviewer gate, and approval before implement-loop handoff.
  v1 is handoff-only: it does not edit code.
  Invoke with: /debug-loop <symptom-or-file>.
---

# Debug Loop

## Goal

Investigate one bug through a disciplined loop:

```text
load symptom -> symptom validation -> evidence source map
             -> reproduction gate -> hypothesis + root-cause trace
             -> handoff generation -> self-check + reviewer gate -> approval
```

Hypothesis generation is blocked until RED evidence exists. Fix handoff is blocked
until root-cause trace evidence exists. `debug-loop` v1 does not edit code. Fixes
happen only through an approved `implement-loop` handoff.

Reference files:

- `codex-model-check.md`
- `debug-loop/symptom-validation.md`
- `debug-loop/evidence-map.md`
- `debug-loop/reproduction-gate.md`
- `debug-loop/root-cause-trace.md`
- `debug-loop/handoff-format.md`
- `debug-loop/review-gates.md`

## Inputs

The symptom can be:

- a file path;
- a short identifier that resolves to a bug report;
- inline description.

## Constants

- `MAX_DEBUG_ITERATIONS = 5`
- Debug reports are written to `.claude/debug-reports/` by default.
- Divergence reports go to `.claude/debug-reports/divergence-reports/`.

## Stage 0: Load Symptom

1. Resolve the symptom (file path, identifier, or inline text).
2. Extract observed behavior and any initial context.
3. Proceed immediately to Stage 1.

Initialize:

```text
debug_iteration = 0
debug_converged = false
symptom_validated = false
evidence_established = false
red_evidence = ""
root_cause_trace = ""
debug_report_path = ""
CODEX_MODEL = ""
CODEX_BASE_COMMAND = ""
```

## Stage 0.1: Codex Model Check

Read `codex-model-check.md`.

Follow the protocol in `codex-model-check.md`: probe `gpt-5.5` locally first; only
run a web-search sub-agent if the probe fails. Record `CODEX_MODEL` and
`CODEX_BASE_COMMAND` in loop state. Use these values at Stage 6b.

## Stage 1: Symptom Validation

Read `debug-loop/symptom-validation.md`.

Ask the user in one batch:

1. Observed behavior (what happens).
2. Expected behavior (what should happen).
3. Environment (version, OS, config, dependency versions).
4. Reproduction inputs (exact steps, inputs, commands).
5. Constraints (cannot change X, must stay compatible with Y).
6. Success criteria (what does "fixed" look like?).

**Do not begin Stage 2 until the user has answered all required questions.**

Set `symptom_validated = true` only after returning `SYMPTOM_VALIDATION: status: COMPLETE`.

## Stage 2: Evidence Source Map

Read `debug-loop/evidence-map.md`.

Rank all available evidence by authority and list it.

**User resolution is required for any conflict among reproduction evidence, runtime
traces/logs, dependency behavior, data shape, specs/docs, source contracts, and
generated/context-only sources. Do not resolve conflicts autonomously.**

Set `evidence_established = true` only after returning `EVIDENCE_MAP: ESTABLISHED`.

## Stage 3: Reproduction Gate

Read `debug-loop/reproduction-gate.md`.

Establish a deterministic, repeatable reproduction of the symptom before any analysis.

**Do not generate hypotheses until RED evidence exists.**

Set `red_evidence` only after returning `REPRODUCTION: CONFIRMED`.

## Stage 4: Hypothesis and Root-Cause Trace

Read `debug-loop/root-cause-trace.md`.

Form bounded, evidence-backed hypotheses only after `red_evidence` is confirmed.

**Do not generate the handoff until root-cause trace evidence exists.**

Set `root_cause_trace` only after returning `ROOT_CAUSE: TRACED`.

## Stage 5: Debug Handoff Generation

Read `debug-loop/handoff-format.md`.

Produce an `implement-loop` task file using the canonical schema: `CONTEXT`,
`WHAT_TO_DO`, `TESTS`, `VERIFY`, and `CHECKLIST`.

`debug-loop` v1 does not edit code. The handoff document is the deliverable.

Record `debug_report_path` after writing the report and handoff.

## Stage 6: Self-Check and Reviewer Gate

Read `debug-loop/review-gates.md`.

Self-check before review:

1. RED evidence is present and reproducible.
2. Root-cause trace cites at least one allowed evidence type (file/line, config,
   runtime evidence, dependency behavior, or data shape).
3. `WHAT_TO_DO` is scoped to the traced root cause; no speculative changes.
4. Handoff schema is complete: `CONTEXT`, `WHAT_TO_DO`, `TESTS`, `VERIFY`, `CHECKLIST`.
5. No unresolved decisions remain.
6. `TESTS` includes a regression test that would have caught the bug.

Run internal reviewer passes, then Codex review of the debug report and handoff.
A failed verdict enters the repair loop. Stop after `MAX_DEBUG_ITERATIONS`.

## Stage 7: Approval Gate

When all Stage 6 checks pass:

1. Report `debug_report_path` to the user.
2. Summarize the symptom, RED evidence, root cause, and proposed fix scope.
3. List any non-blocking findings.
4. Verify before presenting:
   - No unresolved decisions remain.
   - `red_evidence` is present.
   - `root_cause_trace` is present.
   - Handoff is complete.
5. **A debug report with unresolved decisions may not be presented for approval.**
6. **Wait for explicit user approval before handing off to `implement-loop`.**

Do not invoke `implement-loop` automatically.

## Repair Loop

```text
while debug_iteration < MAX_DEBUG_ITERATIONS and not debug_converged:
    debug_iteration += 1
    if Stage 6 fails:
        list every blocking finding verbatim
        map each finding to the affected report/handoff section
        revise only those sections
        re-run Stage 6 self-check and reviewer gate
    else:
        debug_converged = true
```

A regression failure prevents convergence. "Symptom disappeared" without passing
regression checks is not convergence.

If the loop exhausts `MAX_DEBUG_ITERATIONS` without converging, write a divergence
report to `.claude/debug-reports/divergence-reports/` and stop.

## Iteration Log

```yaml
- debug_iteration: N
  red_evidence_present: true|false
  root_cause_traced: true|false
  report_path: <path>
  stage_6_self_check: all_pass|partial_fail
  stage_6_self_check_failed: [<list or none>]
  stage_6a_internal_overall: PASS|FAIL
  stage_6a_blocking_count: N
  stage_6a_nonblocking_count: N
  stage_6b_codex_overall: PASS|FAIL|ERROR
  stage_6b_codex_error_reason: <if ERROR>
  stage_6b_codex_command: <exact command or n/a>
  stage_6b_codex_verdict_path: <path or n/a>
  converged: true|false
```
