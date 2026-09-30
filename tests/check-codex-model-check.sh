#!/usr/bin/env bash
# Verify that every loop with a Codex gate runs a model-check sub-agent at
# startup and substitutes the verified model into the Codex command.
# Run from anywhere; paths are resolved relative to the repo root.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_DIR="$REPO_ROOT/skills"

PASS=0
FAIL=0

check() {
    local desc="$1"
    local file="$2"
    local pattern="$3"
    if [[ ! -f "$file" ]]; then
        echo "FAIL: $desc"
        echo "      file missing: $file"
        FAIL=$((FAIL + 1))
        return
    fi
    if grep -qE "$pattern" "$file"; then
        echo "PASS: $desc"
        PASS=$((PASS + 1))
    else
        echo "FAIL: $desc"
        echo "      file:    $file"
        echo "      pattern: $pattern"
        FAIL=$((FAIL + 1))
    fi
}


check_absent() {
    local desc="$1"
    local file="$2"
    local pattern="$3"
    if [[ -f "$file" ]] && ! grep -qiE "$pattern" "$file"; then
        echo "PASS: $desc"
        PASS=$((PASS + 1))
    else
        echo "FAIL: $desc"
        echo "      file:    $file"
        echo "      forbidden pattern: $pattern"
        FAIL=$((FAIL + 1))
    fi
}

# --- codex-model-check.md: shared sub-doc exists and is complete -------------
check \
    "codex-model-check.md exists with CODEX_MODEL output field" \
    "$SKILL_DIR/codex-model-check/SKILL.md" \
    "CODEX_MODEL"

check \
    "codex-model-check.md spawns a sub-agent" \
    "$SKILL_DIR/codex-model-check/SKILL.md" \
    "[Ss]ub.agent"

check \
    "codex-model-check.md has fallback behavior for FAILED or UNVERIFIED" \
    "$SKILL_DIR/codex-model-check/SKILL.md" \
    "fallback"

check \
    "codex-model-check.md documents VERIFIED handling" \
    "$SKILL_DIR/codex-model-check/SKILL.md" \
    "VERIFIED"

check \
    "codex-model-check.md provides a codex exec command template" \
    "$SKILL_DIR/codex-model-check/SKILL.md" \
    "codex exec"

# --- debug-loop keeps the Codex gate and records CODEX_MODEL ---------------
check \
    "debug-loop.md records CODEX_MODEL in loop state" \
    "$SKILL_DIR/debug-loop/SKILL.md" \
    "CODEX_MODEL"

check \
    "debug-loop/review-gates.md uses CODEX_MODEL in Codex command" \
    "$SKILL_DIR/debug-loop/review-gates.md" \
    "CODEX_MODEL"

# --- implement-loop and plan-loop have no Codex stage -------------------------
for f in implement-loop/SKILL.md implement-loop/review-gates.md plan-loop/review-gates.md; do
    check_absent \
        "$f has no Codex model check or Codex gate" \
        "$SKILL_DIR/$f" \
        "CODEX_MODEL|codex exec|codex-model-check"
done

check_absent \
    "plan-loop/SKILL.md has no Codex model check or Codex gate" \
    "$SKILL_DIR/plan-loop/SKILL.md" \
    "CODEX_MODEL|codex exec|codex-model-check|Stage 6b"

# --- Summary -----------------------------------------------------------------
echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]]
