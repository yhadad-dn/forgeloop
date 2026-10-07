# ForgeLoop Conventions

## Status reports

Use this format only when the user asks for a status (not for every reply):

1. **Context**: open with one or two sentences on where things stand.
2. **Done**: list what was done in plain words. Never refer to work by stage
   letters, iteration numbers, REQ/TASK IDs, plan rows, waves, or milestone
   names; those are for your own tracking.
3. **Progress**: show two parts, in this order:
   - **Flow chart** of the process, as text in a code block: arrows for order,
     branches for substeps, parallel substeps on separate lines. Scope: the current
     task with all its subtasks, plus the parent stage it sits in and the stages
     directly before and after it. Collapse older finished work into one line
     (`earlier: picker 0.15.0 ✅`) only when it matters for context.
     Marks after a step: ✅ done and tested (name the proof in the report),
     🔄 in progress, ⬜ not started. Name steps in plain words (same rule as **Done**).
   - **Progress bars** for the current task only: one line per group with a count
     ("3 of 3 features built and tested"), plus an Overall line. A bar is ✅ steps
     divided by all steps, never a guess; 🔄 and ⬜ steps do not count.

   ```
   STATUS: ForgeLoop 0.16.0 (durable default, tmux close, STE default)
   FLOW
    earlier: picker 0.15.0 ✅
    Plan ✅ ─► Build ─┬─ Picker + helper ✅ ─► Setup items ✅ ─► Docs ✅ ─► Pushed ✅
                      └─ 0.16.0 ─┬─ Durable default on VM ✅ ─► tmux close at end ✅
                                 └─ STE default on ✅
             ─► Review 🔄 ─► GPU run 🔄 ████░░ ─► Push 0.16.0 ⬜ ─► Live checks ⬜
   PROGRESS (current task: release 0.16.0)
    Code        ██████████ 100%   3 of 3 features built and tested
    Release     ░░░░░░░░░░   0%   0 of 1 (push)
    Overall     ██████░░░░  57%   8 of 14 steps (🔄 and ⬜ not counted)
   ```
4. **Cluster**: if the status involves cluster work (an allocation, a GPU run, a
   running job), run `python3 {CLUSTER_STATUS} --job <id> [--log <run log>]` (or
   `--mine`) and show its output in a code block. Never assemble node, GPU, or job
   numbers by hand or from memory. Show the block as the script prints it. Right
   after the code block, for each `🧑‍💻 Your job` line add the job name and one
   four-word sentence on what it does, from its `does:` evidence (`purpose unknown`
   if none; never guess beyond it). Explain each ⚠ in one line: meaning and proposal.
   Warnings: only for the run in scope; `--warnings` only when asked for health.
   **Runs** (GPU runs, test suites over one hour): start only with `forgeloop_run.py
   start`; chart them 🔄 with a bar. Rules: ${CLAUDE_PLUGIN_ROOT}/skills/implement-loop/run-card.md.
5. **Close** with three bolded items:
   - **Next:** what happens next.
   - **What's stopping us:** each blocker (cluster, failing check, dependency,
     pending decision) and who or what can remove it, or "nothing".
   - **From you:** what the user has to decide or provide, or "nothing".

## Summaries

Use when the user asks for a summary. Five parts, in order:

1. **Project**: one or two sentences on what the project is and why it exists.
2. **Assignment**: one or two sentences on the current task: its goal, where it
   came from (plan, request, bug), and what counts as done.
3. **Milestones**: the major steps completed so far, oldest first, as bullets or a
   one-line flow (`plan approved → allocator built → GPU proof passed`). Each gives
   the outcome, not the activity, plus its evidence when there is one (a commit, a
   test, a run result). Only milestones that changed where the assignment stands.
4. **Status**: the status-report format from **Progress** onward (flow chart, progress
   bars, cluster block if cluster work is involved). Skip its context and done list.
5. **Close**: **Next:**, **What's stopping us:**, **From you:**, as in a status report.

## Times

Show all times in Israel time (Asia/Jerusalem) only: no UTC in status reports,
tables, or ETAs. Logs may stay in UTC; convert when reporting.
