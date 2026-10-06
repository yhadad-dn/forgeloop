---
name: cost-heatmap
description: >
  Builds and opens an interactive heat map of your coding-agent token usage and estimated
  list-price cost across Claude Code and Codex (other tools via a CSV import), from local
  transcripts. Refreshed automatically in the background each session. Groups sessions into topics
  tailored to your work, shows run-rate, recurring-job cost, model mix, and cost-reduction
  actions. Invoke with: /cost-heatmap. Also use for "where are my Claude tokens going",
  "claude cost dashboard", "token spend heat map".
---

# Cost Heatmap

Sources: Claude Code (`~/.claude/projects`), Codex (`~/.codex/sessions`, or `$CODEX_HOME`), and
any other tool through `external_turns.csv`. Cost is a list-price estimate, not a bill.
Everything runs locally; only numeric usage, project folder names, and short session
titles are written.

A SessionStart hook refreshes the page in the background (at most hourly, never with a
budget); `FORGELOOP_COST_HEATMAP=off` disables it. This skill is for the interactive pass:
topics, pricing, and presenting.

`cost_heatmap.py` and `dashboard.template.html` sit next to this file. Call the script by
its path in this skill's directory.
Output goes to `~/.claude/forgeloop/cost-heatmap/` (all repos together; it holds session
titles, so keep it out of repos) unless the user names another folder, passed as `--dir`.

## Settings

Read `## Cost heatmap` in `.claude/forgeloop.md` if present:

- `budget_monthly`: USD per month to compare the run-rate against. Omit for no budget KPI.
  Applies to this skill only; the background refresh never uses a budget.
- `budget_ends`: `YYYY-MM-DD`, optional.

Pass them as `--budget N --budget-ends DATE` on `build`. Never invent a budget.

## Steps

1. **Collect.** Run `python3 cost_heatmap.py collect [--dir D]` (`--tools claude,codex` to
   limit, `--root` / `--codex-root` for non-default locations). If it reports no
   transcripts, run `inspect`. If it warns about unpriced models, look up the rates and put
   them in `pricing.json` (`{"model": {"in": 5, "out": 30, "cr": 0.5}}`, USD per million
   tokens, `cr` = cached-input rate) instead of leaving them at $0. Skip this when `turns.csv` in the
   output folder is under a few hours old and the user only wants a rebuild.
2. **Topics.** Read `session_titles.csv`. Derive about six topic names that fit THIS user's
   work, plus `Misc`. Write `session_topics.csv` (`session_dir,topic`), one row per session.
   It overrides the built-in keyword fallback. After building, move titled sessions out of
   `Misc` and rebuild. Keep titles out of any message beyond what the user needs to see.
3. **Build.** `python3 cost_heatmap.py build [--dir D] [--budget N --budget-ends DATE]`
   writes `cost-heatmap.html`.
4. **Pricing freshness.** If `pricing-check.json` in the output folder is missing or its
   `last_checked` is over 7 days old, check the per-million rates at
   https://platform.claude.com/docs/en/about-claude/pricing, update `PRICING` in
   `cost_heatmap.py` only if they drifted (plugin files are read-only when installed: tell
   the user and note the drift in the report instead), write `pricing-check.json` with
   today's date, and rebuild.
5. **Present.** Offer to open the HTML. Give a four-line read: top topics and projects,
   model mix, the recurring-task run-rate and its direction, and the top cost-reduction
   action with its monthly estimate. State that costs are list-price estimates.

## Other tools

For any tool without a built-in reader, write `external_turns.csv` in the output folder with
columns `ts,session_id,tool,model,project,input_tokens,cache_write_tokens,cache_read_tokens,output_tokens,title`
(`input_tokens` excludes cached tokens; `ts` is ISO 8601; one row per model call or per day
is fine). `collect` merges it, and the Tool dimension shows it. Price its models in
`pricing.json`.

## Notes

- Dimensions: topic, recurring task, tool, project, model, tool/MCP server, main vs subagent,
  session; against week, month, or day. Cells drill into sessions.
- Recurring tasks are detected from titles: one title shared by 3+ sessions is a job.
  Renamed jobs are stitched when titles overlap and start within 14 days.
- The project label is the last segment of Claude's encoded folder name, so it is lossy
  (`-home-dn-my-repo` shows as `repo`).
- Subagent logs are counted once; duplicate message ids across files are merged.
- Codex billing: cached input is priced at the model's cached rate; reasoning tokens are
  inside output tokens. Codex token counts are cumulative, so the reader bills deltas.
