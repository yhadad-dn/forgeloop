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

- `../codex-model-check/SKILL.md`
- `preflight.md`
- `allocation-map.md`
- `node-recommender.md`
- `allocate.md`
- `srun-inside.md`

## Paths, Agents, and Repo Configuration

- File references in this skill are relative to this skill's directory; `../<skill>/`
  points at a sibling ForgeLoop skill.
- ForgeLoop agents (`developer`, `refactorer`, `source-check`, `tester`,
  `reviewer-*`) are named `forgeloop:<agent>` when ForgeLoop is installed as a plugin,
  and `<agent>` when installed into a repo's `.claude/`.
- Paths like `.claude/plans/` refer to the target repo, never the plugin directory.
- Before Stage 0, read `.claude/forgeloop.md` in the target repo if it exists. Its
  values (node map path, subnet router, partitions) override the defaults below.

## Constants

- **Node map**: `$FORGELOOP_CLUSTER_NODE_MAP` if set, else the `node_map` value in
  `.claude/forgeloop.md`, else `~/.claude/forgeloop/cluster_node_map.md`. If none
  exists, stop and ask the user for the node map location.
- **Reports**: `.claude/cluster-reports/`
- **Tailscale subnet router**: `100.109.84.43` (DriveNets default; override with
  `subnet_router` in `.claude/forgeloop.md`)
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

Read `../codex-model-check/SKILL.md`.

Follow the protocol in `../codex-model-check/SKILL.md`: probe `gpt-5.5` locally first; only
run a web-search sub-agent if the probe fails. Record `CODEX_MODEL` and
`CODEX_BASE_COMMAND` in loop state.

## Stage 1: Pre-flight

Read `preflight.md`.

Verify Tailscale VPN, SSH access to a key-auth node, tmux installation, and SSHPASS
availability. Abort with a clear message on any hard failure. Do not proceed to Stage 2
until pre-flight passes.

## Stage 2: Allocation Map

Read `allocation-map.md`.

Survey every node via `sinfo`, `squeue`, and SSH `ps aux`. Build a full per-node
status table. Display it to the user before any further action.

## Stage 3: Recommendation

Read `node-recommender.md`.

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

Read `allocate.md`.

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

Read `srun-inside.md`.

Run the user's command inside the active salloc via `--jobid`. Verify the job is
still in state `R` before issuing srun.
