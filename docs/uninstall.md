# Uninstall

## Plugin

```text
/plugin uninstall forgeloop@forgeloop
/plugin marketplace remove forgeloop
```

## Repo install

`install.sh` copies plain files under `.claude/`. Remove:

```text
.claude/skills/implement-loop/
.claude/skills/plan-loop/
.claude/skills/debug-loop/
.claude/skills/cluster-loop/
.claude/skills/codex-model-check/
.claude/agents/developer.md
.claude/agents/refactorer.md
.claude/agents/source-check.md
.claude/agents/reviewer-*.md
.claude/forgeloop.md
.claude/AGENTS.template.md
.claude/CLAUDE.template.md
```

If you edited the templates or `forgeloop.md` after install, review before deleting.
