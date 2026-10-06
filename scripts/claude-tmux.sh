#!/usr/bin/env bash
# Start Claude Code inside a tmux session that outlives the SSH/VS Code connection,
# or re-attach if the session already exists.
#
# Usage: claude-tmux.sh [session-name] [-- claude args...]
#   claude-tmux.sh                    # session "claude", fresh claude
#   claude-tmux.sh work -- --resume   # session "work", pick a past conversation
set -euo pipefail

session="claude"
if [[ $# -gt 0 && "$1" != "--" ]]; then
  session="$1"
  shift
fi
[[ "${1:-}" == "--" ]] && shift

command -v tmux >/dev/null || { echo "tmux not found" >&2; exit 1; }
command -v claude >/dev/null || { echo "claude not found" >&2; exit 1; }

if tmux has-session -t "$session" 2>/dev/null; then
  echo "Re-attaching to existing tmux session '$session' (claude args ignored)."
else
  tmux new-session -d -s "$session" -c "$PWD" claude "$@"
fi

if [[ -n "${TMUX:-}" ]]; then
  tmux switch-client -t "$session"
else
  exec tmux attach -t "$session"
fi
