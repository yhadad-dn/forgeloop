# Changelog

## 0.16.0

- **ASD-STE100 answer style is now on by default** for all users (it was opt-in). Precedence:
  a non-empty `FORGELOOP_STYLE` wins (`ste` is on, any other value is off); else the first
  line of `~/.claude/forgeloop/style` (`ste` is on, any other value is off); else on. Turn it
  off with `FORGELOOP_STYLE=off` or a style file that contains `off`. `/forgeloop:setup`
  reports the `ste-style` item as `ok` ("on by default"); `--ste` still writes `ste` into the
  style file, idempotently, and never changes a file the user set to another value.
- **Durable sessions are the default on a Remote-SSH VM**: `/forgeloop:setup` includes the
  durable items (wrapper copy, VS Code machine setting) when the host classifies as
  `remote_ssh`. You still approve the diff once per VM; the plugin never writes the VS Code
  setting silently. `--durable` forces them on; new `--no-durable` skips them. The one-line
  setup hint uses the same default, so a pending durable item makes it fire on a VM.
  Other hosts behave as before.
- **Session end closes the tmux session**: new `forgeloop_tmux.py end-current` closes the
  current tmux session about 2 seconds later, only when `$TMUX` is set and the session name
  starts with `fl-`; otherwise it prints one line and does nothing. The 57-minute idle
  checkpoint runs it as its last step, after the summary is written (unattended), and so
  does an explicit request such as "end session". The idle checkpoint closes the session
  after 57 idle minutes even if you are still attached (summary saved first), and closing
  needs `TMUX_PANE`.
- **New setup item `tmux-end-rule`** (durable only): an allow rule for exactly
  `python3 ~/.claude/forgeloop/forgeloop_tmux.py end-current` in `permissions.allow`.
- **Status format has a flow chart**: Progress now starts with a FLOW chart, then progress
  bars for the current task only, then Cluster and Close. Marks: ✅ done and tested, 🔄 in
  progress, blank not started. Scope: the current task and its subtasks, its parent stage,
  and the stages directly before and after; older finished work collapses into one
  `earlier:` line. Bars count only ✅ steps. Summaries inherit it.
- **Cluster block is a "what can I use" view**: `cluster_status.py` now prints `🟢 Free now`
  (free GPUs per node, most free first), `🔴 Full` (full is normal, never a warning), one
  `🧑‍💻 Your job` line per job (id, SLURM name, node, end time) with a `does:` evidence line
  (step names, GPU-holding process commands with secrets stripped, containers, tmux session,
  log name), and `⚠️` lines only for real problems of the run in scope (a `--job` run or its
  nodes; `--mine` alone shows none; `--warnings`, `--plain`, `--detail` show all; the exit code
  counts only shown warnings; `--json` stays complete with a `relevant` flag). `--plain` prints the previous default;
  `--detail` is unchanged; `--json` stays compatible and adds `does_evidence` per job and
  `cluster_gpus`. Status reports add the job name and a four-word purpose sentence per job.

## 0.15.0

- **Saved-session picker moved into the plugin**: a new `SessionStart` hook
  (`hooks/session_picker.py`) replaces the personal `session-continuity` hook, including
  the 57-minute idle checkpoint. It lists `.claude/session_state_*.md` files in the project.
- **Two-step picker**: step 1 chooses a session (newest 3), or "Fresh start, clean up, or
  older". A chosen session offers Load, Delete or Back. Clean up is a tick list to delete
  several sessions at once. Older sessions page by 3.
- **Exact name shown**: every entry is labeled with the `Name:` line of its file, and the
  first reply after a load starts with `Loaded session: <name>`.
- **Summary removed on load**: the file is deleted right after it is read. A failed read
  keeps it.
- **Helper `hooks/session_state.py`** (`list`, `consume`, `delete`, stdlib only). Keys must
  match `[A-Za-z0-9_-]{1,64}`; it refuses symlinks, non-files, the current session, and any
  `--dir` not named `.claude`.
- **`/forgeloop:setup` new items**: `session-allow-rule` (one `Bash(python3 <root>/hooks/session_state.py:*)`
  allow rule) and `retire-session-hook` (removes the personal `session-continuity` hook
  entry; the old script file stays on disk). Both need approval and write a backup.
- **Off switch**: `FORGELOOP_SESSIONS=off` (the legacy `SESSION_CONTINUITY=off` also works).
- NOTE: until you run `/forgeloop:setup`, two pickers appear (the personal one and this
  one). The allow rule path contains the plugin version, so setup reports the rule again
  after each upgrade. The rule matches any arguments, so only the helper's key rules and
  the `.claude`-directory check limit what it can delete.
- NOTE: `--keep` and the `.claude`-name check are not security boundaries. The allow rule
  lets the helper delete any `session_state_<key>.md` in any `.claude` directory.
- Hardening: names and summaries from session files lose control characters, `[`, `]` and
  backticks and are capped (60 and 200 characters); `consume` exits 3 when it printed the file
  but could not remove it; the picker is off unless the plugin root and project path match
  `[A-Za-z0-9_./+@:-]+`.

## 0.14.0

- **Durable VS Code sessions on a Remote-SSH VM**: with `/forgeloop:setup --durable`, a new
  session started from the VS Code extension runs as a Remote Control server inside a
  detached `fl-*` tmux session, so it survives a closed laptop (not a VM reboot or sleep).
  The panel shows the session name, link and attach command. Everything except a real
  session start passes through unchanged; any failure falls back to a normal session.
- **`/forgeloop:tmux-session`** skill: `list` and `stop` (confirmation first; only `fl-*`
  sessions).
- Other remote hosts (container, WSL, Codespaces): a session hint asks whether to enable
  it. `FORGELOOP_DURABLE=off` disables the wrapper and the hint.
- `scripts/claude-tmux.sh`: terminal launcher for a tmux session running `claude`.
- Details in `docs/durable-sessions.md`.

## 0.13.2

- **Clean-tree check ignores untracked `.claude/` files**: the `implement-loop` Stage 0
  check no longer blocks on untracked files under any `.claude/` directory (for example
  `.claude/session_state_*.md` from the session-continuity hook). Tracked, staged and
  other changes still block, as do look-alike paths such as `.claude.bak/`.

## 0.13.1

- **No manual settings changes**: every ForgeLoop feature works with no edit to
  `settings.json`, and each one has an off switch or file (audit table in the README).
  New `FORGELOOP_COST_BAND=off` switches the session cost band off.
- **`/forgeloop:setup` skill** (`skills/setup/forgeloop_setup.py`, stdlib only): `plan`
  shows the exact diff, `apply` writes it after approval with a timestamped backup,
  `--check` writes nothing and exits 1 when something is pending, `--team-snippet` prints
  the JSON for a repo's `.claude/settings.json`. User scope only; refuses to touch a
  settings file that is not strict JSON.
- **Setup hint**: the `SessionStart` hook checks once per ForgeLoop version (stamp in
  `~/.claude/forgeloop/setup-stamp`) and adds one line telling you to run
  `/forgeloop:setup` when something is pending. It never writes settings and fails open.
  `FORGELOOP_SETUP_HINT=off` disables it.
- Documented team rollout (`extraKnownMarketplaces`, `enabledPlugins`) and managed settings.

## 0.13.0

- **Opt-in ASD-STE100 answer style**: `styles/ste.md` holds the rules; the
  `SessionStart` hook adds them after the team conventions when `FORGELOOP_STYLE=ste`
  or the first line of `~/.claude/forgeloop/style` is `ste`. Off by default. Covers
  chat replies only (not code, commands, or commit messages), and keeps the content
  complete: plain words must not remove a fact, risk, or trade-off.

## 0.12.0

- **Live session cost above the prompt**: a mod module (`hooks/session_cost.tsx`,
  registered under `modules` in `hooks/hooks.json`) shows `Session $1.84 · ctx 41%` in
  the band above the prompt after every turn, and writes the same text to the terminal
  status line. Figures come from the engine's own session usage (the same totals `/cost`
  reports; a list-price estimate, not a bill), so it needs no pricing table. Drawn
  per surface, including the VS Code extension where the band slot is available.

## 0.11.0

- **New `cost-heatmap` skill**: builds a self-contained interactive HTML heat map of
  agent token usage and list-price cost from local transcripts: Claude Code and Codex,
  plus any other tool via `external_turns.csv`. Ported from a Cowork-oriented dashboard:
  stdlib-only script, no org branding, optional monthly budget via `.claude/forgeloop.md`
  (`## Cost heatmap`), Tool and Project dimensions, generic fallback topics (Claude writes
  per-user topics), `pricing.json` overrides, unpriced models reported not guessed.
  Output in `~/.claude/forgeloop/cost-heatmap/`. Not a gated loop.
- **New SessionStart hook** `cost_heatmap_refresh.py`: refreshes the heat map in the
  background each session (hourly at most, detached, never with a budget). Off with
  `FORGELOOP_COST_HEATMAP=off`.

## 0.10.1

- **Fix HEAD-as-baseline assumption in implement-loop**: Stage 0 now asserts a clean
  working tree (`assert_clean_tree`), hard-blocking on pre-existing dirty files so they
  are never attributed to iteration 1's scope, Stage R's N=2 fallback or Stage B's file
  list. ForgeLoop's own artifact paths are excluded by pathspec, so it never blocks on
  its own prior-run leftovers. Never auto-commits or auto-stashes. Resolves the
  0.10.0 follow-up caveat. `.gitignore` gains the `clean-code`, `run-proofs`,
  `plans/followups` and `plans/divergence-reports` artifact entries.
- `marketplace.json` version corrected (was stale at 0.9.0).

## 0.10.0

- **Git-diff-narrowed repair scope**: implement-loop's Stage R and Stage A.5 now
  compute a precise per-iteration file list from persisted git tree snapshots —
  what the previous repair pass actually touched — instead of rediscovering scope
  or diffing cumulatively against the task's starting commit. Soft starting point,
  never a hard restriction. Found and fixed through 4 real review iterations
  (untracked-file-union pollution, a missing then too-narrow forbidden-path filter
  for ForgeLoop's own `.claude/` artifacts, an incomplete N>2 fallback); a 5th issue
  (HEAD as an unsafe baseline on a dirty working tree) surfaced at the iteration cap
  and is tracked as a follow-up rather than rushed through
  (`.claude/plans/followups/repair-scope-git-diff-narrowing-1.md`).
- **Declarative `Sources` section** in `.claude/forgeloop.md`: repos can declare
  authoritative/context-only sources once instead of restating source-ranking rules
  per task or hand-writing them as CLAUDE.md prose (which drifts — a real example
  CLAUDE.md re-explained ForgeLoop's own ranking logic and then went stale against
  it). `implement-loop` Stage 0.5 and `plan-loop` Stage 2 treat declared entries as
  pre-ranked, but still verify each one against the specific claim.
- **New convention**: a commit that leaves a referenced plan, ADR, or doc out of
  sync with what was actually built is incomplete, not merely untidy. Added to
  implement-loop's Stage D, both Checklist templates, and the README's Philosophy
  list.
- README: added Mermaid flowcharts to the Debug/Plan/Implement Loop sections, a
  version line in the header, and documentation for the previously-undocumented
  `explorer` agent (shipped in 0.9.0, missing from the README until now).

## 0.9.0

- **New `explorer` agent**: shared, read-only (`Read, Grep, Glob`), `model: haiku`,
  citations-only broad search for the one real undirected-search moment in each of
  `implement-loop` (Stage A), `plan-loop` (Stage 2), and `debug-loop` (Stage 4) — not
  wired into `refactorer` or implement-loop's Stage B reviewers, which already receive
  an explicit file list, and not into `cluster-loop`, whose survey is SSH/sinfo/squeue,
  not file/symbol search. Dispatched only when the task doesn't already pinpoint a
  location; its citations are a starting point, never exhaustive — the dispatching
  agent confirms them itself before relying on them, and in `debug-loop` an explorer
  citation alone never satisfies the `file_line` trace-evidence requirement.
  Adapted from the `caveman-explore` agent in `github.com/JuliusBrussee/caveman` (MIT).
  Planned via `/plan-loop`, implemented via `/implement-loop`: RED → GREEN on 4 new
  check-script assertion groups (245 → 260 total), Stage A.5 clean-code pass returned
  `NO_CHANGES` (reasoned: no safe simplification found), Stage B reviewer gate passed
  with zero blocking findings across correctness/security/hygiene, Stage C run-proof
  passed (the agent, dispatched for real, correctly cited
  `implement-loop/SKILL.md:150` for a live question, independently re-verified).
  The token/cost-reduction claim this was built for is tracked as a follow-up
  measurement against real usage, not gated by this release.

## 0.8.1

- **Fixed:** `implement-loop/SKILL.md`'s Stage B description still named all five
  pre-0.7.0 reviewers in prose ("correctness; security; performance; standards;
  dead-code/slop") after the roster was cut to three dispatches
  (`reviewer-correctness`, `reviewer-security`, `reviewer-hygiene`) in 0.7.0.
  `review-gates.md` and the agent files were already correct — this was a plain
  prose list, not a backtick-quoted agent name, so the greps that verified the
  0.7.0 removal didn't catch it. Found by a peer Claude session (DNRT) cross-
  checking a live `~/.claude` resync against the shipped skill files.

## 0.8.0

- **Scoped `tools:` on every agent.** None previously declared one, so each got
  Claude Code's full default tool set on every dispatch. `reviewer-correctness`,
  `reviewer-security`, `reviewer-hygiene`, and `source-check` are now
  `Read, Grep, Glob` (plus `WebFetch` for `source-check`, which may need to check
  a published spec by URL) — matching what their own rules already say ("do not
  edit files"). `refactorer` drops `Write` (it edits existing in-scope files, never
  creates new ones). `developer` is unchanged in substance (`Read, Write, Edit,
  Bash, Grep, Glob`), just now stated explicitly.
  Measured: in an isolated paired dispatch with no MCP servers loaded, full vs.
  restricted tool lists showed no measurable difference in
  `cache_creation_input_tokens` (19026 vs 19444) — this harness's own built-in
  tools are small next to an MCP-heavy setup. The restriction is still applied
  for scope discipline (an agent that says "never edits files" shouldn't be able
  to) and is expected to matter more in a session with MCP servers loaded, which
  was not this test's environment — that expectation is reasoned, not measured.
- **`reviewer-hygiene` runs on `model: haiku`.** Its findings are mostly
  `NON_BLOCKING` by the agent's own design (see 0.7.0); a missed nit there is
  cheap. `reviewer-correctness` and `reviewer-security` are unchanged — never
  downgraded, same reasoning as not merging them.
- **Terse one-line finding format** for `reviewer-correctness`, `reviewer-security`,
  and `reviewer-hygiene`: `BLOCKING|NON_BLOCKING [facet]: <file>:<line> —
  <problem>. <fix>.` instead of free-form prose, reusing the existing
  BLOCKING/NON_BLOCKING vocabulary rather than inventing new severities.
  Measured on one paired real dispatch (identical synthetic diff, same 3 real
  findings both times — a dead redundant branch, an unused non-retry-safe
  idempotency key, missing regression tests): 2305 → 1438 output tokens, a 38%
  reduction, no information lost. This is a single run, not an average; rerun
  before trusting it on a different workload.
  Ideas scouted from `github.com/JuliusBrussee/caveman` (MIT): its
  `caveman-explore` agent (`tools: Read, Glob, Grep`, `model: haiku`) and
  `caveman-review`'s one-line finding format. Its own terse-voice persona was
  deliberately not adopted — its own `docs/HONEST-NUMBERS.md` measures that at
  3–9% output reduction with a documented net-negative failure mode, and it
  conflicts with the structured status/summary conventions already in this file.

## 0.7.0

- **Reviewer roster cut from 9 agents to 6**, to reduce the dispatches `implement-loop`
  makes per iteration without weakening any blocking check:
  - Removed `tester`: no loop ever dispatched it (every reference to "tester" was the
    boilerplate agent list or prose that never named an invocation). Coverage repair
    is now an ordinary Stage R repair iteration; `coverage_decision`'s
    `measured_below_threshold_tester_run` is renamed `measured_below_threshold_repair_run`.
  - Merged `reviewer-performance`, `reviewer-standards`, and `reviewer-slop` into one
    `reviewer-hygiene` agent. All three checklists are kept verbatim inside it, with
    findings labeled `[standards]`/`[slop]`/`[performance]` so nothing is lost; it
    also removes a duplicate Stage A.5 scope check that had drifted into both
    `standards` and `slop` separately.
  - `reviewer-correctness` and `reviewer-security` are unchanged and still dispatched
    standalone — merging either into a shared pass was considered and rejected, since
    diluting the two highest-stakes reviewers would trade correctness for tokens.
  - `implement-loop`'s full reviewer gate (new code surfaces or larger diffs) is now
    3 dispatches (correctness, security, hygiene) instead of 5. The reduced-fan-out
    tiers for small/docs diffs also use `reviewer-hygiene` and are unchanged in count.

## 0.6.0

- `implement-loop` states its governing principle, "Correctness Only Goes Up": no
  stage may weaken tests, thresholds, run proofs, or source correspondence; unprovable
  A.5/repair changes are reverted; a gate that cannot run is never a pass; ForgeLoop
  versions never change mid-task.

- **Session conventions hook**: a `SessionStart` hook injects `conventions.md` into
  every session: status-report format (context, plain-words done list, visual
  progress, cluster block, **Next:** / **What's stopping us:** / **From you:**) and Israel time. Personal
  (`~/.claude/forgeloop/conventions.md`) and repo (`## Conventions` in
  `.claude/forgeloop.md`) layers override it; `FORGELOOP_CONVENTIONS=off` disables it.
  Summaries: project and assignment context, milestones with evidence, then the
  status format from progress onward.
- **`cluster_status.py`** (`/forgeloop:cluster-loop status`): a job table built for
  "status?" (progress, finish time vs expiry, state), a compact GPU line per node,
  and warnings with a proposed action; `--detail` for the full per-node view.
  Finish time from the log's ETA or tqdm remaining time, else a rate estimate from
  overall progress (nested epoch/step counters handled) and the SLURM step's
  elapsed time. Fast: one SLURM round trip, parallel probes with per-node
  timeouts, ssh ControlMaster, GPU-method and 20 s result caches, `--timing`.
  Verified against the live cluster (54/54 fields): probes over ssh (an srun step's
  cgroup hides the GPUs), KFD-based GPU-holder detection, workload ownership from
  `sacct` (who held the node when it started), container logs as a progress source,
  `slurm_host`/`job_name` settings, and a clear "no SLURM client" message.
  Stdlib only; missing data shows as n/a or "—", never guessed.

- **ForgeLoop is now a Claude Code plugin**, with this repo as its own
  marketplace: `/plugin marketplace add yhadad-dn/forgeloop`, then
  `/plugin install forgeloop@forgeloop`. Also distributed to the DriveNets team
  via the `gpu-team` marketplace (`plugins/forgeloop/` in
  `drivenets/dn-ai-plugins-marketplace`). Skills become `/forgeloop:<name>`,
  agents `forgeloop:<agent>`.
- Layout: `skill/.claude/skills/<name>.md` → `skills/<name>/SKILL.md` (sub-files beside
  it), `skill/.claude/agents/` → `agents/`, CLAUDE/AGENTS templates → `templates/`.
  File references are relative to each skill's directory.
- Repo settings move to `.claude/forgeloop.md` (template: `templates/forgeloop.md`),
  read by every loop before Stage 0; plugin files stay read-only.
- `cluster-loop` node map is configurable (`FORGELOOP_CLUSTER_NODE_MAP`,
  `.claude/forgeloop.md`, default `~/.claude/forgeloop/cluster_node_map.md`) instead of
  a hard-coded personal path.
- `debugger.md` resolves `dap_client.py` via `${CLAUDE_PLUGIN_ROOT}` for plugin installs.
- `install.sh` copies the plugin layout into `.claude/` for non-plugin installs.
- New `tests/check-plugin.sh`: manifest validation, version agreement, skill/agent
  names, stale-layout scan, and resolution of every skill-relative file reference.

- Added **Stage A.5: Clean-Code Pass** to `implement-loop`, between the developer pass
  and the reviewer gate. New `refactorer` agent and `implement-loop/clean-code.md`,
  adapted from `code-simplification` (addyosmani/agent-skills, MIT) and
  `code-simplifier` (anthropics/claude-plugins-official). Behavior gate: test files
  byte-identical, full suite green with Stage A counts, coverage not lower; failing
  changes restored from a throwaway-index snapshot; separate feature/refactor patches.

- `implement-loop` Stage C is now a **Run-Proof Gate** instead of a Codex review:
  the task's `RUN_PROOF` command runs locally (CPU) or via `srun --jobid` inside a
  `cluster-loop` allocation (GPU), with working-tree sync checks and quoted log
  evidence per pass criterion. New `implement-loop/run-proof.md`.
- Tasks require a `RUN_PROOF` section; `plan-loop` and `debug-loop` handoffs must emit
  one, and `plan-loop` requirements validation asks for it.
- Removed the Codex gate (Stage 6b) and Codex model check from `plan-loop`, and the
  Codex model check from `implement-loop`. `debug-loop` keeps its Codex gate.
- Removed the unused `templates/codex-review-prompt.md`.
- Updated check scripts to assert the run-proof gate and the absence of Codex in
  `implement-loop` and `plan-loop`.

## 0.5.0

- Added `cluster-loop` workflow skill (v1: map + recommend + allocate + srun).
- Added `skill/.claude/skills/cluster-loop/` sub-files (preflight, allocation-map,
  node-recommender, allocate, srun-inside).
- Added `templates/cluster-loop-report.md` report template.
- Added `tests/check-cluster-loop-skill.sh` enforcement checks (20 assertions).
- Extended `cluster_node_map.md` with formalized schema (partition, auth_type,
  sshpass_required, last_known_status, last_surveyed).
- Updated README, CHANGELOG, CLAUDE.template.md.

## 0.4.0

- Added `codex-model-check.md`: sub-agent that verifies the current Codex CLI model
  at loop startup and stores it in `CODEX_MODEL`.
- Added Stage 0.1 (Codex Model Check) to `implement-loop`, `plan-loop`, and
  `debug-loop`.
- Replaced hard-coded `gpt-5.5` with `${CODEX_MODEL}` in all three
  `review-gates.md` files.
- Added `tests/check-codex-model-check.sh` (11 assertions).
- Updated `docs/codex-cli-setup.md` to document the model-check protocol.

## 0.3.0

- Added `debug-loop` workflow skill (v1: handoff-only).
- Added `skill/.claude/skills/debug-loop/` sub-files (symptom-validation,
  evidence-map, reproduction-gate, root-cause-trace, handoff-format, review-gates).
- Added `templates/debug-loop-report.md` report and handoff template.
- Added `tests/check-debug-loop-skill.sh` enforcement checks (29 assertions).
- Updated README, CHANGELOG, CLAUDE.template.md.

## 0.2.0

- Added `plan-loop` workflow skill.
- Added `skill/.claude/skills/plan-loop/` sub-files (requirements-validation,
  source-authority, plan-format, review-gates).
- Added `templates/plan-loop-plan.md` plan template.
- Added `tests/check-plan-loop-skill.sh` enforcement checks.
- Updated README, CLAUDE.template.md.

## 0.1.0

- Initial ForgeLoop extraction.
- Added `implement-loop` workflow.
- Added portable agents, templates, docs, and safe installer.

