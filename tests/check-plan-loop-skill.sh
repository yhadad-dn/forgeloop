#!/usr/bin/env bash
# Verify that plan-loop skill text enforces required behaviors.
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

# --- Behavior 1: Requirements validation runs before plan generation ----------
check \
    "Stage 4 may only run after Stage 1 (requirements validated first)" \
    "$SKILL_DIR/plan-loop.md" \
    "May only run after Stage 1"

check \
    "requirements-validation.md exists with a gate clause" \
    "$SKILL_DIR/plan-loop/requirements-validation.md" \
    "Do not proceed to Stage 2 until"

# --- Behavior 2: No new sources during plan generation -----------------------
check \
    "source-authority.md forbids new-source discovery in Stage 4" \
    "$SKILL_DIR/plan-loop/source-authority.md" \
    "must not discover or rely on"

check \
    "plan-loop.md forbids new-source discovery in Stage 4" \
    "$SKILL_DIR/plan-loop.md" \
    "Do not discover or rely on new"

# --- Behavior 3: User-only conflict resolution -------------------------------
check \
    "source-authority.md prohibits autonomous source-conflict resolution" \
    "$SKILL_DIR/plan-loop/source-authority.md" \
    "Do not choose between conflicting sources autonomously"

check \
    "plan-loop.md prohibits autonomous decisions in Stage 3" \
    "$SKILL_DIR/plan-loop.md" \
    "Do not make any autonomous decisions"

# --- Behavior 4: No approval while unresolved decisions remain ---------------
check \
    "plan-format.md blocks approval when Unresolved Decisions section is non-empty" \
    "$SKILL_DIR/plan-loop/plan-format.md" \
    "plan may not proceed to approval"

check \
    "plan-loop.md blocks approval when unresolved decisions remain" \
    "$SKILL_DIR/plan-loop.md" \
    "may not be presented for approval"

# --- Behavior 5: Complete implement-loop handoff schema in plan-format.md ----
check \
    "plan-format.md — implement-loop Handoff heading" \
    "$SKILL_DIR/plan-loop/plan-format.md" \
    "implement-loop Handoff"

check \
    "plan-format.md — Acceptance criteria for implement-loop field" \
    "$SKILL_DIR/plan-loop/plan-format.md" \
    "Acceptance criteria for implement-loop"

check \
    "plan-format.md — Tests to write (TDD) field" \
    "$SKILL_DIR/plan-loop/plan-format.md" \
    "Tests to write \(TDD\)"

check \
    "plan-format.md — Verification commands field" \
    "$SKILL_DIR/plan-loop/plan-format.md" \
    "Verification commands"

check \
    "plan-format.md — Checklist field" \
    "$SKILL_DIR/plan-loop/plan-format.md" \
    "Checklist"

check \
    "plan-format.md — Source check completed checklist item" \
    "$SKILL_DIR/plan-loop/plan-format.md" \
    "Source check completed"

check \
    "plan-format.md — RED evidence captured checklist item" \
    "$SKILL_DIR/plan-loop/plan-format.md" \
    "RED evidence captured"

check \
    "plan-format.md — GREEN evidence captured checklist item" \
    "$SKILL_DIR/plan-loop/plan-format.md" \
    "GREEN evidence captured"

check \
    "plan-format.md — Reviewer gate passed checklist item" \
    "$SKILL_DIR/plan-loop/plan-format.md" \
    "Reviewer gate passed"

check \
    "plan-format.md — Codex gate passed checklist item" \
    "$SKILL_DIR/plan-loop/plan-format.md" \
    "Codex gate passed"

check \
    "plan-format.md — User approved commit checklist item" \
    "$SKILL_DIR/plan-loop/plan-format.md" \
    "User approved commit"

# --- Behavior 5: Complete implement-loop handoff schema in template -----------
check \
    "plan-loop-plan.md — implement-loop Handoff heading" \
    "$TMPL_DIR/plan-loop-plan.md" \
    "implement-loop Handoff"

check \
    "plan-loop-plan.md — Acceptance criteria for implement-loop field" \
    "$TMPL_DIR/plan-loop-plan.md" \
    "Acceptance criteria for implement-loop"

check \
    "plan-loop-plan.md — Tests to write (TDD) field" \
    "$TMPL_DIR/plan-loop-plan.md" \
    "Tests to write \(TDD\)"

check \
    "plan-loop-plan.md — Verification commands field" \
    "$TMPL_DIR/plan-loop-plan.md" \
    "Verification commands"

check \
    "plan-loop-plan.md — Checklist field" \
    "$TMPL_DIR/plan-loop-plan.md" \
    "Checklist"

check \
    "plan-loop-plan.md — Source check completed checklist item" \
    "$TMPL_DIR/plan-loop-plan.md" \
    "Source check completed"

check \
    "plan-loop-plan.md — RED evidence captured checklist item" \
    "$TMPL_DIR/plan-loop-plan.md" \
    "RED evidence captured"

check \
    "plan-loop-plan.md — GREEN evidence captured checklist item" \
    "$TMPL_DIR/plan-loop-plan.md" \
    "GREEN evidence captured"

check \
    "plan-loop-plan.md — Reviewer gate passed checklist item" \
    "$TMPL_DIR/plan-loop-plan.md" \
    "Reviewer gate passed"

check \
    "plan-loop-plan.md — Codex gate passed checklist item" \
    "$TMPL_DIR/plan-loop-plan.md" \
    "Codex gate passed"

check \
    "plan-loop-plan.md — User approved commit checklist item" \
    "$TMPL_DIR/plan-loop-plan.md" \
    "User approved commit"

# --- Approval gate and supporting files --------------------------------------
check \
    "plan-loop.md references implement-loop at the approval gate" \
    "$SKILL_DIR/plan-loop.md" \
    "implement-loop"

check \
    "plan-loop/review-gates.md exists" \
    "$SKILL_DIR/plan-loop/review-gates.md" \
    "Stage 6"

# --- Summary -----------------------------------------------------------------
echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]]
