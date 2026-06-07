---
name: plan-loop
description: >
  Gated planning loop with requirements validation, source authority mapping,
  user-only decision resolution, plan generation, self-check, reviewer gates,
  and approval before implement-loop handoff.
  Invoke with: /plan-loop <request-or-file>.
---

# Plan Loop

## Goal

Produce one verified, implementation-ready plan through a disciplined loop:

```text
load request -> requirements validation -> source authority map
             -> decision gate -> plan generation -> plan self-check
             -> reviewer gate -> approval
```

No plan generation begins until requirements are validated and source authority is
established. No approval is granted while decisions remain unresolved.

Reference files:

- `codex-model-check.md`
- `plan-loop/requirements-validation.md`
- `plan-loop/source-authority.md`
- `plan-loop/plan-format.md`
- `plan-loop/review-gates.md`

## Inputs

The request can be:

- a file path;
- a short identifier that resolves to a request file;
- inline description.

## Constants

- `MAX_REPAIR_ITERATIONS = 5`
- Plans are written to `.claude/plans/` by default.
- Divergence reports go to `.claude/plans/divergence-reports/`.

## Stage 0: Load Request

1. Resolve the request (file path, identifier, or inline text).
2. Extract the raw goal and any initial constraints.
3. Proceed immediately to Stage 1.

Initialize:

```text
repair_iteration = 0
plan_converged = false
requirements_validated = false
sources_established = false
decisions_resolved = false
plan_path = ""
CODEX_MODEL = ""
CODEX_BASE_COMMAND = ""
```

## Stage 0.1: Codex Model Check

Read `codex-model-check.md`.

Spawn a sub-agent to verify the current recommended Codex CLI model. Record
`CODEX_MODEL` and `CODEX_BASE_COMMAND` in loop state. Use these values at Stage 6b.

## Stage 1: Requirements Validation

Read `plan-loop/requirements-validation.md`.

Ask the user concise targeted questions to establish the goal, non-goals, constraints,
and success criteria. Collect all questions in one batch.

**Do not begin Stage 2 until the user has answered all required questions.**

Set `requirements_validated = true` only after returning `REQUIREMENTS_VALIDATION: status: COMPLETE`.

## Stage 2: Reliable-Source Map

Read `plan-loop/source-authority.md`.

List all authoritative sources, rank their authority, and mark context-only sources.

**Stop and ask the user if source authority is missing or conflicting. Do not choose
between conflicting sources autonomously.**

Set `sources_established = true` only after returning `SOURCE_MAP: ESTABLISHED`.

## Stage 3: Decision Gate

Enumerate every unresolved decision and conflict visible at this point.

For each item:
- State the decision or conflict clearly.
- Present the options without recommending one.
- Ask the user to choose.

**Do not make any autonomous decisions. Do not proceed to Stage 4 until every item has
an explicit user answer recorded.**

Set `decisions_resolved = true` after all items are answered.

## Stage 4: Plan Generation

**May only run after Stage 1, Stage 2, and Stage 3 are complete.**

(`requirements_validated = true` AND `sources_established = true` AND
`decisions_resolved = true`)

Use only:
- validated requirements from Stage 1;
- approved sources from Stage 2;
- explicit user decisions from Stage 3.

**Do not discover or rely on new external sources during this stage.** If a new source
seems necessary, stop and return to Stage 2 for user-reviewed approval of that source.

Generate the plan using the format in `plan-loop/plan-format.md`. Write the plan file
and record its path in `plan_path`.

## Stage 5: Plan Self-Check

After generating the plan, verify:

1. **Requirement coverage**: every requirement from Stage 1 is addressed by at least
   one design element.
2. **Source traceability**: every design decision cites a source from Stage 2 or an
   explicit user decision from Stage 3.
3. **No unresolved decisions**: the plan's "Unresolved Decisions" section contains only
   `NONE`.
4. **No placeholders**: no `TODO`, `TBD`, or `...` remain in the plan.
5. **Signature consistency**: all function/class signatures are consistent across the
   plan sections.

If any check fails, revise the plan before entering Stage 6. Do not proceed while any
check is failing.

## Stage 6: Reviewer Gate

Read `plan-loop/review-gates.md`.

Run internal reviewer passes (completeness, traceability, consistency, feasibility,
handoff), then a Codex review pass. A failed verdict enters the repair loop. Stop after
`MAX_REPAIR_ITERATIONS`.

## Stage 7: Approval Gate

When all Stage 5 checks and Stage 6 gates pass:

1. Report `plan_path` to the user.
2. Summarize the plan in one paragraph.
3. List any non-blocking findings from Stage 6.
4. **A plan with unresolved decisions may not be presented for approval.** Verify
   the "Unresolved Decisions" section is `NONE` before presenting.
5. **Wait for explicit user approval before handing off to `implement-loop`.**

Do not invoke `implement-loop` automatically.

## Repair Loop

```text
while repair_iteration < MAX_REPAIR_ITERATIONS and not plan_converged:
    repair_iteration += 1
    if Stage 6 fails:
        list every blocking finding verbatim
        map each finding to the affected plan section
        revise only those sections
        re-run Stage 5
        re-run Stage 6
    else:
        plan_converged = true
```

If the loop exhausts `MAX_REPAIR_ITERATIONS` without converging, write a divergence
report to `.claude/plans/divergence-reports/` and stop.

## Iteration Log

Record one entry per repair iteration:

```yaml
- repair_iteration: N
  plan_path: <path>
  stage_5_checks: all_pass|partial_fail
  stage_5_failed_checks: [<list or none>]
  stage_6a_internal_overall: PASS|FAIL
  stage_6a_blocking_count: N
  stage_6a_nonblocking_count: N
  stage_6b_codex_overall: PASS|FAIL|ERROR
  stage_6b_codex_error_reason: <if ERROR>
  stage_6b_codex_command: <exact command or n/a>
  stage_6b_codex_verdict_path: <path or n/a>
  converged: true|false
```
