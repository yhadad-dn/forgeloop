# Run Card

Rules for long runs. The helper is `forgeloop_run.py` (in this directory). It starts the
run detached, keeps a run record, and prints status and cards. It never judges the pass
criteria; you fill each one with PASS or FAIL and a quoted log line.

Call it only as `python3 "${CLAUDE_PLUGIN_ROOT}/skills/implement-loop/forgeloop_run.py" <command>`. If
`CLAUDE_PLUGIN_ROOT` is empty, do not guess a path. Tell the
user to run the helper in their own terminal from the installed plugin directory
(`~/.claude/plugins/cache/forgeloop/forgeloop/<version>/skills/implement-loop/forgeloop_run.py`),
then stop.

## Runs in scope

- GPU runs.
- Test suites expected to take over one hour.

Other runs follow the normal rules.

## Rules

1. **Start** the run only with the helper (`forgeloop_run.py start`). Never build a background
   command by hand. When the task defines `pass_criteria`, pass them with `--criteria-file`
   (a JSON list); without it the card has no checklist. Secrets go by
   environment variable, not by argument: the argument list is hashed and shown on the card (secrets
   stripped), and the real one lives only until the run launches.

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/implement-loop/forgeloop_run.py" start --task <task> --device cpu|gpu \
     [--jobid <id>] --cwd <dir> --timeout HH:MM:SS [--iter N] [--criteria-file F] -- <command>
   ```

2. **Show the RUN CARD** that `start` prints, as printed.
3. **Updates**:
   - If the run is the only thing happening: every 10 minutes. Call ScheduleWakeup with
     `delaySeconds=600`; when it fires, run
     `python3 "${CLAUDE_PLUGIN_ROOT}/skills/implement-loop/forgeloop_run.py" status --record <record>` and report
     one line. Repeat until the run finishes. Stop the cadence as soon as the user sends
     other work.
   - If other work is happening: report only when the user asks.
4. **At the end** show `python3 "${CLAUDE_PLUGIN_ROOT}/skills/implement-loop/forgeloop_run.py" card --record <record> --kind finish`.
   Fill each criterion with PASS/FAIL and a quoted log line. The script never judges.
   Only state `passed` can support an overall PASS. `failed` is FAIL. `timeout`, `lost`
   and `error` are never a pass: for `timeout` ask the user (hang = FAIL, undersized
   budget = rerun longer); `lost` and `error` are ERROR (the run could not be observed or
   launched), rerun after asking the user. `⚠ supervisor lost, child still running` is
   not terminal: keep waiting and check again. Compare the card's `command sha256` with
   the sha256 of the task's `RUN_PROOF` command text.
5. **Flow chart**: the run step is 🔄 with a bar from the record (progress from `status`).
   It becomes ✅ only when the criteria pass.
6. **Idle checkpoint**: a ScheduleWakeup call replaces any pending one, including the
   session-continuity idle checkpoint (`delaySeconds=3420`, 57 minutes). In the
   same turn in which you show the finish card, call ScheduleWakeup(3420) again; when the
   user sends other work during the cadence, stop the cadence and re-arm in that turn.

## Run record

`.claude/run-proofs/<task>-iter<N>.json` (log beside it, same name with `.log`). Never
stage or commit these files. A run without a record that has a terminal state (`passed`,
`failed`, `timeout`, `lost`, `error`) is not counted as proof.
