# Stage 4 Debugger Protocol

Read during Stage 4 (root-cause trace) only. No other stage invokes the debugger.
All debugger commands are issued programmatically through `scripts/dap_client.py`
— there is never a human at a debug console.

The debugger produces hard RED→GREEN proof of a hypothesis:

- **RED session (Step 4.1)**: run the Stage 3 reproduction command against the
  original code with breakpoints at the hypothesized defect site; capture frames,
  locals, and exception state; confirm the failure.
- **GREEN session (Step 4.2)**: apply the minimal provisional fix to a temporary
  patched workspace, rerun the same reproduction command, and confirm
  `status: CLEAN_EXIT`. The temp workspace is deleted afterwards; it is never
  staged or committed.

## Section 1: Pre-flight (`DEBUGGER_PREFLIGHT`)

Run both checks before launching any debugger.

**A. Reproducer check.** Inspect the Stage 3 `REPRODUCTION` block:

- `type: failing_test | failing_command` → extract the runnable command (with its
  cwd, env, and args) and proceed.
- `type: log_trace | manual_repro` → `DEBUGGER_PREFLIGHT: BLOCKED`. Surface this to
  the user and request a `failing_test` or `failing_command` reproduction. Running
  a DAP/pdb session without a deterministic command produces false RED/GREEN proof.

Extract the interpreter: if the reproducer starts with a Python executable (e.g.
`.venv/bin/python`), pass it as `--python-exe`; the default is `python3` and is
only safe when the Stage 3 reproducer also uses the system `python3`. Using a
different interpreter than the reproducer runs in the wrong venv and produces
false RED/GREEN proof.

The `--target-cmd` passed to `dap_client.py` is the reproducer minus the
interpreter. Accepted forms: `path/to/script.py [args]` or `-m module.name [args]`
(covers `-m pytest ...`). Blocked forms (report `DEBUGGER_PREFLIGHT: BLOCKED`, ask
the user for a Python-compatible reproducer): bare console scripts (`pytest`,
`make test`, `uv run`), shell constructs (`VAR=val cmd`, `cmd && cmd2`, redirects),
non-Python interpreters. Never silently translate `pytest` to `-m pytest` — that
substitutes a different interpreter and dependency set than the Stage 3 reproducer.

**B. Language detection and debugger availability.**

| Language | Extension | Debugger | Availability check | Launch command | DAP start request | Fallback |
|---|---|---|---|---|---|---|
| Python | .py | debugpy | `{python_exe} -c "import debugpy"` → exit 0 | `{python_exe} -m debugpy --listen 127.0.0.1:{PORT} --wait-for-client {reproducer_cmd_parts}` | `attach({connect: {host, port}})` | pdb |
| Go | .go | dlv | `dlv version` → exit 0 | `dlv dap --listen 127.0.0.1:{PORT}` (then DAP `launch`) | `launch({mode: "debug"\|"test", program, [args]})` | none — BLOCKED if dlv missing |
| Node.js | .js | — | — | — | — | none — BLOCKED at MVP (CDP protocol differs from DAP; deferred) |

Port selection: default 5678; if the bind fails, increment and retry until a free
port is found; pass the chosen port as `--port`.

Required output block:

```text
DEBUGGER_PREFLIGHT: READY | BLOCKED | FALLBACK_PDB
language: python | go | node
debugger: debugpy | pdb | dlv | none
reproducer_cmd: <Stage 3 command, verbatim>
python_exe: <interpreter extracted from reproducer, or n/a>
blocked_reason: <reason, or "none">
```

`BLOCKED` (exit code 3 from `dap_client.py`) must never enter the pdb fallback —
only exit code 1 (connection failure) does.

## Section 2: RED Session (`DEBUGGER_RED`)

1. Launch the target under the debug server, wrapping it so the real process exit
   code is captured (debugpy attach mode never emits the DAP `exited` event; the
   wrapper file is the exit-code source of record). Create the exit-code file
   with `mktemp` under `.claude/debug-reports/` (gitignored) — a predictable,
   world-writable `/tmp` path could be pre-created or symlinked by another
   local user on a shared host, spoofing false RED/GREEN proof:

   ```bash
   mkdir -p .claude/debug-reports
   exit_code_file="$(mktemp .claude/debug-reports/debug-exit-red.XXXXXX)"
   ( {python_exe} -m debugpy --listen 127.0.0.1:{PORT} --wait-for-client \
       {reproducer_cmd_parts}; echo $? > "$exit_code_file" ) &
   ```

   Use the same cwd and env as the Stage 3 reproduction.

2. Connect and run the session:

   ```bash
   python3 scripts/dap_client.py \
     --host 127.0.0.1 --port {PORT} \
     --breakpoints {file}:{line}[,{file}:{line}...] \
     --output .claude/debug-reports/debugger-session-{N}-red.json \
     --mode red --debugger debugpy \
     --target-cmd "{reproducer_cmd_parts}" \
     --python-exe {python_exe} \
     --exit-code-file "$exit_code_file"
   ```

   The client performs: initialize → attach → wait_for_initialized →
   setBreakpoints → setExceptionBreakpoints (uncaught filters only, selected from
   the adapter's advertised capabilities) → configurationDone → capture stop
   (stackTrace, scopes, variables, exceptionInfo on exception stops) → optional
   `--step-sequence step_over,step_in,step_out` for step execution →
   continue → wait for exit. Entry stops are skipped automatically; only
   `breakpoint` and `exception` stops count as evidence. Secondary stops after
   continue are captured and continued until the process exits.

3. Parse the output JSON. RED is confirmed only when the stop was reached
   (`status: BREAKPOINT_HIT | EXCEPTION_CAUGHT`) AND the process failed
   (`exit_code != 0` or `exception` present). `NO_STOP` (exit code 2) means the
   hypothesis site was never reached — revise the hypothesis and repeat.

For Go: launch `dlv dap --listen 127.0.0.1:{PORT}` and invoke with
`--debugger dlv --program {pkg_or_file} --dlv-mode {debug|test}`. Derive the mode
from the Stage 3 reproducer: `go test ./pkg -run TestFoo` →
`--dlv-mode test --dlv-args "-test.run,TestFoo"` (dlv `mode:"test"` runs the test
binary directly, so the flag is `-test.run`, never `-run`); a binary or
`go run main.go` → `--dlv-mode debug`. `mode:"test"` needs a single resolvable
package path — resolve `./pkg/...` globs to one package or report
`DEBUGGER_PREFLIGHT: BLOCKED`. `--target-cmd` is ignored for dlv. There is no pdb
fallback for Go.

Required output block (recorded in the root-cause trace):

```text
DEBUGGER_RED: BREAKPOINT_HIT | EXCEPTION_CAUGHT | NO_STOP | TIMEOUT | FALLBACK_PDB
session_file: .claude/debug-reports/debugger-session-{N}-red.json
breakpoints: <file:line list>
failure_evidence: <exception type/message, or nonzero exit code>
```

## Section 3: GREEN Session (`DEBUGGER_GREEN`)

1. Apply the minimal provisional fix to a **temporary patched workspace** — e.g. a
   temp copy of the affected module placed on `PYTHONPATH`, or a temp workspace
   tree with the fix applied. Never edit, stage, or commit the real tree. Do NOT
   run the bare target script instead of the reproduction command — that skips the
   test harness/import context and risks false `CLEAN_EXIT`.
2. Launch the debugger against the patched workspace with the **same Stage 3
   reproduction command, cwd, env, and args** as RED (same wrapper pattern with
   a fresh `mktemp` exit-code file, e.g.
   `exit_code_file="$(mktemp .claude/debug-reports/debug-exit-green.XXXXXX)"`),
   and run:

   ```bash
   python3 scripts/dap_client.py \
     --host 127.0.0.1 --port {PORT} \
     --breakpoints {file}:{line} \
     --output .claude/debug-reports/debugger-session-{N}-green.json \
     --mode green --debugger debugpy \
     --target-cmd "{same_reproducer_cmd_parts}" \
     --python-exe {python_exe} \
     --exit-code-file "$exit_code_file"
   ```

3. Confirm `status: CLEAN_EXIT` (exit code 0, no unhandled exception). GREEN
   accepts both paths: breakpoint reached then clean exit, or no stop at all (the
   fix may bypass or delete the fault site).
4. **Delete the temporary patched workspace.** Verify no `/tmp/debug-proof-fix-*`
   or temp workspace remnants remain.
5. If GREEN fails (`status: FAILED`), revise the hypothesis and repeat from the
   RED session.

Required output block (recorded in the handoff CHECKLIST):

```text
DEBUGGER_GREEN: CLEAN_EXIT | FAILED
session_file: .claude/debug-reports/debugger-session-{N}-green.json
temp_workspace_deleted: true
```

## Section 4: pdb fallback (Python only)

Trigger conditions (either):

- pre-flight `{python_exe} -c "import debugpy"` fails, or
- `dap_client.py` exits with code 1 (DAP connection failed after `--retry`
  attempts, default 3 retries with 1s delay).

Exit code 3 (BLOCKED / invalid arguments) must NOT trigger the pdb fallback.
The pdb fallback applies only to Python; Go/dlv targets have no fallback.

Invoke via `dap_client.py --debugger pdb`, which drives `{python_exe} -m pdb`
over stdin and writes structured JSON; it writes the raw combined transcript
beside the JSON output (`{output-minus-.json}-raw.txt`), so with `--output`
under `.claude/debug-reports/` the transcript is gitignored too. Or run the
equivalent manually:

**RED (pdb):**

```bash
mkdir -p .claude/debug-reports
printf "break {file}:{line}\ncontinue\nwhere\npp locals()\nclear {file}:{line}\ncontinue\n" \
  | {python_exe} -m pdb {reproducer_cmd_parts...} \
  > .claude/debug-reports/debugger-session-{N}-red-pdb-raw.txt 2>&1
```

- `clear` before the final `continue` is required: if the target line is in a
  loop, a re-hit at stdin EOF raises `BdbQuit` (nonzero exit) that would be
  misread as target failure.
- No trailing `quit`: quit can interrupt Traceback printing before capture.
- `> file 2>&1` order is required — the reverse (`2>&1 > file`) sends stderr to
  the terminal and misses Traceback output.

RED is accepted (`exit_confirmed: true`) only when BOTH hold:

- **A — breakpoint reached**: the `where` output contains a frame matching the pdb
  frame format `{file}({line})` (e.g. `buggy.py(42)`). Do NOT search for
  `file.py:42` — that matches the "Breakpoint 1 at ..." header, not a real stop.
  No matching frame → treat as `NO_STOP` regardless of exit code; revise the
  hypothesis.
- **B — failure evidence** (at least one): `Traceback` in the raw output; or
  `The program exited via sys.exit().` with parsed `Exit status:` value other than
  `"0"` (handle negative, multi-digit, and non-integer values — never a `[1-9]`
  regex); or the pdb process itself exits nonzero.

Output: `.claude/debug-reports/debugger-session-{N}-red-pdb.json` with
`status: FALLBACK_PDB`, text-parsed `frames`, `exception`, `debugger: pdb`,
`exit_confirmed`. Record `DEBUGGER_RED: FALLBACK_PDB`.

**GREEN (pdb):**

```bash
mkdir -p .claude/debug-reports
printf "continue\nquit\n" \
  | {python_exe} -m pdb {reproducer_cmd_parts...} \
  > .claude/debug-reports/debugger-session-{N}-green-pdb-raw.txt 2>&1
```

`CLEAN_EXIT` requires ALL of: no `Traceback` in the raw output; no
`The program exited via sys.exit().` with non-`"0"` exit status (pdb itself exits
0 even when the target calls `sys.exit(1)`); and the pdb process exits 0.
Otherwise `FAILED`. Output:
`.claude/debug-reports/debugger-session-{N}-green-pdb.json`. Delete the temp
workspace after GREEN.

## Evidence Mapping

- RED session JSON maps into `root-cause-trace.md` as trace evidence
  `type: debugger_session`; the `location` is the session JSON path (never a
  string sentinel).
- Record the session pair in the `ROOT_CAUSE` output's `debugger_evidence` block
  (see `root-cause-trace.md`).
- In the evidence map, `debugger_session` ranks with runtime evidence (rank 1):
  it is a direct observation of running code.

## `dap_client.py` Exit Codes

| Code | Meaning | Action |
|---|---|---|
| 0 | session completed, JSON written | parse JSON |
| 1 | connection failed after retries | pdb fallback (Python only) |
| 2 | RED: no stop before exit, or TIMEOUT | revise hypothesis |
| 3 | invalid arguments / `DEBUGGER_PREFLIGHT: BLOCKED` | surface to user; never pdb fallback |
| 4 | DAP protocol error | inspect stderr; retry once, then surface |

Every wait operation (`wait_for_stop`, `wait_for_exit`) enforces a fresh
per-call deadline from `--timeout` (default 60s). Only the DAP `exited` event is
authoritative for the wire-level exit code; `terminated` is supplementary. When
the adapter closes without `exited` (debugpy attach mode always does), the client
recovers the real process exit code from `--exit-code-file` and records
`exit_code_source: process_wait` in the JSON.
