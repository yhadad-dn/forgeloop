#!/usr/bin/env python3
"""SessionStart hook: inject ForgeLoop conventions into the session context.

Layers, later wins on conflict:
  1. the plugin's conventions.md (team default)
  2. ~/.claude/forgeloop/conventions.md (personal)
  3. the "## Conventions" section of <project>/.claude/forgeloop.md (repo)
Set FORGELOOP_CONVENTIONS=off to disable.

Optional answer style: when FORGELOOP_STYLE=ste, or the first line of
~/.claude/forgeloop/style is "ste", the plugin's styles/ste.md (ASD-STE100) is added
after the team layer. Any other value, or no setting, adds nothing.
"""

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
    return read(root / "styles" / "ste.md") if name == "ste" else ""


def repo_section(text: str) -> str:
    m = re.search(r"^## Conventions\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1).strip() if m else ""


def main() -> int:
    if os.environ.get("FORGELOOP_CONVENTIONS", "").lower() in ("off", "0", "false", "no"):
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
    if not layers:
        return 0

    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                             "additionalContext": HEADER + "\n\n".join(layers)}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
