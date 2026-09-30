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
- `device: gpu` → run inside a SLURM allocation through `cluster-loop`. Ask the user
  for an active job ID, or offer `/cluster-loop` to allocate one (its approval gate
  applies; never allocate without it). Record `RUN_JOBID`.

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

Capture full stdout+stderr to `.claude/run-proofs/<task>-iter${ITER}.log` (create the
directory; never stage or commit it).

CPU:

```bash
cd ${CWD} && timeout ${TIMEOUT_SECONDS} bash -lc '${COMMAND}' \
  > .claude/run-proofs/<task>-iter${ITER}.log 2>&1; echo "exit=$?"
```

GPU (per `cluster-loop/srun-inside.md`; no `--pty` — output must be captured):

```bash
timeout ${TIMEOUT_SECONDS} srun --jobid=${RUN_JOBID} --chdir=${CWD} bash -lc '${COMMAND}' \
  > .claude/run-proofs/<task>-iter${ITER}.log 2>&1; echo "exit=$?"
```

For runs longer than a few minutes, launch inside the allocation's tmux session with
the same redirect and poll the log; do not block on it blindly.

### 3. Judge

Check each `pass_criteria` entry against the log. Every PASS must quote the log line
(or computed value) that proves it. Inferred or assumed results are not evidence.

## Required Output

```text
RUN_PROOF_RESULT:
  overall: PASS | FAIL | ERROR
  device: cpu | gpu
  target: local | job <RUN_JOBID> on <nodelist>
  command: <exact command run>
  exit_code: <n>
  duration: <HH:MM:SS>
  log_path: .claude/run-proofs/<task>-iter<N>.log
  criteria:
    - <criterion>: PASS | FAIL — <quoted log evidence>
  FIX_BRIEF:
    - <what failed, with log excerpt, and the observed vs expected value; or "none">
```

## Verdict Handling

- `PASS`: every criterion passed with quoted evidence.
- `FAIL`: the command ran but a criterion failed (non-zero exit, wrong output, missed
  threshold, crash, OOM in the code under test). Produces a `FIX_BRIEF` → Stage R.
- `ERROR`: the proof could not run for reasons outside the code — allocation not
  `R`/expired, node can't see the tree, GPU not visible, missing dataset or
  credentials. `ERROR` is never a pass and never a reason to change code. Stop and
  ask the user (re-allocate, fix environment), then rerun the same proof.
- Timeout: report the last log lines and ask the user whether it is a hang in the
  changed code (→ `FAIL`) or an undersized budget (→ rerun with a longer timeout).
  Do not decide autonomously.
