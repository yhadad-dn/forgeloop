#!/usr/bin/env python3
"""Debug Adapter Protocol client for debug-loop Stage 4 RED/GREEN sessions.

Drives a debugpy (Python) or dlv (Go) DAP server over TCP: initialize,
attach/launch, breakpoints, exception breakpoints, stop capture (frames,
locals, exceptionInfo), optional step sequence, continue-until-exit, and a
structured JSON session report. Includes a stdin-driven pdb fallback for
Python targets when debugpy is unavailable.

Stdlib-only by design: debugpy is the target server launched externally,
never imported here.

Exit codes:
  0  session completed, JSON written
  1  connection failed after --retry attempts (caller may use pdb fallback)
  2  RED mode: no breakpoint/exception stop before exit, or TIMEOUT
  3  invalid arguments or DEBUGGER_PREFLIGHT: BLOCKED (never pdb fallback)
  4  DAP protocol error (start rejected, malformed response)
"""

import argparse
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
from typing import Optional

EVIDENCE_STOP_REASONS = ("breakpoint", "exception")
MAX_FRAMES = 20
MAX_VARS_PER_SCOPE = 50
OUTPUT_TAIL_CHARS = 2000
PDB_SYSEXIT_MARKER = "The program exited via sys.exit()."


class DAPStartError(Exception):
    """attach/launch was rejected or the target died before initialized."""


class DAPProtocolError(Exception):
    """The adapter returned a failed or malformed response."""


class DAPSession:
    """Drives a single Debug Adapter Protocol session over TCP."""

    def __init__(self, host: str, port: int, retry: int = 3,
                 retry_delay: float = 1.0, timeout: float = 60.0) -> None:
        self.host = host
        self.port = port
        self.retry = max(1, retry)
        self.retry_delay = retry_delay
        self.timeout = timeout
        self._sock = None
        self._recv_buf = b""
        self._seq = 0
        self._start_request_seq = None
        self._event_queues = {}
        self._response_map = {}
        self._capabilities = {}
        self._terminated_seen = False

    # -- transport -------------------------------------------------------

    def connect(self) -> bool:
        if self._sock is not None:
            return True
        for attempt in range(self.retry):
            try:
                self._sock = socket.create_connection(
                    (self.host, self.port), timeout=self.timeout)
                # Short poll tick so wait loops can evaluate their own
                # deadlines; per-call deadlines govern timeouts, not the
                # socket timeout.
                self._sock.settimeout(0.25)
                return True
            except OSError:
                if attempt < self.retry - 1:
                    time.sleep(self.retry_delay)
        return False

    def send(self, message: dict) -> None:
        body = json.dumps(message).encode("utf-8")
        header = b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n"
        self._sock.sendall(header + body)

    def _read_more(self) -> None:
        chunk = self._sock.recv(65536)
        if not chunk:
            raise EOFError("DAP socket closed")
        self._recv_buf += chunk

    def recv(self) -> dict:
        while b"\r\n\r\n" not in self._recv_buf:
            self._read_more()
        header, _, rest = self._recv_buf.partition(b"\r\n\r\n")
        match = re.search(rb"Content-Length:\s*(\d+)", header)
        if match is None:
            raise DAPProtocolError(f"missing Content-Length in {header!r}")
        length = int(match.group(1))
        self._recv_buf = rest
        while len(self._recv_buf) < length:
            self._read_more()
        body, self._recv_buf = (self._recv_buf[:length],
                                self._recv_buf[length:])
        message = json.loads(body)
        if message.get("type") == "event":
            name = message.get("event")
            self._event_queues.setdefault(name, []).append(message)
            if name == "terminated":
                # Supplementary lifecycle signal only; `exited` stays the
                # single authoritative exit event.
                self._terminated_seen = True
        elif message.get("type") == "response":
            self._response_map[message.get("request_seq")] = message
        return message

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _send_request(self, command: str, arguments: dict = None) -> int:
        seq = self._next_seq()
        message = {"seq": seq, "type": "request", "command": command}
        if arguments is not None:
            message["arguments"] = arguments
        self.send(message)
        return seq

    def _wait_for_response(self, request_seq: int) -> dict:
        deadline = time.time() + self.timeout
        while request_seq not in self._response_map:
            if time.time() > deadline:
                raise TimeoutError(
                    f"no response for request seq {request_seq}")
            try:
                self.recv()
            except TimeoutError:
                continue  # poll tick; the deadline above governs
            except (OSError, EOFError) as exc:
                raise DAPProtocolError(
                    f"socket closed awaiting response {request_seq}: {exc}")
        response = self._response_map.pop(request_seq)
        if not response.get("success", False):
            raise DAPProtocolError(
                f"{response.get('command')} failed: "
                f"{response.get('message', 'no message')}")
        return response

    # -- session setup ---------------------------------------------------

    def initialize(self) -> dict:
        seq = self._send_request("initialize", {
            "clientID": "dap_client",
            "adapterID": "dap_client",
            "linesStartAt1": True,
            "columnsStartAt1": True,
            "pathFormat": "path",
            "locale": "en",
        })
        response = self._wait_for_response(seq)
        self._capabilities = response.get("body") or {}
        return response

    def attach(self) -> None:
        self._start_request_seq = self._send_request("attach", {
            "connect": {"host": self.host, "port": self.port},
        })

    def launch(self, program: str, mode: str = "debug",
               args: list = None) -> None:
        arguments = {"mode": mode, "program": program}
        if args:
            arguments["args"] = list(args)
        self._start_request_seq = self._send_request("launch", arguments)

    def wait_for_initialized(self) -> None:
        deadline = time.time() + self.timeout
        while True:
            if self._event_queues.get("initialized"):
                return
            start_response = self._response_map.get(self._start_request_seq)
            if start_response is not None and not start_response.get(
                    "success", False):
                raise DAPStartError(
                    "attach/launch rejected: "
                    f"{start_response.get('message', 'no message')}")
            if self._event_queues.get("exited"):
                raise DAPStartError(
                    "target exited before initialized "
                    "(build failure, wrong port, or immediate crash)")
            if time.time() > deadline:
                raise TimeoutError("timed out waiting for initialized event")
            try:
                self.recv()
            except TimeoutError:
                continue  # poll tick; the deadline above governs
            except (OSError, EOFError) as exc:
                raise DAPStartError(
                    f"socket closed before initialized: {exc}")

    def set_breakpoints(self, source: str, lines: list) -> list:
        seq = self._send_request("setBreakpoints", {
            "source": {"path": source},
            "breakpoints": [{"line": line} for line in lines],
            "lines": list(lines),
        })
        response = self._wait_for_response(seq)
        return (response.get("body") or {}).get("breakpoints", [])

    def set_exception_breakpoints(self, filters: list = None) -> None:
        if filters is None:
            advertised = self._capabilities.get(
                "exceptionBreakpointFilters") or []
            filters = [
                f.get("filter") or f.get("filterId")
                for f in advertised
                if "uncaught" in str(f.get("filter")
                                     or f.get("filterId") or "").lower()
            ]
        seq = self._send_request("setExceptionBreakpoints",
                                 {"filters": filters})
        self._wait_for_response(seq)

    def configuration_done(self) -> None:
        seq = self._send_request("configurationDone")
        self._wait_for_response(seq)

    # -- run-state waits ---------------------------------------------------

    def wait_for_stop(self) -> Optional[dict]:
        deadline = time.time() + self.timeout
        grace_deadline = None
        while True:
            if self._event_queues.get("stopped"):
                return self._event_queues["stopped"].pop(0)
            if self._event_queues.get("exited"):
                return None  # NO_STOP; exited stays queued for wait_for_exit
            if self._terminated_seen and grace_deadline is None:
                # debugpy attach mode ends no-stop sessions with `terminated`
                # only (no `exited`, socket held open); without this grace
                # window a GREEN run whose fix bypasses the breakpoint would
                # burn the whole timeout and be misclassified as TIMEOUT.
                # Capped by the main deadline: once terminated is seen the
                # outcome is NO_STOP, never TIMEOUT.
                grace_deadline = min(time.time() + min(2.0, self.timeout),
                                     deadline)
            now = time.time()
            if grace_deadline is not None and now >= grace_deadline:
                return None  # NO_STOP; caller recovers exit code out-of-band
            if now > deadline:
                raise TimeoutError("timed out waiting for stopped event")
            try:
                self.recv()
            except TimeoutError:
                continue  # poll tick; the deadline above governs
            except (OSError, EOFError):
                if self._event_queues.get("stopped"):
                    return self._event_queues["stopped"].pop(0)
                return None

    def wait_for_exit(self, on_stop=None) -> Optional[int]:
        deadline = time.time() + self.timeout
        grace_deadline = None
        while True:
            if self._event_queues.get("exited"):
                event = self._event_queues["exited"].pop(0)
                return (event.get("body") or {}).get("exitCode")
            if self._event_queues.get("stopped"):
                # Secondary stop: the debuggee is paused again; continue or
                # `exited` never arrives.
                event = self._event_queues["stopped"].pop(0)
                if on_stop is not None:
                    on_stop(event)
                thread_id = (event.get("body") or {}).get("threadId", 1)
                self.do_continue(thread_id)
                continue
            if self._terminated_seen and grace_deadline is None:
                # debugpy attach mode never follows `terminated` with
                # `exited` (the adapter holds the socket open awaiting
                # disconnect); give `exited` a short grace window, then
                # let the caller recover the exit code out-of-band. Capped
                # by the main deadline so terminated never ends in TIMEOUT.
                grace_deadline = min(time.time() + min(2.0, self.timeout),
                                     deadline)
            now = time.time()
            if grace_deadline is not None and now >= grace_deadline:
                return None
            if now > deadline:
                raise TimeoutError("timed out waiting for exited event")
            try:
                self.recv()
            except TimeoutError:
                continue  # poll tick; the deadlines above govern
            except (OSError, EOFError):
                # Socket closed without `exited`: no authoritative exit
                # code exists on the wire.
                return None

    # -- state capture -----------------------------------------------------

    def get_stack_trace(self, thread_id: int) -> list:
        seq = self._send_request("stackTrace", {"threadId": thread_id})
        response = self._wait_for_response(seq)
        return (response.get("body") or {}).get("stackFrames", [])

    def get_scopes(self, frame_id: int) -> list:
        seq = self._send_request("scopes", {"frameId": frame_id})
        response = self._wait_for_response(seq)
        return (response.get("body") or {}).get("scopes", [])

    def get_variables(self, variables_reference: int) -> list:
        seq = self._send_request("variables",
                                 {"variablesReference": variables_reference})
        response = self._wait_for_response(seq)
        return (response.get("body") or {}).get("variables", [])

    def get_exception_info(self, thread_id: int) -> dict:
        seq = self._send_request("exceptionInfo", {"threadId": thread_id})
        response = self._wait_for_response(seq)
        return response.get("body") or {}

    # -- execution control ---------------------------------------------------

    def do_continue(self, thread_id: int) -> None:
        self._send_request("continue", {"threadId": thread_id})

    def _step(self, command: str, thread_id: int) -> Optional[dict]:
        """Send a step request; return the stopped event, or None when the
        step ran the debuggee to completion (exited queued, or terminated
        without exited — debugpy attach mode). The exited event is left
        queued for wait_for_exit."""
        self._send_request(command, {"threadId": thread_id})
        deadline = time.time() + self.timeout
        grace_deadline = None
        while not self._event_queues.get("stopped"):
            if self._event_queues.get("exited"):
                return None  # step ran the debuggee to completion
            if self._terminated_seen and grace_deadline is None:
                grace_deadline = min(time.time() + min(2.0, self.timeout),
                                     deadline)
            now = time.time()
            if grace_deadline is not None and now >= grace_deadline:
                return None  # terminated, no exited (debugpy attach mode)
            if now > deadline:
                raise TimeoutError(f"timed out waiting for stop after "
                                   f"{command}")
            try:
                self.recv()
            except TimeoutError:
                continue  # poll tick; the deadline above governs
            except (OSError, EOFError) as exc:
                # A crash here would exit the interpreter with code 1, which
                # callers read as "connection failed -> pdb fallback".
                raise DAPProtocolError(
                    f"socket closed while stepping ({command}): {exc}")
        return self._event_queues["stopped"].pop(0)

    def step_over(self, thread_id: int) -> Optional[dict]:
        return self._step("next", thread_id)

    def step_in(self, thread_id: int) -> Optional[dict]:
        return self._step("stepIn", thread_id)

    def step_out(self, thread_id: int) -> Optional[dict]:
        return self._step("stepOut", thread_id)

    def disconnect(self) -> None:
        try:
            if self._sock is not None:
                self._send_request("disconnect")
        except OSError:
            pass
        try:
            if self._sock is not None:
                self._sock.close()
        except OSError:
            pass
        self._sock = None

    # -- capture helpers -----------------------------------------------------

    def _capture_frames(self, thread_id: int) -> list:
        frames = []
        for index, raw in enumerate(self.get_stack_trace(thread_id)
                                    [:MAX_FRAMES]):
            entry = {
                "id": raw.get("id"),
                "name": raw.get("name"),
                "source": (raw.get("source") or {}).get("path"),
                "line": raw.get("line"),
                "locals": {},
                "globals_sampled": {},
            }
            if index == 0:
                for scope in self.get_scopes(raw.get("id")):
                    if scope.get("expensive"):
                        continue
                    name = str(scope.get("name") or "").lower()
                    bucket = (entry["globals_sampled"] if "global" in name
                              else entry["locals"])
                    variables = self.get_variables(
                        scope.get("variablesReference"))
                    for var in variables[:MAX_VARS_PER_SCOPE]:
                        bucket[var.get("name")] = str(var.get("value"))
            frames.append(entry)
        return frames

    def _capture_exception(self, thread_id: int) -> dict:
        try:
            info = self.get_exception_info(thread_id)
        except (DAPProtocolError, TimeoutError, OSError, EOFError):
            return {"type": "unknown", "message": "", "traceback": ""}
        return {
            "type": info.get("exceptionId"),
            "message": info.get("description"),
            "traceback": (info.get("details") or {}).get("stackTrace", ""),
        }

    def _output_tail(self, categories: tuple) -> str:
        text = "".join(
            (event.get("body") or {}).get("output", "")
            for event in self._event_queues.get("output", [])
            if (event.get("body") or {}).get("category", "stdout")
            in categories)
        return text[-OUTPUT_TAIL_CHARS:]

    # -- full session ----------------------------------------------------------

    def _recover_exit_code(self, exit_code_file: str) -> Optional[int]:
        """Read the debuggee's exit code from the agent's launch wrapper.

        debugpy in --listen --wait-for-client attach mode never sends the
        DAP `exited` event, so no exit code exists on the wire. The launch
        wrapper (`{cmd}; echo $? > file`) writes the real process exit code;
        this is used only when the adapter closed without `exited`.
        """
        deadline = time.time() + min(self.timeout, 15.0)
        while time.time() < deadline:
            try:
                with open(exit_code_file, "r", encoding="utf-8") as fh:
                    text = fh.read().strip()
                if text:
                    return int(text)
            except (OSError, ValueError):
                pass
            time.sleep(0.1)
        return None

    def run_session(self, breakpoints: list, mode: str,
                    debugger: str = "debugpy", program: str = None,
                    dlv_mode: str = "debug", dlv_args: list = None,
                    step_sequence: list = None, target: str = None,
                    exit_code_file: str = None) -> dict:
        started = time.time()
        result = {
            "status": "ERROR",
            "mode": mode,
            "debugger": debugger,
            "language": "go" if debugger == "dlv" else "python",
            "target": target or program or (
                breakpoints[0].rsplit(":", 1)[0] if breakpoints else None),
            "port": self.port,
            "breakpoints_requested": list(breakpoints),
            "breakpoints_verified": [],
            "stop_reason": None,
            "frames": [],
            "exception": None,
            "stdout_tail": "",
            "stderr_tail": "",
            "exit_code": None,
            "exit_code_source": None,
            "session_duration_ms": 0,
            "steps": [],
        }
        if not self.connect():
            raise ConnectionError(
                f"could not connect to {self.host}:{self.port} "
                f"after {self.retry} attempts")
        try:
            self.initialize()
            if debugger == "dlv":
                self.launch(program, dlv_mode, dlv_args)
            else:
                self.attach()
            self.wait_for_initialized()

            by_source = {}
            for spec in breakpoints:
                source, _, line = spec.rpartition(":")
                by_source.setdefault(source, []).append(int(line))
            for source, lines in by_source.items():
                for bp in self.set_breakpoints(source, lines):
                    if bp.get("verified"):
                        result["breakpoints_verified"].append(
                            f"{source}:{bp.get('line')}")
            self.set_exception_breakpoints()
            self.configuration_done()

            stop_event = None
            while True:
                event = self.wait_for_stop()
                if event is None:
                    break
                body = event.get("body") or {}
                if body.get("reason") in EVIDENCE_STOP_REASONS:
                    stop_event = event
                    break
                # Entry/step/pause stops are not evidence; continue past them.
                self.do_continue(body.get("threadId", 1))

            if stop_event is not None:
                body = stop_event.get("body") or {}
                thread_id = body.get("threadId", 1)
                result["stop_reason"] = body.get("reason")
                result["frames"] = self._capture_frames(thread_id)
                if result["stop_reason"] == "exception":
                    result["exception"] = self._capture_exception(thread_id)
                step_methods = {"step_over": self.step_over,
                                "step_in": self.step_in,
                                "step_out": self.step_out}
                debuggee_ended_mid_step = False
                for action in (step_sequence or []):
                    if step_methods[action](thread_id) is None:
                        # Debuggee ended mid-step; keep prior evidence and
                        # let wait_for_exit classify via exit-code recovery.
                        debuggee_ended_mid_step = True
                        break
                    frames = self._capture_frames(thread_id)
                    result["steps"].append({
                        "action": action,
                        "frames": frames,
                        "locals": frames[0]["locals"] if frames else {},
                    })
                if not debuggee_ended_mid_step:
                    self.do_continue(thread_id)

            def on_secondary_stop(event):
                body = event.get("body") or {}
                if (body.get("reason") == "exception"
                        and result["exception"] is None):
                    result["exception"] = self._capture_exception(
                        body.get("threadId", 1))

            result["exit_code"] = self.wait_for_exit(
                on_stop=on_secondary_stop)
            result["exit_code_source"] = (
                "dap_exited_event" if result["exit_code"] is not None
                else None)
            if result["exit_code"] is None and exit_code_file:
                result["exit_code"] = self._recover_exit_code(exit_code_file)
                result["exit_code_source"] = (
                    "process_wait" if result["exit_code"] is not None
                    else None)

            if result["exit_code"] is None:
                result["status"] = "ERROR"
            elif mode == "green":
                clean = (result["exit_code"] == 0
                         and result["exception"] is None)
                result["status"] = "CLEAN_EXIT" if clean else "FAILED"
            elif stop_event is None:
                result["status"] = "NO_STOP"
            elif (result["stop_reason"] == "exception"
                  or result["exception"] is not None):
                result["status"] = "EXCEPTION_CAUGHT"
            else:
                result["status"] = "BREAKPOINT_HIT"
        except TimeoutError as exc:
            result["status"] = "TIMEOUT"
            result["error"] = str(exc)
        finally:
            result["stdout_tail"] = self._output_tail(("stdout", "console"))
            result["stderr_tail"] = self._output_tail(("stderr",))
            result["session_duration_ms"] = int(
                (time.time() - started) * 1000)
            self.disconnect()
        return result


# -- pdb fallback (Python only) ------------------------------------------------


def _pdb_sysexit_status(raw: str) -> Optional[str]:
    index = raw.find(PDB_SYSEXIT_MARKER)
    if index == -1:
        return None
    match = re.search(r"Exit status:\s*(.+)", raw[index:])
    if match is None:
        return ""
    return match.group(1).strip()


def _pdb_sysexit_failed(raw: str) -> bool:
    status = _pdb_sysexit_status(raw)
    # sys.exit() -> "None" and sys.exit(0) -> "0" are clean; anything else
    # (including "-1", "42", and string messages) is a failure.
    return status is not None and status not in ("0", "None")


# pdb renders stack frames as `  /path/to/file.py(42)funcname()` (current
# frame prefixed with `> `). Matching `file:line` instead would hit the
# "Breakpoint 1 at file.py:42" header and produce false positives.
_PDB_FRAME_RE = re.compile(
    r"^\s*>?\s*(\S+\.py)\((\d+)\)(<module>|[A-Za-z_]\w*)\(\)", re.M)


def _pdb_breakpoint_hit(raw: str, breakpoints: list) -> bool:
    for spec in breakpoints:
        source, _, line = spec.rpartition(":")
        want = os.path.normpath(source)
        for match in _PDB_FRAME_RE.finditer(raw):
            if match.group(2) != line:
                continue
            frame_path = os.path.normpath(match.group(1))
            # Path-suffix comparison, not basename: a same-named file in an
            # unrelated directory must not count as proof the hypothesized
            # site was reached.
            if frame_path == want or frame_path.endswith(os.sep + want):
                return True
    return False


def _parse_pdb_frames(raw: str) -> list:
    frames = []
    for match in _PDB_FRAME_RE.finditer(raw):
        frames.append({
            "source": match.group(1),
            "line": int(match.group(2)),
            "name": match.group(3),
        })
    return frames


def _pdb_exception_text(raw: str) -> Optional[str]:
    index = raw.find("Traceback")
    if index != -1:
        return raw[index:index + 4000]
    if _pdb_sysexit_failed(raw):
        return f"sys.exit({_pdb_sysexit_status(raw)})"
    return None


def _parse_pdb_red(raw: str, breakpoints: list, returncode: int) -> dict:
    hit = _pdb_breakpoint_hit(raw, breakpoints)
    failure = ("Traceback" in raw or _pdb_sysexit_failed(raw)
               or returncode != 0)
    return {
        "status": "FALLBACK_PDB" if hit else "NO_STOP",
        "debugger": "pdb",
        "frames": _parse_pdb_frames(raw),
        "exception": _pdb_exception_text(raw),
        "exit_confirmed": hit and failure,
    }


def _parse_pdb_green(raw: str, returncode: int) -> dict:
    clean = ("Traceback" not in raw and not _pdb_sysexit_failed(raw)
             and returncode == 0)
    return {
        "status": "CLEAN_EXIT" if clean else "FAILED",
        "debugger": "pdb",
        "frames": _parse_pdb_frames(raw),
        "exception": _pdb_exception_text(raw),
    }


def run_pdb_session(reproducer_cmd: list, breakpoints: list,
                    output_path: str, mode: str = "red",
                    python_exe: str = "python3", timeout: int = 60) -> dict:
    if mode == "red":
        commands = []
        for spec in breakpoints:
            commands.append(f"break {spec}")
        commands.append("continue")
        commands.append("where")
        commands.append("pp locals()")
        for spec in breakpoints:
            # Clear before resuming: a re-hit inside a loop would raise
            # BdbQuit at stdin EOF and masquerade as target failure.
            commands.append(f"clear {spec}")
        commands.append("continue")
        # No trailing `quit`: quit can interrupt Traceback printing before
        # it reaches the raw output file.
        stdin_text = "\n".join(commands) + "\n"
    else:
        stdin_text = "continue\nquit\n"

    base = output_path[:-5] if output_path.endswith(".json") else output_path
    raw_path = base + "-raw.txt"
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    argv = [python_exe, "-m", "pdb"] + list(reproducer_cmd)
    try:
        with open(raw_path, "wb") as raw_file:
            # stdout to file first, stderr merged into it — the `> file 2>&1`
            # ordering; the reverse would lose Traceback output.
            proc = subprocess.run(argv, input=stdin_text.encode("utf-8"),
                                  stdout=raw_file, stderr=subprocess.STDOUT,
                                  timeout=timeout)
        returncode = proc.returncode
    except subprocess.TimeoutExpired:
        result = {
            "status": "TIMEOUT",
            "mode": mode,
            "debugger": "pdb",
            "frames": [],
            "exception": None,
            "exit_confirmed": False,
            "breakpoints_requested": list(breakpoints),
            "raw_output": raw_path,
            "returncode": None,
        }
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
        return result

    with open(raw_path, "r", encoding="utf-8", errors="replace") as fh:
        raw = fh.read()

    if mode == "red":
        result = _parse_pdb_red(raw, breakpoints, returncode)
    else:
        result = _parse_pdb_green(raw, returncode)
    result.update({
        "mode": mode,
        "breakpoints_requested": list(breakpoints),
        "raw_output": raw_path,
        "returncode": returncode,
    })
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    return result


# -- dispatch --------------------------------------------------------------


def detect_language(target: str) -> str:
    extension = os.path.splitext(target)[1].lower()
    return {".py": "python", ".go": "go", ".js": "node"}.get(
        extension, "unknown")


def _blocked(reason: str) -> None:
    print(f"DEBUGGER_PREFLIGHT: BLOCKED — {reason}", file=sys.stderr)
    raise SystemExit(3)


def select_debugger(language: str, check: bool = True,
                    python_exe: str = "python3") -> str:
    if language == "python":
        if not check:
            return "debugpy"
        try:
            rc = subprocess.run([python_exe, "-c", "import debugpy"],
                                capture_output=True, timeout=30).returncode
        except (OSError, subprocess.TimeoutExpired):
            rc = 1
        return "debugpy" if rc == 0 else "pdb"
    if language == "go":
        if not check or shutil.which("dlv"):
            return "dlv"
        _blocked("dlv not found for Go target; install delve "
                 "(Go has no pdb fallback)")
    if language == "node":
        _blocked("Node.js debugging deferred: CDP protocol differs from DAP")
    _blocked(f"unsupported language {language!r}")


def validate_target_cmd(cmd: str) -> list:
    if not cmd or not cmd.strip():
        _blocked("empty --target-cmd; supply 'script.py [args]' or "
                 "'-m module [args]'")
    if re.search(r"&&|\|\||;|\||>|<", cmd):
        _blocked(f"shell constructs not accepted in --target-cmd: {cmd!r}")
    parts = shlex.split(cmd)
    first = parts[0]
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", first):
        _blocked(f"env-var assignment not accepted in --target-cmd: "
                 f"{first!r}")
    if first == "-m":
        if len(parts) < 2:
            _blocked("-m requires a module name")
        return parts
    if first.endswith(".py"):
        return parts
    _blocked(f"bare command {first!r} not accepted; do not translate "
             "console scripts (e.g. 'pytest') — supply an explicit "
             "'script.py [args]' or '-m module [args]' form")


# -- CLI ---------------------------------------------------------------------


def _write_output(path: str, result: dict) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DAP client for debug-loop Stage 4 RED/GREEN sessions")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5678)
    parser.add_argument("--breakpoints", default="",
                        help="comma-separated file:line specs")
    parser.add_argument("--output", required=True)
    parser.add_argument("--mode", choices=("red", "green"), required=True)
    parser.add_argument("--target-cmd", default=None,
                        help="Stage 3 reproducer parts after the "
                             "interpreter (debugpy/pdb only)")
    parser.add_argument("--python-exe", default="python3")
    parser.add_argument("--debugger", default="auto",
                        choices=("auto", "debugpy", "dlv", "pdb"))
    parser.add_argument("--program", default=None,
                        help="Go package path or source file (dlv only)")
    parser.add_argument("--dlv-mode", default="debug",
                        choices=("debug", "test"))
    parser.add_argument("--dlv-args", default=None,
                        help="comma-separated test-binary args, e.g. "
                             "'-test.run,TestFoo'")
    parser.add_argument("--exit-code-file", default=None,
                        help="file the launch wrapper writes the debuggee's "
                             "exit code to (`{cmd}; echo $? > file`); used "
                             "when the adapter closes without an `exited` "
                             "event (debugpy attach mode)")
    parser.add_argument("--step-sequence", default=None,
                        help="comma-separated step actions: "
                             "step_over,step_in,step_out")
    parser.add_argument("--retry", type=int, default=3)
    parser.add_argument("--retry-delay", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    breakpoints = [s.strip() for s in args.breakpoints.split(",")
                   if s.strip()]
    for spec in breakpoints:
        source, sep, line = spec.rpartition(":")
        if not sep or not source or not line.isdigit():
            _blocked(f"malformed breakpoint {spec!r}; expected file:line")

    debugger = args.debugger
    if debugger == "auto":
        probe = (breakpoints[0].rsplit(":", 1)[0] if breakpoints
                 else (args.program or args.target_cmd or ""))
        language = detect_language(probe)
        debugger = select_debugger(language, check=True,
                                   python_exe=args.python_exe)

    step_sequence = None
    if args.step_sequence:
        step_sequence = [s.strip() for s in args.step_sequence.split(",")
                         if s.strip()]
        invalid = set(step_sequence) - {"step_over", "step_in", "step_out"}
        if invalid:
            _blocked(f"invalid step actions: {sorted(invalid)}")

    if debugger == "pdb":
        parts = validate_target_cmd(args.target_cmd)
        result = run_pdb_session(parts, breakpoints, args.output,
                                 mode=args.mode, python_exe=args.python_exe,
                                 timeout=args.timeout)
        if result["status"] == "TIMEOUT":
            raise SystemExit(2)
        if args.mode == "red" and not result.get("exit_confirmed"):
            raise SystemExit(2)
        raise SystemExit(0)

    target = None
    dlv_args = None
    if debugger == "dlv":
        # Explicit --debugger dlv must fail BLOCKED (exit 3) when Delve is
        # missing, same as the auto path — never exit 1, which callers read
        # as "connection failed -> pdb fallback" (there is no Go fallback).
        if not shutil.which("dlv"):
            _blocked("dlv not found for Go target; install delve "
                     "(Go has no pdb fallback)")
        if not args.program:
            _blocked("--program is required for dlv "
                     "(--target-cmd is ignored)")
        if args.dlv_args:
            dlv_args = [s.strip() for s in args.dlv_args.split(",")
                        if s.strip()]
        target = args.program
    else:
        parts = validate_target_cmd(args.target_cmd)
        target = parts[1] if parts[0] == "-m" else parts[0]

    session = DAPSession(args.host, args.port, retry=args.retry,
                         retry_delay=args.retry_delay, timeout=args.timeout)
    if not session.connect():
        print(f"connection to {args.host}:{args.port} failed after "
              f"{args.retry} attempts", file=sys.stderr)
        raise SystemExit(1)

    try:
        result = session.run_session(
            breakpoints=breakpoints, mode=args.mode, debugger=debugger,
            program=args.program, dlv_mode=args.dlv_mode, dlv_args=dlv_args,
            step_sequence=step_sequence, target=target,
            exit_code_file=args.exit_code_file)
    except (DAPStartError, DAPProtocolError) as exc:
        _write_output(args.output, {
            "status": "ERROR", "mode": args.mode, "debugger": debugger,
            "error": str(exc),
        })
        print(f"DAP error: {exc}", file=sys.stderr)
        raise SystemExit(4)

    _write_output(args.output, result)
    if result["status"] == "TIMEOUT":
        raise SystemExit(2)
    if args.mode == "red" and result["status"] == "NO_STOP":
        raise SystemExit(2)
    if result["status"] == "ERROR":
        raise SystemExit(4)
    raise SystemExit(0)


if __name__ == "__main__":
    main()
