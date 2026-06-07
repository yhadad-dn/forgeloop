# Plan Review Gates

## Stage 6a: Internal Plan Reviewer Gate

Review the generated plan document (not code) from five angles:

| Reviewer | Focus |
|---|---|
| completeness | Every REQ-N has at least one design element and at least one test |
| traceability | Every design decision cites a source, a requirement, or an explicit user decision |
| consistency | All function/class signatures are consistent across plan sections |
| feasibility | No dependency cycles; no missing prerequisite tasks; constraints are respected |
| handoff | `implement-loop Handoff` section is complete, specific, and actionable |

Classify each finding:

- `BLOCKING`: missing requirement coverage, untraceable design decision, broken or
  incomplete handoff, unresolved decision remaining in the plan, inconsistent signatures.
- `NON_BLOCKING`: style, minor clarity improvement, suggestion.

Do not proceed to Stage 6b (Codex) until Stage 6a returns no blocking findings.

## Stage 6b: Codex Gate

Run an independent Codex review of the plan after Stage 6a passes. This gate is required
by default. If your repo cannot use Codex, document an explicit fallback policy before
running `plan-loop`; do not silently treat Codex as optional.

Prompt contract:

```text
OVERALL: PASS | FAIL
BLOCKING_FINDINGS:
  - <severity>: <section> — <issue> — <required fix>
NON_BLOCKING_FINDINGS:
  - <severity>: <section> — <issue>
CHECKLIST_RESULTS:
  - Check N: PASS | FAIL — <reason>
FIX_BRIEF:
  - <exact change to the plan, or "none">
```

Suggested command:

```bash
codex exec review \
  -m "${CODEX_MODEL}" \
  --output-last-message ".claude/codex_verdicts/plan_verdict_iter${ITER}.md" \
  - < /tmp/codex_plan_prompt_iter${ITER}.txt
```

`CODEX_MODEL` is set in Stage 0.1 of the loop by the Codex model check sub-agent.
See `codex-model-check.md` for the verification protocol and fallback behavior.

Verdict handling:

- Accept only a verdict whose first line is `OVERALL: PASS` or `OVERALL: FAIL`.
- Require a `FIX_BRIEF` section.
- Retry malformed or empty output once.
- Treat unavailable CLI, authentication failure, unsupported model, or denied approval
  as `codex_overall = ERROR`.
- If retry also errors, write a divergence report to
  `.claude/plans/divergence-reports/`.

## Codex Prompt Template for Plan Review

```text
Review this plan against the stated requirements and source authority map.
Return exactly:

OVERALL: PASS | FAIL
BLOCKING_FINDINGS:
  - <severity>: <section> — <issue> — <required fix>
NON_BLOCKING_FINDINGS:
  - <severity>: <section> — <issue>
CHECKLIST_RESULTS:
  - REQ coverage: PASS | FAIL — <reason>
  - Source traceability: PASS | FAIL — <reason>
  - Unresolved decisions: PASS | FAIL — <reason>
  - Placeholder scan: PASS | FAIL — <reason>
  - Handoff completeness: PASS | FAIL — <reason>
FIX_BRIEF:
  - <exact plan section change, or "none">

=== REQUIREMENTS ===
...

=== SOURCE MAP ===
...

=== PLAN ===
...
```

## Repair Loop

When Stage 6a or 6b returns blocking findings:

1. List every blocking finding verbatim.
2. Map each finding to the plan section it affects.
3. Revise only the affected sections. Do not touch unrelated sections.
4. Re-run Stage 5 self-check.
5. Re-run Stage 6a and Stage 6b.

If the loop exhausts `MAX_REPAIR_ITERATIONS` without converging, write a divergence
report and stop.
