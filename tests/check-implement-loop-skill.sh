#!/usr/bin/env bash
# Verify that implement-loop skill text enforces required behaviors.
# Each assertion is a grep that must match the specified file.
# Run from anywhere; paths are resolved relative to the repo root.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_DIR="$REPO_ROOT/skills"
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

# --- Required files exist (verified via meaningful content pattern) -----------
check \
    "implement-loop.md exists" \
    "$SKILL_DIR/implement-loop/SKILL.md" \
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
    "implement-loop/run-proof.md exists" \
    "$SKILL_DIR/implement-loop/run-proof.md" \
    "RUN_PROOF"

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

# --- Behavior 2: Stage C is a real CPU/GPU run proof, not Codex --------------
check \
    "implement-loop/run-proof.md exists with RUN_PROOF_RESULT output" \
    "$SKILL_DIR/implement-loop/run-proof.md" \
    "RUN_PROOF_RESULT"

check \
    "implement-loop.md Stage C is the run-proof gate" \
    "$SKILL_DIR/implement-loop/SKILL.md" \
    "Stage C: Run-Proof Gate"

check \
    "implement-loop.md blocks at Stage 0 when RUN_PROOF is missing" \
    "$SKILL_DIR/implement-loop/SKILL.md" \
    "never invent a command"

check \
    "run-proof.md routes GPU runs through a SLURM allocation" \
    "$SKILL_DIR/implement-loop/run-proof.md" \
    "srun --jobid"

check \
    "run-proof.md verifies the node sees the current working tree" \
    "$SKILL_DIR/implement-loop/run-proof.md" \
    "sha256sum -c"

check \
    "run-proof.md requires quoted log evidence per criterion" \
    "$SKILL_DIR/implement-loop/run-proof.md" \
    "quote the log line"

check \
    "run-proof.md: ERROR is never a pass" \
    "$SKILL_DIR/implement-loop/run-proof.md" \
    "never a pass"

check \
    "run-proof.md: weakening the proof is a plan amendment" \
    "$SKILL_DIR/implement-loop/run-proof.md" \
    "PLAN_AMENDMENT_REQUIRED"

check \
    "reports.md convergence report includes run-proof evidence" \
    "$SKILL_DIR/implement-loop/reports.md" \
    "Run proof:"

check \
    "task-plan.md template has a RUN_PROOF section" \
    "$TMPL_DIR/task-plan.md" \
    "RUN_PROOF:"

check_absent \
    "implement-loop/review-gates.md has no Codex gate" \
    "$SKILL_DIR/implement-loop/review-gates.md" \
    "codex"

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

# --- Behavior 5: Stage A.5 clean-code pass before reviewers --------------------
check \
    "implement-loop.md defines Stage A.5 clean-code pass" \
    "$SKILL_DIR/implement-loop/SKILL.md" \
    "Stage A.5: Clean-Code Pass"

check \
    "implement-loop.md main loop runs A.5 before Stage B" \
    "$SKILL_DIR/implement-loop/SKILL.md" \
    "Stage A.5: clean-code pass \\(never fails the loop\\)"

check \
    "clean-code.md requires test files to stay byte-identical" \
    "$SKILL_DIR/implement-loop/clean-code.md" \
    "sha256sum -c"

check \
    "clean-code.md snapshots without staging (throwaway index)" \
    "$SKILL_DIR/implement-loop/clean-code.md" \
    "GIT_INDEX_FILE"

check \
    "clean-code.md restores failing changes from the snapshot" \
    "$SKILL_DIR/implement-loop/clean-code.md" \
    "git restore --source"

check \
    "clean-code.md protects source-mirroring code" \
    "$SKILL_DIR/implement-loop/clean-code.md" \
    "mirrors an authoritative source"

check \
    "clean-code.md honors simplify-ignore markers" \
    "$SKILL_DIR/implement-loop/clean-code.md" \
    "simplify-ignore-start"

check \
    "clean-code.md emits separate feature and refactor patches" \
    "$SKILL_DIR/implement-loop/clean-code.md" \
    "refactor.patch"

check \
    "refactorer agent exists and never edits tests" \
    "$REPO_ROOT/agents/refactorer.md" \
    "Never edit test files"

check \
    "refactorer agent credits its upstream sources" \
    "$REPO_ROOT/agents/refactorer.md" \
    "addyosmani/agent-skills"

check \
    "reports.md convergence report includes the clean-code pass" \
    "$SKILL_DIR/implement-loop/reports.md" \
    "Clean-code pass:"

check \
    "review-gates.md hands the refactor patch to reviewers" \
    "$SKILL_DIR/implement-loop/review-gates.md" \
    "CLEAN_CODE_RESULT"

# --- Principle: implement-loop only strengthens correctness -------------------
check \
    "implement-loop SKILL.md states the correctness-only-goes-up principle" \
    "$SKILL_DIR/implement-loop/SKILL.md" \
    "Correctness Only Goes Up"

check \
    "implement-loop SKILL.md forbids switching versions mid-task" \
    "$SKILL_DIR/implement-loop/SKILL.md" \
    "Never switch ForgeLoop versions in the middle of a task"

# --- Behavior 6: reviewer-hygiene merge (performance+standards+slop) -----------
check \
    "reviewer-hygiene agent exists and labels findings by merged facet" \
    "$REPO_ROOT/agents/reviewer-hygiene.md" \
    "\\[standards\\|slop\\|performance\\]"

check \
    "reviewer-hygiene retains the standards forbidden-artifact check" \
    "$REPO_ROOT/agents/reviewer-hygiene.md" \
    "forbidden files"

check \
    "reviewer-hygiene retains the slop dead-code check" \
    "$REPO_ROOT/agents/reviewer-hygiene.md" \
    "dead code"

check \
    "reviewer-hygiene retains the performance non-blocking-by-default rule" \
    "$REPO_ROOT/agents/reviewer-hygiene.md" \
    "NON_BLOCKING"

check \
    "review-gates.md full gate is three reviewers, not five" \
    "$SKILL_DIR/implement-loop/review-gates.md" \
    "three dispatches instead of the previous five"

# --- Behavior 7: terse one-line reviewer output (measured ~38% fewer output
# tokens on a paired real dispatch; see CHANGELOG) ------------------------------
for name in reviewer-correctness reviewer-security reviewer-hygiene; do
    check \
        "agents/$name.md specifies a one-line-per-finding output format" \
        "$REPO_ROOT/agents/$name.md" \
        "One line per finding"

    check \
        "agents/$name.md's finding format carries BLOCKING/NON_BLOCKING and a fix" \
        "$REPO_ROOT/agents/$name.md" \
        "BLOCKING\\|NON_BLOCKING.*—.*fix"

    check \
        "agents/$name.md bans preamble/summary restating the diff" \
        "$REPO_ROOT/agents/$name.md" \
        "No preamble, no summary"
done

check_deleted() {
    local desc="$1"
    local file="$2"
    if [[ ! -e "$file" ]]; then
        echo "PASS: $desc"
        PASS=$((PASS + 1))
    else
        echo "FAIL: $desc"
        echo "      file should not exist: $file"
        FAIL=$((FAIL + 1))
    fi
}

check_deleted \
    "reviewer-performance.md removed (merged into reviewer-hygiene)" \
    "$REPO_ROOT/agents/reviewer-performance.md"

check_deleted \
    "reviewer-standards.md removed (merged into reviewer-hygiene)" \
    "$REPO_ROOT/agents/reviewer-standards.md"

check_deleted \
    "reviewer-slop.md removed (merged into reviewer-hygiene)" \
    "$REPO_ROOT/agents/reviewer-slop.md"

check_deleted \
    "tester.md removed (unused — no loop ever dispatched it)" \
    "$REPO_ROOT/agents/tester.md"

check_absent \
    "coverage-gate.md no longer names a separate tester agent" \
    "$SKILL_DIR/implement-loop/coverage-gate.md" \
    "tester agent|tester/coverage pass"

# --- Summary -------------------------------------------------------------------
echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]]
