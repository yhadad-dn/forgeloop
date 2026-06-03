# Debug Report: {bug title}

**Status:** {In Progress | Approved | Handed Off}
**Date:** {YYYY-MM-DD}
**Report path:** {this file's path}

---

## Symptom

**Observed:** {what happens}
**Expected:** {what should happen}
**Environment:** {version, OS, config, dependency versions}
**Reproduction inputs:** {exact steps or inputs}
**Constraints:** {what cannot be changed, or "none"}
**Success criteria:** {what "fixed" looks like}

## Evidence Map

| Type | Source | Shows |
|------|--------|-------|
| runtime | {log / test / trace reference} | {what it demonstrates} |
| spec/contract | {doc or file:line} | {what it demonstrates} |
| dependency | {changelog or source location} | {what it demonstrates} |
| data shape | {boundary or interface} | {what it demonstrates} |

Context-only sources: {list or "none"}

Conflicts: {description or "none"}

## Reproduction (RED Evidence)

**Type:** {failing_test | failing_command | log_trace | manual_repro}
**Description:** {what was done to reproduce}

```
{captured output}
```

**Deterministic:** {true | false | unknown}

## Root-Cause Trace

**Selected root cause:** {description}

**Trace evidence:**
- Type: {file_line | config | runtime_evidence | dependency_behavior | data_shape}
- Location: {file:line, config key, log reference, dependency version, or boundary}
- Supports: {how this evidence supports the hypothesis}

**Ruled out alternatives:**
- {alternative}: {reason ruled out, or "none"}

**Confidence:** {high | medium | low}
**Residual uncertainty:** {remaining unknown, or "none"}

## Unresolved Decisions

NONE — debug report may not be presented for approval with any entry here.

---

## implement-loop Handoff

### CONTEXT

Bug: {one-sentence symptom description}

Environment: {version, OS, config, dependency versions}

RED evidence: {type and reference — test name, command, or log location}

Root cause: {selected root cause}

Trace: {evidence type and location — file:line, config key, log reference,
dependency version, or data boundary}

Confidence: {high | medium | low}

Residual uncertainty: {any remaining unknown, or "none"}

### WHAT_TO_DO

Fix the traced root cause. Do not change behavior beyond what is needed to correct
the defect.

- {fix description, scoped strictly to the traced root cause}
- {any additional constraint from symptom validation}

### TESTS

Write or update tests that:

- Prove the bug is fixed (RED before fix, GREEN after fix).
- Guard against recurrence (regression tests committed alongside the fix).

Tests to write:
- {test name}: {what it verifies} — cite RED evidence and root-cause trace.

### VERIFY

```bash
{targeted test command that exercises the fix}
{full suite command}
{repro command to confirm the original symptom is gone}
```

### CHECKLIST

- [ ] Source check completed using evidence sources in this report
- [ ] RED evidence was present before fix
- [ ] GREEN evidence captured after fix
- [ ] Coverage evidence reported
- [ ] Regression tests committed alongside fix
- [ ] Reviewer gate passed
- [ ] Codex gate passed or repo policy fallback applied
- [ ] User approved commit
