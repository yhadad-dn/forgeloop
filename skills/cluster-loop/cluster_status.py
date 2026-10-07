#!/usr/bin/env python3
"""Cluster status for ForgeLoop: are my jobs progressing, when do they finish, what is wrong.

Default view is "what can I use": free GPUs now, fully busy nodes, one line per job of
yours (id, name, node, end time, plus `does:` evidence), and a warning only for a real
problem (a full node is normal, never a warning). `--plain` prints the previous default
(one row per job with progress, finish time, expiry, state, one line per node, warnings).
`--detail` adds the full per-node view (per-GPU numbers, processes, containers, disk).
Times are Israel time. Stdlib only.

Usage:
  cluster_status.py --mine
  cluster_status.py --job 21577 [--log run.log] [--label "rank-alloc proof run"]
  cluster_status.py --job 21577 --log a.log --job 21580 --log b.log   # pairs in order
  cluster_status.py --mine --plain | --detail | --warnings | --json | --timing | --fresh | --raw

Warnings: the default view shows a warning only if it belongs to a --job run or to a node
such a job runs on; --mine alone shows none. `--warnings`, `--plain` and `--detail` show all.
`--json` is complete and marks each warning (`warning_details`) and job with `relevant`.

Speed: all SLURM data comes back in one round trip; node probes run in parallel
(`srun --overlap`, 15 s timeout each) and run their own commands in parallel; ssh to
--slurm-host / FORGELOOP_SLURM_HOST reuses one connection (ControlMaster); how each
node exposes its GPUs is cached; results are cached for 20 s (`--fresh` bypasses).
Fields that cannot be collected show as n/a or "—" with a note; nothing is guessed.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import os
import re
import shlex
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ISRAEL = ZoneInfo("Asia/Jerusalem")
GIB = 2 ** 30  # memory is shown in GiB, labelled GB as vendors do (MI355X: 288 GB)
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "forgeloop" / "cluster-status"
RESULT_TTL_S = 20
PROBE_TIMEOUT_S = 15

IDLE_UTIL_PCT = 5.0
IDLE_MEM_FRAC = 0.02
MEM_HIGH_FRAC = 0.92
DISK_HIGH_PCT = 90
EXPIRY_SOON = timedelta(minutes=30)
LOG_STALE = timedelta(minutes=10)
LOG_ERROR_RE = re.compile(r"Traceback|\bError\b|OutOfMemory|out of memory|\bOOM\b|\bNaN\b|\bnan\b|Segmentation fault|\bKilled\b")

SQUEUE_FMT = "%i|%j|%T|%P|%N|%S|%e|%L|%u|%M|%r|%E"

SNAPSHOT = r"""
set +e
command -v squeue >/dev/null 2>&1 || { echo "=== noslurm"; echo "=== end"; exit 0; }
echo "=== offset"; date +%z
IDS=__IDS__
if [ -n "$IDS" ]; then SEL="-j $IDS"; else SEL="-u $USER"; fi
echo "=== jobs"; squeue -h $SEL -o "__FMT__"
echo "=== steps"; squeue -h -s $SEL -o "%i|%j|%M"
echo "=== detail"
for j in $(squeue -h $SEL -t R -o %i); do
  echo "@@JOB $j"
  info=$(scontrol show job -o "$j")
  nl=$(echo "$info" | grep -o ' NodeList=[^ ]*' | cut -d= -f2)
  echo "@@HOSTS $j $(scontrol show hostnames "$nl" | tr '\n' ' ')"
  echo "@@TRES $j $(echo "$info" | grep -o ' AllocTRES=[^ ]*' | cut -d= -f2-) $(echo "$info" | grep -o ' NumNodes=[0-9]*' | cut -d= -f2)"
  out=$(echo "$info" | grep -o ' StdOut=[^ ]*' | cut -d= -f2)
  if [ -n "$out" ] && [ -r "$out" ]; then
    echo "@@LOG $j $(stat -c %Y "$out") $out"; tail -c 32768 "$out" | base64 -w0; echo
  fi
done
for spec in __LOGS__; do
  j=${spec%%:*}; p=${spec#*:}
  if [ -r "$p" ]; then echo "@@LOG $j $(stat -c %Y "$p") $p"; tail -c 32768 "$p" | base64 -w0; echo; fi
done
echo "=== sinfo"; sinfo -h -N -o "%N|%T|%E"
echo "=== gres"; sinfo -h -N -O "NodeList:60,Gres:60,GresUsed:80" 2>/dev/null
echo "=== end"
"""

PROBE = r"""
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export PATH="$PATH:${FL_EXTRA_PATH:-/opt/rocm/bin:/opt/rocm/sbin}"
M="${FL_METHOD:-}"
ROCM="--showtemp --showuse --showmeminfo vram --showpower --csv"
if [ -z "$M" ]; then
  if command -v rocm-smi >/dev/null 2>&1; then M=host
  elif command -v nvidia-smi >/dev/null 2>&1; then M=nvidia
  else
    # Hosts often lack rocm-smi; it lives in the workload containers.
    for c in $(docker ps --format '{{.Names}}' 2>/dev/null || sudo -n docker ps --format '{{.Names}}' 2>/dev/null); do
      if docker exec "$c" sh -c 'command -v rocm-smi' >/dev/null 2>&1; then M="docker:$c"; break; fi
      if sudo -n docker exec "$c" sh -c 'command -v rocm-smi' >/dev/null 2>&1; then M="sudo-docker:$c"; break; fi
    done
  fi
fi
[ -n "$M" ] || M=none
case "$M" in
  host)          (rocm-smi $ROCM > "$T/gpu" 2>/dev/null; rocm-smi --showpids --csv > "$T/pids" 2>/dev/null) & ;;
  nvidia)        (nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw \
                    --format=csv,noheader,nounits > "$T/gpu" 2>/dev/null) &
                 (nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits > "$T/pids" 2>/dev/null) & ;;
  docker:*)      (docker exec "${M#docker:}" rocm-smi $ROCM > "$T/gpu" 2>/dev/null) & ;;
  sudo-docker:*) (sudo -n docker exec "${M#sudo-docker:}" rocm-smi $ROCM > "$T/gpu" 2>/dev/null) & ;;
esac
(ps -eo pid=,user=,etimes=,pcpu=,args= --sort=-pcpu 2>/dev/null | head -60 > "$T/ps") &
(docker ps --format '{{.Names}}\t{{.Image}}\t{{.RunningFor}}\t{{.CreatedAt}}' > "$T/docker" 2>/dev/null \
  || sudo -n docker ps --format '{{.Names}}\t{{.Image}}\t{{.RunningFor}}\t{{.CreatedAt}}' > "$T/docker" 2>/dev/null) &
(df -P / /tmp /dev/shm > "$T/df" 2>/dev/null) &
# PIDs holding an AMD GPU: world-readable, so other users' processes are visible without root
(K="${FL_KFD_DIR:-/sys/class/kfd/kfd/proc}"; [ -d "$K" ] && { echo readable > "$T/kfdok"; ls "$K" > "$T/kfd"; }) &
(free -b 2>/dev/null | awk 'NR==2 {print $2, $3}' > "$T/mem"; { cat /proc/loadavg; nproc; } > "$T/load" 2>/dev/null) &
wait
# exact details for every GPU-holding PID, however little CPU it uses
GP=$( { cat "$T/kfd"; sed -n 's/^"\{0,1\}PID\([0-9]*\).*/\1/p' "$T/pids"; } 2>/dev/null | sort -u | paste -sd, -)
[ -n "$GP" ] && ps -o pid=,user=,etimes=,pcpu=,args= -p "$GP" > "$T/gpups" 2>/dev/null
echo "=== method"; echo "$M"
for s in gpu pids kfd kfdok gpups ps docker df mem load; do echo "=== $s"; cat "$T/$s" 2>/dev/null; done
echo "=== end"
"""

# The probe's own GPU queries show up as GPU holders; never report them.
PROBE_SELF = re.compile(r"rocm-smi|rocm_smi|amd-smi|nvidia-smi|slurmstepd")

SYSTEM_PROCS = re.compile(r"^(\[|/usr/lib/systemd|/sbin/|/usr/sbin/|sshd|slurmstepd|systemd|dbus|agetty|cron|"
                          r"containerd|dockerd|bash -s|ps -eo|head -|awk|sleep|rsyslogd|chronyd|polkitd|"
                          r"tailscaled|node_exporter|prometheus|srun|cat |sort)")


# --- running commands -------------------------------------------------------------

class Runner:
    def __init__(self, slurm_host: str | None):
        self.slurm_host = slurm_host

    def run(self, argv: list[str], stdin: str | None = None, timeout: float = 60) -> tuple[int, str, str]:
        if self.slurm_host:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                    "-o", "ControlMaster=auto", "-o", f"ControlPath={CACHE_DIR}/ssh-%C",
                    "-o", "ControlPersist=10m", self.slurm_host, shlex.join(argv)]
        try:
            p = subprocess.run(argv, input=stdin, capture_output=True, text=True, timeout=timeout)
            return p.returncode, p.stdout, p.stderr
        except FileNotFoundError as e:
            return 127, "", str(e)
        except subprocess.TimeoutExpired:
            return 124, "", f"timed out after {timeout:.0f}s"


def split_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        m = re.fullmatch(r"=== (\w+)", line.strip())
        if m:
            current = m.group(1)
            sections[current] = []
        elif current:
            sections[current].append(line)
    return {k: "\n".join(v).strip("\n") for k, v in sections.items()}


# --- parsing: SLURM -------------------------------------------------------------------

def parse_squeue(text: str) -> list[dict]:
    jobs = []
    for line in text.splitlines():
        parts = line.strip().split("|")
        if len(parts) != 12:
            continue
        jid, name, state, part, nodes, start, end, left, user, used, reason, dep = parts
        jobs.append({"id": jid, "name": name, "state": state, "partition": part, "nodelist": nodes,
                     "start": start, "end": end, "time_left": left, "user": user, "time_used": used,
                     "reason": reason, "depends_on": re.findall(r"(\d+)", dep) if dep not in ("", "(null)") else []})
    return jobs


def parse_steps(text: str) -> dict[str, timedelta]:
    """Elapsed time of the newest running step per job (the run), ignoring extern/batch/probe steps."""
    best: dict[str, tuple[int, timedelta]] = {}
    for line in text.splitlines():
        parts = line.strip().split("|")
        if len(parts) != 3 or "." not in parts[0]:
            continue
        job, _, step = parts[0].partition(".")
        if not step.isdigit() or parts[1] in ("extern", "batch", "bash"):
            continue
        used = parse_duration(parts[2])
        if used is not None and (job not in best or int(step) > best[job][0]):
            best[job] = (int(step), used)
    return {job: used for job, (_, used) in best.items()}


def parse_detail(text: str) -> tuple[dict[str, list[str]], dict[str, dict], dict[str, int]]:
    hosts: dict[str, list[str]] = {}
    logs: dict[str, dict] = {}
    gpus_per_node: dict[str, int] = {}
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("@@HOSTS "):
            _, job, *names = line.split()
            hosts[job] = names
        elif line.startswith("@@TRES "):
            parts = line.split()
            m = re.search(r"gres/gpu=(\d+)", line)
            nodes = int(parts[-1]) if parts[-1].isdigit() else 1
            if m and len(parts) >= 2:
                gpus_per_node[parts[1]] = max(1, int(m.group(1)) // max(nodes, 1))
        elif line.startswith("@@LOG "):
            parts = line.split(" ", 3)
            if len(parts) == 4 and i + 1 < len(lines):
                try:
                    body = base64.b64decode(lines[i + 1]).decode("utf-8", "replace")
                except ValueError:
                    body = ""
                logs[parts[1]] = {"path": parts[3], "mtime": int(parts[2]), "text": body}
    return hosts, logs, gpus_per_node


def parse_sinfo(text: str) -> dict[str, tuple[str, str]]:
    out = {}
    for line in text.splitlines():
        parts = line.strip().split("|")
        if len(parts) == 3:
            out[parts[0]] = (parts[1], "" if parts[2] in ("none", "") else parts[2])
    return out


GPU_COUNT_RE = re.compile(r"\bgpu(?::[A-Za-z][\w.-]*)?:(\d+)")


def parse_gres(text: str) -> dict[str, tuple[int, int]]:
    """`sinfo -N -O NodeList,Gres,GresUsed` -> {node: (gpus total, gpus allocated)}, GPU nodes only."""
    out: dict[str, tuple[int, int]] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[0] in out:
            continue
        total = GPU_COUNT_RE.search(parts[1])
        used = GPU_COUNT_RE.search(parts[2]) if len(parts) > 2 else None
        if total and int(total.group(1)) > 0:
            out[parts[0]] = (int(total.group(1)), min(int(used.group(1)) if used else 0, int(total.group(1))))
    return out


def parse_step_names(text: str) -> dict[str, list[str]]:
    """Names of a job's run steps (not extern/batch), in step order, from `squeue -s`."""
    found: dict[str, list[tuple[int, str]]] = {}
    for line in text.splitlines():
        parts = line.strip().split("|")
        if len(parts) != 3 or "." not in parts[0]:
            continue
        job, _, step = parts[0].partition(".")
        if step.isdigit() and parts[1] not in ("extern", "batch", "bash"):
            found.setdefault(job, []).append((int(step), parts[1]))
    return {j: [n for _, n in sorted(v)] for j, v in found.items()}


def parse_cluster_time(value: str, utc_offset: str) -> datetime | None:
    """SLURM prints local cluster time without a zone; attach the cluster's offset."""
    if not value or value in ("N/A", "Unknown", "None"):
        return None
    try:
        naive = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None
    m = re.fullmatch(r"([+-])(\d{2})(\d{2})", (utc_offset or "").strip() or "+0000")
    if not m:
        return None
    sign = 1 if m.group(1) == "+" else -1
    return naive.replace(tzinfo=timezone(sign * timedelta(hours=int(m.group(2)), minutes=int(m.group(3)))))


def parse_duration(value: str) -> timedelta | None:
    """SLURM durations: [D-][HH:]MM:SS."""
    m = re.fullmatch(r"(?:(\d+)-)?(?:(\d+):)?(\d+):(\d+)", (value or "").strip())
    if not m:
        return None
    days, hours, minutes, seconds = (int(g) if g else 0 for g in m.groups())
    return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)


# --- parsing: node probe ----------------------------------------------------------------

def _num(value) -> float | None:
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return None


def parse_rocm_csv(text: str) -> list[dict]:
    """`rocm-smi --showtemp --showuse --showmeminfo vram --showpower --csv`, parsed by header name."""
    lines = [l for l in text.splitlines() if l.strip()]
    header = next((i for i, l in enumerate(lines) if l.lower().startswith("device")), None)
    if header is None:
        return []

    def col(row: dict, *needles: str):
        for key, value in row.items():
            if key and all(n.lower() in key.lower() for n in needles):
                return value
        return None

    gpus = []
    for row in csv.DictReader(io.StringIO("\n".join(lines[header:]))):
        m = re.search(r"(\d+)", row.get("device") or "")
        if not m:
            continue
        total, used = _num(col(row, "VRAM Total Memory")), _num(col(row, "VRAM Total Used"))
        gpus.append({"index": int(m.group(1)), "util_pct": _num(col(row, "GPU use")),
                     "mem_used_gb": used / GIB if used is not None else None,
                     "mem_total_gb": total / GIB if total is not None else None,
                     "temp_c": _num(col(row, "Temperature", "edge") or col(row, "Temperature")),
                     "power_w": _num(col(row, "Power"))})
    return gpus


def parse_nvidia_csv(text: str) -> list[dict]:
    gpus = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 6 or not parts[0].isdigit():
            continue
        used, total = _num(parts[2]), _num(parts[3])
        gpus.append({"index": int(parts[0]), "util_pct": _num(parts[1]),
                     "mem_used_gb": used / 1024 if used is not None else None,
                     "mem_total_gb": total / 1024 if total is not None else None,
                     "temp_c": _num(parts[4]), "power_w": _num(parts[5])})
    return gpus


def parse_gpu_pids(text: str) -> set[int]:
    pids = set()
    for line in text.splitlines():
        m = re.fullmatch(r"(?:PID)?(\d+)", line.split(",")[0].strip().strip('"'))
        if m:
            pids.add(int(m.group(1)))
    return pids


def parse_ps(text: str) -> list[dict]:
    procs = []
    for line in text.splitlines():
        parts = line.split(None, 4)
        if len(parts) == 5 and parts[0].isdigit():
            procs.append({"pid": int(parts[0]), "user": parts[1],
                          "elapsed_s": int(parts[2]) if parts[2].isdigit() else 0,
                          "pcpu": _num(parts[3]) or 0.0, "args": parts[4]})
    return procs


def parse_docker(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        c = dict(zip(("name", "image", "running_for"), parts[:3]))
        m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ([+-]\d{4})", parts[3]) if len(parts) > 3 else None
        c["created"] = datetime.strptime(" ".join(m.groups()), "%Y-%m-%d %H:%M:%S %z") if m else None
        out.append(c)
    return out


def parse_df(text: str) -> list[dict]:
    out, seen = [], set()
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 6 and parts[4].endswith("%") and parts[5] not in seen:
            seen.add(parts[5])
            out.append({"mount": parts[5], "use_pct": int(parts[4].rstrip("%")),
                        "free_gb": int(parts[3]) * 1024 / GIB if parts[3].isdigit() else None,
                        "size_gb": int(parts[1]) * 1024 / GIB if parts[1].isdigit() else None})
    return out


# --- progress and ETA ---------------------------------------------------------------------

TQDM_RE = re.compile(r"(\d+)/(\d+)\s*\[([\d:]+)<([\d:]+)")
EPOCH_RE = re.compile(r"\bepoch\s*[:=]?\s*(\d+)\s*/\s*(\d+)", re.I)
INNER_RE = re.compile(r"\b(?:step|iter(?:ation)?|batch|it)\s*[:=]?\s*(\d+)\s*/\s*(\d+)", re.I)
ANY_FRAC_RE = re.compile(r"(?<![\d.])(\d+)\s*/\s*(\d+)(?![\d.])")
PCT_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d+)?)\s*%")
ETA_RE = re.compile(r"\b(?:ETA|remaining|time left)\s*[:=]?\s*((?:\d+-)?\d{1,3}:\d{2}(?::\d{2})?)", re.I)
PROGRESS_HINT = re.compile(r"epoch|step|iter|batch|it/s|s/it|%|ETA|loss|remaining|\d+\s*/\s*\d+", re.I)


def clock_to_td(text: str) -> timedelta | None:
    m = re.fullmatch(r"(?:(\d+)-)?(\d+):(\d{2})(?::(\d{2}))?", text)
    if not m:
        return None
    d, a, b, c = (int(g) if g else 0 for g in m.groups())
    # h:mm:ss when three fields, else mm:ss (tqdm and most loggers)
    return timedelta(days=d, hours=a, minutes=b, seconds=c) if m.group(4) else timedelta(days=d, minutes=a, seconds=b)


def parse_progress(line: str) -> dict:
    """Overall fraction, a short counter label, and a printed remaining time, from one log line."""
    out: dict = {"fraction": None, "counter": None, "remaining": None, "remaining_source": None}
    t = TQDM_RE.search(line)
    if t:
        done, total = int(t.group(1)), int(t.group(2))
        if total:
            out.update(fraction=done / total, counter=f"{done}/{total}")
        out.update(remaining=clock_to_td(t.group(4)), remaining_source="tqdm")
    ep, inner = EPOCH_RE.search(line), INNER_RE.search(line)
    if ep and int(ep.group(2)):
        a, b = int(ep.group(1)), int(ep.group(2))
        within = int(inner.group(1)) / int(inner.group(2)) if inner and int(inner.group(2)) else 0.0
        # epoch counters are 1-based while running ("epoch 2/3" = in the second epoch)
        out.update(fraction=min(1.0, (max(a - 1, 0) + within) / b), counter=f"ep{a}/{b}")
    elif out["fraction"] is None and inner and int(inner.group(2)):
        out.update(fraction=int(inner.group(1)) / int(inner.group(2)), counter=f"{inner.group(1)}/{inner.group(2)}")
    elif out["fraction"] is None:
        p = PCT_RE.search(line)
        f = ANY_FRAC_RE.search(line)
        if p and float(p.group(1)) <= 100:
            out["fraction"] = float(p.group(1)) / 100
        elif f and int(f.group(2)):
            out.update(fraction=int(f.group(1)) / int(f.group(2)), counter=f"{f.group(1)}/{f.group(2)}")
    if out["remaining"] is None:
        e = ETA_RE.search(line)
        if e:
            out.update(remaining=clock_to_td(e.group(1)), remaining_source="log")
    return out


def analyze_log(log: dict, now: datetime) -> dict:
    lines = [l for l in re.split(r"[\r\n]+", log.get("text", "")) if l.strip()]
    progress_lines = [l.strip() for l in lines if PROGRESS_HINT.search(l)]
    info = {"path": log["path"], "age": timedelta(seconds=max(0, now.timestamp() - log["mtime"])),
            "last": (progress_lines[-1] if progress_lines else (lines[-1].strip() if lines else ""))[:120],
            "errors": [l.strip()[:120] for l in lines[-200:] if LOG_ERROR_RE.search(l)][-2:]}
    info.update(parse_progress(progress_lines[-1]) if progress_lines else parse_progress(""))
    return info


def estimate_finish(log: dict | None, run_elapsed: timedelta | None, now: datetime) -> tuple[datetime | None, str]:
    """Finish time and its source: printed remaining time first, then rate from progress."""
    if not log:
        return None, "no log"
    if log.get("fraction") is not None and log["fraction"] >= 1.0:
        return now, "done"
    if log.get("remaining") is not None:
        return now + log["remaining"], log["remaining_source"]
    f = log.get("fraction")
    if f and f > 0 and run_elapsed and run_elapsed.total_seconds() > 60:
        return now + run_elapsed * ((1 - f) / f), "rate"
    if f is None:
        return None, "log has no progress counter"
    return None, "too early to estimate"


# --- collection -----------------------------------------------------------------------------

def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def save_json(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        tmp.replace(path)
    except OSError:
        pass


def collect(runner: Runner, job_ids: list[str], log_args: dict[str, str], timing: dict,
            owner_name: str | None = None) -> dict:
    notes: list[str] = []
    t0 = time.monotonic()
    local_logs, remote_specs = {}, []
    for job, path in log_args.items():
        if path.startswith("docker:"):
            continue  # read from the job's node after the probes
        p = Path(path).expanduser()
        if p.is_file():
            st = p.stat()
            with open(p, "rb") as f:
                f.seek(max(0, st.st_size - 32768))
                local_logs[job] = {"path": path, "mtime": int(st.st_mtime), "text": f.read().decode("utf-8", "replace")}
        else:
            remote_specs.append(f"{job}:{path}")

    script = (SNAPSHOT.replace("__IDS__", shlex.quote(",".join(job_ids)))
              .replace("__FMT__", SQUEUE_FMT)
              .replace("__LOGS__", " ".join(shlex.quote(s) for s in remote_specs)))
    rc, out, err = runner.run(["bash", "-s"], stdin=script, timeout=30)
    timing["slurm snapshot (1 round trip)"] = time.monotonic() - t0
    sec = split_sections(out)
    if "end" not in sec:
        return {"jobs": [], "notes": [f"SLURM snapshot failed: {err.strip()[:200] or rc}"], "collected_at": _now()}
    if "noslurm" in sec:
        where = f"on {runner.slurm_host}" if runner.slurm_host else "on this host"
        return {"jobs": [], "no_slurm": True, "collected_at": _now(),
                "notes": [f"no SLURM client {where}: pass --slurm-host <ssh target>, or set FORGELOOP_SLURM_HOST "
                          f"or slurm_host in .claude/forgeloop.md"]}

    offset = sec.get("offset", "").strip()
    jobs = parse_squeue(sec.get("jobs", ""))
    steps = parse_steps(sec.get("steps", ""))
    hosts, remote_logs, gpus_per_node = parse_detail(sec.get("detail", ""))
    sinfo = parse_sinfo(sec.get("sinfo", ""))
    gres = parse_gres(sec.get("gres", ""))
    step_names = parse_step_names(sec.get("steps", ""))
    for jid in job_ids:
        if not any(j["id"] == jid for j in jobs):
            notes.append(f"job {jid} not found in squeue (finished, cancelled, or wrong ID)")

    now = _now()
    for job in jobs:
        job["start_dt"] = parse_cluster_time(job["start"], offset)
        job["end_dt"] = parse_cluster_time(job["end"], offset)
        job["left_td"] = parse_duration(job["time_left"])
        job["hosts"] = hosts.get(job["id"], [])
        job["steps"] = step_names.get(job["id"], [])
        raw_log = local_logs.get(job["id"]) or remote_logs.get(job["id"])
        job["log"] = analyze_log(raw_log, now) if raw_log else None
        run_elapsed = steps.get(job["id"]) or parse_duration(job["time_used"])
        job["finish_dt"], job["finish_source"] = estimate_finish(job["log"], run_elapsed, now)
        if job["id"] in log_args and not raw_log:
            notes.append(f"log for job {job['id']} not readable: {log_args[job['id']]}")

    # One probe per node, all in parallel; a node shared by several of our jobs is probed once.
    t1 = time.monotonic()
    methods = load_json(CACHE_DIR / "methods.json")
    targets = {}
    for job in jobs:
        if job["state"] == "RUNNING":
            for host in job["hosts"]:
                targets.setdefault(host, job["id"])
    nodes: dict[str, dict] = {}
    if targets:
        with ThreadPoolExecutor(max_workers=min(16, len(targets))) as pool:
            futures = {host: pool.submit(probe_node, runner, jid, host, methods.get(host, ""),
                                         gpus_per_node.get(jid, 0))
                       for host, jid in targets.items()}
            for host, fut in futures.items():
                nodes[host] = fut.result()
    timing[f"node probes ({len(targets)} in parallel)"] = time.monotonic() - t1

    resolve_owners(runner, jobs, nodes, offset, owner_name, timing, now)

    # Container logs: explicit --log docker:<name>, or a container this job (or its chained
    # predecessor, per accounting) started.
    t2 = time.monotonic()
    wanted = {}
    for job in jobs:
        if job["state"] != "RUNNING" or not job["hosts"] or job.get("log"):
            continue
        host = job["hosts"][0]
        arg = log_args.get(job["id"], "")
        if arg.startswith("docker:"):
            wanted[job["id"]] = (host, arg[len("docker:"):], "explicit")
        elif job["id"] not in log_args and host in nodes and job.get("start_dt"):
            inherited = {e["what"][len("container "):] for jid, e in nodes[host].get("workloads", [])
                         if jid == job["id"] and e["verdict"] == "ours" and e["what"].startswith("container ")}
            mine = [c for c in nodes[host]["containers"] if c.get("created")
                    and (c["created"] >= job["start_dt"] - timedelta(minutes=5) or c["name"] in inherited)]
            if mine:
                wanted[job["id"]] = (host, max(mine, key=lambda c: c["created"])["name"], "auto")
    if wanted:
        with ThreadPoolExecutor(max_workers=min(16, len(wanted))) as pool:
            futs = {jid: pool.submit(read_container_log, runner, host, name) for jid, (host, name, _) in wanted.items()}
            for job in jobs:
                if job["id"] in futs:
                    raw = futs[job["id"]].result()
                    if raw:
                        job["log"] = analyze_log(raw, now)
                        run_elapsed = steps.get(job["id"]) or parse_duration(job["time_used"])
                        job["finish_dt"], job["finish_source"] = estimate_finish(job["log"], run_elapsed, now)
                    elif wanted[job["id"]][2] == "explicit":
                        notes.append(f"container log for job {job['id']} not readable: {wanted[job['id']][1]}")
        timing[f"container logs ({len(wanted)} in parallel)"] = time.monotonic() - t2

    for host, node in nodes.items():
        node["slurm_state"], node["slurm_reason"] = sinfo.get(host, ("", ""))
        if node.get("method") and node["method"] != "none" and node["gpus"]:
            methods[host] = node["method"]
        elif host in methods:
            methods.pop(host)  # re-discover next time
    save_json(CACHE_DIR / "methods.json", methods)
    cluster_gpus = {h: {"total": t, "used": u, "state": sinfo.get(h, ("", ""))[0]} for h, (t, u) in gres.items()}
    return {"jobs": jobs, "nodes": nodes, "notes": notes, "collected_at": _now(), "cluster_gpus": cluster_gpus,
            "log_args": dict(log_args)}


def resolve_owners(runner: Runner, jobs: list[dict], nodes: dict[str, dict], offset: str,
                   owner_name: str | None, timing: dict, now: datetime) -> None:
    """For GPU workloads that started before the job holding their node, ask SLURM accounting
    which job held the node when they started. Ours if that job is ours (name filter, else
    same user); foreign otherwise. A chained hold's successor inherits its predecessor's work."""
    t = time.monotonic()
    queries = []  # (job, node, label, started_at)
    for job in jobs:
        start = job.get("start_dt")
        if job["state"] != "RUNNING" or not start:
            continue
        for host in job["hosts"]:
            n = nodes.get(host)
            if not n or not n.get("gpu_evidence") or not n["procs"]:
                continue
            boxes = [c for c in n["containers"] if c.get("created") and c["created"] < start - timedelta(minutes=5)]
            for c in boxes:
                queries.append((job, n, f"container {c['name']}", c["created"]))
            if not boxes:
                older = [p for p in n["procs"] if p["elapsed_s"] > (now - start).total_seconds() + 300]
                if older:
                    p = max(older, key=lambda q: q["elapsed_s"])
                    queries.append((job, n, f"pid {p['pid']} ({p['args'][:40]})", now - timedelta(seconds=p["elapsed_s"])))
    if not queries:
        return
    m = re.fullmatch(r"([+-])(\d{2})(\d{2})", offset or "+0000")
    tz = timezone((1 if m.group(1) == "+" else -1) * timedelta(hours=int(m.group(2)), minutes=int(m.group(3)))) if m else timezone.utc
    script = "command -v sacct >/dev/null 2>&1 || { echo @@NOSACCT; exit 0; }\n" + "".join(
        f"echo '@@Q {i}'; sacct -a -X -n -P -N {shlex.quote(n['host'])} -S {when.astimezone(tz):%Y-%m-%dT%H:%M:%S} "
        f"-E {when.astimezone(tz):%Y-%m-%dT%H:%M:%S} -o JobID,JobName,User,Start,End 2>/dev/null\n"
        for i, (_, n, _, when) in enumerate(queries))
    rc, out, _ = runner.run(["bash", "-s"], stdin=script, timeout=20)
    if "@@NOSACCT" in out or rc != 0:
        out = ""  # no accounting: every workload stays "unknown", never "foreign"
    answers: dict[int, list[list[str]]] = {}
    current = None
    for line in out.splitlines():
        if line.startswith("@@Q "):
            current = int(line.split()[1])
            answers[current] = []
        elif current is not None and line.count("|") == 4:
            answers[current].append(line.split("|"))
    for i, (job, n, label, when) in enumerate(queries):
        holders = answers.get(i)
        entry = {"what": label, "started": when}
        if holders is None:
            entry["verdict"] = "unknown"  # accounting unavailable: fall back to "predates this job"
        elif not holders:
            entry.update(verdict="foreign", reason="started while no job held the node")
        else:
            jid, jname, juser, _, jend = holders[0]
            ours = (re.search(owner_name, jname) if owner_name else juser == job["user"])
            entry.update(verdict="ours" if ours else "foreign", owner=f"{jid} {jname}",
                         owner_end=parse_cluster_time(jend, offset),
                         reason=f"started under job {jid} {jname}")
        n.setdefault("workloads", []).append((job["id"], entry))
    timing["workload owners (1 round trip)"] = time.monotonic() - t


def read_container_log(runner: Runner, host: str, name: str) -> dict | None:
    """Last lines of a container's output; the newest line's timestamp stands in for mtime."""
    q = shlex.quote(name)
    rc, out, _ = runner.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", host,
                             f"docker logs -t --tail 300 {q} 2>&1 || sudo -n docker logs -t --tail 300 {q} 2>&1"],
                            timeout=PROBE_TIMEOUT_S)
    lines, newest = [], None
    for line in out.replace("\r", "\n").splitlines():
        m = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.\d+)?(Z|[+-]\d{2}:\d{2})\s?(.*)", line)
        if m:
            ts = datetime.fromisoformat(m.group(1) + ("+00:00" if m.group(2) == "Z" else m.group(2)))
            newest = max(newest, ts) if newest else ts
            lines.append(m.group(3))
        elif line.strip():
            lines.append(line)
    if not lines or newest is None:
        return None
    return {"path": f"docker:{name} on {host}", "mtime": int(newest.timestamp()), "text": "\n".join(lines)}


def probe_node(runner: Runner, job_id: str, host: str, method: str, gpus: int = 0) -> dict:
    """Probe over ssh to the node first: a plain srun step lives in its own cgroup and sees
    no GPUs. Fall back to an srun step that requests the job's GPUs when ssh is refused."""
    t = time.monotonic()
    env = f"FL_METHOD={shlex.quote(method)} " if method else ""
    rc, out, err = runner.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", host,
                               f"{env}bash -s"], stdin=PROBE, timeout=PROBE_TIMEOUT_S)
    via = "ssh"
    if "=== end" not in out and rc != 124:
        gres = [f"--gres=gpu:{gpus}"] if gpus else []
        rc, out, err = runner.run(["srun", f"--jobid={job_id}", "--overlap", *gres, "-w", host, "-N1", "-n1",
                                   "bash", "-c", f"{env}bash -s"], stdin=PROBE, timeout=PROBE_TIMEOUT_S)
        via = "srun"
    node = {"host": host, "notes": [], "raw": out, "probe_s": time.monotonic() - t, "via": via}
    if "=== end" not in out:
        node["notes"].append("probe timed out" if rc == 124 else f"probe failed ({err.strip()[:100] or rc})")
    sec = split_sections(out)
    node["method"] = sec.get("method", "").strip()
    gpus = parse_nvidia_csv(sec.get("gpu", "")) if node["method"] == "nvidia" else parse_rocm_csv(sec.get("gpu", ""))
    node["gpus"] = sorted(gpus, key=lambda g: g["index"])
    if not gpus and "=== end" in out:
        node["notes"].append("GPU metrics unavailable (no rocm-smi/nvidia-smi on host or in containers)")
    gpu_procs = parse_ps(sec.get("gpups", ""))
    procs = gpu_procs + [p for p in parse_ps(sec.get("ps", "")) if p["pid"] not in {g["pid"] for g in gpu_procs}]
    gpu_pids = parse_gpu_pids(sec.get("pids", "")) | {int(x) for x in sec.get("kfd", "").split() if x.isdigit()}
    kfd_readable = bool(sec.get("kfdok", "").strip())
    if gpu_pids or kfd_readable:
        # only processes proven to hold a GPU; these are the only ones judged as foreign
        node["procs"], node["proc_source"], node["gpu_evidence"] = \
            [p for p in procs if p["pid"] in gpu_pids and not PROBE_SELF.search(p["args"])], "holding a GPU", True
        if not node["procs"]:
            node["proc_source"] = "none hold a GPU"
        missing = gpu_pids - {p["pid"] for p in procs}
        node["procs"] += [{"pid": pid, "user": "?", "elapsed_s": 0, "pcpu": 0.0, "args": "(not in top-60 ps)"}
                          for pid in sorted(missing)]
    else:
        node["procs"] = [p for p in procs if not SYSTEM_PROCS.search(p["args"]) and p["pcpu"] >= 1.0][:8]
        node["proc_source"], node["gpu_evidence"] = "top CPU processes; GPU holders unknown", False
    node["containers"] = parse_docker(sec.get("docker", ""))
    node["disks"] = parse_df(sec.get("df", ""))
    mem = sec.get("mem", "").split()
    node["ram"] = (int(mem[0]) / GIB, int(mem[1]) / GIB) if len(mem) == 2 and all(m.isdigit() for m in mem) else None
    load = sec.get("load", "").split()
    node["load"] = (_num(load[0]), int(load[-1])) if len(load) >= 6 and load[-1].isdigit() else None
    return node


# --- judging --------------------------------------------------------------------------------

def idle_gpus(node: dict) -> list[int]:
    return [g["index"] for g in node["gpus"] if (g["util_pct"] or 0) < IDLE_UTIL_PCT
            and g["mem_total_gb"] and (g["mem_used_gb"] or 0) / g["mem_total_gb"] < IDLE_MEM_FRAC]


def assess(job: dict, nodes: dict[str, dict], now: datetime, jobs: list[dict] | None = None) -> tuple[str, list[str]]:
    """Short state for the table, and warnings each with a proposed action."""
    successors = [j["id"] for j in (jobs or []) if job["id"] in j.get("depends_on", [])]
    covered = f"; successor job {', '.join(successors)} is queued to continue" if successors else ""
    if job["state"] == "PENDING":
        start = f", expected start {fmt_time(job['start_dt'], now)}" if job.get("start_dt") else ""
        return f"… pending ({job['reason']}{start})", []
    if job["state"] != "RUNNING":
        return job["state"].lower(), []
    warns: list[tuple[int, str, str]] = []  # (priority, state word, warning)
    log, fin, end = job.get("log"), job.get("finish_dt"), job.get("end_dt")
    my_nodes = [nodes[h] for h in job["hosts"] if h in nodes]
    for n in my_nodes:
        if n.get("slurm_state", "").lower().startswith(("drain", "down", "fail")):
            warns.append((0, "node " + n["slurm_state"],
                          f"{n['host']} is {n['slurm_state']} ({n['slurm_reason'] or 'no reason'}) → the run may be "
                          f"killed; check with the cluster admins"))
    if fin and end and fin > end:
        short = fin - end
        warns.append((1, "expires before done",
                      f"expires {fmt_time(end, now)}, {fmt_td(short)} before it finishes"
                      + (covered if covered else " → extend the allocation, or restart with a longer --time")))
    if log and log["age"] > LOG_STALE:
        busy = [g for n in my_nodes for g in n["gpus"] if (g["util_pct"] or 0) >= IDLE_UTIL_PCT]
        held = [g for n in my_nodes for g in n["gpus"] if (g["mem_used_gb"] or 0) > 1]
        gpu_note = ", GPUs 0% with memory held" if my_nodes and not busy and held else ""
        warns.append((2, f"stalled {fmt_td(log['age'])}",
                      f"log silent {fmt_td(log['age'])}{gpu_note} → likely hung; last: \"{log['last'][:70]}\""))
    for e in (log or {}).get("errors", []):
        warns.append((3, "errors in log", f"log error: {e[:90]} → check whether the run is still healthy"))
    for n in my_nodes:
        full = [g["index"] for g in n["gpus"]
                if g["mem_total_gb"] and (g["mem_used_gb"] or 0) / g["mem_total_gb"] > MEM_HIGH_FRAC]
        if full:
            warns.append((4, "OOM risk", f"{n['host']} GPU {fmt_ranges(full)} memory above "
                                         f"{int(MEM_HIGH_FRAC * 100)}% → out-of-memory risk if usage grows"))
        start = job.get("start_dt")
        if n.get("gpu_evidence") and start:
            age = (now - start).total_seconds() + 300
            older = [p for p in n["procs"] if p["elapsed_s"] > age]
            old_boxes = [c for c in n["containers"] if c.get("created") and c["created"] < start - timedelta(minutes=5)]
            resolved = [e for jid, e in n.get("workloads", []) if jid == job["id"]]
            held = [g["index"] for g in n["gpus"] if (g["mem_used_gb"] or 0) > 1]
            gpus_txt = f" and holds GPU {fmt_ranges(held)}" if held else ""
            for e in resolved:
                if e["verdict"] == "foreign":
                    ended = e.get("owner_end")
                    gone = f" (that job ended {fmt_time(ended, now)})" if ended and ended < now else ""
                    warns.append((4, "foreign workload",
                                  f"{n['host']}: {e['what']} {e['reason']}{gone}{gpus_txt} → not ours; the hold "
                                  f"does not keep it off the node; ask its owner or the admins"))
            if resolved and all(e["verdict"] != "unknown" for e in resolved):
                older = []  # accounting answered; the age heuristic is not needed
            if older:
                what = (f"container {old_boxes[0]['name']}" if old_boxes else f"pid {older[0]['pid']} ({older[0]['args'][:40]})")
                # container creation time is exact; a process's age is a lower bound for its container
                lead = fmt_td(start - old_boxes[0]["created"] if old_boxes
                              else timedelta(seconds=older[0]["elapsed_s"]) - (now - start))
                warns.append((4, "possibly foreign",
                              f"{n['host']}: {what} started {lead} before this job{gpus_txt}; owner unknown "
                              f"(no accounting data) → check whether it is yours"))
        foreign = [p for p in n["procs"] if n.get("gpu_evidence") and p["user"] not in (job["user"], "root", "?")
                   and not (start and p["elapsed_s"] > (now - start).total_seconds() + 300)]
        for p in foreign[:3]:
            warns.append((5, "foreign process", f"{n['host']}: pid {p['pid']} of {p['user']} "
                                                f"({p['args'][:50]}) holds a GPU → it competes with our run; ask them or the admins"))
        for d in n["disks"]:
            if d["use_pct"] >= DISK_HIGH_PCT:
                warns.append((6, "disk full", f"{n['host']} {d['mount']} at {d['use_pct']}% "
                                              f"({fmt_size(d.get('free_gb'))} free of {fmt_size(d.get('size_gb'))}) "
                                              f"→ writes or data loading can fail if it fills"))
    left = job.get("left_td")
    if left is not None and left < EXPIRY_SOON and not (fin and end and fin > end):
        warns.append((7, f"expires in {fmt_td(left)}", f"allocation expires in {fmt_td(left)}"
                      + (covered if covered else " → extend it if the work is not done")))
    if warns:
        warns.sort(key=lambda w: w[0])
        return "⚠ " + warns[0][1], [w[2] for w in warns]
    if fin and end:
        return f"✓ on track ({fmt_td(end - fin)} spare)", []
    return "✓ running", []


# --- formatting ---------------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def fmt_time(dt: datetime | None, now: datetime | None = None) -> str:
    if dt is None:
        return "—"
    local = dt.astimezone(ISRAEL)
    today = (now or _now()).astimezone(ISRAEL).date()
    return local.strftime("%H:%M") if local.date() == today else local.strftime("%b %d %H:%M")


def fmt_td(td: timedelta | None) -> str:
    if td is None:
        return "—"
    minutes = int(abs(td.total_seconds()) // 60)
    days, rem = divmod(minutes, 1440)
    hours, mins = divmod(rem, 60)
    if days:
        return f"{days}d{hours}h"
    return f"{hours}h{mins:02d}m" if hours else f"{mins}m"


def fmt_size(gb: float | None) -> str:
    if gb is None:
        return "n/a"
    return f"{gb / 1024:.1f} TB" if gb >= 1024 else f"{gb:.0f} GB"


def fmt_ranges(nums: list[int]) -> str:
    nums, out, start = sorted(nums), [], None
    for i, n in enumerate(nums):
        start = n if start is None else start
        if i == len(nums) - 1 or nums[i + 1] != n + 1:
            out.append(str(start) if start == n else f"{start},{n}" if n == start + 1 else f"{start}–{n}")
            start = None
    return ",".join(out)


def bar(frac: float | None, width: int = 10) -> str:
    if frac is None:
        return "·" * width
    eighths = round(max(0.0, min(1.0, frac)) * width * 8)
    full, part = divmod(eighths, 8)
    return ("█" * full + ("▏▎▍▌▋▊▉"[part - 1] if part else "")).ljust(width, "░")


SPARK = "▁▂▃▄▅▆▇█"


def spark(values: list[float | None]) -> str:
    return "".join("·" if v is None else SPARK[min(7, int(max(0.0, min(1.0, v)) * 7.999))] for v in values)


def render_plain(data: dict, detail: bool, labels: dict[str, str], tmux: list[str]) -> str:
    """The previous default view: job table, node lines, warnings."""
    now, jobs, nodes = data["collected_at"], data["jobs"], data.get("nodes", {})
    lines: list[str] = []
    if data.get("no_slurm"):
        pass  # the note says what to do
    elif not jobs:
        lines.append("no jobs found")
    else:
        rows = []
        for job in jobs:
            state, warns = assess(job, nodes, now, jobs)
            job["_state"], job["_warns"] = state, warns
            log = job.get("log")
            if log and log.get("fraction") is not None:
                pct = int(log["fraction"] * 100)  # round down: 99.97% is not done
                prog = f"{bar(log['fraction'])} {pct:3d}%" + (f" {log['counter']}" if log.get("counter") else "")
            elif job["state"] == "RUNNING":
                prog = "—  (no log)" if not log else "—  (no counter)"
            else:
                prog = ""
            fin = job.get("finish_dt")
            finishes = ("~" if job.get("finish_source") == "rate" else "") + fmt_time(fin, now) if fin else "—"
            node_txt = job["hosts"][0] + (f"+{len(job['hosts']) - 1}" if len(job["hosts"]) > 1 else "") if job["hosts"] else "—"
            rows.append([job["id"], labels.get(job["id"], job["name"])[:24], node_txt, prog, finishes,
                         fmt_time(job.get("end_dt"), now) if job["state"] == "RUNNING" else "", state])
        head = ["JOB", "WHAT", "NODE", "PROGRESS", "FINISHES", "EXPIRES", "STATE"]
        widths = [max(len(str(r[i])) for r in rows + [head]) for i in range(len(head))]
        for r in [head] + rows:
            lines.append("  ".join(str(c).ljust(w) for c, w in zip(r, widths)).rstrip())

        warn_lines = [(j, w) for j in jobs for w in j["_warns"]]
        if warn_lines:
            lines.append("")
            for j, w in warn_lines:
                lines.append(f"⚠ {j['id']}  {w}")
        # ETA sources that are not obvious
        for j in jobs:
            if j["state"] == "RUNNING" and not j.get("finish_dt") and j.get("finish_source") not in ("no log",):
                lines.append(f"  {j['id']}: no finish time ({j['finish_source']})")

        if nodes:
            lines.append("")
            busy_total = sum(1 for n in nodes.values() for g in n["gpus"] if (g["util_pct"] or 0) >= IDLE_UTIL_PCT)
            all_total = sum(len(n["gpus"]) for n in nodes.values())
            width = max(len(h) for h in nodes)
            for host, n in nodes.items():
                if not n["gpus"]:
                    lines.append(f"GPUs  {host.ljust(width)}  n/a  {'; '.join(n['notes'])}")
                    continue
                util = spark([(g["util_pct"] or 0) / 100 if g["util_pct"] is not None else None for g in n["gpus"]])
                busy = len(n["gpus"]) - len(idle_gpus(n)) if n["gpus"] else 0
                idle = idle_gpus(n)
                extra = f" · idle GPU {fmt_ranges(idle)}" if idle else ""
                mem_spark = ""
                if any((g["util_pct"] or 0) < IDLE_UTIL_PCT and (g["mem_used_gb"] or 0) > 1 for g in n["gpus"]):
                    mem_spark = "  mem " + spark([(g["mem_used_gb"] or 0) / g["mem_total_gb"] if g["mem_total_gb"] else None
                                                  for g in n["gpus"]])
                lines.append(f"GPUs  {host.ljust(width)}  util {util}{mem_spark}  {busy}/{len(n['gpus'])} in use{extra}")
            if len(nodes) > 1 and all_total:
                lines.append(f"      {busy_total} of {all_total} GPUs busy across {len(nodes)} nodes")
            for host, n in nodes.items():
                for note in n["notes"]:
                    if n["gpus"]:
                        lines.append(f"  note: {host}: {note}")

    return _finish(lines, data, detail, tmux)


def _finish(lines: list[str], data: dict, detail: bool, tmux: list[str]) -> str:
    now, jobs, nodes = data["collected_at"], data["jobs"], data.get("nodes", {})
    if detail:
        for host, n in nodes.items():
            lines += ["", *render_node_detail(n, tmux, now)]
        for job in jobs:
            if job.get("log"):
                lg = job["log"]
                lines += ["", f"log {job['id']}: {lg['path']} (updated {fmt_td(lg['age'])} ago)",
                          f"  last: {lg['last']}"]
    for note in data.get("notes", []):
        lines.append(f"note: {note}")
    lines.append("")
    lines.append(f"collected {fmt_time(now, now)} Israel time")
    return "\n".join(lines).rstrip() + "\n"


SECRET_RE = re.compile(r"key|token|secret|password", re.I)
EVIDENCE_CMD_MAX = 100
# SLURM flags whose "=value" is an id or a size, never a secret: kept in shown commands.
SAFE_VALUE_FLAGS = frozenset({"--jobid", "--job-name", "--partition", "--nodelist", "--nodes",
                              "--time", "--gres", "--ntasks", "--cpus-per-task"})


def sanitize_command(cmd: str, limit: int = EVIDENCE_CMD_MAX) -> str:
    """A command line safe to show: tokens that look like secrets are dropped (with the value
    that follows a bare flag), and everything after '=' is dropped."""
    out, skip_next = [], False
    for tok in cmd.split():
        if skip_next:
            skip_next = False
            continue
        if SECRET_RE.search(tok):
            skip_next = tok.startswith("-") and "=" not in tok
            continue
        flag, eq, val = tok.partition("=")
        out.append(tok if eq and flag in SAFE_VALUE_FLAGS else flag + eq)
    return " ".join(out)[:limit].rstrip()


def job_evidence(job: dict, nodes: dict[str, dict], tmux: list[str], label: str | None,
                 log_arg: str | None) -> list[str]:
    """What a job appears to do, from data already gathered: step names, the job's GPU-holding
    (or busiest) processes and its containers on its nodes, tmux session, label, log file."""
    ev: list[str] = [f"step {sanitize_command(n, 40)}" for n in job.get("steps", [])[:3]]
    now, start = _now(), job.get("start_dt")
    for host in job.get("hosts", []):
        n = nodes.get(host)
        if not n:
            continue
        procs = [p for p in n["procs"] if p["user"] in (job["user"], "root", "?")
                 and not p["args"].startswith("(not in")
                 and not (start and p["elapsed_s"] > (now - start).total_seconds() + 300)]
        ev += [f"proc {sanitize_command(p['args'])}" for p in procs[:2]]
        ours = {e["what"][len("container "):] for jid, e in n.get("workloads", [])
                if jid == job["id"] and e["verdict"] == "ours" and e["what"].startswith("container ")}
        ev += [f"container {c['name']}" for c in n["containers"]
               if (start and c.get("created") and c["created"] >= start - timedelta(minutes=5)) or c["name"] in ours][:2]
    for host in job.get("hosts", []):
        session = next((s for s in tmux if host in s), None)
        if session:
            ev.append(f"tmux {session}")
            break
    if label:
        ev.append(f"label {sanitize_command(label, 60)}")
    if job.get("log") and job["log"].get("path"):
        ev.append(f"log {os.path.basename(job['log']['path'])}")
    elif log_arg:
        ev.append(f"log {os.path.basename(log_arg)}")
    return list(dict.fromkeys(ev))


def short_names(names) -> dict[str, str]:
    """Drop the common 'amd-' prefix, but only when every short name stays unique."""
    pool = sorted(set(names))
    short = {n: n[4:] if n.startswith("amd-") else n for n in pool}
    return short if len(set(short.values())) == len(pool) else {n: n for n in pool}


def warning_scope(data: dict, relevant: set[str] | None) -> list[tuple[dict, str, bool]]:
    """Every warning as (job, text, relevant). A warning is relevant when its job is one of the
    jobs named with --job, or when it is led by a node one of those jobs runs on. `relevant`
    None means "no scope given" (treated as nothing relevant)."""
    relevant = relevant or set()
    nodes = data.get("nodes", {})
    all_hosts = {h for j in data["jobs"] for h in j["hosts"]}
    rel_hosts = {h for j in data["jobs"] if j["id"] in relevant for h in j["hosts"]}
    out = []
    for job in data["jobs"]:
        _, warns = assess(job, nodes, data["collected_at"], data["jobs"])
        for w in warns:
            led = next((h for h in all_hosts if w.startswith(h)), None)
            out.append((job, w, job["id"] in relevant or (led is not None and led in rel_hosts)))
    return out


def count_shown_warnings(data: dict, relevant: set[str] | None, show_all: bool) -> int:
    """Warnings the user sees; the exit code follows this, so a hidden warning never changes it."""
    return sum(1 for _, _, rel in warning_scope(data, relevant) if show_all or rel)


def render(data: dict, detail: bool, labels: dict[str, str], tmux: list[str], plain: bool = False,
           relevant: set[str] | None = None, show_all_warnings: bool = False) -> str:
    """Default view: what can I use now, my jobs with evidence of what they do, and warnings only
    for the run in scope (`relevant` job ids). --plain, --detail and --warnings show every warning."""
    if plain:
        return render_plain(data, detail, labels, tmux)
    show_all_warnings = show_all_warnings or detail
    now, jobs, nodes = data["collected_at"], data["jobs"], data.get("nodes", {})
    gpus = {h: g for h, g in (data.get("cluster_gpus") or {}).items()
            if not g.get("state", "").lower().startswith(("drain", "down", "fail", "maint"))}
    short = short_names(list(gpus) + [h for j in jobs for h in j["hosts"]])
    sh = lambda h: short.get(h, h)
    lines: list[str] = []
    if not data.get("cluster_gpus"):
        lines.append("🟢 Free now: n/a (SLURM GPU counts not available)")
    else:
        free = sorted(((g["total"] - g["used"], h) for h, g in gpus.items() if g["total"] > g["used"]),
                      key=lambda x: (-x[0], x[1]))
        total = sum(f for f, _ in free)
        lines.append("🟢 Free now: " + (f"{total} GPU{'s' if total != 1 else ''}  ("
                                       + ", ".join(f"{sh(h)} ×{f}" for f, h in free) + ")" if free else "none"))
        full = sorted(sh(h) for h, g in gpus.items() if g["total"] <= g["used"])
        if full:
            lines.append("🔴 Full: " + ", ".join(full))
    if data.get("no_slurm"):
        pass  # the note says what to do
    elif not jobs:
        lines.append("no jobs found")
    log_args = data.get("log_args", {})
    for job in jobs:
        state, warns = assess(job, nodes, now, jobs)
        job["_state"], job["_warns"] = state, warns
        evidence = job.get("does_evidence")
        if evidence is None:
            evidence = job["does_evidence"] = job_evidence(job, nodes, tmux, labels.get(job["id"]), log_args.get(job["id"]))
        node_txt = ",".join(sh(h) for h in job["hosts"]) or "—"
        ends = fmt_time(job.get("end_dt"), now) if job.get("end_dt") else "—"
        lines.append(f"🧑‍💻 Your job {job['id']} · {job['name']} · {node_txt} · ends {ends}")
        lines.append("   does: " + ("; ".join(evidence) if evidence else "(no evidence)"))
    for job, w, rel in warning_scope(data, relevant):
        if not (rel or show_all_warnings):
            continue
        for full_name in sorted(short, key=len, reverse=True):
            w = w.replace(full_name, short[full_name])
        node_led = any(w.startswith(v) for v in short.values())
        lines.append(f"⚠️ {w}" if node_led else f"⚠️ {job['id']}: {w}")
    return _finish(lines, data, detail, tmux)


def render_node_detail(n: dict, tmux: list[str], now: datetime) -> list[str]:
    session = next((s for s in tmux if n["host"] in s), None)
    ctx = [n["host"]] + ([f"tmux {session}"] if session else [])
    if n.get("load") and n["load"][0] is not None:
        ctx.append(f"load {n['load'][0]:.1f}/{n['load'][1]} cores")
    if n.get("ram"):
        ctx.append(f"RAM {n['ram'][1]:.0f}/{n['ram'][0]:.0f} GB")
    out = [" · ".join(ctx)]
    if n["gpus"]:
        out.append("GPU  util              mem                 temp   power")
        for g in n["gpus"]:
            u = g["util_pct"]
            mf = g["mem_used_gb"] / g["mem_total_gb"] if g["mem_used_gb"] is not None and g["mem_total_gb"] else None
            mem = f"{g['mem_used_gb']:.0f}/{g['mem_total_gb']:.0f} GB" if mf is not None else "n/a"
            temp = f"{g['temp_c']:.0f}°C" if g["temp_c"] is not None else "n/a"
            power = f"{g['power_w']:.0f} W" if g["power_w"] is not None else "n/a"
            util = f"{u:3.0f}%" if u is not None else " n/a"
            out.append(f"{g['index']:>2}   {bar(u / 100 if u is not None else None)} {util}   "
                       f"{bar(mf, 6)} {mem:<11} {temp:>5}  {power:>6}")
    if n.get("gpu_evidence") and not n["procs"]:
        out.append("processes: none hold a GPU")
    if n["procs"]:
        out.append(f"processes ({n['proc_source']}):")
        for p in n["procs"][:6]:
            out.append(f"  pid {p['pid']:<8} {p['user']:<10} {fmt_td(timedelta(seconds=p['elapsed_s'])):>6}  {p['args'][:70]}")
    if n["containers"]:
        out.append("containers: " + "; ".join(f"{c['name']} ({c['image']}, {c['running_for']})" for c in n["containers"][:4]))
    if n["disks"]:
        out.append("disk: " + " · ".join(f"{d['mount']} {d['use_pct']}% ({fmt_size(d.get('free_gb'))} free)"
                                         for d in n["disks"]))
    out.append(f"probe: {n['probe_s']:.1f}s over {n.get('via', '?')}, GPUs via {n.get('method') or 'n/a'}")
    return out


def to_json(data: dict) -> str:
    def default(o):
        if isinstance(o, datetime):
            return o.astimezone(ISRAEL).isoformat()
        if isinstance(o, timedelta):
            return int(o.total_seconds())
        return str(o)
    slim = json.loads(json.dumps(data, default=default))
    for n in slim.get("nodes", {}).values():
        n.pop("raw", None)
    for j in slim.get("jobs", []):
        if j.get("log"):
            j["log"].pop("text", None)
    return json.dumps(slim, indent=2, ensure_ascii=False)


def read_settings() -> dict[str, str]:
    """slurm_host and job_name from the repo's .claude/forgeloop.md, then ~/.claude/forgeloop/forgeloop.md."""
    found: dict[str, str] = {}
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    for path in (project / ".claude" / "forgeloop.md", Path.home() / ".claude" / "forgeloop" / "forgeloop.md"):
        try:
            text = path.read_text()
        except OSError:
            continue
        for key in ("slurm_host", "job_name"):
            m = re.search(rf"^\s*-?\s*{key}:\s*`?([^`\s(][^`\s]*)`?", text, re.M)
            if m and key not in found:
                found[key] = m.group(1)
    return found


def local_tmux_sessions() -> list[str]:
    try:
        p = subprocess.run(["tmux", "ls", "-F", "#{session_name}"], capture_output=True, text=True, timeout=3)
        return p.stdout.split() if p.returncode == 0 else []
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--job", action="append", default=[], help="SLURM job ID (repeatable)")
    ap.add_argument("--log", action="append", default=[],
                    help="run log paired with the --job before it: a file path, or docker:<container> on the job's "
                         "node (default: the container the job started, if any)")
    ap.add_argument("--label", action="append", default=[], help="short description, paired with --job")
    ap.add_argument("--mine", action="store_true", help="all jobs of the current user")
    ap.add_argument("--name", help="only jobs whose name matches this regex (e.g. '^yhadad_' on a shared account)")
    ap.add_argument("--slurm-host", default=None,
                    help="ssh target that has the SLURM client (default: FORGELOOP_SLURM_HOST, then slurm_host in "
                         ".claude/forgeloop.md or ~/.claude/forgeloop/forgeloop.md, else run locally)")
    ap.add_argument("--plain", action="store_true", help="print the previous default view (job table, node lines)")
    ap.add_argument("--detail", action="store_true", help="add the full per-node view")
    ap.add_argument("--warnings", action="store_true",
                    help="show every warning (all jobs and nodes); default shows only those of the --job runs")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--raw", action="store_true", help="append raw node probe output")
    ap.add_argument("--timing", action="store_true", help="print how long each phase took (stderr)")
    ap.add_argument("--fresh", action="store_true", help="ignore the 20 s result cache")
    args = ap.parse_args(argv)
    settings = read_settings()
    args.slurm_host = args.slurm_host or os.environ.get("FORGELOOP_SLURM_HOST") or settings.get("slurm_host")
    if args.mine and not args.name:
        args.name = settings.get("job_name")
    if not args.job and not args.mine:
        ap.error("give --job <id> or --mine")
    log_args = dict(zip(args.job, args.log))
    relevant = set(args.job)  # the run(s) the task is about; --mine alone names none
    labels = dict(zip(args.job, args.label))

    key = hashlib.sha1(json.dumps([sorted(args.job), args.log, args.label, args.mine, args.slurm_host, args.name,
                                   args.detail, args.json, args.raw, args.plain, args.warnings]).encode()).hexdigest()[:16]
    cache_file = CACHE_DIR / f"result-{key}.json"
    cached = {} if args.fresh else load_json(cache_file)
    if cached and time.time() - cached.get("ts", 0) < RESULT_TTL_S:
        sys.stdout.write(cached["text"])
        if args.timing:
            print(f"timing: served from cache ({time.time() - cached['ts']:.0f}s old)", file=sys.stderr)
        return cached["rc"]

    t0 = time.monotonic()
    timing: dict[str, float] = {}
    data = collect(Runner(args.slurm_host), args.job, log_args, timing, owner_name=args.name)
    if args.name:
        data["jobs"] = [j for j in data["jobs"] if re.search(args.name, j["name"])]
    t1 = time.monotonic()
    if args.json:
        tmux = local_tmux_sessions()
        for job in data["jobs"]:
            job["does_evidence"] = job_evidence(job, data.get("nodes", {}), tmux, labels.get(job["id"]),
                                                log_args.get(job["id"]))
            job["state_summary"], job["warnings"] = assess(job, data.get("nodes", {}), data["collected_at"], data["jobs"])
            job["relevant"] = job["id"] in relevant
        flags = {}
        for job, w, rel in warning_scope(data, relevant):
            flags.setdefault(job["id"], []).append({"text": w, "relevant": rel})
        for job in data["jobs"]:
            job["warning_details"] = flags.get(job["id"], [])
        text = to_json(data) + "\n"
    else:
        text = render(data, args.detail, labels, local_tmux_sessions(), plain=args.plain,
                      relevant=relevant, show_all_warnings=args.warnings)
        if args.raw:
            text += "".join(f"\n--- raw probe: {h} ---\n{n.get('raw', '')}\n" for h, n in data.get("nodes", {}).items())
    timing["render"] = time.monotonic() - t1
    timing["total"] = time.monotonic() - t0
    sys.stdout.write(text)
    if args.timing:
        for phase, secs in timing.items():
            print(f"timing: {phase:<34} {secs:6.2f}s", file=sys.stderr)
        for h, n in data.get("nodes", {}).items():
            print(f"timing:   probe {h:<28} {n['probe_s']:6.2f}s", file=sys.stderr)

    if data.get("no_slurm"):
        rc = 3
    elif not data["jobs"]:
        rc = 2
    else:
        # Exit code reflects only the warnings that are shown: a hidden, out-of-scope warning
        # must not make the run in scope look unhealthy. Full views (--plain, --detail,
        # --warnings, --json) show everything, so they keep the old meaning.
        full = args.plain or args.detail or args.warnings or args.json
        rc = 1 if count_shown_warnings(data, relevant, full) else 0
    save_json(cache_file, {"ts": time.time(), "text": text, "rc": rc})
    return rc


if __name__ == "__main__":
    sys.exit(main())
