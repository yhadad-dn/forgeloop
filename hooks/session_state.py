#!/usr/bin/env python3
"""Saved-session helper: list, consume (load then remove) and delete session summaries.

Library for hooks/session_picker.py and a small CLI the model runs for the picker:
  python3 session_state.py list    --dir <project>/.claude [--keep <id>]
  python3 session_state.py consume --dir <project>/.claude [--keep <id>] <key>
  python3 session_state.py delete  --dir <project>/.claude [--keep <id>] <key>...

A key is the text between "session_state_" and ".md" and must match [A-Za-z0-9_-]{1,64}.
The helper builds the path itself (never takes a path or glob), refuses symlinks and
anything that is not a regular file, refuses the current session's key (--keep), and
refuses any --dir that is not named ".claude". An allow rule for this script matches any
arguments, so these checks are the only limit on what it can delete.
Exit codes: 0 success, 1 file missing or unreadable, 2 bad usage or bad key,
3 consume printed the file but could not remove it.
"""

import errno
import os
import re
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

KEY_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
PREFIX, SUFFIX = "session_state_", ".md"
ID_RE = re.compile(r"\b[0-9a-f]{8}\b")
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
NAME_MAX, SUMMARY_MAX = 60, 200


@dataclass(frozen=True)
class Session:
    key: str            # text between "session_state_" and ".md"
    path: Path
    name: str           # exact Name: line, or a derived fallback
    name_derived: bool  # True when there was no Name: line
    summary: str
    mtime: float


def human_age(mtime: float, now: float | None = None) -> str:
    seconds = (time.time() if now is None else now) - mtime
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h ago"
    return f"{seconds / 86400:.1f}d ago"


def first_sentence(text: str, limit: int = 140) -> str:
    text = re.sub(r"^[-*\s]+", "", text.strip())
    text = re.sub(r"^[A-Za-z /]{1,24}:\s+(?=[A-Z`])", "", text)  # drop a leading "Label: "
    match = re.search(r"(?<=[.!?])\s", text)
    text = text[: match.start()] if match else text
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def sanitize(text: str, limit: int) -> str:
    """Untrusted-file text made safe to show: no control or non-printable characters, no
    `[`, `]` or backtick, at most `limit` characters (ellipsis when cut)."""
    text = "".join(c for c in text if c.isprintable() and c not in "[]`").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def describe(path: Path) -> tuple[str, str, bool]:
    """(name, one-sentence summary, name_derived) of a state file; never the session ID.

    Preferred: `Name:` and `Summary:` lines at the top of the file. Fallback for older
    files: the heading minus ID/date/boilerplate, and the first content line.
    """
    try:
        lines = [l.strip() for l in path.read_text(encoding="utf-8").splitlines()]
    except (OSError, ValueError):
        return "Unnamed session", "(unreadable)", True

    def field(label: str) -> str:
        for line in lines[:12]:
            if line.lower().startswith(label.lower() + ":"):
                return line.split(":", 1)[1].strip()
        return ""

    name, summary = field("Name"), field("Summary")
    derived = not name
    if not summary:
        for line in lines:
            if line and not line.startswith("#") and not line.lower().startswith("name:"):
                summary = first_sentence(line)
                break
    if not name:
        heading = next((l.lstrip("# ").strip() for l in lines if l.startswith("#")), "")
        heading = ID_RE.sub("", DATE_RE.sub("", heading))
        heading = re.sub(r"(?i)\bsession\b|\bstate\b|written manually", "", heading)
        heading = re.sub(r"[()—–\-,:]+", " ", heading)
        name = " ".join(heading.split())
    if not name:
        name = " ".join(summary.split()[:6]) or "Unnamed session"
    return (sanitize(name, NAME_MAX) or "Unnamed session",
            sanitize(summary, SUMMARY_MAX) or "(no summary yet)", derived)


def list_sessions(state_dir: Path, keep: str = "") -> list[Session]:
    """Regular session files with a valid key, newest first; the `keep` key is skipped."""
    found = []
    try:
        candidates = list(state_dir.glob(f"{PREFIX}*{SUFFIX}"))
    except OSError:
        return []
    for p in candidates:
        key = p.name[len(PREFIX):-len(SUFFIX)]
        try:
            if key == keep or not KEY_RE.match(key) or p.is_symlink() or not p.is_file():
                continue
            mtime = p.stat().st_mtime
        except OSError:
            continue
        name, summary, derived = describe(p)
        found.append(Session(key, p, name, derived, summary, mtime))
    return sorted(found, key=lambda s: s.mtime, reverse=True)


def resolve(state_dir: Path, key: str) -> Path:
    """Path of the key's file. ValueError on a bad key, a symlink or a non-file.
    A file that does not exist is not an error here; callers see it as exit 1."""
    if not KEY_RE.match(key):
        raise ValueError(f"bad session key: {key!r}")
    path = state_dir / f"{PREFIX}{key}{SUFFIX}"
    if path.is_symlink():
        raise ValueError("refusing a symlink")
    if path.exists() and not path.is_file():
        raise ValueError("refusing a non-regular file")
    return path


def consume(state_dir: Path, key: str, out: TextIO, keep: str = "") -> int:
    """Print the file's content, flush, then remove it. A failed read keeps the file."""
    try:
        if key == keep:
            raise ValueError("refusing the current session")
        path = resolve(state_dir, key)
    except ValueError as e:
        print(f"session_state: {e}", file=sys.stderr)
        return 2
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as e:
        print(f"session_state: cannot read session: {e}", file=sys.stderr)
        return 2 if e.errno == errno.ELOOP else 1
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            print("session_state: refusing a non-regular file", file=sys.stderr)
            return 2
        with os.fdopen(fd, "rb", closefd=False) as f:
            text = f.read().decode("utf-8")
    except (OSError, ValueError) as e:
        print(f"session_state: cannot read session: {e}", file=sys.stderr)
        return 1
    finally:
        os.close(fd)
    out.write(text)
    out.flush()
    try:
        path.unlink()
    except OSError as e:
        print(f"session_state: loaded but not removed: {e}", file=sys.stderr)
        return 3
    return 0


def delete(state_dir: Path, keys: list[str], keep: str = "") -> int:
    """Remove each named file. Any bad key means nothing is removed (2)."""
    try:
        if not keys or keep in keys:
            raise ValueError("no keys, or the current session")
        paths = [resolve(state_dir, k) for k in dict.fromkeys(keys)]
    except ValueError as e:
        print(f"session_state: {e}", file=sys.stderr)
        return 2
    status = 0
    for path in paths:
        try:
            path.unlink()
        except OSError as e:
            print(f"session_state: cannot remove session: {e}", file=sys.stderr)
            status = 1
    return status


def main(argv: list[str]) -> int:
    usage = "usage: session_state.py list|consume|delete --dir <project>/.claude [--keep <id>] [key...]"
    if not argv or argv[0] not in ("list", "consume", "delete"):
        print(usage, file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    state_dir, keep, keys = None, "", []
    i = 0
    while i < len(rest):
        if rest[i] in ("--dir", "--keep") and i + 1 < len(rest):
            if rest[i] == "--dir":
                state_dir = Path(rest[i + 1])
            else:
                keep = rest[i + 1]
            i += 2
        else:
            keys.append(rest[i])
            i += 1
    if state_dir is None or state_dir.name != ".claude":
        print(usage + "\n--dir must name a directory called .claude", file=sys.stderr)
        return 2
    if cmd == "list":
        for s in list_sessions(state_dir, keep):
            print(f"{s.key}\t{s.name}\t{human_age(s.mtime)}\t{s.summary}")
        return 0
    if cmd == "consume":
        if len(keys) != 1:
            print(usage, file=sys.stderr)
            return 2
        return consume(state_dir, keys[0], sys.stdout, keep)
    return delete(state_dir, keys, keep)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:  # never traceback at the model
        print(f"session_state: {e}", file=sys.stderr)
        sys.exit(2)
