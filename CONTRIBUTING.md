# Contributing

ForgeLoop workflows should stay portable.

Before opening a change:

- remove project-specific paths, names, cluster details, or credentials;
- keep skills in plain Markdown;
- reference files relative to the skill's directory (`../<skill>/<file>` for siblings),
  never by install location;
- put repo-specific settings in `templates/forgeloop.md`, not in skill files;
- bump the version in `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`,
  and `CHANGELOG.md` together;
- run `tests/check-*.sh` (including `check-plugin.sh`) before pushing;
- add examples or docs for new workflow behavior;
- keep default behavior strict and safe;
- update the README when install or policy changes.

For new workflow skills, follow the pattern:

```text
skills/<name>/SKILL.md
skills/<name>/*.md
docs/<name>.md
examples/<name>-example.md
```

