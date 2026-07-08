#!/usr/bin/env bash
# Verify that the debug-loop debugger sub-system skill text enforces required
# behaviors. Each assertion is a grep that must match (or must not match) the
# specified file. Run from anywhere; paths are resolved relative to repo root.

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

check_absent() {
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
        echo "FAIL: $desc"
        echo "      file:              $file"
        echo "      forbidden pattern: $pattern"
        FAIL=$((FAIL + 1))
    else
        echo "PASS: $desc"
        PASS=$((PASS + 1))
    fi
}

# --- Check 1: debugger.md exists ----------------------------------------------
check \
    "debug-loop/debugger.md exists" \
    "$SKILL_DIR/debug-loop/debugger.md" \
    "dap_client"

# --- Check 2: pre-flight status block defined ---------------------------------
check \
    "debugger.md defines DEBUGGER_PREFLIGHT" \
    "$SKILL_DIR/debug-loop/debugger.md" \
    "DEBUGGER_PREFLIGHT"

# --- Check 3: RED session block defined ---------------------------------------
check \
    "debugger.md defines DEBUGGER_RED" \
    "$SKILL_DIR/debug-loop/debugger.md" \
    "DEBUGGER_RED"

# --- Check 4: GREEN session block defined --------------------------------------
check \
    "debugger.md defines DEBUGGER_GREEN" \
    "$SKILL_DIR/debug-loop/debugger.md" \
    "DEBUGGER_GREEN"

# --- Check 5: pdb fallback documented ------------------------------------------
check \
    "debugger.md documents the pdb fallback" \
    "$SKILL_DIR/debug-loop/debugger.md" \
    "pdb fallback"

# --- Check 6: Go dispatch via dlv ----------------------------------------------
check \
    "debugger.md dispatches Go targets to dlv" \
    "$SKILL_DIR/debug-loop/debugger.md" \
    "dlv"

# --- Check 7: root-cause-trace.md allows debugger_session evidence -------------
check \
    "root-cause-trace.md includes debugger_session as a trace evidence type" \
    "$SKILL_DIR/debug-loop/root-cause-trace.md" \
    "debugger_session"

# --- Check 8: root-cause-trace.md carries debugger_evidence block --------------
check \
    "root-cause-trace.md defines the debugger_evidence output block" \
    "$SKILL_DIR/debug-loop/root-cause-trace.md" \
    "debugger_evidence"

# --- Check 9: evidence-map.md ranks debugger_session evidence ------------------
check \
    "evidence-map.md includes debugger_session evidence" \
    "$SKILL_DIR/debug-loop/evidence-map.md" \
    "debugger_session"

# --- Check 10: debug-loop.md references the debugger sub-file ------------------
check \
    "debug-loop.md references debug-loop/debugger.md" \
    "$SKILL_DIR/debug-loop.md" \
    "debug-loop/debugger\.md"

# --- Check 11: v2 wording — stale v1 phrase removed ----------------------------
check_absent \
    "debug-loop.md no longer contains stale v1 phrase 'does not edit code'" \
    "$SKILL_DIR/debug-loop.md" \
    "does not edit code"

# --- Check 11b: no predictable /tmp exit-code paths in the launch guidance -----
check_absent \
    "debugger.md does not recommend predictable /tmp/debug-exit paths" \
    "$SKILL_DIR/debug-loop/debugger.md" \
    "/tmp/debug-exit"

# --- Check 11c: no predictable /tmp pdb transcript paths ------------------------
check_absent \
    "debugger.md does not recommend predictable /tmp/debugger-session paths" \
    "$SKILL_DIR/debug-loop/debugger.md" \
    "/tmp/debugger-session"

# --- Check 11d: mktemp templates are portable (no suffix after the X's) ---------
check_absent \
    "debugger.md mktemp templates are suffix-free (BSD/macOS compatible)" \
    "$SKILL_DIR/debug-loop/debugger.md" \
    "XXXXXX\."

# --- Check 12: review gates accept debugger_session ----------------------------
check \
    "review-gates.md accepts debugger_session as trace evidence" \
    "$SKILL_DIR/debug-loop/review-gates.md" \
    "debugger_session"

# --- Check 13: report template accepts debugger_session ------------------------
check \
    "debug-loop-report.md accepts debugger_session as trace evidence" \
    "$TMPL_DIR/debug-loop-report.md" \
    "debugger_session"

# --- Check 14: DAP client ships inside the installable payload ------------------
check \
    "dap_client.py is part of the skill payload (skills/debug-loop/)" \
    "$SKILL_DIR/debug-loop/dap_client.py" \
    "class DAPSession"

# --- Check 15: debugger.md invokes the shipped client, not a repo-only path -----
check \
    "debugger.md references the shipped debug-loop/dap_client.py" \
    "$SKILL_DIR/debug-loop/debugger.md" \
    "debug-loop/dap_client\.py"

# --- Check 15b: repo-only invocation must not creep back into the commands ------
check_absent \
    "debugger.md does not invoke the repo-only scripts/dap_client.py path" \
    "$SKILL_DIR/debug-loop/debugger.md" \
    "python3 scripts/dap_client"

# --- Check 16 (functional): installer delivers dap_client.py --------------------
# Fresh target dir: install.sh's overwrite guard runs before its --dry-run
# branch, so a stray .claude under a shared path would fail this spuriously.
DRYRUN_TARGET="$(mktemp -d)"
if bash "$REPO_ROOT/scripts/install.sh" --dry-run "$DRYRUN_TARGET" 2>/dev/null \
        | grep -q "skills/debug-loop/dap_client\.py"; then
    echo "PASS: install.sh --dry-run lists skills/debug-loop/dap_client.py"
    PASS=$((PASS + 1))
else
    echo "FAIL: install.sh --dry-run lists skills/debug-loop/dap_client.py"
    FAIL=$((FAIL + 1))
fi
rmdir "$DRYRUN_TARGET" 2>/dev/null || true

# --- Summary -------------------------------------------------------------------
echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]]
