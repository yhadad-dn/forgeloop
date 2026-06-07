#!/usr/bin/env bash
# Verify that every loop with a Codex gate runs a model-check sub-agent at
# startup and substitutes the verified model into the Codex command.
# Run from anywhere; paths are resolved relative to the repo root.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_DIR="$REPO_ROOT/skill/.claude/skills"

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

# --- codex-model-check.md: shared sub-doc exists and is complete -------------
check \
    "codex-model-check.md exists with CODEX_MODEL output field" \
    "$SKILL_DIR/codex-model-check.md" \
    "CODEX_MODEL"

check \
    "codex-model-check.md spawns a sub-agent" \
    "$SKILL_DIR/codex-model-check.md" \
    "[Ss]ub.agent"

check \
    "codex-model-check.md has fallback behavior for FAILED or UNVERIFIED" \
    "$SKILL_DIR/codex-model-check.md" \
    "fallback"

check \
    "codex-model-check.md documents VERIFIED handling" \
    "$SKILL_DIR/codex-model-check.md" \
    "VERIFIED"

check \
    "codex-model-check.md provides a codex exec command template" \
    "$SKILL_DIR/codex-model-check.md" \
    "codex exec"

# --- Each loop main skill records CODEX_MODEL at startup --------------------
check \
    "implement-loop.md records CODEX_MODEL in loop state" \
    "$SKILL_DIR/implement-loop.md" \
    "CODEX_MODEL"

check \
    "plan-loop.md records CODEX_MODEL in loop state" \
    "$SKILL_DIR/plan-loop.md" \
    "CODEX_MODEL"

check \
    "debug-loop.md records CODEX_MODEL in loop state" \
    "$SKILL_DIR/debug-loop.md" \
    "CODEX_MODEL"

# --- Each loop's review-gates.md uses CODEX_MODEL variable in the command ----
check \
    "implement-loop/review-gates.md uses CODEX_MODEL in Codex command" \
    "$SKILL_DIR/implement-loop/review-gates.md" \
    "CODEX_MODEL"

check \
    "plan-loop/review-gates.md uses CODEX_MODEL in Codex command" \
    "$SKILL_DIR/plan-loop/review-gates.md" \
    "CODEX_MODEL"

check \
    "debug-loop/review-gates.md uses CODEX_MODEL in Codex command" \
    "$SKILL_DIR/debug-loop/review-gates.md" \
    "CODEX_MODEL"

# --- Summary -----------------------------------------------------------------
echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]]
