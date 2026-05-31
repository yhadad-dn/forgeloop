# Project Agent Policy

Copy this file to `.claude/AGENTS.md` in a target repo and adapt it.

## Core Rules

- Repo source files and official specs are source of truth.
- Keep changes minimal and traceable to the task.
- Verify before declaring done.
- Do not edit generated result artifacts by hand.
- Ask when requirements conflict.

## Routing

| Task | Route |
|---|---|
| Implement/fix code | `/implement-loop` |
| Plan a larger change | your planning workflow |
| Review a finished diff | reviewer agents |
| Improve coverage | tester agent |

## Repo-Specific Forbidden Paths

Fill this in for your project:

- `<generated-results-dir>/`
- `<large-artifact-dir>/`
- `dist/`
- generated lock/output artifacts that should not be hand-edited
