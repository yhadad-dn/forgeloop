# Node Recommender

Score and rank nodes from the allocation map. Present clear recommendations before
any allocation action.

## Scoring Criteria

All three must be met for a node to be `RECOMMENDED`:

| Criterion | Check | Score |
|-----------|-------|-------|
| SLURM idle | `sinfo` state = `idle` | +1 |
| No squeue jobs | `squeue -w <hostname>` returns empty | +1 |
| Clean ps | SSH `ps aux` shows no non-SLURM processes | +1 |

**Score 3/3 → `RECOMMENDED`**
**Score 1–2/3 → `PARTIAL`** (show which criteria failed and why)
**Score 0/3 → `UNAVAILABLE`**

## Recommendation Table

Present sorted by score descending. Partition and auth type shown for each node:

```
RECOMMENDATION — <timestamp>

| # | Hostname           | Partition | Auth     | Score | Status        | Blocking Reason              |
|---|--------------------|-----------|----------|-------|---------------|------------------------------|
| 1 | amd-mi355x-des2-1  | XAI       | key      | 3/3   | RECOMMENDED ✅ | —                            |
| 2 | amd-mi355x-des2-2  | TEST      | key      | 3/3   | RECOMMENDED ✅ | —                            |
| 3 | amd-mi355x-ses2-1  | XAI       | password | 2/3   | PARTIAL ⚠️    | Dirty ps: proc X (user Y)    |
| 4 | amd-mi355x-1       | XAI       | key      | 0/3   | UNAVAILABLE ❌ | SLURM alloc; job 12345 jsmith|
```

## Tiebreaker Rules

When two nodes have equal score:
1. Prefer key-auth nodes (more reliable SSH, no SSHPASS dependency)
2. Prefer DELL chassis (des2-*) when the job is a benchmark (different perf profile)
3. Otherwise order by hostname alphabetically

## Edge Cases

- **No RECOMMENDED nodes**: show PARTIAL nodes with their blocking reasons and suggest
  checking back later or coordinating with the team.
- **All UNAVAILABLE**: display the full map with occupants and suggest waiting.
- **Node surveyed as CLEAR but partition is wrong**: note the partition mismatch —
  still show it but mark it as `WRONG_PARTITION` for the requested allocation.
