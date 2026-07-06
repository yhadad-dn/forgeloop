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
   - **debugger_session**: captured DAP/pdb session (frames, locals, exception at the
     hypothesized defect site) — location is the path to the
     `debugger-session-{N}-red.json` file.
3. Eliminate alternative hypotheses before selecting one. Document why each alternative
   was ruled out.
4. If evidence contradicts the leading hypothesis, record it, revise the ranking, and
   repeat.

## Debugger Evidence (Steps 4.1 and 4.2)

Read `debug-loop/debugger.md` for the full protocol. Only Stage 4 invokes the
debugger; Stage 3 is never modified by it.

- **Step 4.1 — RED session**: after pre-flight (`DEBUGGER_PREFLIGHT: READY`),
  launch the Stage 3 reproduction command (same cwd, env, args) under the
  debugger and run `scripts/dap_client.py --mode red` with breakpoints at the
  hypothesized defect site. RED is confirmed only when the stop is reached
  (`BREAKPOINT_HIT` or `EXCEPTION_CAUGHT`) and the process fails. `NO_STOP`
  means the hypothesis site was never reached — revise the hypothesis
  (increments `hypothesis_attempt`).
- **Step 4.2 — GREEN session**: apply the minimal provisional fix to a temporary
  patched workspace, rerun the same reproduction command with
  `dap_client.py --mode green`, and confirm `status: CLEAN_EXIT`. Delete the
  temp workspace afterwards; it is never staged or committed.
- Map the RED session file into `trace_evidence` as `type: debugger_session`
  with `location` set to the session JSON path (never a string sentinel).

## Required Output

```text
ROOT_CAUSE: TRACED | UNRESOLVED | MULTIPLE
HYPOTHESES:
  - rank: 1
    hypothesis: <description>
    trace_evidence:
      type: file_line | config | runtime_evidence | dependency_behavior | data_shape | debugger_session
      location: <file:line, config key, log reference, dependency version, boundary, or debugger-session path>
      supports: <how this evidence supports the hypothesis>
    ruled_out_alternatives:
      - <alternative hypothesis>: <reason ruled out, or "none">
SELECTED_ROOT_CAUSE: <selected hypothesis text>
CONFIDENCE: high | medium | low
RESIDUAL_UNCERTAINTY: <remaining unknown, or "none">
debugger_evidence:   # optional; present when Steps 4.1/4.2 ran
  red_session: <path to debugger-session-N-red.json (DAP) or debugger-session-N-red-pdb.json (pdb fallback)>
  green_session: <path to debugger-session-N-green.json (DAP) or debugger-session-N-green-pdb.json (pdb fallback)>
  red_status: BREAKPOINT_HIT | EXCEPTION_CAUGHT | NO_STOP | FALLBACK_PDB
  green_status: CLEAN_EXIT | FAILED
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
