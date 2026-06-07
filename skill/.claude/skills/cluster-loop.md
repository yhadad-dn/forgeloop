---
name: cluster-loop
description: >
  SLURM cluster allocation skill. Surveys the full allocation map, recommends
  available nodes (idle + no jobs + clean ps), allocates via salloc --no-shell
  inside an auto-created tmux session, and runs srun inside the active allocation.
  Invoke with: /cluster-loop [map|recommend|allocate|srun]
---

# Cluster Loop

## Goal

Manage SLURM cluster allocations through a disciplined, gate-driven flow:

```text
pre-flight -> allocation map -> recommendation -> approval gate
          -> tmux + salloc -> confirm -> srun
```

## Sub-Commands

- `/cluster-loop` — full pipeline (pre-flight through confirmation)
- `/cluster-loop map` — build and display the allocation map only
- `/cluster-loop recommend` — map + scored node recommendation
- `/cluster-loop allocate <node> <partition> <duration>` — allocate a specific node
- `/cluster-loop srun <jobid> <command>` — srun inside an active allocation

## Reference Files

- `codex-model-check.md`
- `cluster-loop/preflight.md`
- `cluster-loop/allocation-map.md`
- `cluster-loop/node-recommender.md`
- `cluster-loop/allocate.md`
- `cluster-loop/srun-inside.md`

## Constants

- **Node map**: `~/.claude/projects/-home-dn-research-KV-Compacting/memory/cluster_node_map.md`
- **Reports**: `.claude/cluster-reports/`
- **Tailscale subnet router**: `100.109.84.43`
- **tmux session name**: `cluster-<node>-<YYYYMMDD-HHMM>`

## Stage 0: Load Request

Parse the sub-command and arguments. If invoked with no sub-command, run the full
pipeline. If invoked with a sub-command, jump directly to the corresponding stage.

Initialize:

```text
job_name = ""
partition = ""
node_list = []
duration = ""
jobid = ""
tmux_session = ""
allocation_map = {}
recommendation = []
CODEX_MODEL = ""
CODEX_BASE_COMMAND = ""
```

## Stage 0.1: Codex Model Check

Read `codex-model-check.md`.

Spawn a sub-agent to verify the current recommended Codex CLI model. Record
`CODEX_MODEL` and `CODEX_BASE_COMMAND` in loop state.

## Stage 1: Pre-flight

Read `cluster-loop/preflight.md`.

Verify Tailscale VPN, SSH access to a key-auth node, tmux installation, and SSHPASS
availability. Abort with a clear message on any hard failure. Do not proceed to Stage 2
until pre-flight passes.

## Stage 2: Allocation Map

Read `cluster-loop/allocation-map.md`.

Survey every node via `sinfo`, `squeue`, and SSH `ps aux`. Build a full per-node
status table. Display it to the user before any further action.

## Stage 3: Recommendation

Read `cluster-loop/node-recommender.md`.

Score each node on three criteria: SLURM idle, no squeue entries, clean ps.
Present a sorted recommendation table with explicit reasoning per node.

## Stage 4: Approval Gate

Ask the user to confirm before any allocation:

- Which node(s) to allocate
- Partition (`XAI` or `TEST`)
- Job name
- Duration (format: `HH:MM:SS`)

**Do not proceed to Stage 5 without explicit user confirmation of all four fields.**

## Stage 5: Allocate

Read `cluster-loop/allocate.md`.

Create a named tmux session and run `salloc --no-shell` inside it. Poll until the
job reaches state `R`. Handle race conditions by re-scanning automatically.

## Stage 6: Confirm

When allocation is confirmed active, display:

- tmux session name
- SLURM job ID
- Node list
- Partition
- Expiry time
- How to attach: `tmux attach -t <session>`
- How to srun: `/cluster-loop srun <jobid> <command>`

## Stage 7: srun (on request)

Read `cluster-loop/srun-inside.md`.

Run the user's command inside the active salloc via `--jobid`. Verify the job is
still in state `R` before issuing srun.
