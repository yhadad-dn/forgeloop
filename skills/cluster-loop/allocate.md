# Allocate

Create a tmux session and run `salloc --no-shell` inside it. This keeps the
allocation alive across terminal disconnects.

## Pre-conditions

All of the following must be true before running any command here:

- Pre-flight passed
- Allocation map built
- Recommendation made, and it marks the node free (idle + no jobs + clean ps)

If the recommender finds no free node, do not allocate. Report that instead.

## Announce

There is no approval step: you may allocate alone, but you MUST tell the user.

- Allocate only a node the recommender marks free. Keep every pre-flight check and
  every recommendation rule.
- Pick partition (`XAI` or `TEST`), job name, and duration (`HH:MM:SS`) by the existing
  defaults.
- Never allocate more than one node unless the task needs it, and say so.
- Never touch another user's job.
- Run the allocation below, then report right away in the reply: node, partition, job
  name, duration, expiry in Israel time, and how to release it (`scancel <jobid>`).
- The reply must contain all six announce fields (node, partition, job name, duration,
  expiry in Israel time, scancel hint) BEFORE any `srun` or run-wrapper call. This
  holds also when the allocation is made inside implement-loop Stage 0.

Claude Code's own permission prompt for `salloc` may still appear. It is separate from
ForgeLoop.

## Allocation Protocol

### Step 1 — Generate session name

```bash
SESSION="cluster-${NODE}-$(date +%Y%m%d-%H%M)"
SLURM_JOB_NAME="yhadad_${JOB_NAME}"
```

### Step 2 — Ensure session name is unique

```bash
tmux ls 2>/dev/null | grep -q "^${SESSION}:" && SESSION="${SESSION}-2"
```

### Step 3 — Create tmux session and run salloc

```bash
tmux new-session -d -s "${SESSION}" \
  "salloc --no-shell --job-name='${SLURM_JOB_NAME}' \
   -p ${PARTITION} -w ${NODE_LIST} -t ${DURATION}"
```

### Step 4 — Poll until state R (timeout 30s)

```bash
for i in $(seq 1 10); do
  # exact job-name match (not grep), newest id first; or take the id from the salloc output
  JOBID=$(squeue -u $USER -h -o "%i %T %j" | awk -v n="${SLURM_JOB_NAME}" '$3==n && $2=="R"{print $1}' | sort -n | tail -1)
  [[ -n "${JOBID}" ]] && break
  sleep 3
done
```

### Step 5 — Verify tmux session still alive

```bash
tmux ls | grep "^${SESSION}:"
```

## Race Condition Handling

If `salloc` exits before reaching state `R` (node was grabbed by another user):

1. `tmux kill-session -t "${SESSION}"` — clean up silently
2. Return to Stage 2 (allocation map): re-scan all nodes automatically
3. Return to Stage 3 (node recommender): re-present updated recommendation
4. Prefix the new map with: `"Node was taken. Updated allocation map:"` (still announce the final allocation)
5. No error — treat as a normal re-scan, not a failure

## Success Output

```
ALLOCATION CONFIRMED (announce this to the user)
(checklist: node, partition, job name, duration, expiry in Israel time, scancel hint,
all in the reply BEFORE any `srun` or run-wrapper call)

  tmux session: cluster-<node>-<YYYYMMDD-HHMM>
  SLURM job ID: <JOBID>
  Node list:    <node1,node2,...>
  Partition:    <XAI|TEST>
  Expires at:   <datetime, Israel time>
  Job name:     <SLURM job name>
  Duration:     <HH:MM:SS>
  Release:      scancel <jobid>

To attach:  tmux attach -t cluster-<node>-<YYYYMMDD-HHMM>
To srun:    /cluster-loop srun <JOBID> <command>
```
