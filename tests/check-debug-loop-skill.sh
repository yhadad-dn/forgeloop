#!/usr/bin/env bash
# Verify that debug-loop skill text enforces required behaviors.
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
    "debug-loop.md exists" \
    "$SKILL_DIR/debug-loop.md" \
    "MAX_DEBUG_ITERATIONS"

check \
    "debug-loop/symptom-validation.md exists" \
    "$SKILL_DIR/debug-loop/symptom-validation.md" \
    "Stage 1"

check \
    "debug-loop/evidence-map.md exists" \
    "$SKILL_DIR/debug-loop/evidence-map.md" \
    "EVIDENCE_MAP"

check \
    "debug-loop/reproduction-gate.md exists" \
    "$SKILL_DIR/debug-loop/reproduction-gate.md" \
    "RED evidence"

check \
    "debug-loop/root-cause-trace.md exists" \
    "$SKILL_DIR/debug-loop/root-cause-trace.md" \
    "root.cause"

check \
    "debug-loop/handoff-format.md exists" \
    "$SKILL_DIR/debug-loop/handoff-format.md" \
    "CONTEXT"

check \
    "debug-loop/review-gates.md exists" \
    "$SKILL_DIR/debug-loop/review-gates.md" \
    "Stage 6"

check \
    "templates/debug-loop-report.md exists" \
    "$TMPL_DIR/debug-loop-report.md" \
    "CONTEXT"

# --- Behavior 1: Hypothesis blocked until RED evidence exists ----------------
check \
    "debug-loop.md blocks hypothesis generation until RED evidence exists" \
    "$SKILL_DIR/debug-loop.md" \
    "Do not generate hypotheses until RED evidence exists"

check \
    "reproduction-gate.md blocks Stage 4 until RED evidence exists" \
    "$SKILL_DIR/debug-loop/reproduction-gate.md" \
    "Do not proceed to Stage 4 until RED evidence exists"

# --- Behavior 2: v2 prohibits staging/committing code ------------------------
check \
    "debug-loop.md prohibits staging or committing code" \
    "$SKILL_DIR/debug-loop.md" \
    "does not stage or commit"

# --- Behavior 3: Root-cause trace required before fix handoff ----------------
check \
    "debug-loop.md blocks handoff until root-cause trace evidence exists" \
    "$SKILL_DIR/debug-loop.md" \
    "Do not generate the handoff until root-cause trace evidence exists"

check \
    "root-cause-trace.md specifies trace requirement" \
    "$SKILL_DIR/debug-loop/root-cause-trace.md" \
    "root.cause trace"

# --- Behavior 4: Trace evidence types — all five required kinds --------------
check \
    "root-cause-trace.md includes file and line as a trace type" \
    "$SKILL_DIR/debug-loop/root-cause-trace.md" \
    "file and line"

check \
    "root-cause-trace.md includes config (configuration key) as a trace type" \
    "$SKILL_DIR/debug-loop/root-cause-trace.md" \
    "configuration key"

check \
    "root-cause-trace.md includes runtime evidence as a trace type" \
    "$SKILL_DIR/debug-loop/root-cause-trace.md" \
    "runtime evidence"

check \
    "root-cause-trace.md includes dependency behavior as a trace type" \
    "$SKILL_DIR/debug-loop/root-cause-trace.md" \
    "dependency behavior"

check \
    "root-cause-trace.md includes data shape as a trace type" \
    "$SKILL_DIR/debug-loop/root-cause-trace.md" \
    "data shape"

# --- Behavior 4a: Stage 4 debugger sub-system integration --------------------
check \
    "debug-loop.md references debug-loop/debugger.md" \
    "$SKILL_DIR/debug-loop.md" \
    "debug-loop/debugger\.md"

check \
    "evidence-map.md includes debugger_session evidence" \
    "$SKILL_DIR/debug-loop/evidence-map.md" \
    "debugger_session"

check \
    "root-cause-trace.md includes debugger_session as a trace type" \
    "$SKILL_DIR/debug-loop/root-cause-trace.md" \
    "debugger_session"

# --- Behavior 4b: Stage 4 hypothesis attempts are bounded -------------------
check \
    "root-cause-trace.md: Stage 4 hypothesis tracing is bounded by MAX_DEBUG_ITERATIONS" \
    "$SKILL_DIR/debug-loop/root-cause-trace.md" \
    "hypothesis_attempt"

# --- Behavior 4c: FLAKY reproduction cannot proceed as confirmed RED evidence
check \
    "reproduction-gate.md: FLAKY does not qualify as confirmed RED evidence" \
    "$SKILL_DIR/debug-loop/reproduction-gate.md" \
    "does not qualify as confirmed RED evidence"

# --- Behavior 5: User resolution required for all evidence conflicts ---------
check \
    "evidence-map.md requires user resolution for all conflicts" \
    "$SKILL_DIR/debug-loop/evidence-map.md" \
    "User resolution is required"

# --- Behavior 6: Unresolved decisions block approval ------------------------
check \
    "debug-loop.md blocks approval when unresolved decisions remain" \
    "$SKILL_DIR/debug-loop.md" \
    "may not be presented for approval"

# --- Behavior 7: Regression failure prevents convergence --------------------
check \
    "debug-loop.md: regression failure prevents convergence" \
    "$SKILL_DIR/debug-loop.md" \
    "regression failure prevents convergence"

# --- Behavior 8: Bounded iterations -----------------------------------------
check \
    "debug-loop.md: MAX_DEBUG_ITERATIONS = 5" \
    "$SKILL_DIR/debug-loop.md" \
    "MAX_DEBUG_ITERATIONS = 5"

# --- Behavior 9: implement-loop handoff schema in handoff-format.md ----------
# (section-level: CONTEXT / WHAT_TO_DO / TESTS / VERIFY / CHECKLIST)
check \
    "handoff-format.md — CONTEXT field" \
    "$SKILL_DIR/debug-loop/handoff-format.md" \
    "CONTEXT"

check \
    "handoff-format.md — WHAT_TO_DO field" \
    "$SKILL_DIR/debug-loop/handoff-format.md" \
    "WHAT_TO_DO"

check \
    "handoff-format.md — TESTS field" \
    "$SKILL_DIR/debug-loop/handoff-format.md" \
    "TESTS"

check \
    "handoff-format.md — VERIFY field" \
    "$SKILL_DIR/debug-loop/handoff-format.md" \
    "VERIFY"

check \
    "handoff-format.md — CHECKLIST field" \
    "$SKILL_DIR/debug-loop/handoff-format.md" \
    "CHECKLIST"

# --- Behavior 10: implement-loop handoff schema in template ------------------
# (section-level: CONTEXT / WHAT_TO_DO / TESTS / VERIFY / CHECKLIST)
check \
    "debug-loop-report.md — CONTEXT field" \
    "$TMPL_DIR/debug-loop-report.md" \
    "CONTEXT"

check \
    "debug-loop-report.md — WHAT_TO_DO field" \
    "$TMPL_DIR/debug-loop-report.md" \
    "WHAT_TO_DO"

check \
    "debug-loop-report.md — TESTS field" \
    "$TMPL_DIR/debug-loop-report.md" \
    "TESTS"

check \
    "debug-loop-report.md — VERIFY field" \
    "$TMPL_DIR/debug-loop-report.md" \
    "VERIFY"

check \
    "debug-loop-report.md — CHECKLIST field" \
    "$TMPL_DIR/debug-loop-report.md" \
    "CHECKLIST"

# --- Behavior 11: Handoff mapped content in handoff-format.md ----------------
check \
    "handoff-format.md — symptom/bug field" \
    "$SKILL_DIR/debug-loop/handoff-format.md" \
    "Bug:"

check \
    "handoff-format.md — RED evidence field" \
    "$SKILL_DIR/debug-loop/handoff-format.md" \
    "RED evidence"

check \
    "handoff-format.md — root cause field" \
    "$SKILL_DIR/debug-loop/handoff-format.md" \
    "Root cause"

check \
    "handoff-format.md — trace field" \
    "$SKILL_DIR/debug-loop/handoff-format.md" \
    "Trace:"

check \
    "handoff-format.md — constraints field" \
    "$SKILL_DIR/debug-loop/handoff-format.md" \
    "constraint"

check \
    "handoff-format.md — tests to write field" \
    "$SKILL_DIR/debug-loop/handoff-format.md" \
    "Tests to write"

check \
    "handoff-format.md — targeted test command field" \
    "$SKILL_DIR/debug-loop/handoff-format.md" \
    "targeted test command"

check \
    "handoff-format.md — full suite command field" \
    "$SKILL_DIR/debug-loop/handoff-format.md" \
    "full suite command"

check \
    "handoff-format.md — regression test field" \
    "$SKILL_DIR/debug-loop/handoff-format.md" \
    "[Rr]egression test"

# --- Behavior 12: Handoff mapped content in template -------------------------
check \
    "debug-loop-report.md — symptom/bug field" \
    "$TMPL_DIR/debug-loop-report.md" \
    "Bug:"

check \
    "debug-loop-report.md — RED evidence field" \
    "$TMPL_DIR/debug-loop-report.md" \
    "RED evidence"

check \
    "debug-loop-report.md — root cause field" \
    "$TMPL_DIR/debug-loop-report.md" \
    "Root cause"

check \
    "debug-loop-report.md — trace field" \
    "$TMPL_DIR/debug-loop-report.md" \
    "Trace:"

check \
    "debug-loop-report.md — constraints field" \
    "$TMPL_DIR/debug-loop-report.md" \
    "constraint"

check \
    "debug-loop-report.md — tests to write field" \
    "$TMPL_DIR/debug-loop-report.md" \
    "Tests to write"

check \
    "debug-loop-report.md — targeted test command field" \
    "$TMPL_DIR/debug-loop-report.md" \
    "targeted test command"

check \
    "debug-loop-report.md — full suite command field" \
    "$TMPL_DIR/debug-loop-report.md" \
    "full suite command"

check \
    "debug-loop-report.md — regression test field" \
    "$TMPL_DIR/debug-loop-report.md" \
    "[Rr]egression test"

# --- Summary -----------------------------------------------------------------
echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]]
