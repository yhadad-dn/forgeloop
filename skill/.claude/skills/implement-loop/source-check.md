# Reliable-Source Check

Run before any implementation work.

## Source Priority

1. Published paper, specification, or official documentation explicitly identified by the
   task.
2. The repo's primary spec or source files for implementation contracts.
3. Generated docs, plans, ADRs, and prior AI reviews as context only.

If authoritative sources disagree, return `CONFLICT`.

## Required Output

```text
SOURCE_CHECK: PASS | CONFLICT | NO_SOURCE_BLOCKED | NOT_APPLICABLE
CAPTURED_AT_UTC:
- <timestamp>
SOURCE_USED:
- <source, section/page/file:line>
SOURCE_OF_TRUTH_NOTICE:
- Authoritative for implementation: <sources>
- Context only, not truth: <sources>
SUMMARY:
- <short conclusion>
CONFLICTS:
- <conflict or "none">
REPO_CONTRACT_NOTES:
- <file:line notes or "none">
```

## Handling

- `PASS`: continue.
- `NOT_APPLICABLE`: continue and state why.
- `CONFLICT`: stop and ask the user to decide.
- `NO_SOURCE_BLOCKED`: stop when the task depends on missing external authority.
- Timeout, crash, malformed output, or missing source access: treat as blocked.

