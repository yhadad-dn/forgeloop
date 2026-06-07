# Allocate

Create a tmux session and run `salloc --no-shell` inside it. This keeps the
allocation alive across terminal disconnects.

## Pre-conditions

All of the following must be true before running any command here:

- Pre-flight passed
- Allocation map displayed to user
- Recommendation presented to user
- **User has explicitly confirmed**: node(s), partition, job name, and duration

## Approval Gate

Present this confirmation prompt and wait for explicit user confirmation:

```
Allocating:
  Node(s):    <node-list>
  Partition:  <XAI|TEST>
  Job name:   <job-name>
  Duration:   <HH:MM:SS>

Confirm? [yes/no]
```

**Do not run `tmux new-session` until the user confirms all four fields.**

## Allocation Protocol

### Step 1 — Generate session name

```bash
SESSION="cluster-${NODE}-$(date +%Y%m%d-%H%M)"
```

### Step 2 — Ensure session name is unique

```bash
tmux ls 2>/dev/null | grep -q "^${SESSION}:" && SESSION="${SESSION}-2"
```

### Step 3 — Create tmux session and run salloc

```bash
tmux new-session -d -s "${SESSION}" \
  "salloc --no-shell --job-name='${JOB_NAME}' \
   -p ${PARTITION} -w ${NODE_LIST} -t ${DURATION}"
```

### Step 4 — Poll until state R (timeout 30s)

```bash
for i in $(seq 1 10); do
  JOBID=$(squeue -u $USER -h -o "%i %T %j" | grep "${JOB_NAME}" | awk '$2=="R"{print $1}')
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
4. Prefix the new map with: `"Node was taken. Updated allocation map:"`
5. No error — treat as a normal re-scan, not a failure

## Success Output

```
ALLOCATION CONFIRMED

  tmux session: cluster-<node>-<YYYYMMDD-HHMM>
  SLURM job ID: <JOBID>
  Node list:    <node1,node2,...>
  Partition:    <XAI|TEST>
  Expires at:   <datetime>

To attach:  tmux attach -t cluster-<node>-<YYYYMMDD-HHMM>
To srun:    /cluster-loop srun <JOBID> <command>
```
