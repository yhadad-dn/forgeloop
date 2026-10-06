#!/usr/bin/env bash
# claudeCode.claudeProcessWrapper target for ForgeLoop durable sessions.
# usage: forgeloop-vscode-wrapper.sh <bundled-claude> [claude args]
# exit: exec of <bundled-claude> unchanged, or the launcher's status after
#       starting a durable tmux session (Remote Control server in tmux).
set -u

[ "$#" -ge 1 ] || { echo "usage: $0 <bundled-claude> [claude args]" >&2; exit 2; }
claude="$1"

# Session start = argv contains "--input-format stream-json".
is_session_start() {
  local prev="" a
  for a in "$@"; do
    [ "$prev" = "--input-format" ] && [ "$a" = "stream-json" ] && return 0
    [ "$a" = "--input-format=stream-json" ] && return 0
    prev="$a"
  done
  return 1
}

# Reopened conversations are not new sessions: pass through unchanged.
is_resume() {
  local a
  for a in "$@"; do
    case "$a" in --resume|-r|--continue|-c|--resume=*) return 0 ;; esac
  done
  return 1
}

is_session_start "$@" || exec "$@"
is_resume "$@" && exec "$@"
case "$(printf '%s' "${FORGELOOP_DURABLE:-}" | tr '[:upper:]' '[:lower:]')" in
  off|0|false|no) exec "$@" ;;
esac

self="$(readlink -f "${BASH_SOURCE[0]}")"
dir="$(dirname "$self")"
helper="$dir/forgeloop_tmux.py"
[ -f "$helper" ] || helper="$dir/../skills/tmux-session/forgeloop_tmux.py"
[ -f "$helper" ] || exec "$@"
helper="$(readlink -f "$helper")"

class="$(python3 "$helper" classify </dev/null 2>/dev/null)" || exec "$@"
[ "$class" = "remote_ssh" ] || exec "$@"

name=""
started=0
fallback() {
  local reason="$1"
  shift
  if [ "$started" = 1 ]; then tmux kill-session -t "=$name" >/dev/null 2>&1; fi
  echo "forgeloop: durable tmux session not started ($reason); running claude normally. Manual option: scripts/claude-tmux.sh" >&2
  exec "$@"
}

command -v tmux >/dev/null 2>&1 || fallback "tmux not found" "$@"

ver="$("$claude" --version </dev/null 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1)"
[ -n "$ver" ] || fallback "claude version unknown" "$@"
IFS=. read -r v1 v2 v3 <<<"$ver"
case "$v1$v2$v3" in ''|*[!0-9]*) fallback "claude version unknown" "$@" ;; esac
if [ $((10#$v1)) -lt 2 ] || { [ $((10#$v1)) -eq 2 ] && { [ $((10#$v2)) -lt 1 ] || { [ $((10#$v2)) -eq 1 ] && [ $((10#$v3)) -lt 200 ]; }; }; }; then
  fallback "claude $ver is older than 2.1.200" "$@"
fi

name="$(python3 "$helper" name "$PWD" </dev/null 2>/dev/null)" || fallback "cannot name session" "$@"
[ -n "$name" ] || fallback "cannot name session" "$@"

cmd="$(printf '%q' "$claude") remote-control --spawn session --name $name"
on_signal() {
  [ "$started" = 1 ] && tmux kill-session -t "=$name" >/dev/null 2>&1
  exit 143
}
trap on_signal TERM INT HUP
tmux new-session -d -x 200 -s "$name" -c "$PWD" "$cmd" </dev/null >/dev/null 2>&1 || fallback "tmux start failed" "$@"
started=1

wait_s="${FORGELOOP_URL_WAIT:-15}"
case "$wait_s" in ''|*[!0-9]*) wait_s=15 ;; esac
url=""
tries=$((wait_s * 2))
i=0
while :; do
  url="$(tmux capture-pane -pJ -t "=$name:" 2>/dev/null | grep -oE 'https://claude\.ai/code[/?][^[:space:]]+' | tail -n1)"
  [ -n "$url" ] && break
  [ "$i" -ge "$tries" ] && break
  sleep 0.5
  i=$((i + 1))
done
[ -n "$url" ] || fallback "no session URL within ${wait_s}s" "$@"

record="$HOME/.claude/forgeloop/last-durable-session.txt"
umask 077
mkdir -p "$(dirname "$record")" || fallback "cannot write record" "$@"
tmprec="$(mktemp "$record.XXXXXX")" || fallback "cannot write record" "$@"
{
  echo "Durable session started."
  echo "Session: $name"
  echo "URL: $url"
  echo "Attach: tmux attach -t $name"
  echo "Stop: /forgeloop:tmux-session stop"
} >"$tmprec" && mv -f "$tmprec" "$record" || { rm -f "$tmprec"; fallback "cannot write record" "$@"; }

trap - TERM INT HUP

exec python3 "$helper" launcher "$record"
