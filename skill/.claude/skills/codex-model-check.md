# Codex Model Check

Run at the start of any loop that uses the Codex CLI gate. Verifies the current
recommended Codex CLI model before any gate invocation so the loop uses a working,
up-to-date model rather than a stale default.

## Step 1: Try the default model

Attempt to run a no-op probe with the default model (`gpt-5.5`):

```bash
codex exec review -m "gpt-5.5" --help 2>&1 | head -3
```

If the command exits successfully (exit code 0) or prints recognisable Codex CLI
output, treat the default as **confirmed** — no web search needed:

```text
CODEX_MODEL_CHECK: VERIFIED
CODEX_MODEL: gpt-5.5
CODEX_BASE_COMMAND: codex exec review -m "gpt-5.5"
SOURCE: local-probe
VERIFIED_AT: <UTC timestamp>
```

## Step 2: Web search (only if step 1 fails)

If the probe fails (non-zero exit, "model not found", "unknown model", or similar
error), spawn a sub-agent with web access and give it this prompt:

```
Search for the current recommended model for the OpenAI Codex CLI (the agentic
coding terminal tool, not the original completion API). Check the OpenAI developer
documentation or recent official announcements.

Return exactly:
  CODEX_MODEL: <model identifier, e.g. gpt-5.5>
  CODEX_BASE_COMMAND: codex exec review -m "<model>"
  SOURCE: <URL that confirmed the model>
  VERIFIED_AT: <UTC timestamp>
```

## Required Output

```text
CODEX_MODEL_CHECK: VERIFIED | UNVERIFIED | FAILED
CODEX_MODEL: <model identifier>
CODEX_BASE_COMMAND: codex exec review -m "<model>"
SOURCE: <URL or "unavailable">
VERIFIED_AT: <UTC timestamp>
```

## Handling

- `VERIFIED`: record `CODEX_MODEL` and `CODEX_BASE_COMMAND` in loop state. Use them
  at every Codex gate in this run.
- `UNVERIFIED`: log a warning, use the last-known model as fallback (currently
  `gpt-5.5`), and note the fallback in the iteration log. Do not block the loop.
- `FAILED`: log the failure, use the last-known model as fallback, and document the
  fallback in the iteration log so reviewers are aware.

## Command Template

When constructing the Codex CLI command at any gate, substitute `${CODEX_MODEL}` with
the verified model identifier:

```bash
codex exec review \
  -m "${CODEX_MODEL}" \
  --output-last-message "<verdict-path>" \
  - < <prompt-file>
```

Never hard-code a model name in the gate command. Always use the value set by this
check.
