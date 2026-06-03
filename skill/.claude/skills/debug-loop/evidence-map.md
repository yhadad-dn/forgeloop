# Stage 2: Evidence Source Map

Run after Stage 1. Run before Stage 3.

## Evidence Priority

Rank evidence in this order:

1. **Runtime evidence**: logs, stack traces, crash dumps, test output — authoritative
   for what is actually happening.
2. **Specs and source contracts**: official docs, repo source files — authoritative
   for what should happen.
3. **Dependency behavior**: version changelogs, dependency source code — authoritative
   for symptoms caused by dependency changes.
4. **Data shape**: unexpected input format, type mismatch, schema gap at a system
   boundary — authoritative when the bug manifests at a data interface.
5. **Generated docs, ADRs, prior AI reviews**: context only, not authoritative.

## Required Output

```text
EVIDENCE_MAP: ESTABLISHED | CONFLICT | INSUFFICIENT
EVIDENCE:
  runtime:
    - source: <log file, test output, stack trace location>
      shows: <what it demonstrates about observed behavior>
  specs_contracts:
    - source: <doc or file:line>
      shows: <what it demonstrates about intended behavior>
  dependency:
    - source: <changelog entry or dependency source location>
      shows: <what it demonstrates>
  data_shape:
    - source: <boundary or interface description>
      shows: <what it demonstrates>
  context_only:
    - source: <location>
      note: <why context only>
CONFLICTS:
  - <conflict description, or "none">
MISSING_EVIDENCE:
  - <gap, or "none">
```

## Handling

- `ESTABLISHED`: proceed to Stage 3.
- `CONFLICT`: stop. **User resolution is required for all conflicts among reproduction
  evidence, runtime traces/logs, dependency behavior, data shape, specs/docs, source
  contracts, and generated/context-only sources.** Present each conflict clearly.
  Ask the user to decide. Do not resolve conflicts autonomously.
- `INSUFFICIENT`: stop. Ask the user to provide additional evidence or to make an
  explicit decision that will stand in for it.
