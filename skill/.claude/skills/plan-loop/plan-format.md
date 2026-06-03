# Plan Format

Plans produced by `plan-loop` must follow this format exactly. Omitting a required
section or leaving a placeholder blocks Stage 5 self-check.

---

````markdown
# Plan: {title}

## Goal

{One sentence. Must match REQUIREMENTS_VALIDATION.goal verbatim.}

## User Request Summary

{Verbatim or close paraphrase of the original request. No interpretation or editing.}

## Context

{Background the implementor needs to understand why this plan exists. Every claim must
cite an authoritative source from the Source Map.}

## Reliable Sources

### Authoritative (implementation truth)

| Rank | Name | Location | Covers |
|------|------|----------|--------|
| 1 | {name} | {URL / file:line / citation} | {aspect} |
| 2 | {name} | {URL / file:line / citation} | {aspect} |

### Context-Only (not implementation truth)

| Rank | Name | Location | Note |
|------|------|----------|------|
| 3 | {name} | {URL / file:line / citation} | {why context only} |

## Requirements

- REQ-1: {requirement — cite source or user decision}
- REQ-N: ...

## Non-Goals

- {item, or "none"}

## Constraints

- {item, or "none"}

## Success Criteria

- {criterion}

## Explicit User Decisions

| Decision | User Answer | Resolved in Stage |
|----------|-------------|-------------------|
| {question posed in Stage 3} | {verbatim user answer} | 3 |

## Unresolved Decisions

NONE — plan may not proceed to approval with any entry here.

## Design

{Narrative or structured description of the approach. Every design choice must cite a
requirement (REQ-N), an authoritative source, or an explicit user decision. No
autonomous choices permitted.}

## Files / Modules

| Action | Path | Purpose |
|--------|------|---------|
| create | {path} | {purpose} |
| modify | {path} | {purpose} |

## Classes / Functions / Signatures

```python
# file: path/to/file.py

def function_name(param: Type) -> ReturnType:
    """One-line docstring."""
    ...
```

{List every public interface introduced or changed. Language-appropriate syntax.}

## Task Breakdown

- TASK-1: {title}
  - Depends on: none
  - Files: {list}
  - REQs covered: REQ-N
  - Source: {authoritative source name}

- TASK-N: ...

## Tests Per Task

| Task | Test file | Test name | What it verifies |
|------|-----------|-----------|-----------------|
| TASK-1 | {path} | {test_name} | {criterion} |

## Verification Commands

```bash
{commands to run after implementation}
```

## Risks / Residual Uncertainty

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| {risk} | low/med/high | {mitigation, or "accepted"} |

## implement-loop Handoff

**Task file**: {path to task file generated from this plan, or "inline below"}

**Acceptance criteria for implement-loop**:
- {criterion derived from requirements and design above}

**Tests to write (TDD)**:
- {test name}: {what it must verify and what source backs it}

**Verification commands**:
```bash
{commands}
```

**Checklist**:
- [ ] Source check completed using sources listed in this plan
- [ ] RED evidence captured
- [ ] GREEN evidence captured
- [ ] Coverage evidence reported
- [ ] Reviewer gate passed
- [ ] Codex gate passed or repo policy fallback applied
- [ ] User approved commit
````

---

## Self-Check Reference (Stage 5)

Before submitting the plan for review, verify:

| Check | Criterion |
|-------|-----------|
| Requirement coverage | Every REQ-N has at least one design element and one test |
| Source traceability | Every design choice cites REQ-N, a source, or a user decision |
| Unresolved decisions | "Unresolved Decisions" section contains only `NONE` |
| No placeholders | No `TODO`, `TBD`, `...`, or `{placeholder}` in the plan |
| Signature consistency | Signatures in "Classes / Functions" match usage in "Task Breakdown" |
| Handoff completeness | "implement-loop Handoff" section is filled and actionable |
