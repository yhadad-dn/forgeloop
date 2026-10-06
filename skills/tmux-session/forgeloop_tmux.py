#!/usr/bin/env python3
"""Durable tmux session helpers for ForgeLoop (stdlib only)."""

import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime
from typing import Callable, Mapping

PREFIX = "fl-"
CONTAINER_MARKERS = ("REMOTE_CONTAINERS", "CODESPACES", "WSL_DISTRO_NAME")


def classify_host(env: Mapping[str, str], exists: Callable[[str], bool], allow_other: bool = False) -> str:
    """Return 'local', 'remote_ssh' or 'other_remote'; allow_other maps other_remote to remote_ssh."""
    if not env.get("SSH_CONNECTION"):
        return "local"
    marker = any(env.get(m) for m in CONTAINER_MARKERS) or exists("/.dockerenv")
    if marker and not allow_other:
        return "other_remote"
    return "remote_ssh"


def session_name(cwd: str, now: datetime) -> str:
    base = os.path.basename(cwd.rstrip("/")).lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    stamp = now.strftime("%Y%m%d-%H%M%S")
    return f"{PREFIX}{base}-{stamp}" if base else f"{PREFIX}{stamp}"


def _out(stdout, obj) -> None:
    stdout.write(json.dumps(obj) + "\n")
    stdout.flush()


def launcher_reply(text: str, stdin, stdout) -> None:
    sid = "forgeloop-launcher"
    inited = False
    turn = 0
    try:
        for line in stdin:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue
            kind = msg.get("type")
            if kind == "control_request":
                _out(stdout, {"type": "control_response", "response": {
                    "subtype": "success", "request_id": msg.get("request_id"), "response": {}}})
            elif kind == "user":
                turn += 1
                if not inited:
                    _out(stdout, {"type": "system", "subtype": "init", "session_id": sid, "cwd": ".",
                                  "tools": [], "mcp_servers": [], "model": "forgeloop-launcher",
                                  "permissionMode": "default", "apiKeySource": "none",
                                  "slash_commands": []})
                    inited = True
                _out(stdout, {"type": "assistant", "session_id": sid, "parent_tool_use_id": None,
                              "uuid": str(uuid.uuid4()),
                              "message": {"id": f"msg{turn}", "type": "message", "role": "assistant",
                                          "model": "forgeloop-launcher",
                                          "content": [{"type": "text", "text": text}],
                                          "stop_reason": "end_turn",
                                          "usage": {"input_tokens": 0, "output_tokens": 0}}})
                _out(stdout, {"type": "result", "subtype": "success", "is_error": False,
                              "duration_ms": 1, "duration_api_ms": 0, "num_turns": 1, "result": text,
                              "session_id": sid, "total_cost_usd": 0, "uuid": str(uuid.uuid4()),
                              "usage": {"input_tokens": 0, "output_tokens": 0}})
    except BrokenPipeError:
        return


def is_forgeloop_session(name: str) -> bool:
    return re.fullmatch(r"fl-[a-z0-9][a-z0-9-]*", name) is not None


def list_sessions(run: Callable) -> list:
    try:
        res = run(["tmux", "ls", "-F", "#S"], capture_output=True, text=True)
    except OSError:
        return []
    if res.returncode != 0:
        return []
    return [n for n in res.stdout.splitlines() if is_forgeloop_session(n)]


def stop_session(name: str, run: Callable, delay: int = 2) -> int:
    if not is_forgeloop_session(name):
        return 2
    try:
        if run(["tmux", "has-session", "-t", f"={name}"]).returncode != 0:
            return 1
        res = run(["tmux", "run-shell", "-b", f"sleep {delay}; tmux kill-session -t ={name}"])
    except OSError:
        return 1
    return 0 if res.returncode == 0 else 1


def _allow_other() -> bool:
    path = os.path.join(os.path.expanduser("~"), ".claude", "forgeloop", "durable")
    try:
        with open(path) as f:
            return f.readline().strip() == "yes"
    except OSError:
        return False


def main(argv: list) -> int:
    if not argv:
        print("usage: forgeloop_tmux.py classify|name <cwd>|list|stop <name>|launcher <file>",
              file=sys.stderr)
        return 2
    cmd, args = argv[0], argv[1:]
    if cmd == "classify":
        print(classify_host(os.environ, os.path.exists, _allow_other()))
        return 0
    if cmd == "name" and len(args) == 1:
        print(session_name(args[0], datetime.now()))
        return 0
    if cmd == "list":
        for n in list_sessions(subprocess.run):
            print(n)
        return 0
    if cmd == "stop" and len(args) == 1:
        rc = stop_session(args[0], subprocess.run)
        if rc == 2:
            print(f"refusing to stop non-forgeloop session: {args[0]}", file=sys.stderr)
        return rc
    if cmd == "launcher" and len(args) == 1:
        with open(args[0]) as f:
            text = f.read().rstrip("\n")
        launcher_reply(text, sys.stdin, sys.stdout)
        return 0
    print(f"unknown command or arguments: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
