#!/usr/bin/env python3
"""SessionStart hook: refresh the cost heat map in the background, with no budget.

Rebuilds ~/.claude/forgeloop/cost-heatmap/cost-heatmap.html from local Claude Code and
Codex transcripts. Skips when the page is under an hour old or another refresh holds the
lock. Prints nothing and never blocks the session (the build takes ~20s, so it runs
detached). Set FORGELOOP_COST_HEATMAP=off to disable.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

MAX_AGE = 3600
LOCK_STALE = 600


def main() -> int:
    if os.environ.get("FORGELOOP_COST_HEATMAP", "").lower() in ("off", "0", "false", "no"):
        return 0
    root = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", Path(__file__).resolve().parents[1]))
    script = root / "skills" / "cost-heatmap" / "cost_heatmap.py"
    out = Path.home() / ".claude" / "forgeloop" / "cost-heatmap"
    now = time.time()
    try:
        if not script.is_file():
            return 0
        out.mkdir(parents=True, exist_ok=True)
        page = out / "cost-heatmap.html"
        if page.is_file() and now - page.stat().st_mtime < MAX_AGE:
            return 0
        lock = out / ".refresh.lock"
        if lock.is_file() and now - lock.stat().st_mtime < LOCK_STALE:
            return 0
        lock.write_text(str(os.getpid()))
        with open(out / "refresh.log", "w") as log:
            subprocess.Popen(
                ["sh", "-c", 'python3 "$0" --dir "$1"; rm -f "$1/.refresh.lock"', str(script), str(out)],
                stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
