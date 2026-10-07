#!/usr/bin/env bash
# Verify that cluster-loop skill text enforces required behaviors.
# Each assertion is a grep that must match the specified file.
# Run from anywhere; paths are resolved relative to the repo root.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_DIR="$REPO_ROOT/skills"
TMPL_DIR="$REPO_ROOT/templates"

PASS=0
FAIL=0

check_absent_dir() {
    local desc="$1"
    local dir="$2"
    local pattern="$3"
    if [[ -d "$dir" ]] && ! grep -rqiE -- "$pattern" "$dir"; then
        echo "PASS: $desc"
        PASS=$((PASS + 1))
    else
        echo "FAIL: $desc"
        echo "      dir:     $dir"
        echo "      forbidden pattern: $pattern"
        FAIL=$((FAIL + 1))
    fi
}

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
    "$SKILL_DIR/cluster-loop/SKILL.md" \
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

check \
    "allocate.md prefixes SLURM job name with yhadad_" \
    "$SKILL_DIR/cluster-loop/allocate.md" \
    "yhadad_\\$\\{JOB_NAME\\}"

# --- Behavior 5: Announce step replaces the approval gate -------------------
check \
    "allocate.md has an Announce step" \
    "$SKILL_DIR/cluster-loop/allocate.md" \
    "^## Announce"
check \
    "allocate.md announces node, partition, job name, duration, Israel-time expiry and scancel" \
    "$SKILL_DIR/cluster-loop/allocate.md" \
    "scancel <jobid>"
check \
    "allocate.md allocates only a node the recommender marks free" \
    "$SKILL_DIR/cluster-loop/allocate.md" \
    "only a node the recommender marks free"
check \
    "allocate.md never touches another user's job" \
    "$SKILL_DIR/cluster-loop/allocate.md" \
    "[Nn]ever touch another user's job"
check_absent_dir \
    "cluster-loop no longer waits for a yes before allocating" \
    "$SKILL_DIR/cluster-loop" \
    "Confirm\\? \\[yes/no\\]|Approval Gate"

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

# --- Behavior 8: cluster-loop is out of scope for the explorer agent (REQ-5) --
check_absent_dir \
    "cluster-loop has no explorer references (REQ-5)" \
    "$SKILL_DIR/cluster-loop" \
    "explorer"

# --- Repair: exact job lookup and announce before first use ------------------
check \
    "allocate.md finds the job id by exact job-name match" \
    "$SKILL_DIR/cluster-loop/allocate.md" \
    '\$3==|\$3 ==' 
check \
    "allocate.md announce lists all six fields before any srun or run-wrapper call" \
    "$SKILL_DIR/cluster-loop/allocate.md" \
    "BEFORE any .srun. or run-wrapper call"
check \
    "allocate.md also applies the announce inside implement-loop Stage 0" \
    "$SKILL_DIR/cluster-loop/allocate.md" \
    "implement-loop Stage 0"
check \
    "allocate.md Success Output checklist names the six announce fields" \
    "$SKILL_DIR/cluster-loop/allocate.md" \
    "node, partition, job name, duration, expiry in Israel time, scancel"

# --- Summary -----------------------------------------------------------------
echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]]
