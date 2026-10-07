# Run-Proof Gate

Stage C proves the change works by running it for real, on the device the task names.
Tests passing in Stage A show the code is consistent with its tests; this gate shows
the code actually runs end to end and produces the expected result.

## RUN_PROOF Task Section

Every task must carry a `RUN_PROOF` section:

```text
RUN_PROOF:
  device: cpu | gpu | not_applicable
  command: <exact command, as it would be typed from cwd>
  cwd: <directory, default repo root>
  timeout: <HH:MM:SS>
  pass_criteria:
    - exit code 0
    - <observable signal, e.g. "log contains 'epoch 3/3'", "final loss < 2.0",
       "output matches reference within atol=1e-3">
  exercises: <which acceptance criteria / changed code paths this run covers>
```

Rules:

- `pass_criteria` must include at least one signal beyond exit code 0 that is
  specific to the change. "It didn't crash" alone is not proof.
- `device: not_applicable` is allowed only when the change has no runnable production
  code (docs, config comments, test-only changes). It needs a one-line justification
  and explicit user confirmation at Stage 0.
- If the section is missing or incomplete, stop at Stage 0 and ask the user for it.
  Do not invent a command or criteria.
- The command and criteria are fixed for the whole loop. Weakening them (changing the
  command, loosening thresholds, shrinking the input, adding skip flags) to get a pass
  is `PLAN_AMENDMENT_REQUIRED`, never a repair.

## Stage 0: Target Setup

- `device: cpu` → run locally, from `cwd`.
- `device: gpu` → run inside a SLURM allocation through `cluster-loop`. Reuse
  `RUN_JOBID` if one exists. Otherwise allocate through `/cluster-loop` (its Announce
  step: allocate a free node, then tell the user node, partition, job name, duration,
  expiry, and `scancel <jobid>`). This gate never asks the user for a job id. Record
  `RUN_JOBID`.

## Stage C: Run

### 1. Pre-run checks (GPU)

```bash
squeue -j ${RUN_JOBID} -h -o "%T"          # must be R
srun --jobid=${RUN_JOBID} bash -lc 'rocm-smi --showuse 2>/dev/null || nvidia-smi'
```

Verify the node sees the current working tree, not a stale copy — compare hashes of
every changed file from the Stage B authoritative list:

```bash
sha256sum $(cat /tmp/files_authoritative.txt) > /tmp/run_proof_local.sha
srun --jobid=${RUN_JOBID} bash -lc "cd ${REPO_ROOT} && sha256sum -c -" < /tmp/run_proof_local.sha
```

Any mismatch or missing path → sync the tree (or ask the user how) before running.
A run against stale code is not proof.

### 2. Execute

Start the run only with `forgeloop_run.py` (rules in `run-card.md`; never a hand-built
background command). If `CLAUDE_PLUGIN_ROOT` is empty, do not guess a path: tell the
user to run the helper in their own terminal from the installed plugin directory
(`~/.claude/plugins/cache/forgeloop/forgeloop/<version>/skills/implement-loop/forgeloop_run.py`),
then stop.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/implement-loop/forgeloop_run.py" start --task <task> --device cpu|gpu [--jobid ${RUN_JOBID}] \
  --cwd ${CWD} --timeout ${TIMEOUT} --iter ${ITER} [--criteria-file <json>] -- ${COMMAND}
```

`--criteria-file` is required when the task defines `pass_criteria` (see `run-card.md`).

For `gpu` the helper runs the command with `srun --jobid` inside the allocation (see
`../cluster-loop/srun-inside.md`). It writes the log `.claude/run-proofs/<task>-iter${ITER}.log`
and the record `.claude/run-proofs/<task>-iter${ITER}.json` (never stage or commit them).
A run without a record that has a terminal state is not counted as proof.

Show the RUN CARD, follow the update cadence in `run-card.md`, and poll with
`python3 "${CLAUDE_PLUGIN_ROOT}/skills/implement-loop/forgeloop_run.py" status --record <record>`; do not block on the run blindly. Check
the cluster with `python3 ../cluster-loop/cluster_status.py --job ${RUN_JOBID} --log <log path>`:
a stale log, idle GPUs, or an ETA past the allocation's expiry are reasons to stop and
ask the user before the run wastes the allocation. At the end show
`python3 "${CLAUDE_PLUGIN_ROOT}/skills/implement-loop/forgeloop_run.py" card --record <record> --kind finish`.

### 3. Judge

Check that the record's `command` equals the `RUN_PROOF` command text and that its
`command_sha256` equals the sha256 of that text (the finish card prints both); a
mismatch means the run is not the contracted one and is not proof. Check each `pass_criteria` entry against the log and the run record (the finish card
lists the exit code and state; the script never judges). Every PASS must quote the log line
(or computed value) that proves it. Inferred or assumed results are not evidence.

## Required Output

```text
RUN_PROOF_RESULT:
  overall: PASS | FAIL | ERROR
  device: cpu | gpu
  target: local | job <RUN_JOBID> on <nodelist>
  command: <exact command run>
  state: passed | failed | timeout | lost | error   # from the record; anything else is invalid
  exit_code: <n>
  duration: <HH:MM:SS>
  log_path: .claude/run-proofs/<task>-iter<N>.log
  record_path: .claude/run-proofs/<task>-iter<N>.json   # terminal state required
  criteria:
    - <criterion>: PASS | FAIL — <quoted log evidence>
  FIX_BRIEF:
    - <what failed, with log excerpt, and the observed vs expected value; or "none">
```

## Verdict Handling

- Only state `passed` can support an overall PASS. `failed` is `FAIL`; `lost` and `error`
  are `ERROR`; `timeout` is handled below. A record whose state is not one of the five
  (or is still `starting`/`running`) is not proof.
- `PASS`: state `passed` and every criterion passed with quoted evidence.
- `FAIL`: the command ran but a criterion failed (non-zero exit, wrong output, missed
  threshold, crash, OOM in the code under test). Produces a `FIX_BRIEF` → Stage R.
- `ERROR`: the proof could not run for reasons outside the code — allocation not
  `R`/expired, node can't see the tree, GPU not visible, missing dataset or
  credentials. `ERROR` is never a pass and never a reason to change code. Stop and
  ask the user (re-allocate, fix environment), then rerun the same proof.
- Timeout: report the last log lines and ask the user whether it is a hang in the
  changed code (→ `FAIL`) or an undersized budget (→ rerun with a longer timeout).
  Do not decide autonomously.
