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
for f in .claude-plugin/plugin.json .claude-plugin/marketplace.json; do
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
market_version="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["plugins"][0]["version"])' \
    "$REPO_ROOT/.claude-plugin/marketplace.json")"
changelog_version="$(grep -m1 -oE '^## [0-9]+\.[0-9]+\.[0-9]+' "$REPO_ROOT/CHANGELOG.md" | cut -c4-)"
if [[ "$plugin_version" == "$market_version" && "$plugin_version" == "$changelog_version" ]]; then
    ok "plugin.json, marketplace.json, and CHANGELOG agree on version $plugin_version"
else
    bad "versions agree" "plugin=$plugin_version marketplace=$market_version changelog=$changelog_version"
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
