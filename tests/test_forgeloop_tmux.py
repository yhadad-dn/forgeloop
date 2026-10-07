"""Tests for skills/tmux-session/forgeloop_tmux.py (scratch dirs only; never the real HOME)."""

import importlib.util
import io
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "tmux-session" / "forgeloop_tmux.py"


def load_module():
    spec = importlib.util.spec_from_file_location("forgeloop_tmux", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Result:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


# Trimmed from the recorded VS Code 2.1.289 extension traffic.
INIT = {"request_id": "u505v03sm4j", "type": "control_request",
        "request": {"subtype": "initialize", "hooks": {}, "sdkMcpServers": ["claude-vscode"]}}
GET_SETTINGS = {"request_id": "zhfgi5vim6", "type": "control_request",
                "request": {"subtype": "get_settings"}}
USER = {"type": "user", "uuid": "1f46eaf2", "session_id": "", "parent_tool_use_id": None,
        "origin": {"kind": "human"},
        "message": {"role": "user", "content": [{"type": "text", "text": "hi"}]}}


class TmuxTests(unittest.TestCase):
    def setUp(self):
        self.m = load_module()

    def no_files(self, path):
        return False

    def test_classify_local(self):
        self.assertEqual(self.m.classify_host({}, self.no_files), "local")
        self.assertEqual(self.m.classify_host({"CODESPACES": "true"}, self.no_files), "local")

    def test_classify_remote_ssh(self):
        env = {"SSH_CONNECTION": "1.2.3.4 5 6.7.8.9 22"}
        self.assertEqual(self.m.classify_host(env, self.no_files), "remote_ssh")

    def test_classify_other_remote_markers(self):
        for marker in ("REMOTE_CONTAINERS", "CODESPACES", "WSL_DISTRO_NAME"):
            env = {"SSH_CONNECTION": "x", marker: "1"}
            self.assertEqual(self.m.classify_host(env, self.no_files), "other_remote", marker)
        self.assertEqual(
            self.m.classify_host({"SSH_CONNECTION": "x"}, lambda p: p == "/.dockerenv"),
            "other_remote")

    def test_classify_other_remote_allowed(self):
        env = {"SSH_CONNECTION": "x", "CODESPACES": "true"}
        self.assertEqual(self.m.classify_host(env, self.no_files, allow_other=True), "remote_ssh")
        self.assertEqual(
            self.m.classify_host({"SSH_CONNECTION": "x"}, lambda p: True, allow_other=True),
            "remote_ssh")

    def test_session_name_sanitized(self):
        now = datetime(2026, 10, 6, 13, 5, 9)
        self.assertEqual(self.m.session_name("/home/dn/My Proj_x.y", now),
                         "fl-my-proj-x-y-20261006-130509")
        self.assertEqual(self.m.session_name("/a/b/forgeloop/", now), "fl-forgeloop-20261006-130509")
        self.assertEqual(self.m.session_name("/a/b/--A!!B--", now), "fl-a-b-20261006-130509")

    def test_is_forgeloop_session(self):
        self.assertTrue(self.m.is_forgeloop_session("fl-x-1"))
        self.assertFalse(self.m.is_forgeloop_session("work"))

    def test_stop_refuses_non_forgeloop(self):
        calls = []
        rc = self.m.stop_session("work", lambda *a, **k: calls.append(a))
        self.assertEqual(rc, 2)
        self.assertEqual(calls, [])

    def test_stop_schedules_delayed_kill(self):
        calls = []
        rc = self.m.stop_session("fl-x-1", lambda cmd, **k: calls.append(cmd) or Result(), delay=3)
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [["tmux", "has-session", "-t", "=fl-x-1"],
                                 ["tmux", "run-shell", "-b",
                                  "sleep 3; tmux kill-session -t =fl-x-1"]])

    def test_stop_absent_session_returns_1_without_scheduling(self):
        calls = []

        def run(cmd, **k):
            calls.append(cmd)
            return Result(1)

        self.assertEqual(self.m.stop_session("fl-x-1", run), 1)
        self.assertEqual(calls, [["tmux", "has-session", "-t", "=fl-x-1"]])

    def test_stop_nonzero_returncode(self):
        def run(cmd, **k):
            return Result(0) if cmd[1] == "has-session" else Result(1)
        self.assertEqual(self.m.stop_session("fl-x-1", run), 1)

    def test_stop_tmux_missing(self):
        def run(cmd, **k):
            raise FileNotFoundError("tmux")
        self.assertEqual(self.m.stop_session("fl-x-1", run), 1)

    def test_list_sessions_filters_prefix(self):
        seen = []

        def run(cmd, **k):
            seen.append(cmd)
            return Result(0, "fl-a-1\nwork\nfl-b-2\n\n")

        self.assertEqual(self.m.list_sessions(run), ["fl-a-1", "fl-b-2"])
        self.assertEqual(seen, [["tmux", "ls", "-F", "#S"]])

    def test_list_sessions_tmux_fails(self):
        self.assertEqual(self.m.list_sessions(lambda cmd, **k: Result(1, "")), [])

    def test_list_sessions_tmux_missing(self):
        def run(cmd, **k):
            raise FileNotFoundError("tmux")
        self.assertEqual(self.m.list_sessions(run), [])

    def serve(self, lines, text="HELLO"):
        stdin = io.StringIO("".join(lines))
        stdout = io.StringIO()
        self.m.launcher_reply(text, stdin, stdout)
        return [json.loads(l) for l in stdout.getvalue().splitlines()]

    def test_launcher_reply_protocol(self):
        out = self.serve([json.dumps(INIT) + "\n", "not json\n", "\n",
                          json.dumps(GET_SETTINGS) + "\n", json.dumps(USER) + "\n"])
        self.assertEqual(out[0], {"type": "control_response", "response": {
            "subtype": "success", "request_id": "u505v03sm4j", "response": {}}})
        self.assertEqual(out[1]["response"]["request_id"], "zhfgi5vim6")
        self.assertEqual([o["type"] for o in out[2:]], ["system", "assistant", "result"])
        self.assertEqual(out[2]["subtype"], "init")
        self.assertEqual(out[3]["message"]["content"], [{"type": "text", "text": "HELLO"}])
        self.assertEqual(out[4]["subtype"], "success")
        self.assertEqual(out[4]["result"], "HELLO")

    def test_launcher_reply_second_user_message(self):
        out = self.serve([json.dumps(USER) + "\n", json.dumps(USER) + "\n"])
        self.assertEqual([o["type"] for o in out],
                         ["system", "assistant", "result", "assistant", "result"])

    def test_launcher_reply_unique_ids_and_uuids(self):
        out = self.serve([json.dumps(USER) + "\n"] * 2)
        asst = [o for o in out if o["type"] == "assistant"]
        self.assertEqual(len({a["message"]["id"] for a in asst}), 2)
        for o in out:
            if o["type"] in ("assistant", "result"):
                self.assertRegex(o["uuid"], r"^[0-9a-f-]{36}$")
        self.assertEqual(len({o["uuid"] for o in out if "uuid" in o}), 4)

    def test_launcher_reply_broken_pipe(self):
        class Broken:
            def write(self, s):
                raise BrokenPipeError()

            def flush(self):
                pass
        self.m.launcher_reply("x", io.StringIO(json.dumps(USER) + "\n"), Broken())

    def test_main_launcher_broken_pipe(self):
        f = Path(tempfile.mkdtemp()) / "m.txt"
        f.write_text("x")

        class Broken:
            def write(self, s):
                raise BrokenPipeError()

            def flush(self):
                pass
        with mock.patch("sys.stdin", io.StringIO(json.dumps(USER) + "\n")), \
                mock.patch("sys.stdout", Broken()):
            self.assertEqual(self.m.main(["launcher", str(f)]), 0)

    def test_launcher_reply_eof_without_user(self):
        self.assertEqual(self.serve([]), [])


class MainTests(unittest.TestCase):
    def setUp(self):
        self.m = load_module()
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, argv, env):
        out = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("sys.stdout", out), \
                mock.patch("os.path.exists", lambda p: False):
            rc = self.m.main(argv)
        return rc, out.getvalue()

    def test_main_classify(self):
        rc, out = self.run_main(["classify"], {"HOME": str(self.home)})
        self.assertEqual((rc, out.strip()), (0, "local"))
        env = {"HOME": str(self.home), "SSH_CONNECTION": "x", "CODESPACES": "1"}
        self.assertEqual(self.run_main(["classify"], env)[1].strip(), "other_remote")
        d = self.home / ".claude" / "forgeloop"
        d.mkdir(parents=True)
        (d / "durable").write_text("yes\nignored\n")
        self.assertEqual(self.run_main(["classify"], env)[1].strip(), "remote_ssh")

    def test_main_name(self):
        rc, out = self.run_main(["name", "/x/My Dir"], {})
        self.assertEqual(rc, 0)
        self.assertRegex(out.strip(), r"^fl-my-dir-\d{8}-\d{6}$")

    def test_main_stop_refuses(self):
        self.assertEqual(self.run_main(["stop", "work"], {})[0], 2)

    def test_main_usage(self):
        self.assertEqual(self.run_main([], {})[0], 2)

    def test_main_launcher(self):
        f = self.home / "msg.txt"
        f.write_text("Line1\nLine2\n")
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(USER) + "\n")), \
                mock.patch("sys.stdout", out):
            rc = self.m.main(["launcher", str(f)])
        self.assertEqual(rc, 0)
        lines = [json.loads(l) for l in out.getvalue().splitlines()]
        self.assertEqual(lines[1]["message"]["content"][0]["text"], "Line1\nLine2")


class NameInjectionTests(unittest.TestCase):
    def test_stop_refuses_shell_metacharacters(self):
        mod = load_module()
        calls = []
        for bad in ("fl-x; rm -rf ~", "fl-$(id)", "fl-a b", "fl-a`b`", "fl-"):
            self.assertEqual(mod.stop_session(bad, lambda *a, **k: calls.append(a)), 2)
        self.assertEqual(calls, [])


class EndCurrentTests(unittest.TestCase):
    def setUp(self):
        self.m = load_module()

    def runner(self, name, calls):
        def run(cmd, **kw):
            calls.append(cmd)
            if cmd[:2] == ["tmux", "display-message"]:
                return Result(0, name + "\n")
            return Result(0, "")
        return run

    def test_in_forgeloop_session_calls_delayed_stop_only(self):
        calls, out = [], io.StringIO()
        rc = self.m.end_current({"TMUX": "/tmp/tmux-1/default,1,0", "TMUX_PANE": "%3"}, self.runner("fl-proj-20260101-000000", calls), out)
        self.assertEqual(rc, 0)
        self.assertEqual(calls[0], ["tmux", "display-message", "-p", "-t", "%3", "#S"])
        self.assertEqual(calls[1], ["tmux", "has-session", "-t", "=fl-proj-20260101-000000"])
        self.assertEqual(calls[2][:3], ["tmux", "run-shell", "-b"])
        self.assertIn("sleep 2; tmux kill-session", calls[2][3])
        self.assertFalse(any(c[1] == "kill-session" for c in calls))

    def test_no_tmux_env_touches_nothing(self):
        calls, out = [], io.StringIO()
        self.assertEqual(self.m.end_current({}, self.runner("fl-x", calls), out), 0)
        self.assertEqual(calls, [])
        self.assertEqual(out.getvalue(), "not in a ForgeLoop tmux session; nothing closed\n")

    def test_missing_or_empty_pane_touches_nothing(self):
        for env in ({"TMUX": "x"}, {"TMUX": "x", "TMUX_PANE": ""}, {"TMUX_PANE": "%1"}):
            calls, out = [], io.StringIO()
            self.assertEqual(self.m.end_current(env, self.runner("fl-x", calls), out), 0)
            self.assertEqual(calls, [])
            self.assertEqual(out.getvalue(), "not in a ForgeLoop tmux session; nothing closed\n")

    def test_non_forgeloop_session_not_closed(self):
        calls, out = [], io.StringIO()
        self.assertEqual(self.m.end_current({"TMUX": "x", "TMUX_PANE": "%1"}, self.runner("work", calls), out), 0)
        self.assertEqual(calls, [["tmux", "display-message", "-p", "-t", "%1", "#S"]])
        self.assertEqual(out.getvalue(), "not in a ForgeLoop tmux session; nothing closed\n")

    def test_tmux_failure_or_missing_is_safe(self):
        out = io.StringIO()
        def boom(cmd, **kw):
            raise OSError("no tmux")
        self.assertEqual(self.m.end_current({"TMUX": "x", "TMUX_PANE": "%1"}, boom, out), 0)
        self.assertIn("nothing closed", out.getvalue())

    def test_cli_without_tmux_env(self):
        import subprocess, sys
        env = {k: v for k, v in os.environ.items() if k != "TMUX"}
        p = subprocess.run([sys.executable, str(SCRIPT), "end-current"], capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout, "not in a ForgeLoop tmux session; nothing closed\n")


if __name__ == "__main__":
    unittest.main()
