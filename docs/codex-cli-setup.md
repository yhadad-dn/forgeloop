# Codex CLI Setup

ForgeLoop's Codex gate runs at the end of each loop (Stage C in `implement-loop`,
Stage 6b in `plan-loop` and `debug-loop`).

## Model Verification

Each loop runs a Codex model check sub-agent at startup (Stage 0.1) that searches for
the current recommended Codex CLI model and stores it in `CODEX_MODEL`. The gate
command then uses `${CODEX_MODEL}` rather than a hard-coded model name:

```bash
codex exec review \
  -m "${CODEX_MODEL}" \
  --output-last-message ".claude/codex_verdicts/verdict_iter${ITER}.md" \
  - < /tmp/codex_prompt_iter${ITER}.txt
```

See `skill/.claude/skills/codex-model-check.md` for the full verification protocol,
fallback behavior, and how to handle an unavailable sub-agent.

## If Codex Is Unavailable

Make your fallback explicit in repo policy. Do not silently treat an unavailable
external review as a pass.
