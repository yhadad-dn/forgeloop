# Configuration

ForgeLoop is strict by default. Put repo-specific values in `.claude/forgeloop.md`
(start from `templates/forgeloop.md`); the skills read it before Stage 0 and it
overrides their defaults. Plugin files are read-only, so do not edit the installed
skills themselves.

Adapt these before using it in a real repository:

| Setting | Where |
|---|---|
| Source-of-truth policy | `.claude/CLAUDE.template.md`, `source-check.md` |
| Forbidden generated paths | `.claude/forgeloop.md` (`forbidden_paths`), `.claude/AGENTS.template.md` |
| Test commands | task plans and repo policy |
| Coverage threshold | `.claude/forgeloop.md` (`coverage_threshold`) |
| Run-proof command and pass criteria | `RUN_PROOF` in each task file; protocol in `implement-loop/run-proof.md` |
| Codex command/model (`debug-loop`) | `debug-loop/review-gates.md` |
| Reviewer focus | `.claude/agents/reviewer-*.md` |

Do not weaken a gate silently. If a team chooses not to use Codex or coverage tooling,
document the fallback and make it visible in convergence reports.

