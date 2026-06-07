# Changelog

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

