# Example Task

## Context

The toy calculator should return `None` when division by zero is requested.

## What To Do

- Add `divide(a, b)` to `src/calculator.py`.
- Return `None` when `b == 0`.
- Return normal division otherwise.

## Tests

- Add tests for normal division.
- Add a regression test for divide-by-zero.

## Verify

```bash
python3 -m pytest tests/ -v
```

## Checklist

- [ ] RED test failed before implementation
- [ ] Full test suite passed after implementation
- [ ] Coverage reported

