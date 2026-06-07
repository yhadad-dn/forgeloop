#!/usr/bin/env bash
# Verify that cluster-loop skill text enforces required behaviors.
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
    if grep -qE -- "$pattern" "$file"; then
        echo "PASS: $desc"
        PASS=$((PASS + 1))
    else
        echo "FAIL: $desc"
        echo "      file:    $file"
        echo "      pattern: $pattern"
        FAIL=$((FAIL + 1))
    fi
}

# --- Required files exist ----------------------------------------------------
check \
    "cluster-loop.md exists with sub-command routing" \
    "$SKILL_DIR/cluster-loop.md" \
    "cluster-loop map"

check \
    "cluster-loop/preflight.md exists" \
    "$SKILL_DIR/cluster-loop/preflight.md" \
    "SSHPASS"

check \
    "cluster-loop/allocation-map.md exists" \
    "$SKILL_DIR/cluster-loop/allocation-map.md" \
    "squeue"

check \
    "cluster-loop/node-recommender.md exists" \
    "$SKILL_DIR/cluster-loop/node-recommender.md" \
    "idle"

check \
    "cluster-loop/allocate.md exists" \
    "$SKILL_DIR/cluster-loop/allocate.md" \
    "tmux new-session"

check \
    "cluster-loop/srun-inside.md exists" \
    "$SKILL_DIR/cluster-loop/srun-inside.md" \
    "--jobid"

check \
    "templates/cluster-loop-report.md exists" \
    "$TMPL_DIR/cluster-loop-report.md" \
    "Allocation Map"

# --- Behavior 1: Pre-flight checks Tailscale and tmux -----------------------
check \
    "preflight.md verifies Tailscale VPN reachability" \
    "$SKILL_DIR/cluster-loop/preflight.md" \
    "Tailscale|100\.109\.84\.43"

check \
    "preflight.md verifies tmux is installed" \
    "$SKILL_DIR/cluster-loop/preflight.md" \
    "tmux -V"

check \
    "preflight.md verifies SSHPASS for password nodes" \
    "$SKILL_DIR/cluster-loop/preflight.md" \
    "SSHPASS"

# --- Behavior 2: Allocation map checks both SLURM and non-SLURM processes ---
check \
    "allocation-map.md uses squeue to check SLURM jobs" \
    "$SKILL_DIR/cluster-loop/allocation-map.md" \
    "squeue"

check \
    "allocation-map.md uses ps aux to check non-SLURM processes" \
    "$SKILL_DIR/cluster-loop/allocation-map.md" \
    "ps aux"

# --- Behavior 3: Recommender uses all three criteria ------------------------
check \
    "node-recommender.md scores on SLURM idle state" \
    "$SKILL_DIR/cluster-loop/node-recommender.md" \
    "idle"

check \
    "node-recommender.md scores on no squeue jobs" \
    "$SKILL_DIR/cluster-loop/node-recommender.md" \
    "[Nn]o squeue"

check \
    "node-recommender.md scores on clean ps" \
    "$SKILL_DIR/cluster-loop/node-recommender.md" \
    "[Cc]lean ps"

# --- Behavior 4: Allocate uses tmux + salloc --no-shell ---------------------
check \
    "allocate.md creates tmux session automatically" \
    "$SKILL_DIR/cluster-loop/allocate.md" \
    "tmux new-session"

check \
    "allocate.md uses salloc --no-shell" \
    "$SKILL_DIR/cluster-loop/allocate.md" \
    "salloc.*--no-shell"

# --- Behavior 5: Approval gate before allocation ----------------------------
check \
    "allocate.md requires user confirmation before salloc" \
    "$SKILL_DIR/cluster-loop/allocate.md" \
    "[Cc]onfirm|[Aa]pproval"

# --- Behavior 6: Race condition triggers automatic re-scan ------------------
check \
    "allocate.md re-scans automatically on race condition" \
    "$SKILL_DIR/cluster-loop/allocate.md" \
    "re.scan|re.survey"

# --- Behavior 7: srun runs inside active allocation via --jobid -------------
check \
    "srun-inside.md uses --jobid to run inside active allocation" \
    "$SKILL_DIR/cluster-loop/srun-inside.md" \
    "--jobid"

# --- Summary -----------------------------------------------------------------
echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]]
