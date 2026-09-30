# Changelog

## 0.6.0

- **ForgeLoop is now a Claude Code plugin.** `.claude-plugin/plugin.json` plus a
  single-plugin `marketplace.json` at the repo root:
  `/plugin marketplace add yhadad-dn/forgeloop`, `/plugin install forgeloop@forgeloop`.
  Skills become `/forgeloop:<name>`, agents `forgeloop:<agent>`.
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

