# Stage 4: Root-Cause Trace

Run only after RED evidence is confirmed (Stage 3: `REPRODUCTION: CONFIRMED`).

## Hypothesis Protocol

1. List candidate hypotheses ranked by likelihood given the RED evidence and evidence
   map.
2. For each hypothesis, require root-cause trace evidence to at least one of:
   - **file and line**: exact location in source code where the defect lives.
   - **config**: configuration key, environment variable, or flag whose value causes
     the behavior.
   - **runtime evidence**: log line, stack frame, or trace entry that directly
     implicates the hypothesis.
   - **dependency behavior**: version changelog entry or dependency source showing a
     regression or breaking API change.
   - **data shape**: unexpected input format, type mismatch, or schema gap at a system
     boundary that the code does not handle.
3. Eliminate alternative hypotheses before selecting one. Document why each alternative
   was ruled out.
4. If evidence contradicts the leading hypothesis, record it, revise the ranking, and
   repeat.

## Required Output

```text
ROOT_CAUSE: TRACED | UNRESOLVED | MULTIPLE
HYPOTHESES:
  - rank: 1
    hypothesis: <description>
    trace_evidence:
      type: file_line | config | runtime_evidence | dependency_behavior | data_shape
      location: <file:line, config key, log reference, dependency version, or boundary>
      supports: <how this evidence supports the hypothesis>
    ruled_out_alternatives:
      - <alternative hypothesis>: <reason ruled out, or "none">
SELECTED_ROOT_CAUSE: <selected hypothesis text>
CONFIDENCE: high | medium | low
RESIDUAL_UNCERTAINTY: <remaining unknown, or "none">
```

## Iteration Bound

Stage 4 hypothesis tracing is bounded by `MAX_DEBUG_ITERATIONS`. Track attempts with
`hypothesis_attempt` (incremented each time a hypothesis is revised and re-evaluated).
If `hypothesis_attempt` reaches `MAX_DEBUG_ITERATIONS` without returning
`ROOT_CAUSE: TRACED`, write a divergence report to
`.claude/debug-reports/divergence-reports/` and stop. Do not continue past the bound.

## Gate

- Do not proceed to Stage 5 until `ROOT_CAUSE: TRACED`.
- `UNRESOLVED`: stop. Ask the user for additional evidence or an explicit decision.
- `MULTIPLE`: if two or more root causes are equally supported by evidence, ask the
  user to prioritize before proceeding.
- `CONFIDENCE: low` must be noted as a risk in the handoff.

## Prohibition

Do not select a root cause without trace evidence. "The bug is probably in X" is not
a root-cause trace. Trace evidence must be cited specifically.
