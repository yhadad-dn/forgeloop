# Cost Heatmap

`/forgeloop:cost-heatmap` turns the transcripts Claude Code already writes under
`~/.claude/projects` (or `$CLAUDE_CONFIG_DIR/projects`) and Codex writes under
`~/.codex/sessions` (or `$CODEX_HOME/sessions`) into a self-contained HTML heat map of
estimated list-price cost. It is not a gated loop: it is a report.

```bash
python3 skills/cost-heatmap/cost_heatmap.py            # collect + build
python3 skills/cost-heatmap/cost_heatmap.py build --budget 200 --budget-ends 2026-12-31
python3 skills/cost-heatmap/cost_heatmap.py inspect    # where are the transcripts
```

Output lands in `~/.claude/forgeloop/cost-heatmap/`. The dashboard loads Chart.js
from a CDN, so open it with network access.

Within Claude Code, the skill also writes `session_topics.csv` so topics fit your work
instead of the keyword fallback in the script.

Limits: costs use the `PRICING` table in the script (list prices, cache write x1.25, cache
read x0.10) and are not an invoice; subscription users should read them as "what this
would cost on the API". Project labels are lossy because Claude encodes folder paths.

## Automatic refresh

A SessionStart hook rebuilds the page in the background at the start of every session
(at most once an hour, detached, ~20 s). It never passes a budget, so no budget KPI or
alert appears there; `--budget` is only for manual runs. Disable with
`FORGELOOP_COST_HEATMAP=off`. The log is `refresh.log` next to the page.

## Other tools and pricing

- Tools without a built-in reader: drop `external_turns.csv` in the output folder
  (columns in `skills/cost-heatmap/SKILL.md`).
- `pricing.json` in the output folder overrides or extends the price table, per million
  tokens: `{"gpt-6-astra": {"in": 5, "out": 30, "cr": 0.5}}`. Models with no price are
  costed at $0 and reported by name at build time.
- Built-in OpenAI rows: gpt-5.5 matches OpenAI's published rate; the older rows are
  from memory, so verify them if they matter.
