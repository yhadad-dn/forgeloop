#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: install.sh [--dry-run] [--force] [target-dir]

Copies ForgeLoop's skills and agents into target-dir/.claude, plus the
CLAUDE/AGENTS/forgeloop.md templates. Existing files are not overwritten by default.

Prefer the plugin install when you use Claude Code:
  /plugin marketplace add yhadad-dn/forgeloop
  /plugin install forgeloop@forgeloop
USAGE
}

DRY_RUN=0
FORCE=0
TARGET="."

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --force) FORCE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) TARGET="$1"; shift ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DST="$TARGET/.claude"

# source|destination pairs, relative to ROOT and DST
list_files() {
  (cd "$ROOT" && find skills agents -type f -not -path '*/__pycache__/*' | sort) |
    while IFS= read -r rel; do echo "$rel|$rel"; done
  for t in CLAUDE.template.md AGENTS.template.md forgeloop.md; do
    echo "templates/$t|$t"
  done
}

while IFS='|' read -r src rel; do
  if [[ -e "$DST/$rel" && "$FORCE" -ne 1 ]]; then
    echo "Refusing to overwrite existing file: $DST/$rel" >&2
    echo "Re-run with --force after reviewing the diff, or install into a clean repo." >&2
    exit 1
  fi
done < <(list_files)

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Would copy:"
  list_files | while IFS='|' read -r src rel; do echo "  $DST/$rel"; done
  exit 0
fi

list_files | while IFS='|' read -r src rel; do
  mkdir -p "$(dirname "$DST/$rel")"
  cp "$ROOT/$src" "$DST/$rel"
done

echo "ForgeLoop installed into $DST"
echo "Next: edit .claude/forgeloop.md, then review .claude/AGENTS.template.md and .claude/CLAUDE.template.md"
