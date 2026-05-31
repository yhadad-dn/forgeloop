# Installation

From a target repository:

```bash
git clone https://github.com/<your-user>/forgeloop.git /tmp/forgeloop
/tmp/forgeloop/scripts/install.sh .
```

This copies `skill/.claude/` into the target repo's `.claude/` directory.

Review and adapt:

- `.claude/AGENTS.template.md`
- `.claude/CLAUDE.template.md`
- forbidden generated artifact paths;
- test commands;
- source-of-truth documents.

