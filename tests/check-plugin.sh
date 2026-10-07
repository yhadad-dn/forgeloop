#!/usr/bin/env bash
# Verify ForgeLoop's plugin packaging: manifests, skill layout, versions, and that
# every file reference inside the skills resolves.
# Run from anywhere; paths are resolved relative to the repo root.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PASS=0
FAIL=0

ok()  { echo "PASS: $1"; PASS=$((PASS + 1)); }
bad() { echo "FAIL: $1"; [[ -n "${2:-}" ]] && echo "      $2"; FAIL=$((FAIL + 1)); }

# --- Manifests ------------------------------------------------------------------
for f in .claude-plugin/plugin.json; do
    if python3 -m json.tool "$REPO_ROOT/$f" >/dev/null 2>&1; then
        ok "$f is valid JSON"
    else
        bad "$f is valid JSON"
    fi
done

if command -v claude >/dev/null 2>&1; then
    for target in . skills agents; do
        if out="$(claude plugin validate "$REPO_ROOT/$target" --strict 2>&1)"; then
            ok "claude plugin validate --strict $target"
        else
            bad "claude plugin validate --strict $target" "$(tail -5 <<<"$out")"
        fi
    done
else
    echo "SKIP: claude CLI not found; manifest schema validation skipped"
fi

# --- Versions agree -------------------------------------------------------------
plugin_version="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' \
    "$REPO_ROOT/.claude-plugin/plugin.json")"
changelog_version="$(grep -m1 -oE '^## [0-9]+\.[0-9]+\.[0-9]+' "$REPO_ROOT/CHANGELOG.md" | cut -c4-)"
if [[ "$plugin_version" == "$changelog_version" ]]; then
    ok "plugin.json and CHANGELOG agree on version $plugin_version"
else
    bad "versions agree" "plugin=$plugin_version changelog=$changelog_version"
fi

# The gpu-team marketplace lists this plugin (when checked out inside it)
market="$REPO_ROOT/../../.claude-plugin/marketplace.json"
if [[ -f "$market" ]]; then
    if python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); sys.exit(0 if any(p.get("source")=="./plugins/forgeloop" for p in m["plugins"]) else 1)' "$market"; then
        ok "gpu-team marketplace.json lists ./plugins/forgeloop"
    else
        bad "gpu-team marketplace.json lists ./plugins/forgeloop"
    fi
fi

# This repo's own marketplace.json (when it ships one, as yhadad-dn/forgeloop does)
own_market="$REPO_ROOT/.claude-plugin/marketplace.json"
if [[ -f "$own_market" ]]; then
    market_version="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["plugins"][0]["version"])' "$own_market")"
    if [[ "$market_version" == "$plugin_version" ]]; then
        ok "own marketplace.json agrees with plugin.json on version $plugin_version"
    else
        bad "own marketplace.json version agrees" "plugin=$plugin_version marketplace=$market_version"
    fi
fi

# --- Skill layout -----------------------------------------------------------------
for dir in "$REPO_ROOT"/skills/*/; do
    name="$(basename "$dir")"
    skill="$dir/SKILL.md"
    if [[ -f "$skill" ]] && grep -qE "^name: $name\$" "$skill"; then
        ok "skills/$name/SKILL.md exists with name: $name"
    else
        bad "skills/$name/SKILL.md exists with name: $name"
    fi
done

for f in "$REPO_ROOT"/agents/*.md; do
    name="$(basename "$f" .md)"
    if grep -qE "^name: $name\$" "$f"; then
        ok "agents/$name.md frontmatter name matches file"
    else
        bad "agents/$name.md frontmatter name matches file"
    fi
    if grep -qE "^tools: " "$f"; then
        ok "agents/$name.md declares a scoped tools: list (not the full default set)"
    else
        bad "agents/$name.md declares a scoped tools: list (not the full default set)"
    fi
done

for name in reviewer-correctness reviewer-security reviewer-hygiene source-check; do
    f="$REPO_ROOT/agents/$name.md"
    if grep -qE "^tools: Read, Grep, Glob" "$f"; then
        ok "agents/$name.md is read-only (Read, Grep, Glob only — plus WebFetch where justified)"
    else
        bad "agents/$name.md is read-only (Read, Grep, Glob only — plus WebFetch where justified)"
    fi
done

if grep -qE "^model: haiku" "$REPO_ROOT/agents/reviewer-hygiene.md"; then
    ok "reviewer-hygiene.md uses a cheaper model (its findings are mostly non-blocking by design)"
else
    bad "reviewer-hygiene.md uses a cheaper model (its findings are mostly non-blocking by design)"
fi

for name in reviewer-correctness reviewer-security; do
    if grep -qE "^model: " "$REPO_ROOT/agents/$name.md"; then
        bad "agents/$name.md stays on the default model (highest-stakes reviewer, never downgraded)"
    else
        ok "agents/$name.md stays on the default model (highest-stakes reviewer, never downgraded)"
    fi
done

# --- No stale pre-plugin layout references -----------------------------------------
if grep -rnE "skill/\.claude" "$REPO_ROOT/skills" "$REPO_ROOT/agents" "$REPO_ROOT/scripts" \
        "$REPO_ROOT/tests" "$REPO_ROOT/docs" "$REPO_ROOT/README.md" \
        "$REPO_ROOT/CONTRIBUTING.md" --exclude=check-plugin.sh >/dev/null 2>&1; then
    bad "no references to the old skill/.claude layout" \
        "$(grep -rnE "skill/\.claude" "$REPO_ROOT/skills" "$REPO_ROOT/agents" "$REPO_ROOT/scripts" \
            "$REPO_ROOT/tests" "$REPO_ROOT/docs" "$REPO_ROOT/README.md" "$REPO_ROOT/CONTRIBUTING.md" \
            --exclude=check-plugin.sh | head -3)"
else
    ok "no references to the old skill/.claude layout"
fi

# --- Every file reference inside a skill resolves ------------------------------------
# Backticked references to a sibling skill (`../<skill>/<file>`) or to a file that
# lives in this skill's directory must exist.
if broken="$(python3 - "$REPO_ROOT/skills" <<'PY'
import pathlib, re, sys
root = pathlib.Path(sys.argv[1])
own_files = {p.name for p in root.rglob("*") if p.is_file()}
ref = re.compile(r"`((?:\.\./[a-z-]+/)?[A-Za-z_-]+\.(?:md|py))`")
broken = []
for md in root.rglob("*.md"):
    for m in ref.finditer(md.read_text()):
        target = m.group(1)
        if target.startswith("../") or target in own_files:
            if not (md.parent / target).resolve().exists():
                broken.append(f"{md.relative_to(root)} -> {target}")
print("\n".join(broken))
sys.exit(1 if broken else 0)
PY
)"; then
    ok "every skill-relative file reference resolves"
else
    bad "every skill-relative file reference resolves" "$(head -5 <<<"$broken")"
fi

if grep -qE '^## 0\.17\.0$' "$REPO_ROOT/CHANGELOG.md"; then
    ok "CHANGELOG has a 0.17.0 section"
else
    bad "CHANGELOG has a 0.17.0 section"
fi

# --- Session conventions hook ---------------------------------------------------------
if python3 -m json.tool "$REPO_ROOT/hooks/hooks.json" >/dev/null 2>&1 \
        && grep -q "session_start.py" "$REPO_ROOT/hooks/hooks.json"; then
    ok "hooks/hooks.json registers the SessionStart conventions hook"
else
    bad "hooks/hooks.json registers the SessionStart conventions hook"
fi

if python3 -c 'import json,sys; h=json.load(open(sys.argv[1]))["hooks"]["SessionStart"][0]["hooks"]; sys.exit(0 if any("session_picker.py" in x["command"] and x.get("timeout")==10 for x in h) else 1)' "$REPO_ROOT/hooks/hooks.json" \
        && [[ -f "$REPO_ROOT/hooks/session_picker.py" && -f "$REPO_ROOT/hooks/session_state.py" ]]; then
    ok "hooks/hooks.json registers the session picker; picker and helper files exist"
else
    bad "hooks/hooks.json registers the session picker; picker and helper files exist"
fi

conv_lines="$(wc -l < "$REPO_ROOT/conventions.md")"
if [[ "$conv_lines" -le 70 ]]; then
    ok "conventions.md is $conv_lines lines (limit 70; it is injected into every session)"
else
    bad "conventions.md is $conv_lines lines (limit 70; it is injected into every session)"
fi

if grep -q "{CLUSTER_STATUS}" "$REPO_ROOT/conventions.md" \
        && [[ -f "$REPO_ROOT/skills/cluster-loop/cluster_status.py" ]]; then
    ok "conventions.md points at the shipped cluster_status.py"
else
    bad "conventions.md points at the shipped cluster_status.py"
fi

# --- Installer still delivers the plugin payload -------------------------------------
target="$(mktemp -d)"
bash "$REPO_ROOT/scripts/install.sh" "$target" >/dev/null
if [[ -f "$target/.claude/skills/implement-loop/SKILL.md" && -f "$target/.claude/agents/refactorer.md" \
        && -f "$target/.claude/forgeloop.md" ]]; then
    ok "install.sh copies skills, agents, and forgeloop.md into .claude/"
else
    bad "install.sh copies skills, agents, and forgeloop.md into .claude/"
fi
rm -rf "$target"

# --- Summary -------------------------------------------------------------------------
echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]]
