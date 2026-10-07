"""Tests for skills/implement-loop/forgeloop_run.py.

Real short local commands run detached in scratch directories; SLURM is a fake
squeue/srun on PATH. HOME is a scratch dir, so no real settings or SLURM host is read.
"""

import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "implement-loop" / "forgeloop_run.py"


def load_module():
    spec = importlib.util.spec_from_file_location("forgeloop_run", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class RunTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.work = self.root / "work"
        self.work.mkdir()
        self.home = self.root / "home"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.env = {**os.environ, "HOME": str(self.home), "PATH": f"{self.bin}:{os.environ['PATH']}",
                    "CLAUDE_PROJECT_DIR": str(self.work), "TZ": "UTC"}
        self.env.pop("FORGELOOP_SLURM_HOST", None)
        self.env.pop("SSH_CONNECTION", None)
        self.proofs = self.work / ".claude" / "run-proofs"

    def fake(self, name, body):
        p = self.bin / name
        p.write_text("#!/bin/bash\n" + textwrap.dedent(body))
        p.chmod(p.stat().st_mode | stat.S_IXUSR)

    def fake_slurm(self, state="RUNNING", node="gpu-node-7", name="yhadad_test"):
        self.fake("squeue", f"""
            case "$*" in
              *%N*) echo {node} ;;
              *%j*) echo {name} ;;
              *) [ -n "{state}" ] && echo {state}; exit 0 ;;
            esac
            """)
        self.fake("srun", """
            while [ $# -gt 0 ]; do
              case "$1" in --jobid=*|--chdir=*) cd "${1#--chdir=}" 2>/dev/null; shift ;; *) break ;; esac
            done
            echo "SRUN-ARGS: $*" >> "$FAKE_SRUN_LOG"
            exec "$@"
            """)
        self.env["FAKE_SRUN_LOG"] = str(self.root / "srun.log")

    def run_cli(self, *args, cwd=None, timeout=60):
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd or self.work, env=self.env,
                              capture_output=True, text=True, timeout=timeout)

    def start(self, command, task="t1", extra=(), timeout="00:10:00", device="cpu"):
        return self.run_cli("start", "--task", task, "--device", device, "--cwd", str(self.work),
                            "--timeout", timeout, *extra, "--", *command)

    def record_path(self, task="t1", it=1):
        return self.proofs / f"{task}-iter{it}.json"

    def record(self, task="t1", it=1):
        return json.loads(self.record_path(task, it).read_text())

    def wait_state(self, final=True, task="t1", it=1, limit=20):
        end = time.time() + limit
        while time.time() < end:
            rec = self.record(task, it)
            if rec["state"] not in ("starting", "running"):
                return rec
            time.sleep(0.1)
        self.fail(f"run did not finish: {self.record(task, it)}")


class StartTests(RunTestCase):
    def test_start_returns_immediately_and_run_finishes_after_caller_exits(self):
        t0 = time.time()
        p = self.start(["sleep 1.5; echo epoch 1/3"])
        took = time.time() - t0
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertLess(took, 1.2, "start must not wait for the command")
        self.assertEqual(self.record()["state"], "running")
        self.assertIn("RUN CARD", p.stdout)
        rec = self.wait_state()
        self.assertEqual(rec["state"], "passed")
        self.assertEqual(rec["exit_code"], 0)
        self.assertIn("epoch 1/3", Path(rec["log_path"]).read_text())

    def test_record_fields_and_permissions(self):
        self.start(["echo hi"])
        rec = self.wait_state()
        for key in ("task", "iter", "device", "jobid", "nodelist", "command", "cwd", "started", "timeout_s",
                    "pid", "supervisor_pid", "state", "exit_code", "ended", "log_path", "last_log_line",
                    "progress", "criteria"):
            self.assertIn(key, rec)
        self.assertEqual(rec["task"], "t1")
        self.assertEqual(rec["iter"], 1)
        self.assertEqual(rec["timeout_s"], 600)
        self.assertEqual(rec["cwd"], str(self.work))
        self.assertTrue(rec["log_path"].endswith("t1-iter1.log"))
        self.assertRegex(rec["started"], r"[+-]\d\d:\d\d$")
        self.assertRegex(rec["ended"], r"[+-]\d\d:\d\d$")
        for path in (self.record_path(), Path(rec["log_path"])):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600, path)

    def test_failed_exit_code(self):
        self.start(["echo boom; exit 3"])
        rec = self.wait_state()
        self.assertEqual((rec["state"], rec["exit_code"]), ("failed", 3))

    def test_timeout_state(self):
        t0 = time.time()
        self.start(["sleep 30"], timeout="00:00:01")
        rec = self.wait_state()
        self.assertEqual(rec["state"], "timeout")
        self.assertLess(time.time() - t0, 15)

    def test_command_with_spaces_is_quoted_not_shell_split(self):
        marker = self.work / "a b.txt"
        p = self.start(["touch", str(marker), ";", "$HOME"])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.wait_state()
        self.assertTrue(marker.exists())
        # ';' and '$HOME' were passed to touch as literal file names, not interpreted by a shell
        self.assertTrue((self.work / ";").exists())
        self.assertTrue((self.work / "$HOME").exists())

    def test_secret_stripped_in_display_command_but_real_argv_kept_private(self):
        self.start(["echo", "--api-key", "SEKRET123", "ok"])
        rec = self.wait_state()
        self.assertNotIn("SEKRET123", rec["command"])
        self.assertNotIn("argv_private", rec)  # the real argv does not stay in the record once launched
        self.assertNotIn("SEKRET123", self.record_path().read_text())
        self.assertIn("SEKRET123", Path(rec["log_path"]).read_text())  # the command really ran with it

    def test_gpu_start_refuses_when_job_not_running_and_writes_nothing(self):
        self.fake_slurm(state="PENDING")
        p = self.start(["echo hi"], device="gpu", extra=["--jobid", "123"])
        self.assertEqual(p.returncode, 2)
        self.assertIn("123", p.stderr)
        self.assertEqual(len(p.stderr.strip().splitlines()), 1)
        self.assertFalse(self.proofs.exists())

    def test_gpu_start_refuses_when_job_unknown(self):
        self.fake_slurm(state="")
        p = self.start(["echo hi"], device="gpu", extra=["--jobid", "123"])
        self.assertEqual(p.returncode, 2)
        self.assertFalse(self.proofs.exists())

    def test_gpu_requires_jobid(self):
        p = self.start(["echo hi"], device="gpu")
        self.assertEqual(p.returncode, 2)
        self.assertIn("--jobid", p.stderr)
        self.assertFalse(self.proofs.exists())

    def test_gpu_start_runs_through_srun_with_jobid_and_chdir(self):
        self.fake_slurm()
        p = self.start(["echo gpu-ran"], device="gpu", extra=["--jobid", "123"])
        self.assertEqual(p.returncode, 0, p.stderr)
        rec = self.wait_state()
        self.assertEqual(rec["state"], "passed")
        self.assertEqual(rec["jobid"], "123")
        self.assertEqual(rec["nodelist"], "gpu-node-7")
        self.assertIn("gpu-ran", Path(rec["log_path"]).read_text())
        srun_args = Path(self.env["FAKE_SRUN_LOG"]).read_text()
        self.assertIn("bash -lc", srun_args)
        self.assertNotIn("--pty", srun_args)

    def test_existing_run_is_never_overwritten(self):
        self.start(["echo one"])
        self.wait_state()
        before = self.record_path().read_text()
        p = self.start(["echo two"])
        self.assertEqual(p.returncode, 2)
        self.assertEqual(self.record_path().read_text(), before)

    def test_criteria_file_default_pending(self):
        crit = self.root / "crit.json"
        crit.write_text(json.dumps(["exit code 0", "log contains epoch 3/3"]))
        self.start(["echo hi"], extra=["--criteria-file", str(crit)])
        rec = self.wait_state()
        self.assertEqual(rec["criteria"], [
            {"criterion": "exit code 0", "verdict": "PENDING", "evidence": ""},
            {"criterion": "log contains epoch 3/3", "verdict": "PENDING", "evidence": ""}])

    def test_iter_names_files(self):
        self.start(["echo hi"], extra=["--iter", "4"])
        self.wait_state(it=4)
        self.assertTrue((self.proofs / "t1-iter4.log").exists())

    def test_repo_root_found_from_cwd_via_git(self):
        subprocess.run(["git", "init", "-q", str(self.root / "repo")], check=True)
        sub = self.root / "repo" / "sub"
        sub.mkdir()
        p = self.run_cli("start", "--task", "g", "--device", "cpu", "--cwd", str(sub), "--timeout", "00:01:00",
                         "--", "echo hi")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue((self.root / "repo" / ".claude" / "run-proofs" / "g-iter1.json").exists())
        end = time.time() + 10
        while time.time() < end and not (self.root / "repo" / ".claude" / "run-proofs" / "g-iter1.log").read_text():
            time.sleep(0.1)


class BadArgsTests(RunTestCase):
    def assert_rejected(self, args, needle=None):
        p = self.run_cli(*args)
        self.assertEqual(p.returncode, 2, (p.stdout, p.stderr))
        self.assertTrue(p.stderr.strip())
        self.assertEqual(p.stdout.strip() if "RUN CARD" not in p.stdout else "", "")
        self.assertFalse(self.proofs.exists())
        if needle:
            self.assertIn(needle, p.stderr)

    def base(self, **over):
        a = {"--task": "t1", "--device": "cpu", "--cwd": str(self.work), "--timeout": "00:01:00"}
        a.update(over)
        return ["start", *[x for kv in a.items() for x in kv if x is not None], "--", "echo", "hi"]

    def test_bad_task_name(self):
        self.assert_rejected(self.base(**{"--task": "bad name/x"}), "task")

    def test_bad_device(self):
        self.assert_rejected(self.base(**{"--device": "tpu"}))

    def test_bad_timeout(self):
        self.assert_rejected(self.base(**{"--timeout": "10m"}), "timeout")

    def test_zero_timeout(self):
        self.assert_rejected(self.base(**{"--timeout": "00:00:00"}), "timeout")

    def test_cwd_missing(self):
        self.assert_rejected(self.base(**{"--cwd": str(self.root / "nope")}), "cwd")

    def test_cwd_is_a_file(self):
        f = self.root / "f.txt"
        f.write_text("x")
        self.assert_rejected(self.base(**{"--cwd": str(f)}), "cwd")

    def test_missing_command(self):
        self.assert_rejected(["start", "--task", "t", "--device", "cpu", "--cwd", str(self.work),
                              "--timeout", "00:01:00"], "command")

    def test_bad_iter(self):
        self.assert_rejected(self.base(**{"--iter": "0"}))

    def test_bad_criteria_file(self):
        bad = self.root / "bad.json"
        bad.write_text("{not json")
        self.assert_rejected(self.base(**{"--criteria-file": str(bad)}), "criteria")

    def test_missing_criteria_file(self):
        self.assert_rejected(self.base(**{"--criteria-file": str(self.root / "none.json")}), "criteria")

    def test_no_subcommand(self):
        p = self.run_cli()
        self.assertEqual(p.returncode, 2)

    def test_status_needs_record_or_latest(self):
        p = self.run_cli("status")
        self.assertEqual(p.returncode, 2)

    def test_status_missing_record(self):
        p = self.run_cli("status", "--record", str(self.root / "x.json"))
        self.assertEqual(p.returncode, 2)
        self.assertEqual(len(p.stderr.strip().splitlines()), 1)

    def test_status_latest_without_runs(self):
        p = self.run_cli("status", "--latest")
        self.assertEqual(p.returncode, 2)

    def test_jobid_must_be_numeric(self):
        self.fake_slurm()
        self.assert_rejected(self.base(**{"--device": "gpu", "--jobid": "12;rm"}), "jobid")


class StatusTests(RunTestCase):
    def test_running_line_and_progress_parse(self):
        self.start(["echo 'epoch 2/3 loss 0.5'; sleep 20"])
        time.sleep(1.5)
        p = self.run_cli("status", "--record", str(self.record_path()))
        self.assertEqual(p.returncode, 0, p.stderr)
        line = p.stdout.strip()
        self.assertEqual(len(line.splitlines()), 1)
        self.assertRegex(line, r"^▶ t1 iter 1 · running \d\d:\d\d of 00:10:00 · ")
        self.assertIn("epoch 2/3", line)
        self.assertIn("last: epoch 2/3 loss 0.5", line)
        rec = self.record()
        self.assertEqual(rec["last_log_line"], "epoch 2/3 loss 0.5")
        self.assertAlmostEqual(rec["progress"]["fraction"], 1 / 3, places=3)
        pid = rec["pid"]
        os.killpg(os.getpgid(pid), 15) if pid else None  # leave nothing running

    def test_last_line_truncated_to_100_and_secrets_stripped(self):
        self.start(["echo \"token=abc123 password hunter2 " + "x" * 200 + "\"; sleep 20"])
        time.sleep(1.5)
        line = self.run_cli("status", "--record", str(self.record_path())).stdout
        self.assertNotIn("abc123", line)
        self.assertNotIn("hunter2", line)
        last = line.split("last: ", 1)[1].strip()
        self.assertLessEqual(len(last), 100)
        rec = self.record()
        self.assertNotIn("abc123", rec["last_log_line"])
        self.kill_run(rec)

    def kill_run(self, rec):
        for pid in (rec.get("pid"), rec.get("supervisor_pid")):
            try:
                os.kill(pid, 15)
            except (OSError, TypeError):
                pass

    def test_final_lines(self):
        self.start(["echo ok"], task="p")
        self.wait_state(task="p")
        self.start(["echo bad; exit 7"], task="f")
        self.wait_state(task="f")
        self.start(["sleep 30"], task="to", timeout="00:00:01")
        self.wait_state(task="to")
        out = lambda t: self.run_cli("status", "--record", str(self.record_path(t))).stdout.strip()
        self.assertTrue(out("p").startswith("✅ passed"), out("p"))
        self.assertIn("p iter 1", out("p"))
        self.assertTrue(out("f").startswith("❌ failed exit 7"), out("f"))
        self.assertIn("last: bad", out("f"))
        self.assertTrue(out("to").startswith("⏱ timeout"), out("to"))

    def test_error_state_when_command_cannot_launch(self):
        self.start(["echo hi"], task="e")
        self.wait_state(task="e")
        path = self.record_path("e")
        rec = json.loads(path.read_text())
        rec.update(state="error", exit_code=None)
        path.write_text(json.dumps(rec))
        out = self.run_cli("status", "--record", str(path)).stdout
        self.assertTrue(out.startswith("⚠ error"), out)

    def test_lost_process_detected(self):
        self.start(["echo hi"], task="l")
        self.wait_state(task="l")
        dead = subprocess.Popen(["true"])
        dead.wait()
        path = self.record_path("l")
        rec = json.loads(path.read_text())
        rec.update(state="running", exit_code=None, ended=None, pid=dead.pid, supervisor_pid=dead.pid)
        path.write_text(json.dumps(rec))
        out = self.run_cli("status", "--record", str(path)).stdout
        self.assertTrue(out.startswith("⚠ lost"), out)
        rec2 = json.loads(path.read_text())
        self.assertEqual(rec2["state"], "lost")
        self.assertIsNone(rec2["exit_code"])
        # a second status call keeps it lost
        self.assertEqual(json.loads(self.run_cli("status", "--record", str(path), "--json").stdout)["state"], "lost")

    def test_status_json_hides_private_argv(self):
        self.start(["echo", "--api-key", "SEKRET123"])
        self.wait_state()
        out = self.run_cli("status", "--record", str(self.record_path()), "--json").stdout
        data = json.loads(out)
        self.assertEqual(data["state"], "passed")
        self.assertNotIn("SEKRET123", out)
        self.assertNotIn("argv_private", data)

    def test_latest_picks_newest_record(self):
        self.start(["echo first"], task="a")
        self.wait_state(task="a")
        time.sleep(0.05)
        self.start(["echo second"], task="b")
        self.wait_state(task="b")
        os.utime(self.record_path("a"), (time.time() - 100, time.time() - 100))
        out = self.run_cli("status", "--latest").stdout
        self.assertIn(" b iter 1", out)
        self.assertIn("last: second", out)

    def test_times_are_israel_time(self):
        self.start(["echo hi"])
        self.wait_state()
        rec = self.record()
        m = re.search(r"([+-]\d\d:\d\d)$", rec["started"])
        self.assertIn(m.group(1), ("+02:00", "+03:00"))  # Asia/Jerusalem, although TZ=UTC here
        card = self.run_cli("card", "--record", str(self.record_path())).stdout
        self.assertIn("Israel time", card)
        self.assertNotIn("UTC", card)
        self.assertNotIn("+00:00", card)
        started_local = re.search(r"started: (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", card).group(1)
        self.assertEqual(started_local, rec["started"][:19].replace("T", " "))


class CardTests(RunTestCase):
    def test_start_card(self):
        crit = self.root / "c.json"
        crit.write_text(json.dumps(["exit code 0"]))
        p = self.start(["echo", "--api-key", "SEKRET123"], extra=["--criteria-file", str(crit)], timeout="01:00:00")
        self.assertEqual(p.returncode, 0)
        card = p.stdout
        self.assertIn("RUN CARD", card)
        self.assertIn("t1 iter 1", card)
        self.assertIn("command:", card)
        self.assertNotIn("SEKRET123", card)
        self.assertIn("cpu", card)
        self.assertIn(str(self.work), card)
        self.assertIn("expected time: 01:00:00", card)
        self.assertIn("t1-iter1.log", card)
        self.assertIn("status --record", card)
        self.assertIn(str(self.record_path()), card)
        self.assertIn("Israel time", card)

    def test_finish_card_with_checklist(self):
        crit = self.root / "c.json"
        crit.write_text(json.dumps(["exit code 0", "log shows epoch 3/3"]))
        self.start(["printf 'a\\nb\\nepoch 3/3\\n'; exit 0"], extra=["--criteria-file", str(crit)])
        self.wait_state()
        card = self.run_cli("card", "--record", str(self.record_path())).stdout
        self.assertIn("RUN CARD", card)
        self.assertIn("finished", card)
        self.assertIn("exit code: 0", card)
        self.assertIn("duration:", card)
        self.assertIn("epoch 3/3", card)
        self.assertIn("CHECKLIST", card)
        self.assertEqual(card.count("PENDING"), 2)
        self.assertIn("exit code 0", card)
        self.assertIn("PASS/FAIL", card)
        self.assertNotIn("PASS —", card)  # the script never judges

    def test_card_on_running_run_is_start_card(self):
        self.start(["sleep 20"])
        card = self.run_cli("card", "--record", str(self.record_path())).stdout
        self.assertIn("expected time:", card)
        self.assertNotIn("CHECKLIST", card)
        self.assertNotIn("exit code:", card)
        self.run_cli("status", "--record", str(self.record_path()))
        rec = self.record()
        for pid in (rec["pid"], rec["supervisor_pid"]):
            try:
                os.kill(pid, 15)
            except OSError:
                pass

    def test_card_kind_override(self):
        self.start(["echo hi"])
        self.wait_state()
        card = self.run_cli("card", "--record", str(self.record_path()), "--kind", "start").stdout
        self.assertIn("expected time:", card)


class ModuleTests(RunTestCase):
    def test_reuses_cluster_status_helpers(self):
        mod = load_module()
        self.assertTrue(mod.CS.__file__.endswith("cluster-loop/cluster_status.py"))
        self.assertIs(mod.CS.sanitize_command, mod.CS.sanitize_command)
        self.assertEqual(mod.parse_hms("01:02:03"), 3723)
        self.assertIsNone(mod.parse_hms("1:2"))
        self.assertEqual(mod.fmt_elapsed(723), "12:03")
        self.assertEqual(mod.fmt_elapsed(3723), "1:02:03")


class RepairTests(RunTestCase):
    def test_gpu_job_name_must_have_yhadad_prefix(self):
        self.fake_slurm(name="someone_else_job")
        p = self.start(["echo hi"], device="gpu", extra=["--jobid", "123"])
        self.assertEqual(p.returncode, 2)
        self.assertIn("yhadad_", p.stderr)
        self.assertEqual(len(p.stderr.strip().splitlines()), 1)
        self.assertFalse(self.proofs.exists())

    def test_gpu_job_name_with_prefix_is_accepted(self):
        self.fake_slurm(name="yhadad_train")
        p = self.start(["echo hi"], device="gpu", extra=["--jobid", "123"])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.wait_state()

    def test_command_sha256_in_record_and_card(self):
        import hashlib
        p = self.start(["echo", "--api-key", "SEKRET123"])
        rec = self.wait_state()
        want = hashlib.sha256(b"echo --api-key SEKRET123").hexdigest()
        self.assertEqual(rec["command_sha256"], want)
        self.assertNotIn("SEKRET123", p.stdout)
        self.assertIn(f"command sha256: {want}", p.stdout)
        card = self.run_cli("card", "--record", str(self.record_path()), "--kind", "finish").stdout
        self.assertIn(f"command sha256: {want}", card)

    def test_single_word_command_sha256_is_of_the_shell_string(self):
        import hashlib
        self.start(["echo one"])
        self.assertEqual(self.wait_state()["command_sha256"], hashlib.sha256(b"echo one").hexdigest())

    def test_supervisor_lost_but_child_alive_is_not_terminal(self):
        self.start(["echo hi"], task="s")
        self.wait_state(task="s")
        dead = subprocess.Popen(["true"])
        dead.wait()
        child = subprocess.Popen(["sleep", "30"])
        self.addCleanup(child.kill)
        path = self.record_path("s")
        rec = json.loads(path.read_text())
        rec.update(state="running", exit_code=None, ended=None, pid=child.pid, supervisor_pid=dead.pid)
        path.write_text(json.dumps(rec))
        out = self.run_cli("status", "--record", str(path)).stdout
        self.assertIn("⚠ supervisor lost, child still running", out)
        after = json.loads(path.read_text())
        self.assertEqual(after["state"], "running")
        self.assertIsNone(after["ended"])
        child.kill()
        child.wait()
        out = self.run_cli("status", "--record", str(path)).stdout
        self.assertTrue(out.startswith("⚠ lost"), out)

    def test_refresh_does_not_overwrite_a_record_that_finished_meanwhile(self):
        mod = load_module()
        self.start(["echo hi"], task="r")
        self.wait_state(task="r")
        path = self.record_path("r")
        rec = json.loads(path.read_text())
        rec.update(state="running", exit_code=None, ended=None, last_log_line="stale", progress=None,
                   supervisor_pid=os.getpid(), pid=os.getpid())
        path.write_text(json.dumps(rec))
        real_update = mod.update_record

        def racing_update(p, fn):
            final = json.loads(Path(p).read_text())
            final.update(state="passed", exit_code=0, ended="2026-01-01T00:00:00+02:00",
                         last_log_line="FINAL", progress={"fraction": 1.0, "counter": None, "remaining_s": 0})
            Path(p).write_text(json.dumps(final))
            return real_update(p, fn)

        mod.update_record = racing_update
        try:
            with mock_supervisor(mod):
                mod.refresh(path)
        finally:
            mod.update_record = real_update
        after = json.loads(path.read_text())
        self.assertEqual(after["state"], "passed")
        self.assertEqual(after["last_log_line"], "FINAL")
        self.assertEqual(after["progress"]["fraction"], 1.0)

    def test_start_on_existing_record_only_is_one_line_exit_2_and_touches_nothing(self):
        self.proofs.mkdir(parents=True)
        self.record_path().write_text("{}")
        p = self.start(["echo hi"])
        self.assertEqual(p.returncode, 2)
        self.assertEqual(len(p.stderr.strip().splitlines()), 1)
        self.assertEqual(sorted(x.name for x in self.proofs.iterdir()), ["t1-iter1.json"])
        self.assertEqual(self.record_path().read_text(), "{}")

    def test_concurrent_start_same_task_one_wins_other_exits_2(self):
        procs = [subprocess.Popen([sys.executable, str(SCRIPT), "start", "--task", "c", "--device", "cpu",
                                   "--cwd", str(self.work), "--timeout", "00:01:00", "--", "sleep 1; echo x"],
                                  env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                 for _ in range(4)]
        results = [(p.wait(), p.stderr.read()) for p in procs]
        codes = sorted(r[0] for r in results)
        self.assertEqual(codes, [0, 2, 2, 2], results)
        for code, err in results:
            if code == 2:
                self.assertEqual(len(err.strip().splitlines()), 1, err)
                self.assertNotIn("Traceback", err)
        self.wait_state(task="c")

    def test_start_leaves_nothing_behind_when_a_later_write_fails(self):
        mod = load_module()
        real = mod.write_private

        def boom(path, data):
            raise OSError("disk full")

        mod.write_private = boom
        try:
            rc = mod.main(["start", "--task", "w", "--device", "cpu", "--cwd", str(self.work),
                           "--timeout", "00:01:00", "--", "echo", "SEKRET123"])
        finally:
            mod.write_private = real
        self.assertEqual(rc, 2)
        self.assertEqual(list(self.proofs.iterdir()) if self.proofs.exists() else [], [])

    def test_no_secret_in_any_run_file_after_launch(self):
        self.start(["echo", "--api-key", "SEKRET123"])
        self.wait_state()
        for f in self.proofs.iterdir():
            if f.suffix != ".log":
                self.assertNotIn("SEKRET123", f.read_text(), f)

    def test_early_exit_137_is_failed_not_timeout(self):
        self.start(["exit 137"], timeout="00:00:01")
        time.sleep(1.5)
        rec = self.wait_state()
        self.assertEqual((rec["state"], rec["exit_code"]), ("failed", 137))
        self.assertFalse(rec.get("timed_out"))

    def test_early_exit_124_is_failed_not_timeout(self):
        self.start(["exit 124"])
        self.assertEqual(self.wait_state()["state"], "failed")

    def test_real_timeout_is_timeout_and_flagged(self):
        self.start(["sleep 30"], timeout="00:00:01")
        rec = self.wait_state()
        self.assertEqual(rec["state"], "timeout")
        self.assertTrue(rec["timed_out"])

    def test_timeout_kills_the_whole_process_group(self):
        marker = self.work / "child.pid"
        self.start([f"sleep 30 & echo $! > {marker}; wait"], timeout="00:00:01")
        self.wait_state()
        pid = int(marker.read_text())
        time.sleep(0.3)
        mod = load_module()
        self.assertFalse(mod.process_alive(pid))

    def test_bad_ssh_hosts_rejected(self):
        for host in ("-oProxyCommand=x", "a b", "a;b", "", "-x@h", "u@-h", "a@b@c"):
            self.env["FORGELOOP_SLURM_HOST"] = host
            p = self.start(["echo hi"], device="gpu", extra=["--jobid", "1"])
            if host == "":
                continue  # empty means local SLURM
            self.assertEqual(p.returncode, 2, host)
            self.assertEqual(len(p.stderr.strip().splitlines()), 1, host)
            self.assertFalse(self.proofs.exists(), host)

    def test_ssh_call_has_double_dash_before_host(self):
        mod = load_module()
        argv = mod.build_argv({"timeout_s": 60, "device": "gpu", "jobid": "1", "cwd": "/w"}, ["echo"], "me@node-1.x")
        self.assertEqual(argv[0], "ssh")
        i = argv.index("me@node-1.x")
        self.assertEqual(argv[i - 1], "--")

    def test_build_argv_rejects_dash_host(self):
        mod = load_module()
        with self.assertRaises(mod.UsageError):
            mod.build_argv({"timeout_s": 60, "device": "gpu", "jobid": "1", "cwd": "/w"}, ["echo"], "-oFoo=bar")


class mock_supervisor:
    """Make supervisor_alive report True so refresh() does not flag the record as lost."""

    def __init__(self, mod):
        self.mod = mod

    def __enter__(self):
        self.real = self.mod.supervisor_alive
        self.mod.supervisor_alive = lambda rec: True

    def __exit__(self, *a):
        self.mod.supervisor_alive = self.real


if __name__ == "__main__":
    unittest.main()
