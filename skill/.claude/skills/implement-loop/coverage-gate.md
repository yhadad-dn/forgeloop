# Coverage Gate

Every Stage A handoff must include:

```yaml
TEST_COVERAGE:
  tests_added_or_changed:
    - path::test_name
  acceptance_criteria_covered:
    - criterion: <short name>
      tests: [path::test_name]
  old_bug_regressions:
    - bug: <old behavior>
      tests: [path::test_name]
  untested_risks:
    - <risk, or "none">
  coverage_numbers:
    module.path: 82.1
  coverage_annotations:
    module.path: undercounted_subprocess|none
  coverage_tooling: available|unavailable|not_run
  coverage_decision: measured_pass|measured_below_threshold_tester_run|unavailable_review_required|not_applicable_no_prod_changes
  test_coverage_tester_report:
    status: not_run|run
    modules_below_threshold: [module.path]
    before_after:
      module.path: {before: 61.2, after: 74.8}
    tests_added_or_changed: [path::test_name]
    command: <command, or n/a>
    output_summary: <summary, or n/a>
    residual_risks: [<risk, or "none">]
```

## Subprocess-Executed Code

Tests that exercise code via subprocess (e.g. CLI integration tests invoking a
script) are invisible to default coverage measurement. Before trusting a low
number for such a module, either enable coverage's subprocess support
(`COVERAGE_PROCESS_START` plus parallel mode) or set
`coverage_annotations.<module.path>: undercounted_subprocess` alongside the
measured figure — so reviewers neither treat an under-measured module as below
threshold nor excuse a genuinely low one. Modules without subprocess
undercounting carry `none`.

## Threshold Policy

- If changed production modules have measured coverage below 70%, run a tester/coverage
  pass for those modules.
- If all measured changed production modules are at or above 70%, pass.
- If no production modules changed, mark not applicable.
- If tooling is unavailable, report that explicitly and let reviewers decide whether the
  targeted tests are enough for the risk.

Tune the threshold per repo.

