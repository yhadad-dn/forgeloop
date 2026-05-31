# Contributing

ForgeLoop workflows should stay portable.

Before opening a change:

- remove project-specific paths, names, cluster details, or credentials;
- keep skills in plain Markdown;
- add examples or docs for new workflow behavior;
- keep default behavior strict and safe;
- update the README when install or policy changes.

For new workflow skills, follow the pattern:

```text
skill/.claude/skills/<name>.md
skill/.claude/skills/<name>/*.md
docs/<name>.md
examples/<name>-example.md
```

