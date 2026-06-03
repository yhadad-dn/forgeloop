# Stage 2: Reliable-Source Map

Run after Stage 1 completes. Run before Stage 3 and Stage 4.

## Source Priority

Rank sources in this order:

1. Published paper, specification, or official documentation explicitly identified by
   the user or the request.
2. The repo's primary spec or source files for implementation contracts and current
   behavior.
3. Generated docs, plans, ADRs, and prior AI reviews — context only, not implementation
   authority.
4. Unverified references, blog posts, or undated material — context only, lowest trust.

If authoritative sources (rank 1 or 2) disagree with each other on the same point,
return `SOURCE_MAP: CONFLICT`.

## Required Output

```text
SOURCE_MAP: ESTABLISHED | CONFLICT | NO_AUTHORITY_BLOCKED
SOURCES:
  authoritative:
    - name: <short label>
      location: <URL, file:line, or citation>
      authority_rank: 1|2
      covers: <what aspect of the plan>
  context_only:
    - name: <short label>
      location: <URL, file:line, or citation>
      authority_rank: 3|4
      note: <why context only>
CONFLICTS:
  - <conflict description, or "none">
MISSING_AUTHORITY:
  - <gap description, or "none">
```

## Handling

- `ESTABLISHED`: proceed to Stage 3.
- `CONFLICT`: stop. Present the conflict clearly to the user. Ask for an explicit
  decision. Do not choose between conflicting sources autonomously. Record the user's
  decision as an explicit user decision in Stage 3.
- `NO_AUTHORITY_BLOCKED`: stop when a key design question has no authoritative source.
  Ask the user to provide one or to make an explicit decision that will stand in for it.

## Prohibition

During Stage 4 plan generation, Claude must not discover or rely on sources that are
not listed in the approved `SOURCE_MAP`. Any source found necessary during Stage 4 that
is not already in the map requires returning to Stage 2, adding the source, and getting
user acknowledgement before continuing.
