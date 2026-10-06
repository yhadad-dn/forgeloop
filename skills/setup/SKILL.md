---
name: setup
description: >
  Checks and applies the few user settings ForgeLoop can use: the plugin entries, the
  env flag the cost band needs on Claude Code older than 2.1.287, and the optional STE
  answer style. Shows the exact changes, asks for approval, then writes with a backup.
  Invoke with: /forgeloop:setup (or /forgeloop:setup --check). Also use when the session
  says "ForgeLoop: settings need a one-time check".
---

# ForgeLoop Setup

ForgeLoop works without any settings change. This skill only adds the optional entries
below, and only after the user approves the exact diff. It writes user scope only
(`~/.claude/settings.json` and `~/.claude/forgeloop/style`), never project or managed
settings. Only with `--durable` it writes two more locations: the VS Code remote machine
settings file (`~/.vscode-server/data/Machine/settings.json`) and the copies
`~/.claude/forgeloop/vscode-wrapper.sh` and `~/.claude/forgeloop/forgeloop_tmux.py`. The helper is `forgeloop_setup.py`, next to this file. Run it with:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/setup/forgeloop_setup.py" <command>
```

If `CLAUDE_PLUGIN_ROOT` is empty when you build the command, do not guess a relative
path. Tell the user to run the script in their own terminal from the installed plugin
directory, then stop:

```bash
python3 ~/.claude/plugins/cache/forgeloop/forgeloop/<version>/skills/setup/forgeloop_setup.py plan
```

A clone the user trusts also works. A copy inside a repo (`.claude/skills/setup/`) runs
that repo's code: only run it if the user confirms they trust that repo's copy.

## Items

| Item | Set when |
|------|----------|
| `env.CLAUDE_CODE_ENABLE_FUNCTION_HOOKS="1"` | the CLI version is below 2.1.287 and the key is absent |
| `~/.claude/forgeloop/style` with `ste` | only if the user opts in (`--ste`) |
| `extraKnownMarketplaces.forgeloop` and `enabledPlugins["forgeloop@forgeloop"]` | absent; an existing value (even `false`) is never changed. An existing `forgeloop@<any-marketplace>` install is detected and not duplicated |
| `claudeCode.claudeProcessWrapper` in the machine settings file, plus the wrapper and helper copied to `~/.claude/forgeloop/` | only if the user opts in (`--durable`) and the key is absent. A different existing value is never overwritten; it is reported as `unknown` with the manual line. A machine file with comments (not strict JSON) is left byte-identical and only this item is skipped. A broken `~/.claude/settings.json` does not block it, and the reverse |

Durable sessions need the plugin install: `scripts/install.sh` does not ship `scripts/`, so on that layout the durable items are reported `unknown` and nothing is written. Re-run `/forgeloop:setup --durable` after each plugin upgrade; the installed copy is not refreshed automatically (`--check` reports it).

Warning to show with the durable question: once set, every VS Code window on this VM
uses the wrapper. It passes everything through unchanged except a real Claude session
start. To undo it, delete the `claudeCode.claudeProcessWrapper` key from the machine
settings file, or set `FORGELOOP_DURABLE=off`.

## Steps

1. If the user passed `--check`, run the command with `--check`, show its lines, and
   stop. It writes nothing. Exit 1 means something is pending.
2. Run `plan`. It prints the exact diff and the team snippet. Show the diff to the user
   unchanged. If it exits 2, the settings file is not strict JSON: show the manual lines
   it printed and stop. Nothing was changed.
3. If nothing is pending, say so and stop.
4. Ask the user for approval to apply the diff. Ask separately whether to turn on the
   ASD-STE100 answer style (default no). Also ask separately whether to enable durable
   VS Code sessions (default no) and show the warning above.
5. After approval, run `apply`, adding `--ste` and `--durable` only if the user opted in (pass `--durable` to `plan` and `--check` too). Show the
   backup path it prints. Then run `--check` and report the result.

## If the write is denied

If the permission system denies the Bash call, print this one line for the user to run in
their own terminal, then stop. Never retry a denied write by another route (no Edit,
no Write, no redirect, no other interpreter):

```bash
python3 "<plugin path>/skills/setup/forgeloop_setup.py" apply
```

## Team rollout

`plan` also prints the JSON for a repo's `.claude/settings.json`. It is printed only;
this skill never writes project or managed settings.
