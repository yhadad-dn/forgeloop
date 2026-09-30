# Plan Review Gates

## Stage 6: Internal Plan Reviewer Gate

Review the generated plan document (not code) from five angles:

| Reviewer | Focus |
|---|---|
| completeness | Every REQ-N has at least one design element and at least one test |
| traceability | Every design decision cites a source, a requirement, or an explicit user decision |
| consistency | All function/class signatures are consistent across plan sections |
| feasibility | No dependency cycles; no missing prerequisite tasks; constraints are respected |
| handoff | `implement-loop Handoff` section is complete, specific, and actionable, including a `RUN_PROOF` whose device, command, and pass criteria are concrete |

Classify each finding:

- `BLOCKING`: missing requirement coverage, untraceable design decision, broken or
  incomplete handoff (including a missing or vague `RUN_PROOF`), unresolved decision remaining in the plan, inconsistent signatures.
- `NON_BLOCKING`: style, minor clarity improvement, suggestion.

Stage 6 passes when this internal review returns no blocking findings.

## Repair Loop

When Stage 6 returns blocking findings:

1. List every blocking finding verbatim.
2. Map each finding to the plan section it affects.
3. Revise only the affected sections. Do not touch unrelated sections.
4. Re-run Stage 5 self-check.
5. Re-run Stage 6.

If the loop exhausts `MAX_REPAIR_ITERATIONS` without converging, write a divergence
report and stop.
