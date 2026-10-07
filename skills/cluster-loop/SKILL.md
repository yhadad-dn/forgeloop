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
pre-flight -> allocation map -> recommendation -> announce
          -> tmux + salloc -> confirm -> srun
```

## Sub-Commands

- `/cluster-loop` — full pipeline (pre-flight through confirmation)
- `/cluster-loop map` — build and display the allocation map only
- `/cluster-loop recommend` — map + scored node recommendation
- `/cluster-loop allocate <node> <partition> <duration>` — allocate a specific node
- `/cluster-loop srun <jobid> <command>` — srun inside an active allocation
- `/cluster-loop status [jobid] [--log <path>]` — everything relevant about the job's nodes

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
- ForgeLoop agents (`developer`, `refactorer`, `source-check`,
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

## Stage 4: Announce

No approval step: you may allocate alone, but you MUST tell the user. Allocate only a
node the recommender marks free. Pick partition (`XAI` or `TEST`), job name, and duration
(`HH:MM:SS`) from the existing defaults. If the recommender finds no free node, do not
allocate; report that. Never allocate more than one node unless the task needs it, and
say so. Never touch another user's job. Right after the allocation, report node,
partition, job name, duration, expiry in Israel time, and how to release it
(`scancel <jobid>`). See `allocate.md`. Claude Code may show its own permission prompt
for `salloc`; that is separate from ForgeLoop.

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

Then show the output of `python3 cluster_status.py --job <jobid>` (Stage 8) so the
user sees the allocated GPUs are free: no foreign processes or containers, and
memory near zero.

## Long runs

GPU runs and test suites over one hour start only with
`python3 "${CLAUDE_PLUGIN_ROOT}/skills/implement-loop/forgeloop_run.py" start ...`; if `CLAUDE_PLUGIN_ROOT` is
empty, do not guess a path, tell the user. The update cadence and finish card are in
`../implement-loop/run-card.md`.

## Stage 8: Status (on request, and in every status report)

Run the status script that ships in this skill's directory:

```bash
python3 cluster_status.py --job <jobid> [--log <run log>]   # or --mine
```

Default view, a "what can I use" block: `🟢 Free now` (free GPUs per node, most
free first), `🔴 Full` (fully busy nodes; full is normal, never a warning), one
`🧑‍💻 Your job` line per job (id, SLURM name, node, end time) with a `does:` line of
evidence (step names, GPU-holding process command lines with secrets stripped,
containers, tmux session, log name; `(no evidence)` if none), and a `⚠️` line only
for a real problem (disk, stuck job, node down, ...) that belongs to a `--job` run or to
a node that run uses. `--mine` alone shows no `⚠️` lines; `--warnings` shows every
warning (all jobs and nodes), for when the user asks for cluster health. Show it as printed; in a
status report add the job name and a four-word purpose sentence per job from the
`does:` evidence, never beyond it. `--plain` prints the previous default (one row
per job with progress bar, finish time, expiry, state; one line per node; warnings).
`--detail` adds per-GPU numbers, processes, containers, and disk (both show all
warnings). `--json` adds `does_evidence` per job and is complete: each warning
(`warning_details`) and job carries `relevant`.

- Finish time: a printed ETA or tqdm remaining time from the log, else a rate
  estimate from overall progress and the run step's elapsed time (marked `~`),
  else `—` with the reason. Nested counters (`epoch 2/3 step 1840/2760`) give
  overall progress.
- Logs: pair `--log <path>` or `--log docker:<container>` with each `--job`.
  Without `--log`: a batch job's `StdOut`, or the container the job (or its chained
  predecessor) started, is used automatically.
- Nodes are probed over ssh from the SLURM host: a plain `srun` step runs in its own
  cgroup and sees no GPUs. Fallback: `srun --overlap --gres=gpu:<job's count>`.
- Ownership: a GPU workload that predates the job holding its node is checked
  against SLURM accounting (`sacct`): ours if the job holding the node when it
  started is ours (the `job_name` filter, else the same user), else foreign, naming
  that job. Without accounting it is "possibly foreign", never silently ours.
- Settings: `slurm_host` and `job_name` in the repo's `.claude/forgeloop.md` or in
  `~/.claude/forgeloop/forgeloop.md`; `--mine` then applies `job_name` (the `dn`
  account is shared).
- States, most severe first: node drained/down, killed before done (finishes after
  expiry), stalled (log silent 10+ min), errors in log, OOM risk, foreign process,
  disk full, expires soon, then `✓ on track (<spare>)`.
- Speed: one SLURM round trip, parallel node probes (15 s timeout each), a reused
  ssh connection, a per-node cache of how to read the GPUs, and a 20 s result cache
  (`--fresh` bypasses). `--timing` shows where time goes.

- Set `slurm_host` in `.claude/forgeloop.md` (or `FORGELOOP_SLURM_HOST`) when SLURM
  commands must run over ssh.
- Show the output verbatim in a code block, then explain each ⚠ warning in one line.
- `--json` gives the same data for automation; `--raw` appends raw probe output
  when a field looks wrong.
- Exit codes: 0 healthy, 1 warnings present (only warnings that are shown count), 2 job not found.

## Stage 7: srun (on request)

Read `srun-inside.md`.

Run the user's command inside the active salloc via `--jobid`. Verify the job is
still in state `R` before issuing srun.
