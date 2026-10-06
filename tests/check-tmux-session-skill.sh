#!/usr/bin/env bash
# Verify the tmux-session skill text contract and its user docs.
# Run from anywhere; paths are resolved relative to the repo root.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL="$REPO_ROOT/skills/tmux-session/SKILL.md"
DOC="$REPO_ROOT/docs/durable-sessions.md"
PASS=0
FAIL=0
ok()  { echo "PASS: $1"; PASS=$((PASS + 1)); }
bad() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }

if [[ -f "$SKILL" ]] && grep -qE "^name: tmux-session\$" "$SKILL"; then
    ok "SKILL.md exists with name: tmux-session"
else
    bad "SKILL.md exists with name: tmux-session"
fi
chk() { # label, pattern
    if [[ -f "$SKILL" ]] && grep -qiE "$2" "$SKILL"; then ok "SKILL.md $1"; else bad "SKILL.md $1"; fi
}
chk "documents list"                         'forgeloop_tmux\.py" list'
chk "documents stop"                         'forgeloop_tmux\.py" stop'
chk "mentions the fl- prefix"                'fl-'
chk "requires user confirmation before stop" 'confirm'
chk "documents tmux attach"                  'tmux attach -t'
chk "documents claude remote-control --continue" 'remote-control --continue'

if [[ -f "$DOC" ]] && grep -qiE "reboot|sleep" "$DOC" && grep -qiE "four hours|4 hours|four-hour" "$DOC"; then
    ok "docs/durable-sessions.md states VM reboot/sleep limit and four-hour resume window"
else
    bad "docs/durable-sessions.md states VM reboot/sleep limit and four-hour resume window"
fi

echo "$PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
