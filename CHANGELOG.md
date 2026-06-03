# Changelog

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

