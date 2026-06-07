# Allocation Map

Survey every node in cluster_node_map.md. Build a full per-node status table.

## Per-Node Survey

For each node, run three checks in order:

### 1. SLURM State

```bash
sinfo -n <hostname> --Format=statecompact --noheader
```

Possible states: `idle`, `alloc`, `mix`, `drain`, `down`, `unk`

### 2. Running and Pending Jobs

```bash
squeue -w <hostname> -h -o "%i %u %T %j"
```

Empty output → no jobs on this node.
Non-empty → record each line as a SLURM occupant (job ID, user, state, name).

### 3. Non-SLURM Processes (via SSH)

Key-auth nodes:
```bash
ssh -o BatchMode=yes -o ConnectTimeout=5 dn@<ip> \
  "ps aux --no-header | grep -vE '(sshd|slurmstepd|systemd|ps |grep|bash -c|awk|sed)'"
```

Password nodes (requires `SSHPASS` to be set):
```bash
sshpass -e ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5 dn@<ip> \
  "ps aux --no-header | grep -vE '(sshd|slurmstepd|systemd|ps |grep|bash -c|awk|sed)'"
```

Empty output → clean. Non-empty → list top processes (user, pid, %cpu, command).

If SSH times out: mark the node `UNREACHABLE`.

## Status Classification

| Condition | Status |
|-----------|--------|
| SLURM `idle` + no squeue entries + clean ps | `CLEAR` |
| Has squeue entries in state `R` or `PD` | `OCCUPIED_SLURM` |
| SLURM `idle` but non-empty ps | `OCCUPIED_PROCESS` |
| SLURM state is `alloc`, `mix`, or `drain` | `ALLOCATED` or `DRAINED` |
| SSH timeout or connection refused | `UNREACHABLE` |

## Output Table

Present with `CLEAR` nodes first, then sorted by status:

```
ALLOCATION MAP — <timestamp>

| Hostname           | Partition | SLURM  | Jobs                    | Processes        | Status           |
|--------------------|-----------|--------|-------------------------|------------------|------------------|
| amd-mi355x-des2-1  | XAI       | idle   | none                    | clean            | CLEAR ✅         |
| amd-mi355x-des2-2  | TEST      | idle   | none                    | clean            | CLEAR ✅         |
| amd-mi355x-1       | XAI       | alloc  | 12345 jsmith R benchmark| —                | ALLOCATED ❌     |
| amd-mi355x-2       | XAI       | idle   | none                    | sglang_amd (217G)| OCCUPIED_PROCESS ⚠️|
...
```

Update `last_known_status` and `last_surveyed` in cluster_node_map.md after each
successful survey.
