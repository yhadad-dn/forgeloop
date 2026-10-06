# Durable Sessions (VS Code over Remote-SSH)

A Claude Code session started from the VS Code extension is owned by the VS Code server.
When your laptop closes and the connection is cleaned up, that session dies. On a
Remote-SSH VM, ForgeLoop can instead start the session as a Remote Control server inside
a detached tmux session (`fl-<folder>-<time>`), which keeps running without your laptop.

## What you get, and what you do not

- The panel becomes a **launcher**: your first message is answered with the session name,
  the claude.ai/code link, the `tmux attach` command and the stop command. You continue
  in claude.ai/code or inside tmux. The VS Code panel does not re-attach to the session.
- The session survives a closed lid, a dropped connection and a closed VS Code window.
- It does **not** survive a VM reboot or sleep.
- If the server stops (for example after about 10 minutes without network), run
  `claude remote-control --continue` alone in the project folder; it resumes for about
  four hours. Do not add `--spawn` to `--continue`.
- Remote Control needs a Pro, Max, Team or Enterprise login (no API key) and Claude Code
  2.1.200 or later. Otherwise the wrapper runs a normal session and prints one warning.

## What was measured

A spike on a real Remote-SSH VM established these facts:

- The extension honors `claudeCode.claudeProcessWrapper` set at machine scope.
- `claude auth status` calls go through the wrapper too, so the wrapper passes them through.
- A session start is recognized by `--input-format stream-json` in the arguments.
- The panel talks to the process over stdio in stream-json, which the launcher answers.

## Limits and risks

- The durable session starts with your default permission mode. It does not carry the
  flags the VS Code extension would have set.
- Anyone with access to the signed-in claude.ai account can drive the session.
- A conversation you reopen (`--resume`, `-r`, `--continue`, `-c`) stays a normal,
  non-durable session; the wrapper passes it through unchanged.
  The same applies if the extension's argv contains any resume-like flag (for example an
  extra argument `-c`): the wrapper passes the call through unchanged, with no durable session.
- NOT VERIFIED: that slash commands such as `/forgeloop:tmux-session` work from
  claude.ai/code. Stopping also works from `tmux attach` (end the session there).
- The wrapper writes its files with private permissions. Setup warns when
  `~/.claude/forgeloop` or the copies in it are group/world-writable or not owned by you.

## Turn it on (once per VM)

Run `/forgeloop:setup --durable` (or `python3 skills/setup/forgeloop_setup.py plan --durable`
then `apply --durable`). It shows the diff and asks first. It copies the wrapper and its
helper to `~/.claude/forgeloop/` and sets `claudeCode.claudeProcessWrapper` in
`~/.vscode-server/data/Machine/settings.json`. If that file has comments, setup prints the
one line to add by hand and changes nothing in it. Reload the VS Code window afterwards.

Durable sessions need the plugin install: `scripts/install.sh` does not ship `scripts/`, so
there setup reports the durable items as `unknown` and writes nothing. Re-run
`/forgeloop:setup --durable` after each plugin upgrade; the installed copy in
`~/.claude/forgeloop/` is not refreshed automatically, and `--check` reports it as pending.
Setup exits 2 when `~/.claude/settings.json` is broken, even if the durable items applied.

The wrapper is used by every VS Code window on the VM. It passes every call through
unchanged (for example `claude auth status --json`) except a real session start, and it
only acts when `SSH_CONNECTION` is set and no container marker (`REMOTE_CONTAINERS`,
`CODESPACES`, `WSL_DISTRO_NAME`, `/.dockerenv`) is present. On such other remote hosts a
session hint asks whether to enable it; the answer is stored in
`~/.claude/forgeloop/durable` (`yes` or `no`).

## Stop a session

Run `/forgeloop:tmux-session stop` inside the session (it asks to confirm the name, then
the session ends about two seconds after the reply). `/forgeloop:tmux-session list` shows
the `fl-*` sessions. Only sessions whose name starts with `fl-` can be stopped this way.
From a terminal: `tmux attach -t <name>`, or `python3 skills/tmux-session/forgeloop_tmux.py stop <name>`.

## Switch off or undo

- `FORGELOOP_DURABLE=off` (also `0`, `false`, `no`, any case) in the environment: the wrapper runs `claude` unchanged.
- Delete the `claudeCode.claudeProcessWrapper` key from the machine settings file.
- The last launcher text is kept in `~/.claude/forgeloop/last-durable-session.txt`.

## Terminal and manual use

`scripts/claude-tmux.sh [session] [-- claude args]` starts or re-attaches a tmux session
running a normal `claude` in a terminal. It does not use Remote Control.
