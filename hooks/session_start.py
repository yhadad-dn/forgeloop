#!/usr/bin/env python3
"""SessionStart hook: inject ForgeLoop conventions into the session context.

Layers, later wins on conflict:
  1. the plugin's conventions.md (team default)
  2. ~/.claude/forgeloop/conventions.md (personal)
  3. the "## Conventions" section of <project>/.claude/forgeloop.md (repo)
Set FORGELOOP_CONVENTIONS=off to disable.

Setup hint: on the first session after each ForgeLoop version, the hook checks (read only)
whether /forgeloop:setup has anything to apply and, if so, adds one line to the context.
It never writes settings.json; it writes only ~/.claude/forgeloop/setup-stamp.
Set FORGELOOP_SETUP_HINT=off to disable.

Answer style (ON by default): the plugin's styles/ste.md (ASD-STE100) is added after the
team layer. Precedence: a non-empty FORGELOOP_STYLE wins ("ste" is on, any other value such
as off, 0, false or no is off); else the first line of ~/.claude/forgeloop/style ("ste" is
on, any other non-empty value is off); else (no env, no file, or an empty file) it is on.
Turn it off with FORGELOOP_STYLE=off or a style file that contains "off".

Durable-session question: ForgeLoop supports Remote-SSH hosts by default. On a different
kind of remote host (container, WSL, Codespaces; forgeloop_tmux.classify_host says
other_remote) with no ~/.claude/forgeloop/durable file, the hook adds one line telling
Claude to ask the user and to record yes or no in that file. The hook never writes it.
Set FORGELOOP_DURABLE=off to disable. Any error adds nothing.
"""

import importlib.util
import json
import os
import re
import sys
from pathlib import Path

HEADER = ("The ForgeLoop plugin is installed. Follow these conventions in this session. "
          "Where layers disagree, later layers override earlier ones.\n\n")


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def style_layer(root: Path) -> str:
    name = os.environ.get("FORGELOOP_STYLE", "").strip().lower()
    if not name:
        lines = read(Path.home() / ".claude" / "forgeloop" / "style").splitlines()
        name = lines[0].strip().lower() if lines else ""
    if name and name != "ste":
        return ""
    return read(root / "styles" / "ste.md")


SETUP_HINT = "ForgeLoop: settings need a one-time check. Run /forgeloop:setup."
OFF = ("off", "0", "false", "no")


def setup_hint(root: Path, home: Path) -> str:
    """Return the one-line hint, or '' (nothing pending, already shown for this version,
    FORGELOOP_SETUP_HINT=off, or any error). Writes only ~/.claude/forgeloop/setup-stamp."""
    try:
        if os.environ.get("FORGELOOP_SETUP_HINT", "").strip().lower() in OFF:
            return ""
        version = str(json.loads(read(root / ".claude-plugin" / "plugin.json"))["version"])
        stamp = home / ".claude" / "forgeloop" / "setup-stamp"
        if read(stamp) == version:
            return ""
        path = root / "skills" / "setup" / "forgeloop_setup.py"
        spec = importlib.util.spec_from_file_location("forgeloop_setup", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["forgeloop_setup"] = mod
        spec.loader.exec_module(mod)
        cli = mod.detect_cli_version(timeout=2.0)
        if cli is None:
            return ""
        settings, err = mod.load_settings(str(home / ".claude" / "settings.json"))
        if settings is None:
            return ""
        pending = any(c.status == "pending" for c in mod.compute_changes(settings, str(home), cli, False, mod.default_durable(str(home))))
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(version + "\n", encoding="utf-8")
        return SETUP_HINT if pending else ""
    except Exception:
        return ""


DURABLE_LINE = ("ForgeLoop supports Remote-SSH hosts by default, but this looks like a different kind "
                "of remote host. Ask the user whether to enable durable (tmux) sessions on this kind "
                "of host, then write `yes` or `no` into ~/.claude/forgeloop/durable with the answer "
                "(Claude writes this file at the user's request).")


def durable_line(root: Path, home: Path) -> str:
    """Return the one-line question, or '' (not other_remote, answer file exists,
    FORGELOOP_DURABLE=off, or any error). Never writes."""
    try:
        if os.environ.get("FORGELOOP_DURABLE", "").strip().lower() in OFF:
            return ""
        if (home / ".claude" / "forgeloop" / "durable").exists():
            return ""
        path = root / "skills" / "tmux-session" / "forgeloop_tmux.py"
        spec = importlib.util.spec_from_file_location("forgeloop_tmux", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["forgeloop_tmux"] = mod
        spec.loader.exec_module(mod)
        return DURABLE_LINE if mod.classify_host(os.environ, os.path.exists) == "other_remote" else ""
    except Exception:
        return ""


def repo_section(text: str) -> str:
    m = re.search(r"^## Conventions\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1).strip() if m else ""


def main() -> int:
    if os.environ.get("FORGELOOP_CONVENTIONS", "").lower() in OFF:
        return 0
    root = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", Path(__file__).resolve().parents[1]))
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        event = {}
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd())

    layers = []
    team = read(root / "conventions.md")
    if team:
        layers.append(team.replace("{CLUSTER_STATUS}", str(root / "skills" / "cluster-loop" / "cluster_status.py")))
    style = style_layer(root)
    if style:
        layers.append(style)
    personal = read(Path.home() / ".claude" / "forgeloop" / "conventions.md")
    if personal:
        layers.append("## Personal conventions (override the above)\n\n" + personal)
    repo = repo_section(read(project / ".claude" / "forgeloop.md"))
    if repo:
        layers.append("## Repo conventions (override the above)\n\n" + repo)
    extras = [x for x in (setup_hint(root, Path.home()), durable_line(root, Path.home())) if x]
    if not layers and not extras:
        return 0

    tail = "".join("\n\n" + x for x in extras)
    context = (HEADER + "\n\n".join(layers) + tail) if layers else "\n\n".join(extras)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                             "additionalContext": context}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
