#!/usr/bin/env bash
# Verify the cost-heatmap skill: text contract, no org-specific branding, and an
# end-to-end collect+build against a synthetic transcript.
# Run from anywhere; paths are resolved relative to the repo root.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIR="$REPO_ROOT/skills/cost-heatmap"
PASS=0
FAIL=0
ok()  { echo "PASS: $1"; PASS=$((PASS + 1)); }
bad() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }

grep -qE "^name: cost-heatmap\$" "$DIR/SKILL.md" && ok "SKILL.md name" || bad "SKILL.md name"
grep -qE "\.claude/forgeloop\.md" "$DIR/SKILL.md" && ok "SKILL.md reads budget settings from forgeloop.md" || bad "SKILL.md reads settings"
grep -qE "session_topics\.csv" "$DIR/SKILL.md" && ok "SKILL.md writes per-user topics" || bad "SKILL.md topics"

if grep -rniE "drivenets|cowork|list_sessions" "$DIR" "$REPO_ROOT/hooks/cost_heatmap_refresh.py" >/dev/null; then
    bad "no org-specific or Cowork-only references in skills/cost-heatmap"
else
    ok "no org-specific or Cowork-only references in skills/cost-heatmap"
fi

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/projects/-tmp-demo"
python3 - "$TMP/projects/-tmp-demo/s1.jsonl" <<'PY'
import json, sys
rows = [
    {"type": "user", "sessionId": "s1", "timestamp": "2026-07-01T10:00:00Z",
     "message": {"content": "fix the flaky login test"}},
    {"type": "assistant", "sessionId": "s1", "timestamp": "2026-07-01T10:00:05Z",
     "message": {"id": "m1", "model": "claude-opus-4-5", "content": [],
                 "usage": {"input_tokens": 1000, "cache_creation_input_tokens": 2000,
                           "cache_read_input_tokens": 3000, "output_tokens": 500}}},
]
# duplicate message id must not double count
rows.append(rows[1])
open(sys.argv[1], "w").write("\n".join(json.dumps(r) for r in rows) + "\n")
PY
mkdir -p "$TMP/codex/2026/07/01"
python3 - "$TMP/codex/2026/07/01/rollout-x.jsonl" <<'PY'
import json, sys
tc = lambda inp, cached, out: {"type": "event_msg", "timestamp": "2026-07-01T11:00:00Z", "payload": {
    "type": "token_count", "info": {"total_token_usage": {"input_tokens": inp, "cached_input_tokens": cached,
    "cache_write_input_tokens": 0, "output_tokens": out}}}}
rows = [
    {"type": "session_meta", "payload": {"id": "cx1", "cwd": "/tmp/demo"}},
    {"type": "turn_context", "payload": {"model": "gpt-5.5", "cwd": "/tmp/demo"}},
    {"type": "response_item", "payload": {"type": "message", "role": "user",
                                          "content": [{"type": "input_text", "text": "add a retry"}]}},
    tc(1000, 400, 200), tc(1000, 400, 200), tc(3000, 1400, 500),   # repeated total adds nothing
]
open(sys.argv[1], "w").write("\n".join(json.dumps(r) for r in rows) + "\n")
PY
printf 'ts,session_id,tool,model,project,input_tokens,cache_write_tokens,cache_read_tokens,output_tokens,title\n2026-07-02T09:00:00Z,e1,Gemini CLI,gemini-x,demo,100,0,0,50,ext task\n' > "$TMP/ext.csv"
out="$TMP/out"
mkdir -p "$out"; cp "$TMP/ext.csv" "$out/external_turns.csv"
if python3 "$DIR/cost_heatmap.py" --root "$TMP/projects" --codex-root "$TMP/codex" --dir "$out" >/dev/null 2>&1; then
    ok "collect+build runs on a synthetic transcript"
else
    bad "collect+build runs on a synthetic transcript"
fi
[[ "$(grep -c ',Claude Code,' "$out/turns.csv")" == "1" ]] && ok "duplicate message ids are merged" || bad "duplicate message ids are merged"
[[ "$(grep -c ',Codex,' "$out/turns.csv")" == "2" ]] && ok "codex token_count deltas billed once" || bad "codex token_count deltas billed once"
grep -q "Gemini CLI" "$out/turns.csv" && ok "external_turns.csv rows merged" || bad "external_turns.csv rows merged"
python3 - "$out/turns.csv" <<'PY' && ok "codex cost uses cached-input rate" || bad "codex cost uses cached-input rate"
import csv, sys
cost = sum(float(r["cost_usd"]) for r in csv.DictReader(open(sys.argv[1])) if r["tool"] == "Codex")
# fresh 1600 @5, cached 1400 @0.5, out 500 @30 (per M)
assert abs(cost - (1600 * 5 + 1400 * 0.5 + 500 * 30) / 1e6) < 1e-6, cost
PY
H="$TMP/home"; mkdir -p "$H"
HOME="$H" CLAUDE_PLUGIN_ROOT="$REPO_ROOT" FORGELOOP_COST_HEATMAP=off python3 "$REPO_ROOT/hooks/cost_heatmap_refresh.py" \
    && [[ ! -e "$H/.claude" ]] && ok "refresh hook honours FORGELOOP_COST_HEATMAP=off" || bad "refresh hook honours FORGELOOP_COST_HEATMAP=off"
grep -q cost_heatmap_refresh "$REPO_ROOT/hooks/hooks.json" && ok "refresh hook registered" || bad "refresh hook registered"
grep -q -- "--budget" "$REPO_ROOT/hooks/cost_heatmap_refresh.py" && bad "refresh hook never passes a budget" || ok "refresh hook never passes a budget"
grep -q "Bug fixes" "$out/cost-heatmap.html" && ok "keyword topic fallback applied" || bad "keyword topic fallback applied"
if command -v node >/dev/null 2>&1; then
    node -e "
const h=require('fs').readFileSync('$out/cost-heatmap.html','utf8');
const ms=[...h.matchAll(/<script(?![^>]*src)[^>]*>([\s\S]*?)<\/script>/g)];
for(const m of ms) new Function(m[1]);" 2>/dev/null && ok "dashboard JavaScript parses" || bad "dashboard JavaScript parses"
fi

echo "$PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]]
