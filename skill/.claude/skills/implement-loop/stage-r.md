# Stage R: Repair Plan

Stage R runs only for iterations after the first.

Convert the failed gate's `FIX_BRIEF` into this plan before any developer writes code:

```text
Repair Plan — iteration {N}

Source: {stage_b|stage_c}

Blocking findings to fix:
{copy every blocking finding verbatim}

Root cause:
{why the implementation missed each finding; cite files/functions/tests}

Exact fix scope:
Allowed files:
- {paths needed by blocking findings}
Forbidden files:
- Any unrelated file
- Generated result artifacts
- Later-batch files unless explicitly allowed
Edits:
- {file}: {exact intended edit}

Scope check:
IN_SCOPE | PLAN_AMENDMENT_REQUIRED

Verification:
{exact commands}
```

Rules:

- Do not drop or soften any blocking finding.
- Do not include non-blocking cleanup.
- Stop with `PLAN_AMENDMENT_REQUIRED` if scope expands or requirements conflict.

