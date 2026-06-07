# Debug Report Review Gates

## Stage 6a: Internal Debug Reviewer Gate

Review the debug report and handoff document (not code) from five angles:

| Reviewer | Focus |
|---|---|
| evidence integrity | RED evidence is real, captured, and deterministic; no "I think it reproduces" |
| trace completeness | Root-cause trace cites at least one allowed evidence type; no speculative statements |
| handoff correctness | CONTEXT / WHAT_TO_DO / TESTS / VERIFY / CHECKLIST are complete and internally consistent |
| scope discipline | WHAT_TO_DO is scoped to the traced root cause; no extra or unrelated changes |
| regression coverage | TESTS includes a specific regression test that would have caught the original bug |

Classify each finding:

- `BLOCKING`: missing RED evidence, untraceable root cause, speculative fix in
  `WHAT_TO_DO`, missing or incomplete handoff sections, unresolved decisions, no
  named regression test.
- `NON_BLOCKING`: style, minor clarity improvement, suggestion.

Do not proceed to Stage 6b (Codex) until Stage 6a returns no blocking findings.

## Stage 6b: Codex Gate

Run an independent Codex review of the debug report and handoff after Stage 6a passes.
This gate is required by default. If your repo cannot use Codex, document an explicit
fallback policy before running `debug-loop`; do not silently treat Codex as optional.

Prompt contract:

```text
OVERALL: PASS | FAIL
BLOCKING_FINDINGS:
  - <severity>: <section> — <issue> — <required fix>
NON_BLOCKING_FINDINGS:
  - <severity>: <section> — <issue>
CHECKLIST_RESULTS:
  - RED evidence present: PASS | FAIL — <reason>
  - Root-cause traced: PASS | FAIL — <reason>
  - Handoff complete (all 5 sections): PASS | FAIL — <reason>
  - Scope discipline: PASS | FAIL — <reason>
  - Regression test specified: PASS | FAIL — <reason>
FIX_BRIEF:
  - <exact report/handoff section change, or "none">
```

Suggested command:

```bash
codex exec review \
  -m "${CODEX_MODEL}" \
  --output-last-message ".claude/codex_verdicts/debug_verdict_iter${ITER}.md" \
  - < /tmp/codex_debug_prompt_iter${ITER}.txt
```

`CODEX_MODEL` is set in Stage 0.1 of the loop by the Codex model check sub-agent.
See `codex-model-check.md` for the verification protocol and fallback behavior.

Verdict handling:

- Accept only a verdict whose first line is `OVERALL: PASS` or `OVERALL: FAIL`.
- Require a `FIX_BRIEF` section.
- Retry malformed or empty output once.
- Treat unavailable CLI, authentication failure, unsupported model, or denied approval
  as `codex_overall = ERROR`.
- If retry also errors, write a divergence report.

## Repair Loop

When Stage 6a or 6b returns blocking findings:

1. List every blocking finding verbatim.
2. Map each finding to the report/handoff section it affects.
3. Revise only the affected sections. Do not touch unrelated sections.
4. Re-run Stage 6 self-check.
5. Re-run Stage 6a and Stage 6b.

Stop after `MAX_DEBUG_ITERATIONS` and write a divergence report to
`.claude/debug-reports/divergence-reports/`.
