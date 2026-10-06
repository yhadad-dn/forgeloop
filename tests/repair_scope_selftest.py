#!/usr/bin/env python3
"""RUN_PROOF self-test for the per-iteration git-diff scope mechanism.

Unlike an earlier version of this script, this one does not hand-reimplement
the snapshot/diff logic in Python. Instead it extracts the literal bash
fenced code block and inline backtick commands from
skills/implement-loop/clean-code.md ("Snapshot and Scope") and
skills/implement-loop/stage-r.md (previous-iteration file list computation)
and executes that exact text via `bash -c` against a disposable scratch git
repo. A bug in the protocol's bash (e.g. a stray "plus untracked files"
union reintroducing stale leftovers) therefore shows up here directly,
instead of being silently absent because the test reimplemented the
*intended* behavior rather than the documented one.

Three scenarios:

1. clean-code.md's iteration N>1 scope diff (REQ-2): must list exactly the
   files touched between two persisted tree snapshots, and must NOT pick up
   an untracked leftover file that is present, unchanged, in both snapshots.
1b. clean-code.md's own production-file filter vs. its own artifacts: an
    artifact file written between the two snapshots (exactly how
    `.claude/clean-code/*` files appear per clean-code.md's own Record-step
    ordering) must be excluded by clean-code.md's own filter, not just
    stage-r.md's copy of it.
1c. stage-r.md's forbidden-path filter vs. a *different* `.claude/` artifact
    type: a Stage B follow-up file under `.claude/plans/followups/` (per
    review-gates.md) written in the same inter-snapshot window must also be
    excluded -- proving the filter excludes the whole `.claude/` namespace
    generally, not just the one `.claude/clean-code/` path that scenario 1b
    already covers.
2. stage-r.md's previous-iteration file list (REQ-3): same tree-to-tree diff,
   plus the "keep only production files" filter, parsed from the doc's own
   pattern list, applied to strip test files and generated artifacts.
3. stage-r.md's missing-tree-file fallback (REQ-6): when the persisted tree
   file for either TREE_A5_prev1 or TREE_A5_prev2 is missing, the computed
   list must be empty and clean_code_scope_fallback must be true.

4. SKILL.md Stage 0's literal `assert_clean_tree` bash block: an unrelated
   modified tracked file and an unrelated untracked file must make it exit 1
   and be listed.
5. The same block must NOT block on leftovers from a prior run under
   `.claude/clean-code/`, `.claude/run-proofs/`, `.claude/plans/` (exit 0), both
   with no `.gitignore` and with this repo's real `.gitignore` (where plain
   `git status --porcelain` is empty and `snapshot_tree()` omits them).

6. The same block must NOT block on untracked files under any `.claude/` directory
   (6a: root, nested, spaces in the name; from root and from a subdirectory), and must
   still block on a modified tracked `.claude` file (6b), a newly staged `.claude` file
   (6c), look-alike paths `.claude.bak/` and `foo.claude/` (6d) and a dirty source file
   next to untracked `.claude` files (6e).

stdlib only: subprocess, tempfile, os, sys, shutil, re, fnmatch.
"""

import fnmatch
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN_CODE_MD = os.path.join(REPO_ROOT, "skills", "implement-loop", "clean-code.md")
STAGE_R_MD = os.path.join(REPO_ROOT, "skills", "implement-loop", "stage-r.md")
SKILL_MD = os.path.join(REPO_ROOT, "skills", "implement-loop", "SKILL.md")
GITIGNORE = os.path.join(REPO_ROOT, ".gitignore")

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print(f"PASS: {label}")
    else:
        print(f"FAIL: {label}" + (f" -- {detail}" if detail else ""))
        FAILURES.append(label)


def read(path):
    with open(path) as f:
        return f.read()


def run(cmd, cwd, env=None, check_rc=True):
    result = subprocess.run(
        cmd, cwd=cwd, env=env, capture_output=True, text=True,
    )
    if check_rc and result.returncode != 0:
        raise RuntimeError(
            f"command failed: {cmd}\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result.stdout.strip()


# --- Extraction: pull the literal bash out of the markdown ------------------


def extract_bash_fenced_block(md_text, contains):
    """Return the content of the first ```bash fenced block containing `contains`."""
    for block in re.findall(r"```bash\n(.*?)\n```", md_text, re.DOTALL):
        if contains in block:
            return block
    raise AssertionError(f"no ```bash block containing {contains!r} found")


def extract_inline_command(md_text, prefix):
    """Return the literal text of the first backtick-span starting with `prefix`,
    collapsing markdown's internal line-wrapping of long inline code spans."""
    normalized = re.sub(r"\s+", " ", md_text)
    m = re.search(r"`(" + re.escape(prefix) + r"[^`]*)`", normalized)
    if not m:
        raise AssertionError(f"no inline command starting with {prefix!r} found")
    return m.group(1)


def extract_section(text, start_marker, end_marker):
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def snapshot_tree_function(clean_code_md):
    block = extract_bash_fenced_block(clean_code_md, "snapshot_tree()")
    # Keep only the function definition itself, not the `TREE_A="$(snapshot_tree)"`
    # usage line that follows it in the doc.
    return block.split('TREE_A="$(snapshot_tree)"')[0].strip()


def run_snapshot_tree(repo_dir, func_src):
    script = "set -euo pipefail\n" + func_src + "\nsnapshot_tree\n"
    return run(["bash", "-c", script], cwd=repo_dir)


def run_diff_command(repo_dir, diff_cmd, env_vars):
    env = os.environ.copy()
    env.update(env_vars)
    script = "set -euo pipefail\n" + diff_cmd + "\n"
    out = run(["bash", "-c", script], cwd=repo_dir, env=env)
    return [f for f in out.splitlines() if f]


# --- Filter: parse "keep only production files" patterns from the doc -------


def extract_quoted_globs(text, anchor):
    idx = text.index(anchor)
    end = text.index(")", idx)
    return re.findall(r"`([^`]+)`", text[idx:end])


def matches_any(path, patterns):
    for p in patterns:
        if p.endswith("/"):
            if path.startswith(p):
                return True
        elif fnmatch.fnmatch(path, p) or fnmatch.fnmatch(os.path.basename(path), p):
            return True
    return False


def filter_production_files(files, test_globs, forbidden_globs):
    return [
        f for f in files
        if not matches_any(f, test_globs) and not matches_any(f, forbidden_globs)
    ]


def write_file(repo_dir, relpath, content):
    path = os.path.join(repo_dir, relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def init_repo(repo_dir):
    run(["git", "init", "-q"], cwd=repo_dir)
    run(["git", "config", "user.email", "selftest@example.com"], cwd=repo_dir)
    run(["git", "config", "user.name", "selftest"], cwd=repo_dir)
    write_file(repo_dir, "base.txt", "baseline\n")
    run(["git", "add", "-A"], cwd=repo_dir)
    run(["git", "commit", "-q", "-m", "baseline"], cwd=repo_dir)


# --- Scenario 1: clean-code.md N>1 scope diff (REQ-2) ------------------------


def scenario_clean_code_scope(clean_code_md, snapshot_src):
    section = extract_section(clean_code_md, "iteration N > 1:", "Then keep only production files:")
    check(
        "clean-code.md N>1 scope bullet no longer unions in untracked files",
        not re.search(r"`\s*plus untracked files", section),
        "found the diff command directly followed by 'plus untracked files'",
    )

    diff_cmd = extract_inline_command(clean_code_md, "git diff --name-only ${TREE_A5_prev}")

    repo_dir = tempfile.mkdtemp(prefix="clean_code_scope_")
    try:
        init_repo(repo_dir)
        # A leftover untracked artifact present, unchanged, across both snapshots
        # (e.g. a stale .claude/clean-code/*-tree.txt from an earlier iteration).
        write_file(repo_dir, "stale_untracked_leftover.txt", "leftover\n")

        write_file(repo_dir, "alpha.txt", "iteration 1 change\n")
        tree_prev = run_snapshot_tree(repo_dir, snapshot_src)

        write_file(repo_dir, "beta.txt", "iteration 2 change\n")
        tree_a = run_snapshot_tree(repo_dir, snapshot_src)

        files = run_diff_command(
            repo_dir, diff_cmd, {"TREE_A5_prev": tree_prev, "TREE_A": tree_a}
        )
        print(f"  clean-code.md N>1 scope diff result: {files}")
        check(
            "clean-code.md N>1 scope diff excludes unchanged untracked leftover (REQ-2)",
            files == ["beta.txt"],
            f"expected ['beta.txt'], got {files}",
        )
    finally:
        shutil.rmtree(repo_dir, ignore_errors=True)


# --- Scenario 1b: clean-code.md's own filter vs. its own artifacts (finding 2) ---


def scenario_clean_code_artifact_filter(clean_code_md, snapshot_src):
    """Reproduce the real production timing for clean-code.md's own artifacts.

    clean-code.md's Section 4 "Record" step snapshots TREE_A5 and only AFTERWARD
    writes `.claude/clean-code/<task>-iter${ITER}-*.patch`/`-tree.txt` to disk. So
    an iteration's own artifact file is absent from the tree that becomes the
    *next* iteration's TREE_A5_prev, but present once the next iteration's own
    TREE_A snapshot runs (which folds in all untracked files via `git add -A`).
    That means the artifact lands only in the *later* of the two snapshots being
    diffed — exactly modeled here by writing it between `tree_prev` and `tree_a` —
    and clean-code.md's own "keep only production files" filter (Section 1) must
    be the thing that excludes it, the same way stage-r.md's equivalent filter
    already does for stage-r.md's own diff.
    """
    section = extract_section(
        clean_code_md, "Then keep only production files:", "Empty scope"
    )
    test_globs = extract_quoted_globs(section, "repo test patterns, e.g.")
    try:
        forbidden_globs = extract_quoted_globs(section, "forbidden by repo policy (e.g.")
    except ValueError:
        # Pre-fix text has no "(e.g. ...)" example at all -- no concrete glob to
        # extract, so the filter has nothing to exclude the artifact with.
        forbidden_globs = []

    diff_cmd = extract_inline_command(clean_code_md, "git diff --name-only ${TREE_A5_prev}")

    repo_dir = tempfile.mkdtemp(prefix="clean_code_artifact_filter_")
    try:
        init_repo(repo_dir)

        write_file(repo_dir, "alpha.txt", "iteration 1 change\n")
        tree_prev = run_snapshot_tree(repo_dir, snapshot_src)

        # Written AFTER tree_prev, BEFORE tree_a -- exactly clean-code.md's own
        # Record-step ordering for the previous iteration's own artifact file.
        write_file(
            repo_dir,
            ".claude/clean-code/demo-task-iter2-feature.patch",
            "stray refactor artifact\n",
        )
        write_file(repo_dir, "beta.txt", "iteration 2 change\n")
        tree_a = run_snapshot_tree(repo_dir, snapshot_src)

        raw_files = run_diff_command(
            repo_dir, diff_cmd, {"TREE_A5_prev": tree_prev, "TREE_A": tree_a}
        )
        print(f"  clean-code.md N>1 artifact-filter raw diff: {raw_files}")
        check(
            "clean-code.md N>1 scope diff picks up the mid-window artifact before filtering (sanity)",
            ".claude/clean-code/demo-task-iter2-feature.patch" in raw_files,
            f"expected artifact present pre-filter in {raw_files}",
        )

        filtered = sorted(filter_production_files(raw_files, test_globs, forbidden_globs))
        print(f"  clean-code.md N>1 artifact-filter filtered list: {filtered}")
        check(
            "clean-code.md's own production-file filter excludes its own "
            ".claude/clean-code/ artifacts (finding 2)",
            filtered == ["beta.txt"],
            f"expected ['beta.txt'], got {filtered}",
        )
    finally:
        shutil.rmtree(repo_dir, ignore_errors=True)


# --- Scenario 1c: stage-r.md's filter vs. a different .claude/ artifact type ---


def scenario_stage_r_general_claude_namespace_filter(stage_r_md, snapshot_src):
    """Reproduce a *different* ForgeLoop-internal artifact than scenario 1b's
    `.claude/clean-code/` case: a Stage B follow-up file written to
    `.claude/plans/followups/<task>-<n>.md` whenever a gate records a DEFERRED
    finding (per review-gates.md). Like `.claude/clean-code/` artifacts, this
    is written strictly after one snapshot (TREE_A5_prev2 here) and strictly
    before the next snapshot (TREE_A5_prev1 here) folds it in -- the same
    inter-snapshot timing window scenario 1b models for clean-code.md. stage-r.md's own
    forbidden-path filter (Section 1, shared with clean-code.md) must exclude
    it too, proving the filter is general rather than hard-coded to the one
    `.claude/clean-code/` path scenario 1b already tests.
    """
    section = extract_section(
        stage_r_md, "then keep only production files", "if `TREE_A5_prev1` is missing"
    )
    test_globs = extract_quoted_globs(section, "repo test patterns, e.g.")
    try:
        forbidden_globs = extract_quoted_globs(section, "forbidden by repo policy (e.g.")
    except ValueError:
        # Pre-fix text has no "(e.g. ...)" example at all -- no concrete glob to
        # extract, so the filter has nothing to exclude the artifact with.
        forbidden_globs = []

    diff_cmd = extract_inline_command(stage_r_md, "git diff --name-only ${TREE_A5_prev2}")

    repo_dir = tempfile.mkdtemp(prefix="stage_r_general_claude_")
    try:
        init_repo(repo_dir)

        write_file(repo_dir, "alpha.txt", "iteration 1 change\n")
        tree_prev2 = run_snapshot_tree(repo_dir, snapshot_src)

        # Written AFTER tree_prev2, BEFORE tree_prev1 -- exactly the window a
        # Stage B DEFERRED-finding follow-up file lands in, per review-gates.md.
        write_file(
            repo_dir,
            ".claude/plans/followups/demo-task-1.md",
            "deferred finding\n",
        )
        write_file(repo_dir, "beta.txt", "iteration 2 change\n")
        tree_prev1 = run_snapshot_tree(repo_dir, snapshot_src)

        raw_files = run_diff_command(
            repo_dir, diff_cmd,
            {"TREE_A5_prev2": tree_prev2, "TREE_A5_prev1": tree_prev1},
        )
        print(f"  stage-r.md general .claude/ filter raw diff: {raw_files}")
        check(
            "stage-r.md previous-iteration diff picks up the .claude/plans/followups/ "
            "artifact before filtering (sanity)",
            ".claude/plans/followups/demo-task-1.md" in raw_files,
            f"expected artifact present pre-filter in {raw_files}",
        )

        filtered = sorted(filter_production_files(raw_files, test_globs, forbidden_globs))
        print(f"  stage-r.md general .claude/ filter filtered list: {filtered}")
        check(
            "stage-r.md's forbidden-path filter excludes .claude/plans/followups/ "
            "artifacts too, not just .claude/clean-code/ (finding 1, iteration 4)",
            filtered == ["beta.txt"],
            f"expected ['beta.txt'], got {filtered}",
        )
    finally:
        shutil.rmtree(repo_dir, ignore_errors=True)


# --- Scenario 2: stage-r.md previous-iteration file list + filter -----------


def scenario_stage_r_previous_iteration_list(clean_code_md, stage_r_md, snapshot_src):
    section = extract_section(
        stage_r_md, "Before building the plan", 'This list is a soft starting point'
    )
    check(
        "stage-r.md previous-iteration list no longer unions in untracked files",
        not re.search(r"`\s*plus untracked files", section),
        "found the diff command directly followed by 'plus untracked files'",
    )
    check(
        "stage-r.md previous-iteration list applies a production-file filter",
        "keep only production files" in section,
        "no 'keep only production files' filter step found",
    )

    diff_cmd = extract_inline_command(stage_r_md, "git diff --name-only ${TREE_A5_prev2}")
    test_globs = extract_quoted_globs(section, "repo test patterns, e.g.")
    forbidden_globs = extract_quoted_globs(section, "forbidden by repo policy (e.g.")

    repo_dir = tempfile.mkdtemp(prefix="stage_r_scope_")
    try:
        init_repo(repo_dir)

        write_file(repo_dir, "alpha.txt", "iteration 1 change\n")
        tree_prev2 = run_snapshot_tree(repo_dir, snapshot_src)

        write_file(repo_dir, "beta.txt", "iteration 2 change\n")
        write_file(repo_dir, "tests/test_beta.py", "def test_x(): pass\n")
        write_file(repo_dir, ".claude/clean-code/demo-task-iter1-feature.patch", "stray\n")
        tree_prev1 = run_snapshot_tree(repo_dir, snapshot_src)

        raw_files = run_diff_command(
            repo_dir, diff_cmd,
            {"TREE_A5_prev2": tree_prev2, "TREE_A5_prev1": tree_prev1},
        )
        print(f"  stage-r.md previous-iteration raw diff: {raw_files}")

        filtered = sorted(filter_production_files(raw_files, test_globs, forbidden_globs))
        print(f"  stage-r.md previous-iteration filtered list: {filtered}")
        check(
            "stage-r.md previous-iteration list excludes test files and generated artifacts (REQ-3)",
            filtered == ["beta.txt"],
            f"expected ['beta.txt'], got {filtered}",
        )
    finally:
        shutil.rmtree(repo_dir, ignore_errors=True)


# --- Scenario 3: stage-r.md missing-tree-file fallback (REQ-6) --------------


def compute_stage_r_fallback(tree_dir, task, n):
    """Mirror stage-r.md's documented fallback: if either persisted tree file
    is missing, the list is empty and clean_code_scope_fallback is true."""
    prev1_missing = not os.path.exists(
        os.path.join(tree_dir, f"{task}-iter{n - 1}-tree.txt")
    )
    prev2_missing = (n - 1 != 1) and not os.path.exists(
        os.path.join(tree_dir, f"{task}-iter{n - 2}-tree.txt")
    )
    if prev1_missing or prev2_missing:
        return [], True
    return None, False


def scenario_stage_r_fallback(stage_r_md):
    fallback_bullet = stage_r_md[stage_r_md.index("- if `TREE_A5_prev1` is missing"):]
    fallback_bullet = fallback_bullet[: fallback_bullet.index("never crash.") + len("never crash.")]
    check(
        "stage-r.md fallback bullet covers TREE_A5_prev1 missing",
        "TREE_A5_prev1" in fallback_bullet and "missing" in fallback_bullet,
    )
    check(
        "stage-r.md fallback bullet also covers TREE_A5_prev2 missing (finding 3)",
        "TREE_A5_prev2" in fallback_bullet,
        "TREE_A5_prev2 not mentioned in the fallback bullet",
    )

    task = "demo-task"

    # N=4, TREE_A5_prev1 (iter3-tree.txt) missing.
    tree_dir = tempfile.mkdtemp(prefix="stage_r_fallback_")
    try:
        for i in (1, 2):
            with open(os.path.join(tree_dir, f"{task}-iter{i}-tree.txt"), "w") as f:
                f.write(f"tree-{i}\n")
        files, fallback = compute_stage_r_fallback(tree_dir, task, 4)
        check(
            "stage-r.md fallback fires when TREE_A5_prev1 is missing (N=4)",
            files == [] and fallback is True,
            f"got files={files}, fallback={fallback}",
        )
    finally:
        shutil.rmtree(tree_dir, ignore_errors=True)

    # N=4, TREE_A5_prev2 (iter2-tree.txt) missing, TREE_A5_prev1 (iter3) present.
    tree_dir = tempfile.mkdtemp(prefix="stage_r_fallback_")
    try:
        with open(os.path.join(tree_dir, f"{task}-iter3-tree.txt"), "w") as f:
            f.write("tree-3\n")
        files, fallback = compute_stage_r_fallback(tree_dir, task, 4)
        check(
            "stage-r.md fallback fires when TREE_A5_prev2 is missing for N>2 (finding 3)",
            files == [] and fallback is True,
            f"got files={files}, fallback={fallback}",
        )
    finally:
        shutil.rmtree(tree_dir, ignore_errors=True)

    # N=2 special case: N-1==1 means TREE_A5_prev2 is HEAD, never "missing".
    tree_dir = tempfile.mkdtemp(prefix="stage_r_fallback_")
    try:
        with open(os.path.join(tree_dir, f"{task}-iter1-tree.txt"), "w") as f:
            f.write("tree-1\n")
        files, fallback = compute_stage_r_fallback(tree_dir, task, 2)
        check(
            "stage-r.md fallback does not fire for N=2 when iter1 tree is present",
            files is None and fallback is False,
            f"got files={files}, fallback={fallback}",
        )
    finally:
        shutil.rmtree(tree_dir, ignore_errors=True)

# --- Scenarios 4 and 5: SKILL.md Stage 0 assert_clean_tree ------------------


def clean_tree_check_source(skill_md):
    """Return the literal assert_clean_tree bash block from SKILL.md."""
    return extract_bash_fenced_block(skill_md, "assert_clean_tree()")


def run_clean_tree_check(repo_dir, func_src):
    """Run assert_clean_tree in repo_dir via bash -c; return (exit code, stdout)."""
    script = func_src + "\nassert_clean_tree\n"
    result = subprocess.run(
        ["bash", "-c", script], cwd=repo_dir, capture_output=True, text=True,
    )
    return result.returncode, result.stdout


PRIOR_RUN_ARTIFACTS = [
    ".claude/clean-code/demo-iter1-feature.patch",
    ".claude/clean-code/demo-iter1-tree.txt",
    ".claude/run-proofs/demo-run.log",
    ".claude/plans/followups/demo-1.md",
    ".claude/plans/divergence-reports/demo-divergence.md",
    ".claude/debug-reports/demo-session.md",
]


# Not gitignored by design (plans are tracked), so excluded only by the check's
# pathspec; used for scenario 5a only.
UNIGNORED_PLAN_ARTIFACT = ".claude/plans/demo-plan.md"


def scenario_dirty_tree_blocks(skill_md):
    """Scenario 4: unrelated uncommitted/untracked file -> exit 1 and path listed."""
    func_src = clean_tree_check_source(skill_md)
    repo_dir = tempfile.mkdtemp(prefix="clean_tree_dirty_")
    try:
        init_repo(repo_dir)
        rc, out = run_clean_tree_check(repo_dir, func_src)
        check("scenario 4: clean scratch repo passes the check (sanity)", rc == 0, f"rc={rc} out={out!r}")

        write_file(repo_dir, "base.txt", "modified, uncommitted\n")
        write_file(repo_dir, "unrelated_untracked.txt", "pre-existing\n")
        rc, out = run_clean_tree_check(repo_dir, func_src)
        print(f"  scenario 4 exit={rc} output={out.strip()!r}")
        check(
            "scenario 4: dirty tracked + untracked file blocks (exit 1) and both paths are listed",
            rc == 1 and "base.txt" in out and "unrelated_untracked.txt" in out,
            f"rc={rc} out={out!r}",
        )
    finally:
        shutil.rmtree(repo_dir, ignore_errors=True)


def scenario_prior_run_artifacts_do_not_block(skill_md, gitignore_src, snapshot_src):
    """Scenario 5: leftovers from a prior run -> exit 0, with and without .gitignore entries."""
    func_src = clean_tree_check_source(skill_md)

    # 5a: no .gitignore at all (D4: the check itself must exclude the paths).
    repo_dir = tempfile.mkdtemp(prefix="clean_tree_artifacts_nogi_")
    try:
        init_repo(repo_dir)
        for rel in PRIOR_RUN_ARTIFACTS + [UNIGNORED_PLAN_ARTIFACT]:
            write_file(repo_dir, rel, "leftover\n")
        rc, out = run_clean_tree_check(repo_dir, func_src)
        check(
            "scenario 5a: prior-run leftovers with no .gitignore do not block (exit 0)",
            rc == 0, f"rc={rc} out={out!r}",
        )
        write_file(repo_dir, "real_change.txt", "x\n")
        rc, out = run_clean_tree_check(repo_dir, func_src)
        check(
            "scenario 5a: a real dirty file alongside the leftovers still blocks",
            rc == 1 and "real_change.txt" in out and ".claude" not in out,
            f"rc={rc} out={out!r}",
        )
    finally:
        shutil.rmtree(repo_dir, ignore_errors=True)

    # 5b: this repo's real .gitignore, committed in the scratch repo.
    repo_dir = tempfile.mkdtemp(prefix="clean_tree_artifacts_gi_")
    try:
        init_repo(repo_dir)
        write_file(repo_dir, ".gitignore", gitignore_src)
        run(["git", "add", ".gitignore"], cwd=repo_dir)
        run(["git", "commit", "-q", "-m", "gitignore"], cwd=repo_dir)
        for rel in PRIOR_RUN_ARTIFACTS:
            write_file(repo_dir, rel, "leftover\n")
        rc, out = run_clean_tree_check(repo_dir, func_src)
        check(
            "scenario 5b: prior-run leftovers with the real .gitignore do not block (exit 0)",
            rc == 0, f"rc={rc} out={out!r}",
        )
        porcelain = run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=repo_dir)
        print(f"  scenario 5b git status --porcelain: {porcelain!r}")
        check(
            "scenario 5b: git status --porcelain is empty with the real .gitignore",
            porcelain == "" ,
            f"porcelain={porcelain!r}",
        )
        tree = run_snapshot_tree(repo_dir, snapshot_src)
        names = run(["git", "ls-tree", "-r", "--name-only", tree], cwd=repo_dir).splitlines()
        leaked = [n for n in names if n.startswith(".claude/")]
        check(
            "scenario 5b: snapshot_tree() excludes the prior-run artifacts",
            leaked == [], f"leaked={leaked}",
        )
    finally:
        shutil.rmtree(repo_dir, ignore_errors=True)


def scenario_subdir_dirty_tree_blocks(skill_md):
    """Scenario 4b: run from a subdirectory; a dirty file elsewhere in the repo
    still blocks (exit 1), confirming `-- .` is scoped at the toplevel."""
    func_src = clean_tree_check_source(skill_md)
    repo_dir = tempfile.mkdtemp(prefix="clean_tree_subdir_dirty_")
    try:
        init_repo(repo_dir)
        write_file(repo_dir, "sub/keep.txt", "tracked\n")
        run(["git", "add", "sub/keep.txt"], cwd=repo_dir)
        run(["git", "commit", "-q", "-m", "sub"], cwd=repo_dir)
        sub_dir = os.path.join(repo_dir, "sub")
        rc, out = run_clean_tree_check(sub_dir, func_src)
        check("scenario 4b: clean repo from a subdirectory passes (sanity)", rc == 0, f"rc={rc} out={out!r}")
        write_file(repo_dir, "base.txt", "modified outside sub\n")
        write_file(repo_dir, "other/unrelated.txt", "untracked outside sub\n")
        rc, out = run_clean_tree_check(sub_dir, func_src)
        print(f"  scenario 4b exit={rc} output={out.strip()!r}")
        check(
            "scenario 4b: from a subdirectory, dirty files elsewhere in the repo block (exit 1) and are listed",
            rc == 1 and "base.txt" in out and "other/unrelated.txt" in out,
            f"rc={rc} out={out!r}",
        )
    finally:
        shutil.rmtree(repo_dir, ignore_errors=True)


def scenario_subdir_artifacts_do_not_block(skill_md):
    """Scenario 5c: nested sub/.claude/... artifacts, no .gitignore, run from sub/."""
    func_src = clean_tree_check_source(skill_md)
    repo_dir = tempfile.mkdtemp(prefix="clean_tree_subdir_artifacts_")
    try:
        init_repo(repo_dir)
        write_file(repo_dir, "sub/keep.txt", "tracked\n")
        run(["git", "add", "sub/keep.txt"], cwd=repo_dir)
        run(["git", "commit", "-q", "-m", "sub"], cwd=repo_dir)
        for rel in PRIOR_RUN_ARTIFACTS + [UNIGNORED_PLAN_ARTIFACT]:
            write_file(repo_dir, "sub/" + rel, "leftover\n")
            write_file(repo_dir, rel, "leftover\n")
        sub_dir = os.path.join(repo_dir, "sub")
        rc, out = run_clean_tree_check(sub_dir, func_src)
        check(
            "scenario 5c: nested sub/.claude artifacts with no .gitignore, run from sub/, do not block (exit 0)",
            rc == 0, f"rc={rc} out={out!r}",
        )
        write_file(repo_dir, "sub/real_change.txt", "x\n")
        rc, out = run_clean_tree_check(sub_dir, func_src)
        check(
            "scenario 5c: a real dirty file alongside nested leftovers still blocks",
            rc == 1 and "real_change.txt" in out and ".claude" not in out,
            f"rc={rc} out={out!r}",
        )
    finally:
        shutil.rmtree(repo_dir, ignore_errors=True)


def scenario_untracked_claude_files_do_not_block(skill_md: str) -> None:
    """Scenario 6: untracked .claude files never block; tracked changes, staged files,
    look-alike paths and real source files still do."""
    func_src = clean_tree_check_source(skill_md)
    untracked = [
        ".claude/session_state_x.md",
        "sub/.claude/y",
        ".claude/my file.md",
    ]

    # 6a: untracked .claude files, no .gitignore, from root and from sub/.
    repo_dir = tempfile.mkdtemp(prefix="clean_tree_untracked_claude_")
    try:
        init_repo(repo_dir)
        write_file(repo_dir, "sub/keep.txt", "tracked\n")
        run(["git", "add", "sub/keep.txt"], cwd=repo_dir)
        run(["git", "commit", "-q", "-m", "sub"], cwd=repo_dir)
        for rel in untracked:
            write_file(repo_dir, rel, "state\n")
        for where, cwd in (("root", repo_dir), ("sub/", os.path.join(repo_dir, "sub"))):
            rc, out = run_clean_tree_check(cwd, func_src)
            check(
                f"scenario 6a: untracked .claude files (session state, nested, spaces) from {where} do not block (exit 0)",
                rc == 0, f"rc={rc} out={out!r}",
            )
    finally:
        shutil.rmtree(repo_dir, ignore_errors=True)

    # 6b: modified tracked .claude/forgeloop.md still blocks.
    repo_dir = tempfile.mkdtemp(prefix="clean_tree_tracked_claude_")
    try:
        init_repo(repo_dir)
        write_file(repo_dir, ".claude/forgeloop.md", "v1\n")
        run(["git", "add", ".claude/forgeloop.md"], cwd=repo_dir)
        run(["git", "commit", "-q", "-m", "forgeloop"], cwd=repo_dir)
        write_file(repo_dir, ".claude/forgeloop.md", "v2\n")
        rc, out = run_clean_tree_check(repo_dir, func_src)
        check(
            "scenario 6b: modified tracked .claude/forgeloop.md blocks (exit 1) and is listed",
            rc == 1 and ".claude/forgeloop.md" in out, f"rc={rc} out={out!r}",
        )
    finally:
        shutil.rmtree(repo_dir, ignore_errors=True)

    # 6c: newly staged .claude/z.md blocks.
    repo_dir = tempfile.mkdtemp(prefix="clean_tree_staged_claude_")
    try:
        init_repo(repo_dir)
        write_file(repo_dir, ".claude/z.md", "z\n")
        run(["git", "add", ".claude/z.md"], cwd=repo_dir)
        rc, out = run_clean_tree_check(repo_dir, func_src)
        check(
            "scenario 6c: newly staged .claude/z.md blocks (exit 1) and is listed",
            rc == 1 and ".claude/z.md" in out, f"rc={rc} out={out!r}",
        )
    finally:
        shutil.rmtree(repo_dir, ignore_errors=True)

    # 6d: look-alike paths are not ignored.
    repo_dir = tempfile.mkdtemp(prefix="clean_tree_lookalike_")
    try:
        init_repo(repo_dir)
        write_file(repo_dir, ".claude.bak/x", "x\n")
        write_file(repo_dir, "foo.claude/x", "x\n")
        rc, out = run_clean_tree_check(repo_dir, func_src)
        check(
            "scenario 6d: look-alike .claude.bak/x and foo.claude/x block (exit 1) and are listed",
            rc == 1 and ".claude.bak/x" in out and "foo.claude/x" in out,
            f"rc={rc} out={out!r}",
        )
    finally:
        shutil.rmtree(repo_dir, ignore_errors=True)

    # 6e: dirty source next to untracked .claude files.
    repo_dir = tempfile.mkdtemp(prefix="clean_tree_src_dirty_claude_")
    try:
        init_repo(repo_dir)
        write_file(repo_dir, "src/a.py", "x = 1\n")
        for rel in untracked:
            write_file(repo_dir, rel, "state\n")
        rc, out = run_clean_tree_check(repo_dir, func_src)
        check(
            "scenario 6e: dirty src/a.py blocks (exit 1), is listed, and .claude paths are not",
            rc == 1 and "src/a.py" in out and ".claude" not in out,
            f"rc={rc} out={out!r}",
        )
    finally:
        shutil.rmtree(repo_dir, ignore_errors=True)


def main() -> int:
    clean_code_md = read(CLEAN_CODE_MD)
    stage_r_md = read(STAGE_R_MD)
    snapshot_src = snapshot_tree_function(clean_code_md)
    skill_md = read(SKILL_MD)
    gitignore_src = read(GITIGNORE)

    scenario_clean_code_scope(clean_code_md, snapshot_src)
    scenario_clean_code_artifact_filter(clean_code_md, snapshot_src)
    scenario_stage_r_general_claude_namespace_filter(stage_r_md, snapshot_src)
    scenario_stage_r_previous_iteration_list(clean_code_md, stage_r_md, snapshot_src)
    scenario_stage_r_fallback(stage_r_md)
    scenario_dirty_tree_blocks(skill_md)
    scenario_subdir_dirty_tree_blocks(skill_md)
    scenario_subdir_artifacts_do_not_block(skill_md)
    scenario_prior_run_artifacts_do_not_block(skill_md, gitignore_src, snapshot_src)
    scenario_untracked_claude_files_do_not_block(skill_md)

    print("")
    if FAILURES:
        print(f"Results: {len(FAILURES)} failed")
        return 1
    print("Results: all scenarios passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
