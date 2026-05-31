# Review Gates

## Stage B: Internal Reviewer Gate

Build the authoritative changed file list from git:

```bash
git diff --name-only > /tmp/files_tracked.txt
git diff --cached --name-only >> /tmp/files_tracked.txt
sort -u /tmp/files_tracked.txt -o /tmp/files_tracked.txt
git ls-files --others --exclude-standard > /tmp/files_untracked.txt
cat /tmp/files_tracked.txt /tmp/files_untracked.txt | sort -u > /tmp/files_authoritative.txt
```

Reject any path your repo marks as a generated result or forbidden artifact.

Capture:

- task context and checklist;
- source-check summary;
- developer summary;
- RED/GREEN evidence;
- TEST_COVERAGE;
- tracked diff;
- untracked file contents.

Review with these focuses:

| Reviewer | Focus |
|---|---|
| correctness | logic, edge cases, regressions, source/spec alignment |
| security | unsafe subprocess, filesystem, network, secrets |
| performance | hot-path allocations and avoidable recomputation |
| standards | repo conventions, constants, generated artifact guards |
| slop | dead code, shallow tests, empty comments, premature abstractions |

Classify:

- `BLOCKING`: correctness issue, security issue, violated acceptance criterion, wrong
  source claim, or missing regression coverage for a correctness-sensitive change.
- `NON_BLOCKING`: style, minor maintainability, minor performance.

Blocking findings become `FIX_BRIEF`. Do not proceed to Stage C until Stage B passes.

## Stage C: Codex CLI Gate

Run an independent Codex review after Stage B passes. This gate is required by default.
If your repo cannot use Codex, document an explicit fallback policy before running
ForgeLoop; do not silently treat Codex as optional.

Prompt contract:

```text
OVERALL: PASS | FAIL
BLOCKING_FINDINGS:
  - <severity>: <file:line> — <issue> — <required fix>
NON_BLOCKING_FINDINGS:
  - <severity>: <file:line> — <issue>
CHECKLIST_RESULTS:
  - Check N: PASS | FAIL — <reason>
FIX_BRIEF:
  - <exact change, or "none">
```

Suggested command:

```bash
codex exec review \
  -m "gpt-5.5" \
  --output-last-message ".claude/codex_verdicts/verdict_iter${ITER}.md" \
  - < /tmp/codex_prompt_iter${ITER}.txt
```

Adapt the model name and command to your Codex installation.

Verdict handling:

- Accept only a verdict whose first line is `OVERALL: PASS` or `OVERALL: FAIL`.
- Require a `FIX_BRIEF` section.
- Retry malformed or empty output once.
- Treat unavailable CLI, authentication failure, unsupported model, or denied approval as
  `codex_overall = ERROR`.
- If retry also errors, write a divergence report.
