#!/usr/bin/env python3
"""Unit + integration tests for scripts/dap_client.py.

Uses stdlib unittest only (no pytest). The DAP protocol paths are exercised
against a scripted fake socket; the integration test launches a real debugpy
server if an interpreter with debugpy is available.
"""

import ast
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
FIXTURE = os.path.join(REPO_ROOT, "tests", "fixtures", "buggy_divzero.py")
sys.path.insert(0, SCRIPTS_DIR)

import dap_client  # noqa: E402
from dap_client import (  # noqa: E402
    DAPSession,
    DAPStartError,
    detect_language,
    run_pdb_session,
    _parse_pdb_red,
    _parse_pdb_green,
)


def frame_msg(msg):
    body = json.dumps(msg).encode("utf-8")
    return b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body


class FakeSocket:
    """Scripted DAP adapter endpoint. Each sendall() call carries one framed
    request; the script callback returns the messages to queue as replies.

    idle_when_empty=True mimics debugpy's attach-mode adapter, which holds
    the socket open (recv raises the poll-tick TimeoutError) instead of
    closing it when it has nothing more to send."""

    def __init__(self, script=None, idle_when_empty=False):
        self.script = script or (lambda msg: [])
        self.idle_when_empty = idle_when_empty
        self.raw_sent = b""
        self.sent = []
        self.inbox = b""
        self.closed = False

    def enqueue(self, msg):
        self.inbox += frame_msg(msg)

    def sendall(self, data):
        self.raw_sent += data
        _, _, body = data.partition(b"\r\n\r\n")
        msg = json.loads(body)
        self.sent.append(msg)
        for reply in self.script(msg):
            self.enqueue(reply)

    def recv(self, n):
        if not self.inbox and self.idle_when_empty:
            raise TimeoutError("idle socket poll tick")
        data, self.inbox = self.inbox[:n], self.inbox[n:]
        return data

    def close(self):
        self.closed = True

    def commands(self):
        return [m["command"] for m in self.sent if m.get("type") == "request"]


def debugpy_script(
    initialized_before_response=True,
    filters=None,
    stop_reason="breakpoint",
    exit_code=1,
    verified_lines=(5,),
    fail_start=False,
    exited_before_initialized=False,
    secondary_stops=0,
):
    """Return a script callback emulating a debugpy/dlv DAP adapter."""
    state = {"continues": 0}
    caps = {}
    if filters is not None:
        caps["exceptionBreakpointFilters"] = filters

    def script(msg):
        cmd = msg.get("command")
        seq = msg.get("seq")

        def resp(body=None, success=True):
            r = {"type": "response", "request_seq": seq, "success": success,
                 "command": cmd}
            if body is not None:
                r["body"] = body
            return r

        def event(name, body=None):
            e = {"type": "event", "event": name}
            if body is not None:
                e["body"] = body
            return e

        if cmd == "initialize":
            return [resp(caps)]
        if cmd in ("attach", "launch"):
            if fail_start:
                return [resp(success=False)]
            if exited_before_initialized:
                return [event("exited", {"exitCode": 1})]
            if initialized_before_response:
                return [event("initialized"), resp()]
            return [resp(), event("initialized")]
        if cmd == "setBreakpoints":
            return [resp({"breakpoints": [{"verified": True, "line": ln}
                                          for ln in verified_lines]})]
        if cmd == "setExceptionBreakpoints":
            return [resp({})]
        if cmd == "configurationDone":
            return [resp(),
                    event("stopped", {"reason": stop_reason, "threadId": 1})]
        if cmd == "stackTrace":
            return [resp({"stackFrames": [
                {"id": 11, "name": "divide", "line": 5,
                 "source": {"path": "tests/fixtures/buggy_divzero.py"}}]})]
        if cmd == "scopes":
            return [resp({"scopes": [
                {"name": "Locals", "variablesReference": 101}]})]
        if cmd == "variables":
            return [resp({"variables": [{"name": "x", "value": "42"}]})]
        if cmd == "exceptionInfo":
            return [resp({"exceptionId": "ZeroDivisionError",
                          "description": "division by zero",
                          "details": {"stackTrace": "Traceback ..."}})]
        if cmd in ("next", "stepIn", "stepOut"):
            return [resp(),
                    event("stopped", {"reason": "step", "threadId": 1})]
        if cmd == "continue":
            state["continues"] += 1
            if state["continues"] <= secondary_stops:
                return [resp(),
                        event("stopped", {"reason": "breakpoint", "threadId": 1})]
            return [resp(), event("exited", {"exitCode": exit_code})]
        if cmd == "disconnect":
            return [resp()]
        return [resp()]

    return script


def make_session(fake, timeout=5):
    session = DAPSession("127.0.0.1", 5678, retry=1, retry_delay=0,
                         timeout=timeout)
    session._sock = fake
    return session


class TestDAPProtocol(unittest.TestCase):

    def test_dap_message_framing(self):
        fake = FakeSocket()
        session = make_session(fake)
        session.send({"seq": 1, "type": "request", "command": "initialize"})
        self.assertTrue(fake.raw_sent.startswith(b"Content-Length:"))
        header, _, body = fake.raw_sent.partition(b"\r\n\r\n")
        length = int(header.split(b":")[1].strip())
        self.assertEqual(length, len(body))
        self.assertEqual(json.loads(body)["command"], "initialize")

    def test_initialize_sequence(self):
        fake = FakeSocket(debugpy_script(initialized_before_response=False))
        session = make_session(fake)
        session.initialize()
        session.attach()
        session.wait_for_initialized()
        session.set_breakpoints("tests/fixtures/buggy_divzero.py", [5])
        cmds = fake.commands()
        self.assertEqual(cmds[:3], ["initialize", "attach", "setBreakpoints"])

    def test_set_breakpoints_verified(self):
        fake = FakeSocket(debugpy_script(verified_lines=(5, 9)))
        session = make_session(fake)
        session.initialize()
        session.attach()
        session.wait_for_initialized()
        verified = session.set_breakpoints("a.py", [5, 9])
        self.assertEqual([b["line"] for b in verified if b["verified"]], [5, 9])

    def test_capture_locals_on_stop(self):
        fake = FakeSocket(debugpy_script())
        session = make_session(fake)
        result = session.run_session(
            breakpoints=["tests/fixtures/buggy_divzero.py:5"], mode="red")
        self.assertEqual(result["stop_reason"], "breakpoint")
        self.assertTrue(result["frames"])
        self.assertEqual(result["frames"][0]["locals"].get("x"), "42")

    def test_connection_retry_then_fallback(self):
        attempts = []

        def refuse(*args, **kwargs):
            attempts.append(1)
            raise ConnectionRefusedError("refused")

        argv = ["dap_client.py", "--host", "127.0.0.1", "--port", "50000",
                "--breakpoints", "a.py:5",
                "--output", os.path.join(tempfile.mkdtemp(), "out.json"),
                "--mode", "red", "--debugger", "debugpy",
                "--target-cmd", "a.py", "--retry", "3", "--retry-delay", "0"]
        with mock.patch.object(dap_client.socket, "create_connection",
                               side_effect=refuse):
            with mock.patch.object(sys, "argv", argv):
                with self.assertRaises(SystemExit) as ctx:
                    dap_client.main()
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(len(attempts), 3)

    def test_pdb_fallback_parses_output(self):
        raw_fail = (
            "> /repo/buggy.py(5)divide()\n"
            "-> return a / b\n"
            "Traceback (most recent call last):\n"
            '  File "/repo/buggy.py", line 5, in divide\n'
            "ZeroDivisionError: division by zero\n")
        parsed = _parse_pdb_red(raw_fail, ["buggy.py:5"], returncode=0)
        self.assertTrue(parsed["exit_confirmed"])
        raw_clean = (
            "> /repo/buggy.py(5)divide()\n"
            "-> return a / b\n"
            "The program finished and will be restarted\n")
        parsed = _parse_pdb_red(raw_clean, ["buggy.py:5"], returncode=0)
        self.assertFalse(parsed["exit_confirmed"])

    def test_output_schema_complete(self):
        fake = FakeSocket(debugpy_script())
        session = make_session(fake)
        result = session.run_session(
            breakpoints=["tests/fixtures/buggy_divzero.py:5"], mode="red")
        required = ["status", "mode", "debugger", "language", "target", "port",
                    "breakpoints_requested", "breakpoints_verified",
                    "stop_reason", "frames", "exception", "stdout_tail",
                    "stderr_tail", "exit_code", "exit_code_source",
                    "session_duration_ms", "steps"]
        for key in required:
            self.assertIn(key, result)

    def test_detect_language(self):
        self.assertEqual(detect_language("src/main.py"), "python")
        self.assertEqual(detect_language("cmd/main.go"), "go")
        self.assertEqual(detect_language("app/index.js"), "node")
        self.assertEqual(detect_language("notes.txt"), "unknown")

    def test_no_third_party_imports(self):
        path = os.path.join(SCRIPTS_DIR, "dap_client.py")
        with open(path, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules += [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
        stdlib = set(sys.stdlib_module_names)
        for module in modules:
            top = module.split(".")[0]
            self.assertIn(top, stdlib,
                          f"non-stdlib import in dap_client.py: {module}")

    def test_seq_based_response_routing(self):
        fake = FakeSocket(debugpy_script(initialized_before_response=True))
        session = make_session(fake)
        session.initialize()
        session.attach()
        attach_seq = session._start_request_seq
        session.wait_for_initialized()
        session.set_breakpoints("a.py", [5])
        self.assertIn("setBreakpoints", fake.commands())
        # The attachResponse arrived on the wire after the initialized event
        # and after later requests were issued; it must have been routed into
        # the response map keyed by its request_seq, not by arrival order.
        self.assertIn(attach_seq, session._response_map)
        self.assertEqual(session._response_map[attach_seq]["command"],
                         "attach")

    def test_initialized_event_before_response(self):
        fake = FakeSocket(debugpy_script(initialized_before_response=True))
        session = make_session(fake)
        session.initialize()
        session.attach()
        session.wait_for_initialized()  # must not deadlock
        session.set_breakpoints("a.py", [5])
        self.assertIn("setBreakpoints", fake.commands())

    def test_set_exception_breakpoints_before_configuration_done(self):
        filters = [{"filter": "raised", "label": "Raised Exceptions"},
                   {"filter": "uncaught", "label": "Uncaught Exceptions"}]
        fake = FakeSocket(debugpy_script(filters=filters))
        session = make_session(fake)
        session.run_session(breakpoints=["a.py:5"], mode="red")
        cmds = fake.commands()
        self.assertLess(cmds.index("setBreakpoints"),
                        cmds.index("setExceptionBreakpoints"))
        self.assertLess(cmds.index("setExceptionBreakpoints"),
                        cmds.index("configurationDone"))
        req = [m for m in fake.sent
               if m.get("command") == "setExceptionBreakpoints"][0]
        self.assertEqual(req["arguments"]["filters"], ["uncaught"])

        # No advertised filters -> filters=[]
        fake2 = FakeSocket(debugpy_script(filters=None))
        session2 = make_session(fake2)
        session2.run_session(breakpoints=["a.py:5"], mode="red")
        req2 = [m for m in fake2.sent
                if m.get("command") == "setExceptionBreakpoints"][0]
        self.assertEqual(req2["arguments"]["filters"], [])

    def test_wait_for_exit_secondary_stop(self):
        fake = FakeSocket(debugpy_script(secondary_stops=1, exit_code=7))
        session = make_session(fake)
        result = session.run_session(breakpoints=["a.py:5"], mode="red")
        continues = [m for m in fake.sent if m.get("command") == "continue"]
        self.assertGreaterEqual(len(continues), 2)
        self.assertEqual(result["exit_code"], 7)

    def test_attach_failure_fast_fail(self):
        fake = FakeSocket(debugpy_script(fail_start=True))
        session = make_session(fake)
        session.initialize()
        session.attach()
        with self.assertRaises(DAPStartError):
            session.wait_for_initialized()
        self.assertNotIn("setBreakpoints", fake.commands())

    def test_pre_initialized_exit_fast_fail(self):
        fake = FakeSocket(debugpy_script(exited_before_initialized=True))
        session = make_session(fake)
        session.initialize()
        session.attach()
        with self.assertRaises(DAPStartError):
            session.wait_for_initialized()
        self.assertNotIn("setBreakpoints", fake.commands())

    def test_step_operations(self):
        fake = FakeSocket(debugpy_script())
        session = make_session(fake)
        session.initialize()
        session.attach()
        session.wait_for_initialized()
        session.set_breakpoints("a.py", [5])
        session.set_exception_breakpoints()
        session.configuration_done()
        session.wait_for_stop()
        for method, command in ((session.step_over, "next"),
                                (session.step_in, "stepIn"),
                                (session.step_out, "stepOut")):
            stopped = method(1)
            self.assertEqual(stopped["body"]["reason"], "step")
            req = [m for m in fake.sent if m.get("command") == command][0]
            self.assertEqual(req["arguments"]["threadId"], 1)

    def test_run_session_step_sequence(self):
        fake = FakeSocket(debugpy_script())
        session = make_session(fake)
        result = session.run_session(breakpoints=["a.py:5"], mode="red",
                                     step_sequence=["step_over", "step_in"])
        cmds = fake.commands()
        self.assertIn("next", cmds)
        self.assertIn("stepIn", cmds)
        self.assertLess(cmds.index("next"), cmds.index("stepIn"))
        self.assertEqual(len(result["steps"]), 2)
        for entry, action in zip(result["steps"], ["step_over", "step_in"]):
            self.assertEqual(entry["action"], action)
            self.assertIn("frames", entry)
            self.assertIn("locals", entry)

    def test_explicit_dlv_missing_is_blocked(self):
        # Explicit --debugger dlv with Delve absent must exit 3 (BLOCKED),
        # never 1 — exit 1 signals "connection failed -> pdb fallback" and
        # Go has no pdb fallback.
        argv = ["dap_client.py", "--port", "50001",
                "--breakpoints", "pkg/main.go:5",
                "--output", os.path.join(tempfile.mkdtemp(), "out.json"),
                "--mode", "red", "--debugger", "dlv", "--program", "./pkg"]
        with mock.patch.object(dap_client.shutil, "which",
                               return_value=None):
            with mock.patch.object(sys, "argv", argv):
                with self.assertRaises(SystemExit) as ctx:
                    dap_client.main()
        self.assertEqual(ctx.exception.code, 3)

    def test_green_no_stop_terminated_without_exited(self):
        # Regression: debugpy attach mode ends a no-stop session with
        # `terminated` only — no `exited`, socket held open. A GREEN fix
        # that bypasses the breakpoint must classify as CLEAN_EXIT via the
        # exit-code file, not burn the timeout and report TIMEOUT.
        def script(msg):
            cmd = msg.get("command")
            seq = msg.get("seq")
            resp = {"type": "response", "request_seq": seq, "success": True,
                    "command": cmd}
            if cmd in ("attach", "launch"):
                return [{"type": "event", "event": "initialized"}, resp]
            if cmd == "configurationDone":
                # Program runs to completion without hitting the breakpoint.
                return [resp, {"type": "event", "event": "terminated"}]
            if cmd == "setBreakpoints":
                return [dict(resp, body={"breakpoints": [
                    {"verified": True, "line": 5}]})]
            return [resp]

        fake = FakeSocket(script, idle_when_empty=True)
        session = make_session(fake, timeout=1)
        tmpdir = tempfile.mkdtemp(prefix="dap-exitcode-")
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        exit_file = os.path.join(tmpdir, "exit.code")
        with open(exit_file, "w", encoding="utf-8") as fh:
            fh.write("0\n")
        result = session.run_session(breakpoints=["a.py:5"], mode="green",
                                     exit_code_file=exit_file)
        self.assertEqual(result["status"], "CLEAN_EXIT")
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["exit_code_source"], "process_wait")
        self.assertIsNone(result["stop_reason"])

    def test_pdb_red_requires_breakpoint_hit(self):
        raw = ("Traceback (most recent call last):\n"
               '  File "/repo/other.py", line 99, in main\n'
               "RuntimeError: crash at unrelated site\n")
        parsed = _parse_pdb_red(raw, ["buggy.py:5"], returncode=1)
        self.assertFalse(parsed["exit_confirmed"])
        # A same-named file in an unrelated directory is not proof the
        # hypothesized site was reached.
        raw_collision = ("> /vendor/thirdparty/buggy.py(5)helper()\n"
                         "-> raise RuntimeError\n"
                         "Traceback (most recent call last):\n"
                         "RuntimeError: crash in vendored copy\n")
        parsed = _parse_pdb_red(raw_collision, ["src/buggy.py:5"],
                                returncode=1)
        self.assertFalse(parsed["exit_confirmed"])

    def test_pdb_sysexit_edge_cases(self):
        base = "> /repo/buggy.py(5)divide()\n-> return a / b\n"
        for status in ("-1", "42", "error"):
            raw = (base + "The program exited via sys.exit(). "
                   f"Exit status: {status}\n")
            parsed = _parse_pdb_red(raw, ["buggy.py:5"], returncode=0)
            self.assertTrue(parsed["exit_confirmed"],
                            f"sys.exit({status}) must be detected as failure")
            green = _parse_pdb_green(raw, returncode=0)
            self.assertEqual(green["status"], "FAILED")
        raw_zero = (base + "The program exited via sys.exit(). "
                    "Exit status: 0\n")
        parsed = _parse_pdb_red(raw_zero, ["buggy.py:5"], returncode=0)
        self.assertFalse(parsed["exit_confirmed"])
        green = _parse_pdb_green(raw_zero, returncode=0)
        self.assertEqual(green["status"], "CLEAN_EXIT")

    def test_pdb_stderr_captured_to_file(self):
        tmpdir = tempfile.mkdtemp(prefix="dap-test-")
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        script = os.path.join(tmpdir, "stderr_writer.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write("import sys\n"
                     "print('Traceback (most recent call last):',"
                     " file=sys.stderr)\n")
        output = os.path.join(tmpdir, "session-green-pdb.json")
        result = run_pdb_session([script], [f"{script}:2"], output,
                                 mode="green", python_exe=sys.executable,
                                 timeout=30)
        raw_path = result["raw_output"]
        with open(raw_path, "r", encoding="utf-8") as fh:
            raw = fh.read()
        self.assertIn("Traceback", raw)


def _find_debugpy_python():
    candidates = [sys.executable, "python3", "python3.12", "python3.11",
                  "python"]
    seen = set()
    for cand in candidates:
        exe = shutil.which(cand) or cand
        if exe in seen or not os.path.exists(exe):
            continue
        seen.add(exe)
        try:
            rc = subprocess.run([exe, "-c", "import debugpy"],
                                capture_output=True, timeout=30).returncode
        except (OSError, subprocess.TimeoutExpired):
            continue
        if rc == 0:
            return exe
    return None


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestIntegrationRedGreen(unittest.TestCase):

    def _run_cli(self, python_exe, target, port, mode, output):
        # debugpy attach mode never emits the DAP `exited` event, so the
        # launch wrapper writes the real process exit code for the client
        # to recover via --exit-code-file.
        exit_file = output + ".exitcode"
        server = subprocess.Popen(
            ["bash", "-c", '"$1" -m debugpy --listen "127.0.0.1:$2" '
             '--wait-for-client "$3"; echo $? > "$4"', "--",
             python_exe, str(port), target, exit_file],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            client = subprocess.run(
                [sys.executable, os.path.join(SCRIPTS_DIR, "dap_client.py"),
                 "--host", "127.0.0.1", "--port", str(port),
                 "--breakpoints", f"{target}:5",
                 "--output", output, "--mode", mode, "--debugger", "debugpy",
                 "--target-cmd", target, "--exit-code-file", exit_file,
                 "--timeout", "30", "--retry", "20", "--retry-delay", "0.5"],
                capture_output=True, text=True, timeout=120)
            server.communicate(timeout=30)
        finally:
            if server.poll() is None:
                server.kill()
                server.communicate()
        return client

    def test_integration_red_green_cycle(self):
        python_exe = _find_debugpy_python()
        if python_exe is None:
            self.skipTest("no interpreter with debugpy available")
        tmpdir = tempfile.mkdtemp(prefix="dap-integration-")
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)

        # RED: original buggy fixture must fail at the breakpoint line.
        red_json = os.path.join(tmpdir, "session-1-red.json")
        client = self._run_cli(python_exe, FIXTURE, _free_port(), "red",
                               red_json)
        self.assertEqual(client.returncode, 0,
                         f"red session failed: {client.stderr}")
        with open(red_json, "r", encoding="utf-8") as fh:
            red = json.load(fh)
        self.assertIn(red["status"], ("BREAKPOINT_HIT", "EXCEPTION_CAUGHT"))
        self.assertNotEqual(red["exit_code"], 0)
        self.assertTrue(red["frames"])

        # GREEN: patched temp copy must exit cleanly.
        fixed = os.path.join(tmpdir, "fixed_divzero.py")
        with open(FIXTURE, "r", encoding="utf-8") as fh:
            source = fh.read()
        self.assertIn("divide(10, 0)", source)
        with open(fixed, "w", encoding="utf-8") as fh:
            fh.write(source.replace("divide(10, 0)", "divide(10, 2)"))
        green_json = os.path.join(tmpdir, "session-1-green.json")
        client = self._run_cli(python_exe, fixed, _free_port(), "green",
                               green_json)
        self.assertEqual(client.returncode, 0,
                         f"green session failed: {client.stderr}")
        with open(green_json, "r", encoding="utf-8") as fh:
            green = json.load(fh)
        self.assertEqual(green["status"], "CLEAN_EXIT")
        self.assertEqual(green["exit_code"], 0)


if __name__ == "__main__":
    unittest.main()
