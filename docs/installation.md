# Installation

## As a Claude Code plugin (recommended)

In Claude Code:

```text
/plugin marketplace add yhadad-dn/forgeloop
/plugin install forgeloop@forgeloop
```

Skills are then available as `/forgeloop:plan-loop`, `/forgeloop:implement-loop`,
`/forgeloop:debug-loop`, `/forgeloop:cluster-loop`, and `/forgeloop:codex-model-check`.
Agents are named `forgeloop:developer`, `forgeloop:refactorer`, `forgeloop:reviewer-*`,
and so on. Update with `/plugin update forgeloop@forgeloop`.

For a local checkout (development), point the marketplace at the directory:

```text
/plugin marketplace add /path/to/forgeloop
/plugin install forgeloop@forgeloop
```

Then configure each repo you use it in:

```bash
mkdir -p .claude
cp /path/to/forgeloop/templates/forgeloop.md .claude/forgeloop.md   # edit it
```

## Into a repo's `.claude/` (no plugin; also for Codex)

```bash
git clone https://github.com/yhadad-dn/forgeloop.git /tmp/forgeloop
/tmp/forgeloop/scripts/install.sh .
```

This copies `skills/` and `agents/` into `.claude/`, plus `forgeloop.md`,
`AGENTS.template.md`, and `CLAUDE.template.md`. Skills are then `/plan-loop`,
`/implement-loop`, and so on, without the `forgeloop:` prefix.

Review and adapt:

- `.claude/forgeloop.md` — test commands, coverage threshold, forbidden paths, cluster
  settings;
- `.claude/AGENTS.template.md` and `.claude/CLAUDE.template.md`;
- source-of-truth documents.

Do not use both install methods for the same user or repo: the unprefixed copies and
the plugin would both be offered.
