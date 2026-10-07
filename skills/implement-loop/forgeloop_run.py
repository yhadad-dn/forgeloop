#!/usr/bin/env python3
"""Standard run wrapper for ForgeLoop: start a long run detached, keep a run record, show live status.

For GPU runs and test suites expected to take over one hour. The run is launched detached (new
session, survives the caller); a small supervisor (this script, hidden `_supervise`) waits for it
and writes the exit code, end time and final state into the record. The script never judges the
pass criteria; the model fills PASS/FAIL with quoted evidence.

Usage (call it as python3 "${CLAUDE_PLUGIN_ROOT}/skills/implement-loop/forgeloop_run.py" <command>;
if CLAUDE_PLUGIN_ROOT is empty, do not guess a path):
  forgeloop_run.py start --task <name> --device cpu|gpu [--jobid <id>] --cwd <dir> --timeout <HH:MM:SS>
                         [--iter N] [--criteria-file <json>] -- <command...>
  forgeloop_run.py status [--record <json> | --latest] [--json]
  forgeloop_run.py card --record <json> [--kind auto|start|finish]

Files go to <repo root>/.claude/run-proofs/<task>-iter<N>.{log,json} (mode 0600, never deleted).
A single command word is run as a shell string; several words are quoted one by one.
SLURM access (gpu): FORGELOOP_SLURM_HOST or slurm_host in .claude/forgeloop.md, as cluster_status.py.
Times shown are Israel time. Exit 2 with a one-line reason on bad input. Stdlib only.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROG = "forgeloop_run.py"
TASK_RE = re.compile(r"[A-Za-z0-9._-]+")
STARTING_STATES = ("starting", "running")
SCRIPT_TAIL_BYTES = 32768
LAST_LINE_MAX = 100
CARD_TAIL_LINES = 5
KILL_AFTER_S = 5
HOST_RE = re.compile(r"(?!-)[A-Za-z0-9._-]+(@(?!-)[A-Za-z0-9._-]+)?")  # never starts with "-"
JOB_NAME_PREFIX = "yhadad_"


def _load_cluster_status():
    path = HERE.parent / "cluster-loop" / "cluster_status.py"
    spec = importlib.util.spec_from_file_location("forgeloop_cluster_status", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("forgeloop_cluster_status", mod)
    spec.loader.exec_module(mod)
    return mod


CS = _load_cluster_status()
ISRAEL = CS.ISRAEL


class UsageError(Exception):
    pass


class OneLineParser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


# --- small helpers -----------------------------------------------------------------

def now_il() -> datetime:
    return datetime.now(ISRAEL)


def parse_hms(text: str) -> int | None:
    m = re.fullmatch(r"(\d+):([0-5]\d):([0-5]\d)", text or "")
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) if m else None


def fmt_hms(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    return f"{h:02d}:{rem // 60:02d}:{rem % 60:02d}"


def fmt_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    return f"{h}:{rem // 60:02d}:{rem % 60:02d}" if h else f"{rem // 60:02d}:{rem % 60:02d}"


def fmt_il(iso: str | None) -> str:
    if not iso:
        return "—"
    return datetime.fromisoformat(iso).astimezone(ISRAEL).strftime("%Y-%m-%d %H:%M:%S") + " Israel time"


def repo_root(cwd: Path) -> Path:
    try:
        p = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=10)
        if p.returncode == 0 and p.stdout.strip():
            return Path(p.stdout.strip()).resolve()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return cwd


def write_private(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def load_record(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        raise UsageError(f"cannot read run record {path}")


def update_record(path: Path, fn) -> dict:
    """Read-modify-write under a lock, so the supervisor and status never overwrite each other."""
    lock_fd = os.open(str(path) + ".lock", os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        rec = load_record(path)
        fn(rec)
        write_private(path, rec)
        return rec
    finally:
        os.close(lock_fd)


def read_tail(path: str) -> str:
    try:
        with open(path, "rb") as f:
            size = os.fstat(f.fileno()).st_size
            f.seek(max(0, size - SCRIPT_TAIL_BYTES))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def log_lines(text: str) -> list[str]:
    return [l.strip() for l in re.split(r"[\r\n]+", text) if l.strip()]


def strip_secrets(line: str, limit: int) -> str:
    """cluster_status.sanitize_command, plus the word after a secret-looking word ("password hunter2")."""
    out, skip = [], False
    for tok in line.split():
        if skip:
            skip = False
            continue
        if CS.SECRET_RE.search(tok):
            skip = "=" not in tok
        out.append(tok)
    return CS.sanitize_command(" ".join(out), limit)


def log_view(rec: dict) -> tuple[str, dict]:
    """Last log line (secrets stripped, 100 chars) and parsed progress."""
    text = read_tail(rec["log_path"])
    lines = log_lines(text)
    last = strip_secrets(lines[-1], LAST_LINE_MAX) if lines else ""
    info = CS.analyze_log({"path": rec["log_path"], "mtime": int(time.time()), "text": text}, CS._now())
    rem = info.get("remaining")
    progress = {"fraction": info.get("fraction"), "counter": info.get("counter"),
                "remaining_s": int(rem.total_seconds()) if rem else None}
    return last, progress


# --- liveness and refresh --------------------------------------------------------------

def process_alive(pid) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        if stat.rsplit(")", 1)[1].split()[0] == "Z":
            return False
    except (OSError, IndexError):
        pass
    return True


def supervisor_alive(rec: dict) -> bool:
    pid = rec.get("supervisor_pid")
    if not process_alive(pid):
        return False
    try:
        return b"_supervise" in Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return True


def child_orphaned(rec: dict) -> bool:
    """The supervisor is gone but the command it started is still running."""
    return (rec["state"] in STARTING_STATES and rec.get("supervisor_pid") is not None
            and not supervisor_alive(rec) and process_alive(rec.get("pid")))


def refresh(path: Path) -> dict:
    """Re-read the record, mark a vanished supervisor and child as 'lost', refresh last line and progress."""
    rec = load_record(path)
    changed: dict = {}
    if rec["state"] in STARTING_STATES:
        pid_known = rec.get("supervisor_pid") is not None
        age = (now_il() - datetime.fromisoformat(rec["started"])).total_seconds()
        if (pid_known and not supervisor_alive(rec) and not process_alive(rec.get("pid"))) \
                or (not pid_known and age > 10):
            changed["lost"] = True
    last, progress = log_view(rec)

    def apply(r: dict) -> None:
        if r["state"] not in STARTING_STATES:  # the supervisor finished meanwhile: its values are final
            return
        if changed.get("lost") and r.get("exit_code") is None:
            r["state"], r["ended"] = "lost", now_il().isoformat()
        r["last_log_line"], r["progress"] = log_view(r)  # re-read inside the lock, not the pre-lock values

    if (last, progress) != (rec.get("last_log_line"), rec.get("progress")) or changed:
        return update_record(path, apply)
    return rec


# --- rendering ----------------------------------------------------------------------------

def progress_text(rec: dict) -> str:
    pr = rec.get("progress") or {}
    if pr.get("fraction") is None:
        return ""
    counter = re.sub(r"^ep(\d)", r"epoch \1", pr.get("counter") or "")
    return f"{CS.bar(pr['fraction'])} {int(pr['fraction'] * 100)}%" + (f" {counter}" if counter else "")


def duration_s(rec: dict) -> float:
    end = datetime.fromisoformat(rec["ended"]) if rec.get("ended") else now_il()
    return (end - datetime.fromisoformat(rec["started"])).total_seconds()


def status_line(rec: dict) -> str:
    who = f"{rec['task']} iter {rec['iter']}"
    last = f" · last: {rec['last_log_line']}" if rec.get("last_log_line") else ""
    state = rec["state"]
    if child_orphaned(rec):
        return f"⚠ supervisor lost, child still running · {who} · running {fmt_elapsed(duration_s(rec))}{last}"
    if state in STARTING_STATES:
        prog = f" · {progress_text(rec)}" if progress_text(rec) else ""
        return (f"▶ {who} · running {fmt_elapsed(duration_s(rec))} of {fmt_hms(rec['timeout_s'])}{prog}{last}")
    took = f" · took {fmt_elapsed(duration_s(rec))}"
    if state == "passed":
        head = f"✅ passed · {who}{took}"
    elif state == "failed":
        head = f"❌ failed exit {rec.get('exit_code')} · {who}{took}"
    elif state == "timeout":
        head = f"⏱ timeout · {who}{took} (limit {fmt_hms(rec['timeout_s'])})"
    elif state == "lost":
        head = f"⚠ lost · {who}{took} · process gone without an exit code"
    else:
        head = f"⚠ error · {who}{took}"
    return head + last


def public(rec: dict) -> dict:
    return {k: v for k, v in rec.items() if k != "argv_private"}  # legacy records may still carry it


def render_card(rec: dict, path: Path, kind: str) -> str:
    if kind == "auto":
        kind = "start" if rec["state"] in STARTING_STATES else "finish"
    where = f"SLURM job {rec['jobid']} on {rec.get('nodelist') or 'unknown node'} (gpu)" if rec["device"] == "gpu" \
        else "this machine (cpu)"
    status_cmd = f"python3 {Path(__file__).resolve()} status --record {path}"
    lines = [f"RUN CARD — {rec['task']} iter {rec['iter']} — {'started' if kind == 'start' else 'finished'}",
             f"command: {rec['command']}",
             f"command sha256: {rec.get('command_sha256', 'none')}",
             f"runs on: {where}, in {rec['cwd']}",
             f"started: {fmt_il(rec['started'])}"]
    if kind == "start":
        lines += [f"expected time: {fmt_hms(rec['timeout_s'])} (the timeout)",
                  f"log: {rec['log_path']}",
                  f"watch: {status_cmd}"]
    else:
        lines += [f"ended: {fmt_il(rec.get('ended'))}",
                  f"state: {rec['state']}",
                  f"exit code: {rec['exit_code'] if rec.get('exit_code') is not None else 'none'}",
                  f"duration: {fmt_elapsed(duration_s(rec))}",
                  f"log: {rec['log_path']}",
                  "last log lines:"]
        tail = log_lines(read_tail(rec["log_path"]))[-CARD_TAIL_LINES:]
        lines += [f"  {strip_secrets(l, 160)}" for l in tail] or ["  (log is empty)"]
        lines += ["CHECKLIST (the model fills each with PASS/FAIL and quoted log evidence; the script never judges):"]
        lines += [f"  [ ] {c['criterion']} — {c['verdict']}" + (f" — {c['evidence']}" if c.get("evidence") else
                                                                  " (fill PASS/FAIL + quoted evidence)")
                  for c in rec.get("criteria", [])] or ["  (no criteria given)"]
    return "\n".join(lines) + "\n"


# --- start ---------------------------------------------------------------------------------

def load_criteria(path: str | None) -> list[dict]:
    if not path:
        return []
    try:
        data = json.loads(Path(path).read_text())
        if isinstance(data, dict):
            data = data.get("pass_criteria", data.get("criteria"))
        out = []
        for item in data:
            text = item.get("criterion") if isinstance(item, dict) else item
            if not isinstance(text, str) or not text.strip():
                raise ValueError("entry is not text")
            out.append({"criterion": text, "verdict": "PENDING", "evidence": ""})
        return out
    except (OSError, ValueError, TypeError, AttributeError) as e:
        raise UsageError(f"criteria file {path} is not a JSON list of criteria ({e})")


def valid_host(host: str) -> str:
    if host and not HOST_RE.fullmatch(host):
        raise UsageError(f"SLURM host {host!r} is not a plain host name (user@host allowed); fix "
                         f"FORGELOOP_SLURM_HOST or slurm_host")
    return host


def slurm_runner():
    host = valid_host(os.environ.get("FORGELOOP_SLURM_HOST") or CS.read_settings().get("slurm_host") or "")
    return CS.Runner(host or None), host


def check_gpu_job(jobid: str) -> tuple[str, str]:
    runner, host = slurm_runner()
    rc, out, err = runner.run(["squeue", "-j", jobid, "-h", "-o", "%T"], timeout=30)
    state = out.strip().splitlines()[0].strip() if out.strip() else ""
    if rc != 0 and not state:
        raise UsageError(f"cannot check SLURM job {jobid}: {(err.strip() or 'squeue failed')[:120]}")
    if state not in ("R", "RUNNING"):
        raise UsageError(f"SLURM job {jobid} is not running (state: {state or 'not found'}); "
                         f"allocate one with /forgeloop:cluster-loop")
    rc, out, _ = runner.run(["squeue", "-j", jobid, "-h", "-o", "%j"], timeout=30)
    name = out.strip().splitlines()[0].strip() if rc == 0 and out.strip() else ""
    if not name.startswith(JOB_NAME_PREFIX):  # the shared account makes a user check useless
        raise UsageError(f"SLURM job {jobid} is named {name or 'unknown'!r}, not {JOB_NAME_PREFIX}*; "
                         f"refusing to run in a job that is not ours")
    rc, out, _ = runner.run(["squeue", "-j", jobid, "-h", "-o", "%N"], timeout=30)
    return (out.strip().splitlines()[0].strip() if rc == 0 and out.strip() else ""), host or ""


def build_argv(rec_args: dict, command: list[str], host: str) -> list[str]:
    shell_cmd = command[0] if len(command) == 1 else shlex.join(command)
    if rec_args["device"] == "cpu":
        return ["bash", "-lc", shell_cmd]  # the supervisor enforces the timeout
    argv = ["srun", f"--jobid={rec_args['jobid']}", f"--chdir={rec_args['cwd']}", "bash", "-lc", shell_cmd]
    if host:
        argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "--", valid_host(host), shlex.join(argv)]
    return argv


def create_exclusive(path: Path) -> None:
    try:
        os.close(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    except FileExistsError:
        raise UsageError(f"{path} already exists; use a new --iter or --task (nothing is overwritten)")


def cmd_start(args, command: list[str]) -> int:
    if not TASK_RE.fullmatch(args.task):
        raise UsageError(f"--task must match [A-Za-z0-9._-]+, got {args.task!r}")
    timeout_s = parse_hms(args.timeout)
    if not timeout_s:
        raise UsageError(f"--timeout must be HH:MM:SS and greater than zero, got {args.timeout!r}")
    if args.iter < 1:
        raise UsageError("--iter must be 1 or greater")
    if not command or not any(command):
        raise UsageError("a command is required after --")
    cwd = Path(args.cwd).expanduser()
    if not cwd.is_dir():
        raise UsageError(f"--cwd is not an existing directory: {args.cwd}")
    cwd = cwd.resolve()
    criteria = load_criteria(args.criteria_file)
    nodelist, host = "", ""
    if args.device == "gpu":
        if not args.jobid:
            raise UsageError("--device gpu requires --jobid")
        if not re.fullmatch(r"\d+", args.jobid):
            raise UsageError(f"--jobid must be a numeric SLURM job id, got {args.jobid!r}")
        nodelist, host = check_gpu_job(args.jobid)
    elif args.jobid:
        raise UsageError("--jobid is only valid with --device gpu")

    proofs = repo_root(cwd) / ".claude" / "run-proofs"
    stem = f"{args.task}-iter{args.iter}"
    log_path, rec_path, argv_path = proofs / f"{stem}.log", proofs / f"{stem}.json", proofs / f"{stem}.argv"
    real_cmd = command[0] if len(command) == 1 else shlex.join(command)
    argv = build_argv({"timeout_s": timeout_s, "device": args.device, "jobid": args.jobid, "cwd": str(cwd)},
                      command, host)
    rec = {"task": args.task, "iter": args.iter, "device": args.device, "jobid": args.jobid, "nodelist": nodelist,
           "command": CS.sanitize_command(real_cmd, 300),
           "command_sha256": hashlib.sha256(real_cmd.encode()).hexdigest(),
           "cwd": str(cwd), "started": now_il().isoformat(), "timeout_s": timeout_s, "pid": None,
           "supervisor_pid": None, "state": "starting", "exit_code": None, "ended": None, "timed_out": False,
           "log_path": str(log_path), "last_log_line": "", "progress": None, "criteria": criteria}
    created: list[Path] = []
    try:
        proofs.mkdir(parents=True, exist_ok=True)
        for p in (log_path, rec_path):  # exclusive: a concurrent start of the same task/iter loses here
            create_exclusive(p)
            created.append(p)
        fd = os.open(argv_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)  # the supervisor deletes it
        created.append(argv_path)
        with os.fdopen(fd, "w") as f:
            json.dump(argv, f)
        write_private(rec_path, rec)
        sup = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "_supervise", "--record", str(rec_path)],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               start_new_session=True, close_fds=True)
    except (OSError, UsageError) as e:
        for p in created:  # remove only what this call created
            try:
                p.unlink()
            except OSError:
                pass
        if isinstance(e, UsageError):
            raise
        raise UsageError(f"cannot start the run: {e}")
    update_record(rec_path, lambda r: r.update(supervisor_pid=sup.pid) if r["state"] in STARTING_STATES
                  and r.get("supervisor_pid") is None else None)
    end = time.time() + 5
    while time.time() < end:  # the child pid shows up within milliseconds
        cur = load_record(rec_path)
        if cur.get("pid") or cur["state"] not in STARTING_STATES:
            break
        time.sleep(0.05)
    sys.stdout.write(render_card(load_record(rec_path), rec_path, "start"))
    return 0


# --- supervisor ------------------------------------------------------------------------------

def stop_group(child: subprocess.Popen) -> None:
    for sig, wait in ((signal.SIGTERM, KILL_AFTER_S), (signal.SIGKILL, KILL_AFTER_S)):
        try:
            os.killpg(child.pid, sig)
        except OSError:
            pass
        try:
            child.wait(timeout=wait)
            break
        except subprocess.TimeoutExpired:
            continue
    try:
        os.killpg(child.pid, signal.SIGKILL)  # stragglers left in the group
    except OSError:
        pass


def cmd_supervise(args) -> int:
    path = Path(args.record)
    rec = load_record(path)
    argv_path = path.with_suffix(".argv")
    try:
        argv = json.loads(argv_path.read_text())
        argv_path.unlink()  # the real argv (it may hold a secret) is on disk only until launch
        log = open(rec["log_path"], "ab")
        child = subprocess.Popen(argv, cwd=rec["cwd"], stdin=subprocess.DEVNULL, stdout=log,
                                 stderr=subprocess.STDOUT, start_new_session=True)
    except (OSError, ValueError) as e:
        def fail(r):
            r.update(state="error", ended=now_il().isoformat(), supervisor_pid=os.getpid())
        update_record(path, fail)
        with open(rec["log_path"], "ab") as f:
            f.write(f"forgeloop_run: could not launch: {e}\n".encode())
        return 1
    update_record(path, lambda r: r.update(pid=child.pid, supervisor_pid=os.getpid(), state="running"))
    timed_out = False
    try:
        code = child.wait(timeout=rec["timeout_s"])
    except subprocess.TimeoutExpired:
        timed_out = True  # only the supervisor's own deadline makes a timeout
        stop_group(child)
        code = child.returncode
    code = 128 - code if code is not None and code < 0 else code
    state = "timeout" if timed_out else "passed" if code == 0 else "failed"
    last, progress = log_view(rec)
    update_record(path, lambda r: r.update(exit_code=code, ended=now_il().isoformat(), state=state,
                                           timed_out=timed_out, last_log_line=last, progress=progress))
    return 0


# --- status / card ------------------------------------------------------------------------------

def find_latest() -> Path:
    proofs = repo_root(Path(os.getcwd()).resolve()) / ".claude" / "run-proofs"
    records = sorted((p for p in proofs.glob("*-iter*.json")), key=lambda p: p.stat().st_mtime) \
        if proofs.is_dir() else []
    if not records:
        raise UsageError(f"no run records in {proofs}")
    return records[-1]


def cmd_status(args) -> int:
    if bool(args.record) == bool(args.latest):
        raise UsageError("give exactly one of --record <json> or --latest")
    path = Path(args.record) if args.record else find_latest()
    rec = refresh(path)
    print(json.dumps(public(rec), indent=2, ensure_ascii=False) if args.json else status_line(rec))
    return 0


def cmd_card(args) -> int:
    path = Path(args.record)
    sys.stdout.write(render_card(refresh(path), path, args.kind))
    return 0


# --- CLI ---------------------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = OneLineParser(prog=PROG, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", parser_class=OneLineParser)
    s = sub.add_parser("start", help="launch a run detached and print the RUN CARD")
    s.add_argument("--task", required=True, help="name, [A-Za-z0-9._-]+")
    s.add_argument("--device", required=True, choices=["cpu", "gpu"])
    s.add_argument("--jobid", default=None, help="SLURM job id (required for gpu; must be R)")
    s.add_argument("--cwd", required=True, help="existing directory the command runs in")
    s.add_argument("--timeout", required=True, help="HH:MM:SS")
    s.add_argument("--iter", type=int, default=1)
    s.add_argument("--criteria-file", default=None, help="JSON list of pass criteria")
    t = sub.add_parser("status", help="one live status line")
    t.add_argument("--record", default=None)
    t.add_argument("--latest", action="store_true")
    t.add_argument("--json", action="store_true")
    c = sub.add_parser("card", help="print the RUN CARD for start or finish")
    c.add_argument("--record", required=True)
    c.add_argument("--kind", choices=["auto", "start", "finish"], default="auto")
    v = sub.add_parser("_supervise")
    v.add_argument("--record", required=True)
    return ap


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    command: list[str] = []
    if "--" in argv:
        i = argv.index("--")
        argv, command = argv[:i], argv[i + 1:]
    ap = build_parser()
    try:
        args = ap.parse_args(argv)
        if not args.cmd:
            raise UsageError("a command is required: start, status or card (see --help)")
        if args.cmd == "start":
            return cmd_start(args, command)
        if command:
            raise UsageError(f"unexpected arguments after -- for {args.cmd}")
        return {"status": cmd_status, "card": cmd_card, "_supervise": cmd_supervise}[args.cmd](args)
    except UsageError as e:
        print(f"{PROG}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
