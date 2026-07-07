#!/usr/bin/env bash
# Verify that implement-loop skill text enforces required behaviors.
# Each assertion is a grep that must match the specified file.
# Run from anywhere; paths are resolved relative to the repo root.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_DIR="$REPO_ROOT/skill/.claude/skills"
TMPL_DIR="$REPO_ROOT/templates"

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

# --- Required files exist (verified via meaningful content pattern) -----------
check \
    "implement-loop.md exists" \
    "$SKILL_DIR/implement-loop.md" \
    "MAX_ITERATIONS"

check \
    "implement-loop/review-gates.md exists" \
    "$SKILL_DIR/implement-loop/review-gates.md" \
    "Stage B"

check \
    "implement-loop/reports.md exists" \
    "$SKILL_DIR/implement-loop/reports.md" \
    "Convergence Report"

check \
    "implement-loop/coverage-gate.md exists" \
    "$SKILL_DIR/implement-loop/coverage-gate.md" \
    "TEST_COVERAGE"

# --- Behavior 1: DEFERRED findings are tracked, not dropped -------------------
check \
    "review-gates.md defines the DEFERRED finding classification" \
    "$SKILL_DIR/implement-loop/review-gates.md" \
    "DEFERRED"

check \
    "review-gates.md requires DEFERRED findings to become follow-up task files" \
    "$SKILL_DIR/implement-loop/review-gates.md" \
    "followups/"

check \
    "reports.md convergence report carries forward DEFERRED findings" \
    "$SKILL_DIR/implement-loop/reports.md" \
    "Carried-forward findings"

# --- Behavior 2: Codex verdict dual-format acceptance -------------------------
check \
    "review-gates.md accepts the Codex-native review verdict form" \
    "$SKILL_DIR/implement-loop/review-gates.md" \
    "[Nn]ative"

check \
    "review-gates.md maps P1/P2 native findings to FAIL" \
    "$SKILL_DIR/implement-loop/review-gates.md" \
    "P1/P2"

check \
    "review-gates.md maps an explicit no-blocking statement to PASS" \
    "$SKILL_DIR/implement-loop/review-gates.md" \
    "no-blocking statement"

check \
    "review-gates.md: absence of output is never a pass" \
    "$SKILL_DIR/implement-loop/review-gates.md" \
    "never a pass"

check \
    "review-gates.md: ambiguous output retries once then errors" \
    "$SKILL_DIR/implement-loop/review-gates.md" \
    "[Rr]etry once"

check \
    "implement-loop.md Stage C defers to the two accepted verdict forms" \
    "$SKILL_DIR/implement-loop.md" \
    "P1/P2"

check \
    "codex-review-prompt.md documents verdict acceptance for both forms" \
    "$TMPL_DIR/codex-review-prompt.md" \
    "[Nn]ative"

check \
    "codex-review-prompt.md pins the P1/P2-to-FAIL mapping" \
    "$TMPL_DIR/codex-review-prompt.md" \
    "P1/P2"

# --- Behavior 3: Reviewer fan-out is proportional to the diff ------------------
check \
    "review-gates.md defines proportional reviewer fan-out" \
    "$SKILL_DIR/implement-loop/review-gates.md" \
    "proportional"

# --- Behavior 4: Coverage gate is honest about subprocess-run code -------------
check \
    "coverage-gate.md addresses subprocess-executed code undercounting" \
    "$SKILL_DIR/implement-loop/coverage-gate.md" \
    "COVERAGE_PROCESS_START"

check \
    "coverage-gate.md names the undercounted_subprocess annotation" \
    "$SKILL_DIR/implement-loop/coverage-gate.md" \
    "undercounted_subprocess"

check \
    "coverage-gate.md schema has a coverage_annotations slot" \
    "$SKILL_DIR/implement-loop/coverage-gate.md" \
    "coverage_annotations"

# --- Summary -------------------------------------------------------------------
echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]]
