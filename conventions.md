# ForgeLoop Conventions

## Status reports

Use this format only when the user asks for a status (not for every reply):

1. **Context**: open with one or two sentences on where things stand.
2. **Done**: list what was done in plain words. Never refer to work by stage
   letters, iteration numbers, REQ/TASK IDs, plan rows, waves, or milestone
   names; those are for your own tracking.
3. **Progress**: show it visually, in whatever form fits: progress bars, a small
   table, a tree, or a timeline.
4. **Cluster**: if the status involves cluster work (an allocation, a GPU run, a
   running job), run `python3 {CLUSTER_STATUS} --job <id> [--log <run log>]` (or
   `--mine`) and show its output in a code block. Never assemble node, GPU, or job
   numbers by hand or from memory. Explain each ⚠ warning in one line: what it
   means for the run and what you propose.
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
4. **Status**: the status-report format from **Progress** onward (progress, cluster
   block if cluster work is involved). Skip its context and done list.
5. **Close**: **Next:**, **What's stopping us:**, **From you:**, as in a status report.

## Times

Show all times in Israel time (Asia/Jerusalem) only: no UTC in status reports,
tables, or ETAs. Logs may stay in UTC; convert when reporting.
