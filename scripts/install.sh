#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: install.sh [--dry-run] [--force] [target-dir]

Copies ForgeLoop's installable .claude payload into target-dir/.claude.
By default, existing files are not overwritten.
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
SRC="$ROOT/skill/.claude"
DST="$TARGET/.claude"

while IFS= read -r src_file; do
  rel="${src_file#$SRC/}"
  dst_file="$DST/$rel"
  if [[ -e "$dst_file" && "$FORCE" -ne 1 ]]; then
    echo "Refusing to overwrite existing file: $dst_file" >&2
    echo "Re-run with --force after reviewing the diff, or install into a clean repo." >&2
    exit 1
  fi
done < <(find "$SRC" -type f | sort)

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Would copy:"
  find "$SRC" -type f | sort | sed "s#^$SRC/#  $DST/#"
  exit 0
fi

mkdir -p "$DST"
cp -R "$SRC/." "$DST/"

echo "ForgeLoop installed into $DST"
echo "Next: review .claude/AGENTS.template.md and .claude/CLAUDE.template.md"
