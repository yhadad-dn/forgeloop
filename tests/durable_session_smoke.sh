#!/usr/bin/env bash
# Smoke test for scripts/forgeloop-vscode-wrapper.sh against a fake `claude`,
# using a private tmux server. Prints PASS/FAIL lines; exits non-zero on any FAIL.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WRAPPER="$ROOT/scripts/forgeloop-vscode-wrapper.sh"
HELPER="$ROOT/skills/tmux-session/forgeloop_tmux.py"

fails=0
pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; fails=$((fails + 1)); }
check() { # check <description> <command...>
  local d="$1"; shift
  if "$@"; then pass "$d"; else fail "$d"; fi
}

if ! command -v tmux >/dev/null 2>&1; then
  echo "FAIL: tmux not installed"
  exit 1
fi

SCRATCH="$(mktemp -d)"
export TMUX_TMPDIR="$SCRATCH"
cleanup() { tmux kill-server >/dev/null 2>&1; rm -rf "$SCRATCH"; }
trap cleanup EXIT

unset TMUX SSH_CONNECTION REMOTE_CONTAINERS CODESPACES WSL_DISTRO_NAME FORGELOOP_DURABLE FAKE_CLAUDE_NO_URL FAKE_CLAUDE_VERSION
export HOME="$SCRATCH/home"
mkdir -p "$HOME" "$SCRATCH/ws"

FAKE="$SCRATCH/claude"
cat >"$FAKE" <<'EOF'
#!/usr/bin/env bash
if [ "${1:-}" = "--version" ]; then echo "${FAKE_CLAUDE_VERSION:-2.1.300} (Claude Code)"; exit 0; fi
if [ "${1:-}" = "remote-control" ]; then
  if [ -z "${FAKE_CLAUDE_NO_URL:-}" ]; then echo "Session URL: https://claude.ai/code/fake123"; fi
  sleep 600
  exit 0
fi
echo "FAKE-CLAUDE-DIRECT $*"
EOF
chmod +x "$FAKE"

STREAM_ARGS=(--output-format stream-json --verbose --input-format stream-json)
STDIN_LINES='{"type":"control_request","request_id":"r1","request":{"subtype":"initialize"}}
{"type":"user","message":{"role":"user","content":[{"type":"text","text":"hi"}]}}'

fl_sessions() { tmux ls -F '#S' 2>/dev/null | grep '^fl-' || true; }
reset() { tmux kill-server >/dev/null 2>&1; rm -rf "$HOME/.claude"; }

# run_wrapper <outfile> <args...>; stdin from $STDIN_LINES; cwd = scratch workspace
run_wrapper() {
  local out="$1"; shift
  (cd "$SCRATCH/ws" && printf '%s\n' "$STDIN_LINES" | bash "$WRAPPER" "$FAKE" "$@" >"$out" 2>"$out.err")
}

# 1. auth status passthrough
reset
OUT="$SCRATCH/o1"
SSH_CONNECTION="1.1.1.1 1 2.2.2.2 22" run_wrapper "$OUT" auth status --json
check "auth-status passthrough runs fake directly" grep -q "FAKE-CLAUDE-DIRECT auth status --json" "$OUT"
check "auth-status passthrough creates no fl-* session" test -z "$(fl_sessions)"

# 2. local path
reset
OUT="$SCRATCH/o2"
run_wrapper "$OUT" "${STREAM_ARGS[@]}"
check "local path runs fake directly" grep -q "FAKE-CLAUDE-DIRECT --output-format" "$OUT"
check "local path creates no fl-* session" test -z "$(fl_sessions)"

# 3. durable path
reset
OUT="$SCRATCH/o3"
SSH_CONNECTION="1.1.1.1 1 2.2.2.2 22" run_wrapper "$OUT" "${STREAM_ARGS[@]}"
NAME="$(fl_sessions | head -n1)"
check "durable path leaves an fl-* tmux session" test -n "$NAME"
check "durable stdout has the URL" grep -q "https://claude.ai/code/fake123" "$OUT"
check "durable stdout has the attach command" grep -q "tmux attach -t $NAME" "$OUT"
check "durable stdout has assistant message" grep -q '"type": "assistant"' "$OUT"
check "every durable stdout line is valid JSON" python3 -c 'import json,sys
for l in open(sys.argv[1]):
    json.loads(l)' "$OUT"
check "durable path does not run fake directly" bash -c '! grep -q FAKE-CLAUDE-DIRECT "$1"' _ "$OUT"
check "record file is private (mode 600)" bash -c '[ "$(stat -c %a "$1")" = 600 ]' _ "$HOME/.claude/forgeloop/last-durable-session.txt"
check "record file contains the URL" grep -q "https://claude.ai/code/fake123" "$HOME/.claude/forgeloop/last-durable-session.txt"

# 4. stop removes only the fl-* session
tmux new-session -d -s keepme "sleep 600"
python3 "$HELPER" stop "$NAME"
for _ in $(seq 1 12); do
  [ -z "$(fl_sessions)" ] && break
  sleep 0.5
done
check "stop removes the fl-* session" test -z "$(fl_sessions)"
check "stop leaves non-fl session keepme" bash -c "tmux ls -F '#S' | grep -qx keepme"

# 5. timeout fallback
reset
OUT="$SCRATCH/o5"
SSH_CONNECTION="1.1.1.1 1 2.2.2.2 22" FAKE_CLAUDE_NO_URL=1 FORGELOOP_URL_WAIT=3 run_wrapper "$OUT" "${STREAM_ARGS[@]}"
check "timeout fallback runs fake directly" grep -q "FAKE-CLAUDE-DIRECT --output-format" "$OUT"
check "timeout fallback leaves no fl-* session" test -z "$(fl_sessions)"
check "timeout fallback prints one warning naming claude-tmux.sh" bash -c '[ "$(grep -c claude-tmux.sh "$1")" = 1 ]' _ "$OUT.err"

# 6. off switch
reset
OUT="$SCRATCH/o6"
SSH_CONNECTION="1.1.1.1 1 2.2.2.2 22" FORGELOOP_DURABLE=off run_wrapper "$OUT" "${STREAM_ARGS[@]}"
check "off switch runs fake directly" grep -q "FAKE-CLAUDE-DIRECT --output-format" "$OUT"
check "off switch creates no fl-* session" test -z "$(fl_sessions)"

# 7. other-remote
reset
OUT="$SCRATCH/o7a"
REMOTE_CONTAINERS=1 SSH_CONNECTION="1.1.1.1 1 2.2.2.2 22" run_wrapper "$OUT" "${STREAM_ARGS[@]}"
check "other-remote without opt-in runs fake directly" grep -q "FAKE-CLAUDE-DIRECT --output-format" "$OUT"
check "other-remote without opt-in creates no fl-* session" test -z "$(fl_sessions)"
reset
mkdir -p "$HOME/.claude/forgeloop"
echo yes >"$HOME/.claude/forgeloop/durable"
OUT="$SCRATCH/o7b"
REMOTE_CONTAINERS=1 SSH_CONNECTION="1.1.1.1 1 2.2.2.2 22" run_wrapper "$OUT" "${STREAM_ARGS[@]}"
check "other-remote with opt-in creates an fl-* session" test -n "$(fl_sessions)"

# 8. extra fallbacks and passthroughs
SSHV="1.1.1.1 1 2.2.2.2 22"
reset
OUT="$SCRATCH/o8a"
BIN="$SCRATCH/notmux"; mkdir -p "$BIN"
for c in bash python3 grep head tail readlink dirname sleep cat mkdir mv rm mktemp sort tr; do
  p="$(command -v $c)" && ln -sf "$p" "$BIN/$c"
done
(cd "$SCRATCH/ws" && printf '%s\n' "$STDIN_LINES" | SSH_CONNECTION="$SSHV" PATH="$BIN" "$BIN/bash" "$WRAPPER" "$FAKE" "${STREAM_ARGS[@]}" >"$OUT" 2>"$OUT.err")
check "missing tmux runs fake directly" grep -q "FAKE-CLAUDE-DIRECT --output-format" "$OUT"
check "missing tmux warns once" bash -c '[ "$(grep -c claude-tmux.sh "$1")" = 1 ]' _ "$OUT.err"

reset
OUT="$SCRATCH/o8b"
SSH_CONNECTION="$SSHV" FAKE_CLAUDE_VERSION=2.1.100 run_wrapper "$OUT" "${STREAM_ARGS[@]}"
check "old claude runs fake directly" grep -q "FAKE-CLAUDE-DIRECT --output-format" "$OUT"
check "old claude creates no fl-* session" test -z "$(fl_sessions)"

reset
OUT="$SCRATCH/o8c"
SSH_CONNECTION="$SSHV" FAKE_CLAUDE_VERSION=2.1.0200 run_wrapper "$OUT" --output-format stream-json --verbose --input-format=stream-json
NAME="$(fl_sessions | head -n1)"
check "--input-format=stream-json form is durable (leading-zero version ok)" test -n "$NAME"
check "= form stdout is JSON" python3 -c 'import json,sys
for l in open(sys.argv[1]):
    json.loads(l)' "$OUT"

for flag in --resume -r --continue -c; do
  reset
  OUT="$SCRATCH/o8d"
  SSH_CONNECTION="$SSHV" run_wrapper "$OUT" "${STREAM_ARGS[@]}" "$flag" abc
  check "$flag passes through unchanged" grep -q "FAKE-CLAUDE-DIRECT --output-format" "$OUT"
  check "$flag creates no fl-* session" test -z "$(fl_sessions)"
done

for v in OFF False NO 0; do
  reset
  OUT="$SCRATCH/o8e"
  SSH_CONNECTION="$SSHV" FORGELOOP_DURABLE="$v" run_wrapper "$OUT" "${STREAM_ARGS[@]}"
  check "FORGELOOP_DURABLE=$v runs fake directly" grep -q "FAKE-CLAUDE-DIRECT --output-format" "$OUT"
  check "FORGELOOP_DURABLE=$v creates no fl-* session" test -z "$(fl_sessions)"
done

# 9. SIGTERM during URL wait kills the session and does not fall back to claude
reset
OUT="$SCRATCH/o9"
printf '%s\n' "$STDIN_LINES" >"$SCRATCH/stdin9"
(cd "$SCRATCH/ws" && SSH_CONNECTION="$SSHV" FAKE_CLAUDE_NO_URL=1 FORGELOOP_URL_WAIT=10 exec bash "$WRAPPER" "$FAKE" "${STREAM_ARGS[@]}" <"$SCRATCH/stdin9" >"$OUT" 2>"$OUT.err") &
WPID=$!
for _ in $(seq 1 50); do [ -n "$(fl_sessions)" ] && break; sleep 0.1; done
check "SIGTERM case: fl-* session existed before the signal" test -n "$(fl_sessions)"
kill -TERM "$WPID" 2>/dev/null
wait "$WPID"; WRC=$?
check "SIGTERM makes wrapper exit 143" test "$WRC" = 143
check "SIGTERM leaves no fl-* session" test -z "$(fl_sessions)"
check "SIGTERM does not run fake directly" bash -c '! grep -q FAKE-CLAUDE-DIRECT "$1"' _ "$OUT"

echo
if [ "$fails" -ne 0 ]; then
  echo "$fails check(s) FAILED"
  exit 1
fi
echo "All durable session smoke checks passed"
