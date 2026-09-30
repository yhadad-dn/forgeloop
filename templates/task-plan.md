# Task Plan

## Context

Describe the relevant system, source of truth, and why this change is needed.

## What To Do

- Acceptance criterion 1
- Acceptance criterion 2

## Tests

- Add or update `tests/...`
- Old behavior should fail before the fix where practical.

## Verify

```bash
python3 -m pytest tests/ -v --tb=short
git diff --check
```

## Run Proof

The real CPU/GPU run that proves the change works (see
`skill/.claude/skills/implement-loop/run-proof.md`). GPU runs go through `cluster-loop`.

```text
RUN_PROOF:
  device: cpu | gpu | not_applicable
  command: python3 scripts/run_example.py --config configs/small.yaml
  cwd: .
  timeout: 00:15:00
  pass_criteria:
    - exit code 0
    - log contains "done" and final metric >= 0.9
  exercises: acceptance criteria 1 and 2
```

## Checklist

- [ ] Source check completed
- [ ] RED evidence captured
- [ ] GREEN evidence captured
- [ ] Coverage evidence reported
- [ ] Clean-code pass completed (tests untouched, suite green)
- [ ] Reviewer gate passed
- [ ] Run-proof gate passed on the declared CPU/GPU target
- [ ] User approved commit

