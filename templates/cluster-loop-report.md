# Cluster Allocation Report

**Date:** {YYYY-MM-DD HH:MM}
**Operator:** {username}
**Partition:** {XAI | TEST}

---

## Allocation Map

Surveyed: {timestamp}

| Hostname | Partition | SLURM | Jobs | Processes | Status |
|----------|-----------|-------|------|-----------|--------|
| {hostname} | {partition} | {idle/alloc/drain} | {none / user+job} | {clean / process-name} | {CLEAR / OCCUPIED_SLURM / OCCUPIED_PROCESS / DRAINED / UNREACHABLE} |

Nodes skipped (SSHPASS not set): {list or "none"}

---

## Recommendation

| # | Hostname | Partition | Auth | Score | Status | Blocking Reason |
|---|----------|-----------|------|-------|--------|-----------------|
| 1 | {hostname} | {partition} | {key/password} | {3/3} | {RECOMMENDED} | {— or reason} |

---

## Allocation

**tmux session:** `cluster-{node}-{YYYYMMDD-HHMM}`
**SLURM Job ID:** `{JOBID}`
**Node list:** `{node1,node2}`
**Partition:** `{XAI | TEST}`
**Job name:** `{job-name}`
**Duration:** `{HH:MM:SS}`
**Expires at:** `{datetime}`

Attach to session:
```bash
tmux attach -t cluster-{node}-{YYYYMMDD-HHMM}
```

---

## srun Commands

Interactive shell on allocated node:
```bash
srun --jobid={JOBID} --pty bash
```

Run specific command:
```bash
srun --jobid={JOBID} {your-command}
```

Multi-node:
```bash
srun --jobid={JOBID} -N {n} {your-command}
```

---

## Notes

{Race conditions encountered, nodes skipped, warnings from pre-flight, etc.}
