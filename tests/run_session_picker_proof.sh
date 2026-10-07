#!/usr/bin/env bash
# Run proof for the session picker: temp project with 3 fixture sessions, run the hook,
# then run the exact consume and delete commands it printed.
# Run from anywhere; uses only a temp dir, never real session files.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/proj/.claude"
S="$TMP/proj/.claude"

printf 'Name: Cost band work\nSummary: Added the band.\nnotes A\n' > "$S/session_state_aaaa1111.md"
printf 'Name: Fix the parser\nSummary: Parser fixed.\nnotes B\n' > "$S/session_state_bbbb2222.md"
printf 'Name: Third thing\nSummary: Third.\nnotes C\n' > "$S/session_state_cccc3333.md"
touch -d '2 hours ago' "$S/session_state_cccc3333.md"

fail() { echo "FAIL: $1"; exit 1; }

ctx="$(echo "{\"cwd\": \"$TMP/proj\", \"session_id\": \"curr1234-zzzz\"}" \
    | CLAUDE_PLUGIN_ROOT="$REPO_ROOT" python3 "$REPO_ROOT/hooks/session_picker.py" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["hookSpecificOutput"]["additionalContext"])')"

for needle in "**Cost band work**" "**Fix the parser**" "**Third thing**" "delaySeconds=3420"; do
    grep -qF -- "$needle" <<<"$ctx" || fail "hook output lacks: $needle"
done
echo "PASS: hook output has all 3 exact names and the 3420 checkpoint"

consume_cmd="$(grep -oE 'consume command: [^]]+' <<<"$ctx" | head -1 | sed -E 's/^consume command: //; s/ <key>$//')"
delete_cmd="$(grep -oE 'delete command: [^]]+' <<<"$ctx" | head -1 | sed -E 's/^delete command: //; s/ <key> .*$//')"
[[ -n "$consume_cmd" && -n "$delete_cmd" ]] || fail "could not read printed commands"

out="$($consume_cmd aaaa1111)"
grep -q "notes A" <<<"$out" || fail "consume did not print the fixture content"
[[ ! -e "$S/session_state_aaaa1111.md" ]] || fail "consumed file still exists"
echo "PASS: consume printed the content and removed the file"

$delete_cmd bbbb2222
[[ ! -e "$S/session_state_bbbb2222.md" ]] || fail "deleted file still exists"
rc=0
$delete_cmd '../cccc3333' 2>/dev/null || rc=$?
[[ "$rc" -eq 2 && -e "$S/session_state_cccc3333.md" ]] || fail "bad key was not refused (rc=$rc)"
echo "PASS: delete removed the file; a bad key exited 2 and left the third file untouched"
