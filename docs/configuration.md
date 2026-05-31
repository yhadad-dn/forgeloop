# Configuration

ForgeLoop is strict by default. Adapt these before using it in a real repository:

| Setting | Where |
|---|---|
| Source-of-truth policy | `.claude/CLAUDE.template.md`, `source-check.md` |
| Forbidden generated paths | `.claude/AGENTS.template.md`, `review-gates.md` |
| Test commands | task plans and repo policy |
| Coverage threshold | `coverage-gate.md` |
| Codex command/model | `review-gates.md` |
| Reviewer focus | `.claude/agents/reviewer-*.md` |

Do not weaken a gate silently. If a team chooses not to use Codex or coverage tooling,
document the fallback and make it visible in convergence reports.

