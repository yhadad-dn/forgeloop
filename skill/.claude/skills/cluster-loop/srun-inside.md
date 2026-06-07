# srun Inside Active Allocation

Run a command inside an existing `salloc` allocation. Always use `--jobid` to target
the specific allocation rather than relying on ambient environment.

## Pre-conditions

Verify the allocation is still active:

```bash
squeue -j ${JOBID} -h -o "%T"
```

Must return `R`. If it returns nothing or `PD`/`CG`:
> "Allocation ${JOBID} is no longer active. Re-allocate with `/cluster-loop allocate`."

Do not issue srun on an expired or non-running allocation.

## Commands

### Interactive single-node (with PTY)

```bash
srun --jobid=${JOBID} --pty ${COMMAND}
```

Example — open a bash shell on the allocated node:
```bash
srun --jobid=${JOBID} --pty bash
```

### Multi-node parallel

```bash
srun --jobid=${JOBID} -N ${N_NODES} ${COMMAND}
```

### Background (non-interactive, fire and forget)

```bash
srun --jobid=${JOBID} ${COMMAND} &
```

### Docker workload on allocated node

```bash
srun --jobid=${JOBID} --pty docker run --rm \
  --device=/dev/kfd --device=/dev/dri \
  <image> <command>
```

## Notes

- If `--pty` causes "not a terminal" errors in non-interactive contexts, drop `--pty`
  and pipe output explicitly.
- `srun` inherits the node list from the `--jobid` allocation automatically — no need
  to specify `-w` again.
- For long-running workloads, run `srun` inside the tmux session itself:
  `tmux send-keys -t ${SESSION} "srun --jobid=${JOBID} ${COMMAND}" Enter`
