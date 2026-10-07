---
name: tmux-session
description: >
  Lists, stops and ends the durable tmux sessions ForgeLoop starts on Remote-SSH hosts.
  `list` shows the sessions. `stop [name]` ends one after the user confirms its exact
  name. Only sessions whose name starts with fl- are touched. Invoke with:
  /forgeloop:tmux-session list, or /forgeloop:tmux-session stop [name]. `end-current`
  closes the session you are in at the end of a session. Also use when
  the user asks to stop, close, or find their durable tmux session.
---

# ForgeLoop tmux sessions

On a Remote-SSH host, ForgeLoop can run Claude inside a tmux session so it survives a
dropped connection or a closed VS Code window. Session names look like
`fl-<folder>-<YYYYmmdd>-<HHMMSS>`. The helper is `forgeloop_tmux.py`, next to this file.
Run it with:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/tmux-session/forgeloop_tmux.py" <command>
```

If `CLAUDE_PLUGIN_ROOT` is empty when you build the command, do not guess a path. Tell
the user to run the helper in their own terminal from the installed plugin directory,
then stop:

```bash
python3 ~/.claude/plugins/cache/forgeloop/forgeloop/<version>/skills/tmux-session/forgeloop_tmux.py list
```

## list

Run `python3 "${CLAUDE_PLUGIN_ROOT}/skills/tmux-session/forgeloop_tmux.py" list`. Show the names it prints. If it prints nothing, say there
are no ForgeLoop tmux sessions.

## stop [name]

1. Pick the name.
   - If the user gave a name, use it.
   - If not, and `$TMUX` is set, run `tmux display-message -p '#S'` to get the current
     session name. Never run it when `$TMUX` is unset.
   - If `$TMUX` is unset, run `list` and ask the user which session to stop.
2. Refuse any name that does not start with `fl-`. Say why and stop. The helper also
   refuses; never bypass it, and never run `tmux kill-session` yourself.
3. Ask the user to confirm the exact session name. Do not run `stop` before the user
   answers yes.
4. After the user confirms, run `python3 "${CLAUDE_PLUGIN_ROOT}/skills/tmux-session/forgeloop_tmux.py" stop <name>`.
5. Tell the user: the helper schedules the kill about 2 seconds later, so this answer
   arrives first, and this conversation ends right after if it is the current session.

## end-current

Used at the end of a session, after the summary file was written (the idle checkpoint and
an explicit "end session" both run it as the last action). Run
`python3 ~/.claude/forgeloop/forgeloop_tmux.py end-current` (the installed copy; setup adds
an allow rule for exactly this command). It acts only when `$TMUX` is set and
`tmux display-message -p '#S'` returns a name starting with `fl-`; it then schedules the
same 2-second delayed stop as `stop` and exits 0, with no confirmation. Otherwise it prints
`not in a ForgeLoop tmux session; nothing closed` and touches nothing. Never run
`tmux kill-session` yourself.

## Attach and resume

- Attach to a session from any terminal: `tmux attach -t <name>`.
- If the tmux server stops (for example the VM reboots or sleeps), the conversation can
  be resumed for about four hours. Run `claude remote-control --continue` alone. Do not
  combine it with `--spawn`.
