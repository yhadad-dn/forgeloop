"""Tests for skills/cluster-loop/cluster_status.py.

Fake squeue/scontrol/sinfo/srun/ssh/date executables stand in for SLURM and the
nodes; the snapshot and probe scripts run for real in bash against them. Fixture
formats come from the live cluster (2026-09-30): rocm-smi CSV headers, the quoted
`rocm-smi --showpids --csv` PID format, docker CreatedAt, tqdm lines with escape
codes, AllocTRES gres/gpu, and squeue dependency strings like afterany:21632(unfulfilled).
"""

import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "cluster-loop" / "cluster_status.py"

spec = importlib.util.spec_from_file_location("cluster_status", SCRIPT)
cs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cs)

GIB = 2 ** 30
ROCM_CSV = textwrap.dedent(f"""\
    device,Temperature (Sensor edge) (C),Temperature (Sensor junction) (C),Average Graphics Package Power (W),GPU use (%),VRAM Total Memory (B),VRAM Total Used Memory (B)
    card0,45.0,61.0,812.0,82,{288 * GIB},{142 * GIB}
    card1,44.0,60.0,798.0,79,{288 * GIB},{139 * GIB}
    card2,31.0,35.0,140.0,0,{288 * GIB},0
    card3,30.0,34.0,139.0,0,{288 * GIB},{100 * GIB}
    """)
UTC = timezone.utc


def cluster_time(delta: timedelta) -> str:
    """A SLURM timestamp relative to now, in the fake cluster's zone (UTC, like the real one)."""
    return (datetime.now(UTC) + delta).strftime("%Y-%m-%dT%H:%M:%S")


def job_line(jid="21577", name="yhadad_run", state="RUNNING", node="mi355x-4", start=-timedelta(hours=1),
             end=timedelta(hours=3), left="3:00:00", used="1:00:00", user="dn", reason="None", dep="(null)"):
    return "|".join([jid, name, state, "XAI", node, cluster_time(start), cluster_time(end), left, user, used,
                     reason, dep])


PS_TABLE = ("  51234 root 1800 99.0 python3 -m evaluation.run --variant converted\n"
            "   5138 prometheus 90000 13.8 /usr/bin/prometheus-node-exporter\n"
            "1580237 root 2 18.0 slurmstepd: [21577.2]\n"
            "  77777 dn 3 5.0 /usr/bin/python3 /usr/bin/rocm-smi --showpids --csv\n")


class FakeCluster:
    """Fake SLURM and nodes in a temp dir, first on PATH."""

    def __init__(self, jobs, steps="", sinfo="mi355x-4|mixed|none", rocm=ROCM_CSV, kfd_pids=("51234",),
                 ps_extra="", stdout_log=None, container=None, container_log=None, ssh_refused=False,
                 no_slurm=False, shm_pct=40, rocm_in_opt=False, alloc_tres="cpu=128,node=1,gres/gpu=8",
                 root_full=False, sacct_holder="none", gres="", tmux_out="cluster-mi355x-4-20260930-1415"):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.bin, gpu_bin, opt = d / "bin", d / "gpubin", d / "opt"
        for x in (self.bin, gpu_bin, opt):
            x.mkdir()
        (d / "jobs.txt").write_text("\n".join(jobs) + "\n")
        (d / "steps.txt").write_text(steps)
        (d / "sinfo.txt").write_text(sinfo + "\n")
        (d / "gres.txt").write_text(gres)
        (d / "rocm.csv").write_text(rocm)
        (d / "ps.txt").write_text(PS_TABLE + ps_extra)
        (d / "srun.log").write_text("")
        if kfd_pids is not None:
            (d / "kfd").mkdir()
            for pid in kfd_pids:
                (d / "kfd" / pid).mkdir()
        running = [l.split("|")[0] for l in jobs if "|RUNNING|" in l]
        if not no_slurm:
            self._w("squeue", f"""
                if [[ " $* " == *" -s "* ]]; then cat "{d}/steps.txt"
                elif [[ " $* " == *" -t R "* ]]; then printf '%s\\n' {' '.join(running) or "''"} | sed '/^$/d'
                else sed '/^$/d' "{d}/jobs.txt"; fi""")
        stdout = f" StdOut={stdout_log}" if stdout_log else ""
        self._w("scontrol", f"""
            if [ "$1 $2" = "show job" ]; then echo "JobId=$4 NumNodes=1 NodeList=mi355x-4 AllocTRES={alloc_tres}{stdout}"
            else echo mi355x-4; fi""")
        self._w("sinfo", f'''if [[ " $* " == *" -O "* ]]; then cat "{d}/gres.txt"; else cat "{d}/sinfo.txt"; fi''')
        # sacct: who held the node at a given time; "none" = no binary (accounting unavailable)
        if sacct_holder != "none":
            self._w("sacct", f"echo '{sacct_holder}'" if sacct_holder else "true")
        self._w("date", 'if [ "$1" = "+%z" ]; then echo +0000; else /bin/date "$@"; fi')
        smi_dir = opt if rocm_in_opt else gpu_bin
        self._w("rocm-smi", f"""
            if [[ " $* " == *" --showpids "* ]]; then printf 'name, value\\n"PID51234", "python3, 1, 0, 0, 0"\\n'
            else cat "{d}/rocm.csv"; fi""", smi_dir)
        created, logfile = container or ("", ""), d / "container.log"
        logfile.write_text(container_log or "")
        self._w("docker", f"""
            if [ "$1" = logs ]; then cat "{logfile}"
            elif [ -n "{created[0]}" ]; then printf '%s\\t%s\\t%s\\t%s\\n' "{created[0]}" "img:1" "2 hours ago" "{created[1]}"; fi""", gpu_bin)
        self._w("ps", f'cat "{d}/ps.txt"', gpu_bin)
        self._w("df", f"printf 'Filesystem 1024-blocks Used Available Capacity Mounted on\\n/dev/a 7340032000 {7255040000 if root_full else 5211422720} {84934656 if root_full else 2128609280} {99 if root_full else 71}%% /\\ntmpfs 792723456 100 792723356 {shm_pct}%% /dev/shm\\n'", gpu_bin)
        self._w("ssh", f"""
            while [ "$1" = "-o" ]; do shift 2; done
            shift  # host
            [ "{int(ssh_refused)}" = 1 ] && {{ echo "Permission denied" >&2; exit 255; }}
            PATH="{gpu_bin}:$PATH" bash -c "$*" """)
        self._w("srun", f"""
            echo "$*" >> "{d}/srun.log"
            while [ $# -gt 0 ] && [ "$1" != bash ]; do shift; done
            PATH="{gpu_bin}:$PATH" "$@" """)
        self._w("tmux", f"echo '{tmux_out}'" if tmux_out else "exit 1")
        self.srun_log = d / "srun.log"
        (d / "home").mkdir()
        self.env = dict(os.environ, PATH=f"{self.bin}:/usr/bin:/bin", XDG_CACHE_HOME=str(d / "cache"),
                        FL_KFD_DIR=str(d / "kfd"), FL_EXTRA_PATH=str(opt),
                        HOME=str(d / "home"), CLAUDE_PROJECT_DIR=str(d / "home"))  # never read the real user's config
        self.env.pop("FORGELOOP_SLURM_HOST", None)

    def _w(self, name, body, where=None):
        path = (where or self.bin) / name
        path.write_text("#!/usr/bin/env bash\n" + textwrap.dedent(body).strip() + "\n")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)

    def run(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                              env=self.env, timeout=60)

    def close(self):
        self.tmp.cleanup()


def write_log(text, age_s=0):
    f = tempfile.NamedTemporaryFile("w", suffix=".log", delete=False)
    f.write(text)
    f.close()
    t = time.time() - age_s
    os.utime(f.name, (t, t))
    return f.name


def docker_ts(delta: timedelta) -> str:
    return (datetime.now(UTC) + delta).strftime("%Y-%m-%dT%H:%M:%S.123456789Z")


def docker_created(delta: timedelta) -> str:
    return (datetime.now(UTC) + delta).strftime("%Y-%m-%d %H:%M:%S +0000 UTC")


class ProgressParsingTests(unittest.TestCase):
    def test_nested_epoch_and_step_gives_overall_fraction(self):
        p = cs.parse_progress("epoch 2/3 step 1840/2760 loss 1.91")
        self.assertAlmostEqual(p["fraction"], (1 + 1840 / 2760) / 3)
        self.assertEqual(p["counter"], "ep2/3")

    def test_real_tqdm_line_with_escape_codes(self):
        p = cs.parse_progress(" 80%|███████▉  | 23714/29682 [20:31<04:56, 20.14it/s]\x1b[A")
        self.assertAlmostEqual(p["fraction"], 23714 / 29682)
        self.assertEqual(p["remaining"], timedelta(minutes=4, seconds=56))

    def test_printed_eta(self):
        p = cs.parse_progress("step 10/1000 loss 3.2 ETA 1:05:00")
        self.assertEqual(p["remaining"], timedelta(hours=1, minutes=5))

    def test_plain_percent(self):
        self.assertAlmostEqual(cs.parse_progress("progress: 37.5% done")["fraction"], 0.375)

    def test_no_counter(self):
        self.assertIsNone(cs.parse_progress("loading weights")["fraction"])

    def test_rate_based_finish(self):
        now = datetime.now(UTC)
        fin, src = cs.estimate_finish({"fraction": 0.25, "remaining": None}, timedelta(hours=1), now)
        self.assertEqual(src, "rate")
        self.assertAlmostEqual((fin - now).total_seconds(), 3 * 3600, delta=1)

    def test_steps_pick_newest_run_step(self):
        steps = cs.parse_steps("21577.extern|extern|2:00:00\n21577.0|python|1:30:00\n21577.1|python|0:40:00\n")
        self.assertEqual(steps["21577"], timedelta(minutes=40))


class ParseTests(unittest.TestCase):
    def test_rocm_csv_by_header_name(self):
        g = cs.parse_rocm_csv(ROCM_CSV)[0]
        self.assertEqual((g["util_pct"], round(g["mem_total_gb"]), round(g["mem_used_gb"]), g["temp_c"], g["power_w"]),
                         (82.0, 288, 142, 45.0, 812.0))

    def test_quoted_rocm_pids(self):
        self.assertEqual(cs.parse_gpu_pids('name, value\n"PID1580237", "slurmstepd, 0, 0, 0, 0"\n'), {1580237})

    def test_dependency_parsed(self):
        j = cs.parse_squeue(job_line(dep="afterany:21632(unfulfilled)"))[0]
        self.assertEqual(j["depends_on"], ["21632"])

    def test_docker_created_parsed(self):
        c = cs.parse_docker("dsv4agx_decode\timg\t22 hours ago\t2026-09-29 14:57:24 +0000 UTC\n")[0]
        self.assertEqual(c["created"], datetime(2026, 9, 29, 14, 57, 24, tzinfo=UTC))

    def test_disk_free(self):
        d = cs.parse_df("F 1024-blocks Used Available Capacity Mounted\n/dev/a 7340032000 7255040000 84934656 99% /\n")[0]
        self.assertEqual((d["use_pct"], round(d["free_gb"])), (99, 81))


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.fakes, self.logs = [], []

    def tearDown(self):
        for f in self.fakes:
            f.close()
        for l in self.logs:
            os.unlink(l)

    def fake(self, jobs=None, **kw):
        f = FakeCluster(jobs or [job_line()], **kw)
        self.fakes.append(f)
        return f

    def log(self, text, age_s=0):
        path = write_log(text, age_s)
        self.logs.append(path)
        return path

    def row(self, out, jid="21577"):
        return next(l for l in out.splitlines() if l.startswith(jid))

    def test_no_slurm_client_is_reported_not_no_jobs(self):
        r = self.fake(no_slurm=True).run("--plain", "--mine")
        self.assertIn("no SLURM client on this host: pass --slurm-host", r.stdout)
        self.assertNotIn("no jobs found", r.stdout)
        self.assertEqual(r.returncode, 3)

    def test_on_track_job_row(self):
        log = self.log("epoch 2/3 step 1840/2760 loss 1.91\n")
        out = self.fake(steps="21577.0|python|0:30:00\n").run("--plain", "--job", "21577", "--log", log,
                                                              "--label", "rank-alloc proof run").stdout
        row = self.row(out)
        self.assertIn("rank-alloc proof run", row)
        self.assertIn("█████▌░░░░  55% ep2/3", row)
        self.assertIn("✓ on track", row)

    def test_expires_before_done_with_successor(self):
        log = self.log("step 100/1000 loss 3.0\n")
        jobs = [job_line(end=timedelta(hours=1), left="1:00:00"),
                job_line(jid="21600", state="PENDING", node="", reason="Dependency", dep="afterany:21577(unfulfilled)")]
        out = self.fake(jobs, steps="21577.0|python|1:00:00\n").run("--plain", "--mine", "--log", log).stdout
        out = self.fake(jobs, steps="21577.0|python|1:00:00\n").run("--plain", "--job", "21577", "--log", log, "--job", "21600").stdout
        self.assertIn("⚠ expires before done", self.row(out))
        self.assertIn("successor job 21600 is queued to continue", out)

    def test_stalled_log(self):
        log = self.log("step 850/2760 loss 2.04\n", age_s=14 * 60)
        out = self.fake().run("--plain", "--job", "21577", "--log", log).stdout
        self.assertIn("⚠ stalled 14m", out)

    def test_probe_over_ssh_sees_gpus_and_skips_srun(self):
        f = self.fake()
        out = f.run("--plain", "--job", "21577", "--detail").stdout
        self.assertIn("util ▇▇▁▁", out)
        self.assertIn("over ssh", out)
        self.assertEqual(f.srun_log.read_text(), "")

    def test_srun_fallback_requests_the_jobs_gpus(self):
        f = self.fake(ssh_refused=True)
        out = f.run("--plain", "--job", "21577", "--detail").stdout
        self.assertIn("over srun", out)
        self.assertIn("--gres=gpu:8", f.srun_log.read_text())

    def test_rocm_smi_found_in_opt_rocm(self):
        out = self.fake(rocm_in_opt=True).run("--plain", "--job", "21577").stdout
        self.assertIn("GPUs  mi355x-4  util", out)
        self.assertNotIn("GPU metrics unavailable", out)

    def test_probe_self_and_daemons_not_reported(self):
        out = self.fake(kfd_pids=("51234", "1580237", "77777")).run("--plain", "--job", "21577", "--detail").stdout
        self.assertIn("pid 51234", out)
        self.assertNotIn("slurmstepd", out)
        self.assertNotIn("pid 77777", out)
        self.assertNotIn("prometheus", out)
        self.assertNotIn("foreign", out)

    def test_no_gpu_evidence_never_flags_foreign(self):
        # KFD unreadable and no rocm PIDs: processes are listed, never judged
        f = self.fake(kfd_pids=None)
        (Path(f.bin.parent) / "gpubin" / "rocm-smi").write_text(
            "#!/usr/bin/env bash\n[[ \" $* \" == *\" --showpids \"* ]] || cat \"%s\"\n" % (Path(f.bin.parent) / "rocm.csv"))
        out = f.run("--plain", "--job", "21577", "--detail").stdout
        self.assertIn("GPU holders unknown", out)
        self.assertNotIn("foreign", out)

    def test_empty_kfd_means_none_hold_a_gpu(self):
        f = self.fake(kfd_pids=())
        (Path(f.bin.parent) / "gpubin" / "rocm-smi").write_text(
            "#!/usr/bin/env bash\n[[ \" $* \" == *\" --showpids \"* ]] || cat \"%s\"\n" % (Path(f.bin.parent) / "rocm.csv"))
        out = f.run("--plain", "--job", "21577", "--detail").stdout
        self.assertIn("processes: none hold a GPU", out)

    def test_older_workload_owned_by_another_job_is_foreign(self):
        holder = "21633|regeveyal_hpo|dn|2026-09-29T14:56:00|2026-09-29T14:59:17"
        f = self.fake(jobs=[job_line(start=-timedelta(minutes=20))], sacct_holder=holder,
                      container=("dsv4agx_decode", docker_created(-timedelta(hours=22))))
        out = f.run("--plain", "--job", "21577", "--name", "^yhadad_").stdout
        self.assertIn("⚠ foreign workload", self.row(out))
        self.assertIn("container dsv4agx_decode started under job 21633 regeveyal_hpo (that job ended", out)
        self.assertIn("holds GPU 0,1,3", out)

    def test_workload_from_chained_predecessor_is_ours_and_gives_progress(self):
        holder = "21632|yhadad_g3b|dn|2026-09-29T13:26:58|2026-09-30T13:26:59"
        logtxt = f"{docker_ts(-timedelta(seconds=2))}  83%|████████▎ | 24490/29682 [20:40<04:18, 20.1it/s]"
        f = self.fake(jobs=[job_line(start=-timedelta(minutes=3))], sacct_holder=holder,
                      container=("g3_eval_run", docker_created(-timedelta(hours=2))), container_log=logtxt)
        out = f.run("--plain", "--job", "21577", "--name", "^yhadad_").stdout
        self.assertNotIn("foreign", out)
        self.assertIn("82% 24490/29682", self.row(out))

    def test_workload_started_on_unallocated_node_is_foreign(self):
        f = self.fake(jobs=[job_line(start=-timedelta(minutes=20))], sacct_holder="",
                      container=("stray", docker_created(-timedelta(hours=5))))
        out = f.run("--plain", "--job", "21577").stdout
        self.assertIn("started while no job held the node", out)

    def test_no_accounting_falls_back_to_possibly_foreign(self):
        f = self.fake(jobs=[job_line(start=-timedelta(minutes=20))],
                      container=("dsv4agx_decode", docker_created(-timedelta(hours=22))))
        out = f.run("--plain", "--job", "21577").stdout
        self.assertIn("⚠ possibly foreign", self.row(out))
        self.assertIn("started 21h40m before this job", out)
        self.assertIn("owner unknown (no accounting data)", out)

    def test_container_started_by_job_is_ours_and_gives_progress(self):
        logtxt = "\n".join(f"{docker_ts(-timedelta(seconds=5 - i))}  80%|███████▉  | {23700 + i}/29682 "
                           f"[20:30<04:56, 20.15it/s]\x1b[A" for i in range(3))
        f = self.fake(jobs=[job_line(start=-timedelta(hours=3))],
                      container=("g3_eval_run", docker_created(-timedelta(hours=2))), container_log=logtxt)
        r = f.run("--plain", "--job", "21577", "--timing")
        row = self.row(r.stdout)
        self.assertIn("79% 23702/29682", row)
        self.assertNotIn("foreign", r.stdout)
        self.assertIn("container logs (1 in parallel)", r.stderr)

    def test_disk_warning_shows_free_space(self):
        out = self.fake(root_full=True).run("--plain", "--job", "21577").stdout
        self.assertIn("/ at 99% (81 GB free of 6.8 TB)", out)

    def test_name_filter(self):
        jobs = [job_line(), job_line(jid="21241", name="ainic_canary", state="PENDING", node="", reason="JobHeldUser")]
        out = self.fake(jobs).run("--plain", "--mine", "--name", "^yhadad_").stdout
        self.assertIn("21577", out)
        self.assertNotIn("ainic_canary", out)

    def test_batch_job_log_found_via_stdout(self):
        log = self.log("epoch 1/4 step 500/1000\n")
        out = self.fake(stdout_log=log).run("--plain", "--mine").stdout
        self.assertIn("ep1/4", out)

    def test_pending_job(self):
        jobs = [job_line(jid="21600", state="PENDING", node="", reason="Resources", start=timedelta(hours=2))]
        out = self.fake(jobs).run("--plain", "--mine").stdout
        self.assertIn("… pending (Resources, expected start", out)

    def test_result_cache_and_method_cache(self):
        f = self.fake()
        first = f.run("--plain", "--job", "21577", "--timing")
        second = f.run("--plain", "--job", "21577", "--timing")
        self.assertIn("slurm snapshot (1 round trip)", first.stderr)
        self.assertIn("served from cache", second.stderr)
        methods = json.loads((Path(f.env["XDG_CACHE_HOME"]) / "forgeloop" / "cluster-status" / "methods.json").read_text())
        self.assertEqual(methods, {"mi355x-4": "host"})

    def test_missing_gpu_tools_not_invented(self):
        out = self.fake(rocm="").run("--plain", "--job", "21577").stdout
        self.assertIn("n/a  GPU metrics unavailable", out)
        self.assertNotIn("idle GPU", out)

    def test_unknown_job(self):
        r = self.fake(jobs=[""]).run("--plain", "--job", "99999")
        self.assertIn("job 99999 not found in squeue", r.stdout)
        self.assertEqual(r.returncode, 2)

    def test_json(self):
        data = json.loads(self.fake().run("--job", "21577", "--json").stdout)
        self.assertEqual(data["jobs"][0]["id"], "21577")
        self.assertIn("state_summary", data["jobs"][0])
        self.assertNotIn("raw", data["nodes"]["mi355x-4"])

    # --- default view: "what can I use" ---------------------------------------------------

    GRES = ("mi355x-4        gpu:8(S:0-1)        gpu:8(IDX:0-7)\n"
            "amd-mi355x-7    gpu:8(S:0-1)        gpu:0(IDX:N/A)\n"
            "des2-2          gpu:8(S:0-1)        gpu:1(IDX:0)\n"
            "mi355x-9        gpu:8(S:0-1)        gpu:8(IDX:0-7)\n")

    def test_default_free_now_sorted_by_free_count(self):
        out = self.fake(gres=self.GRES).run("--mine").stdout
        self.assertIn("🟢 Free now: 15 GPUs  (mi355x-7 ×8, des2-2 ×7)", out)
        self.assertNotIn("EXPIRES", out)

    def test_default_free_now_none(self):
        gres = "mi355x-4   gpu:8(S:0-1)   gpu:8(IDX:0-7)\nmi355x-9   gpu:8(S:0-1)   gpu:8(IDX:0-7)\n"
        out = self.fake(gres=gres).run("--mine").stdout
        self.assertIn("🟢 Free now: none", out)
        self.assertIn("🔴 Full: mi355x-4, mi355x-9", out)

    def test_default_full_line_omitted_when_nothing_is_full(self):
        out = self.fake(gres="mi355x-4   gpu:8(S:0-1)   gpu:2(IDX:0-1)\n").run("--mine").stdout
        self.assertIn("🟢 Free now: 6 GPUs  (mi355x-4 ×6)", out)
        self.assertNotIn("🔴", out)

    def test_default_full_node_gives_no_warning(self):
        gres = "mi355x-4   gpu:8(S:0-1)   gpu:8(IDX:0-7)\n"
        out = self.fake(gres=gres, rocm=ROCM_CSV.replace(",0\n", f",{1 * GIB}\n")).run("--mine").stdout
        self.assertIn("🔴 Full: mi355x-4", out)
        self.assertNotIn("⚠", out)

    def test_default_keeps_real_problem_warning(self):
        out = self.fake(gres=self.GRES, root_full=True).run("--job", "21577").stdout
        self.assertIn("⚠️ mi355x-4 / at 99% (81 GB free of 6.8 TB) → writes or data loading can fail if it fills", out)

    def test_default_job_warning_without_node_gets_job_prefix(self):
        log = self.log("step 850/2760 loss 2.04\n", age_s=14 * 60)
        out = self.fake(gres=self.GRES).run("--job", "21577", "--log", log).stdout
        self.assertIn("⚠️ 21577: log silent 14m", out)

    def test_default_your_job_line_has_name_node_and_end(self):
        job = job_line(end=timedelta(hours=3), left="3:00:00")
        out = self.fake([job], gres=self.GRES).run("--mine").stdout
        end = cs.fmt_time(datetime.now(UTC) + timedelta(hours=3), datetime.now(UTC))
        line = next(l for l in out.splitlines() if l.startswith("🧑‍💻 Your job"))
        self.assertTrue(line.startswith("🧑‍💻 Your job 21577 · yhadad_run · mi355x-4 · ends "), line)
        self.assertIn("ends " + end[-5:], line)

    def test_default_your_job_line_unknown_end(self):
        parts = job_line(jid="21600", state="PENDING", node="", reason="Resources").split("|")
        parts[6] = "N/A"
        out = self.fake(["|".join(parts)], gres=self.GRES).run("--mine").stdout
        self.assertIn("🧑‍💻 Your job 21600 · yhadad_run · — · ends —", out)

    def test_default_does_evidence_present(self):
        out = self.fake(steps="21577.0|python_eval|0:30:00\n", gres=self.GRES).run("--mine").stdout
        does = next(l for l in out.splitlines() if l.strip().startswith("does:"))
        self.assertIn("step python_eval", does)
        self.assertIn("python3 -m evaluation.run --variant converted", does)
        self.assertIn("tmux cluster-mi355x-4-20260930-1415", does)
        self.assertNotIn("(no evidence)", does)

    def test_default_does_evidence_includes_log_name_and_container(self):
        log = self.log("epoch 1/4 step 500/1000\n")
        f = self.fake(gres=self.GRES, container=("g3_eval_run", docker_created(-timedelta(minutes=10))))
        out = f.run("--job", "21577", "--log", log).stdout
        does = next(l for l in out.splitlines() if l.strip().startswith("does:"))
        self.assertIn("container g3_eval_run", does)
        self.assertIn("log " + os.path.basename(log), does)

    def test_default_does_evidence_absent(self):
        f = self.fake(gres=self.GRES, kfd_pids=(), tmux_out="")
        (Path(f.bin.parent) / "gpubin" / "rocm-smi").write_text(
            "#!/usr/bin/env bash\n[[ \" $* \" == *\" --showpids \"* ]] || cat \"%s\"\n" % (Path(f.bin.parent) / "rocm.csv"))
        out = f.run("--mine").stdout
        self.assertIn("   does: (no evidence)", out)

    def test_does_evidence_strips_secrets(self):
        ps = "  61234 root 600 50.0 python train.py --api_key=abc123 TOKEN=zzz --lr=1e-3 --password hunter2 MODE=fast --epochs 3\n"
        out = self.fake(gres=self.GRES, kfd_pids=("51234", "61234"), ps_extra=ps).run("--mine").stdout
        for secret in ("abc123", "zzz", "hunter2", "TOKEN", "api_key", "password"):
            self.assertNotIn(secret, out)
        self.assertIn("python train.py --lr= MODE= --epochs 3", out)

    def test_sanitize_command_caps_length(self):
        self.assertLessEqual(len(cs.sanitize_command("python " + "x" * 300)), 100)

    def test_short_names(self):
        self.assertEqual(cs.short_names(["amd-mi355x-7", "des2-2"]), {"amd-mi355x-7": "mi355x-7", "des2-2": "des2-2"})
        # stripping would make two names equal: keep full names
        self.assertEqual(cs.short_names(["amd-des2-2", "des2-2"]), {"amd-des2-2": "amd-des2-2", "des2-2": "des2-2"})

    def test_down_node_is_not_free(self):
        f = self.fake(gres=self.GRES, sinfo="mi355x-4|mixed|none\ndes2-2|drained|maintenance")
        out = f.run("--mine").stdout
        self.assertNotIn("des2-2", out.split("\n")[0])

    def test_no_gres_data_is_not_invented(self):
        out = self.fake().run("--mine").stdout
        self.assertIn("🟢 Free now: n/a", out)

    def test_plain_prints_previous_default(self):
        out = self.fake(gres=self.GRES, steps="21577.0|python|0:30:00\n").run("--plain", "--mine").stdout
        self.assertIn("JOB    WHAT", out)
        self.assertIn("EXPIRES  STATE", out)
        self.assertIn("GPUs  mi355x-4  util", out)
        self.assertNotIn("Free now", out)
        self.assertNotIn("Your job", out)

    def test_json_has_does_evidence_per_job(self):
        data = json.loads(self.fake(steps="21577.0|python_eval|0:30:00\n").run("--job", "21577", "--json").stdout)
        ev = data["jobs"][0]["does_evidence"]
        self.assertIsInstance(ev, list)
        self.assertIn("step python_eval", ev)
        self.assertIn("state_summary", data["jobs"][0])

    # --- warnings are shown only for the run in scope -------------------------------------

    @staticmethod
    def synthetic(disk_full_hosts=("n1", "n2"), jobs=(("A", "n1"), ("B", "n2"))):
        node = lambda h: {"host": h, "gpus": [], "procs": [], "containers": [], "notes": [], "slurm_state": "mixed",
                          "slurm_reason": "", "probe_s": 0.1,
                          "disks": [{"mount": "/", "use_pct": 99 if h in disk_full_hosts else 10,
                                     "free_gb": 10.0, "size_gb": 1000.0}]}
        hosts = sorted({h for _, h in jobs})
        js = [{"id": i, "name": f"job{i}", "state": "RUNNING", "hosts": [h], "user": "dn", "steps": [], "depends_on": [],
               "start_dt": None, "end_dt": None, "left_td": None, "log": None, "finish_dt": None, "reason": "",
               "finish_source": "no log"} for i, h in jobs]
        return {"jobs": js, "nodes": {h: node(h) for h in hosts}, "notes": [], "collected_at": datetime.now(UTC)}

    def test_unrelated_job_node_warning_is_hidden(self):
        out = cs.render(self.synthetic(), False, {}, [], relevant={"A"})
        self.assertIn("n1 / at 99%", out)
        self.assertNotIn("n2 / at 99%", out)
        self.assertIn("Your job B", out)  # your-job lines still show

    def test_node_shared_with_relevant_job_shows_other_jobs_warning(self):
        data = self.synthetic(disk_full_hosts=("n1",), jobs=(("A", "n1"), ("B", "n1")))
        out = cs.render(data, False, {}, [], relevant={"B"})
        self.assertEqual(out.count("n1 / at 99%"), 2)  # warned via A and via B; node is B's node too

    def test_no_relevant_jobs_shows_no_warning_lines(self):
        out = cs.render(self.synthetic(), False, {}, [], relevant=set())
        self.assertNotIn("⚠", out)
        self.assertNotIn("hidden", out)
        self.assertIn("Your job A", out)

    def test_show_all_warnings(self):
        out = cs.render(self.synthetic(), False, {}, [], relevant=set(), show_all_warnings=True)
        self.assertIn("n1 / at 99%", out)
        self.assertIn("n2 / at 99%", out)

    def test_shown_warning_count_follows_scope(self):
        data = self.synthetic()
        self.assertEqual(cs.count_shown_warnings(data, {"A"}, False), 1)
        self.assertEqual(cs.count_shown_warnings(data, set(), False), 0)
        self.assertEqual(cs.count_shown_warnings(data, set(), True), 2)

    def test_mine_default_hides_disk_warning_and_exits_zero(self):
        r = self.fake(gres=self.GRES, root_full=True).run("--mine")
        self.assertNotIn("⚠", r.stdout)
        self.assertIn("Your job 21577", r.stdout)
        self.assertEqual(r.returncode, 0)

    def test_mine_warnings_flag_shows_all_and_exits_one(self):
        r = self.fake(gres=self.GRES, root_full=True).run("--mine", "--warnings")
        self.assertIn("⚠️ mi355x-4 / at 99%", r.stdout)
        self.assertEqual(r.returncode, 1)

    def test_job_default_shows_disk_warning_of_its_node_and_exits_one(self):
        r = self.fake(root_full=True).run("--job", "21577")
        self.assertIn("⚠️ mi355x-4 / at 99%", r.stdout)
        self.assertEqual(r.returncode, 1)

    def test_plain_and_detail_keep_all_warnings(self):
        for flag in ("--plain", "--detail"):
            r = self.fake(root_full=True).run("--mine", flag)
            self.assertIn("/ at 99%", r.stdout, flag)
            self.assertEqual(r.returncode, 1, flag)

    def test_json_is_complete_with_relevant_flags(self):
        mine = json.loads(self.fake(root_full=True).run("--mine", "--json").stdout)["jobs"][0]
        self.assertFalse(mine["relevant"])
        self.assertTrue(mine["warnings"])
        self.assertEqual([w["relevant"] for w in mine["warning_details"]], [False] * len(mine["warnings"]))
        named = json.loads(self.fake(root_full=True).run("--job", "21577", "--json").stdout)["jobs"][0]
        self.assertTrue(named["relevant"])
        self.assertTrue(all(w["relevant"] for w in named["warning_details"]))


if __name__ == "__main__":
    unittest.main()
