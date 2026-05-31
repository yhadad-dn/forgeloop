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

## Checklist

- [ ] Source check completed
- [ ] RED evidence captured
- [ ] GREEN evidence captured
- [ ] Coverage evidence reported
- [ ] Reviewer gate passed
- [ ] Codex gate passed or repo policy fallback applied
- [ ] User approved commit

