"""Tests for hooks/session_start.py (conventions layering)."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "session_start.py"


class SessionStartHookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.project = Path(self.tmp.name) / "project"
        self.home.mkdir()
        (self.project / ".claude").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, **env_extra):
        env = dict(os.environ, HOME=str(self.home), CLAUDE_PLUGIN_ROOT=str(ROOT),
                   CLAUDE_PROJECT_DIR=str(self.project))
        env["FORGELOOP_SETUP_HINT"] = "off"   # never spawn the real `claude` unless a test asks
        env.update(env_extra)
        env.pop("FORGELOOP_CONVENTIONS", None) if "FORGELOOP_CONVENTIONS" not in env_extra else None
        p = subprocess.run([sys.executable, str(HOOK)], input="{}", capture_output=True, text=True, env=env, timeout=10)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"] if p.stdout.strip() else None

    def test_team_default_injected_with_resolved_script_path(self):
        ctx = self.run_hook()
        self.assertIn("## Status reports", ctx)
        self.assertIn("Israel time", ctx)
        self.assertIn("**Next:**", ctx)
        self.assertIn("**What's stopping us:**", ctx)
        self.assertIn("**From you:**", ctx)
        self.assertIn("## Summaries", ctx)
        self.assertIn("**Milestones**", ctx)
        self.assertIn(str(ROOT / "skills" / "cluster-loop" / "cluster_status.py"), ctx)
        self.assertNotIn("{CLUSTER_STATUS}", ctx)

    def test_other_remote_line(self):
        fl = self.home / ".claude" / "forgeloop"
        marker = {"SSH_CONNECTION": "1.2.3.4 22 5.6.7.8 22", "CODESPACES": "true"}
        ctx = self.run_hook(**marker)
        self.assertIn("Remote-SSH hosts by default", ctx)
        self.assertIn("~/.claude/forgeloop/durable", ctx)
        self.assertEqual(ctx.count("durable (tmux) sessions"), 1)
        ctx = self.run_hook(FORGELOOP_DURABLE="off", **marker)
        self.assertNotIn("Remote-SSH hosts by default", ctx)
        fl.mkdir(parents=True)
        (fl / "durable").write_text("no\n")
        self.assertNotIn("Remote-SSH hosts by default", self.run_hook(**marker))
        (fl / "durable").unlink()
        self.assertNotIn("Remote-SSH hosts by default", self.run_hook(SSH_CONNECTION="1 2 3 4", CODESPACES="", REMOTE_CONTAINERS="", WSL_DISTRO_NAME=""))
        # not swallowed when there are no convention layers and no setup hint
        empty_root = Path(self.tmp.name) / "root"
        shutil.copytree(ROOT / "skills", empty_root / "skills")
        ctx = self.run_hook(CLAUDE_PLUGIN_ROOT=str(empty_root), **marker)
        self.assertIn("Remote-SSH hosts by default", ctx)


    def test_personal_and_repo_layers_appended_in_order(self):
        (self.home / ".claude" / "forgeloop").mkdir(parents=True)
        (self.home / ".claude" / "forgeloop" / "conventions.md").write_text("Call me Yak.")
        (self.project / ".claude" / "forgeloop.md").write_text(
            "# cfg\n\n## Commands\n\n- x\n\n## Conventions\n\nPaper text: run the lint.\n\n## Gates\n\n- y\n")
        ctx = self.run_hook()
        team, personal, repo = ctx.index("## Status reports"), ctx.index("Call me Yak."), ctx.index("run the lint")
        self.assertLess(team, personal)
        self.assertLess(personal, repo)
        self.assertNotIn("## Gates", ctx)              # only the Conventions section is taken

    def test_ste_style_off_by_default_on_via_env_or_file(self):
        self.assertNotIn("ASD-STE100", self.run_hook())
        self.assertIn("ASD-STE100", self.run_hook(FORGELOOP_STYLE="ste"))
        self.assertNotIn("ASD-STE100", self.run_hook(FORGELOOP_STYLE="other"))
        (self.home / ".claude" / "forgeloop").mkdir(parents=True)
        (self.home / ".claude" / "forgeloop" / "style").write_text("ste\n")
        ctx = self.run_hook()
        self.assertIn("ASD-STE100", ctx)
        self.assertLess(ctx.index("## Status reports"), ctx.index("ASD-STE100"))

    def test_off_switch(self):
        self.assertIsNone(self.run_hook(FORGELOOP_CONVENTIONS="off"))


HINT = "ForgeLoop: settings need a one-time check. Run /forgeloop:setup."


class SetupHintTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.home, self.project, self.bin = base / "home", base / "project", base / "bin"
        for d in (self.home / ".claude", self.project / ".claude", self.bin):
            d.mkdir(parents=True)
        self.settings = self.home / ".claude" / "settings.json"
        self.stamp = self.home / ".claude" / "forgeloop" / "setup-stamp"
        self.root = ROOT
        self.fake_claude("2.1.284 (Claude Code)")

    def tearDown(self):
        self.tmp.cleanup()

    def fake_claude(self, out):
        c = self.bin / "claude"
        c.write_text(f"#!/bin/sh\necho '{out}'\n")
        c.chmod(0o755)

    def run_hook(self, root=None, path=None, **env_extra):
        env = dict(os.environ, HOME=str(self.home), CLAUDE_PLUGIN_ROOT=str(root or self.root),
                   CLAUDE_PROJECT_DIR=str(self.project),
                   PATH=path if path is not None else f"{self.bin}:{os.environ['PATH']}")
        env.pop("FORGELOOP_SETUP_HINT", None)
        env.pop("FORGELOOP_CONVENTIONS", None)
        env.update(env_extra)
        p = subprocess.run([sys.executable, str(HOOK)], input="{}", capture_output=True, text=True,
                           env=env, timeout=15)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"] if p.stdout.strip() else None

    def plugin_copy(self):
        dest = Path(self.tmp.name) / "plugin"
        (dest / "skills").mkdir(parents=True)
        shutil.copytree(ROOT / "hooks", dest / "hooks", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "skills" / "setup", dest / "skills" / "setup",
                        ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "styles", dest / "styles")
        shutil.copy(ROOT / "conventions.md", dest / "conventions.md")
        (dest / ".claude-plugin").mkdir()
        shutil.copy(ROOT / ".claude-plugin" / "plugin.json", dest / ".claude-plugin" / "plugin.json")
        return dest

    def test_setup_hint_once_per_version(self):
        self.assertIn(HINT, self.run_hook())
        self.assertTrue(self.stamp.exists())
        self.assertNotIn(HINT, self.run_hook())
        plugin = self.plugin_copy()
        self.stamp.write_text("0.0.1\n")
        self.assertIn(HINT, self.run_hook(root=plugin))
        meta = json.loads((plugin / ".claude-plugin" / "plugin.json").read_text())
        self.assertEqual(self.stamp.read_text().strip(), meta["version"])
        self.assertNotIn(HINT, self.run_hook(root=plugin))
        meta["version"] = "99.0.0"
        (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps(meta))
        self.assertIn(HINT, self.run_hook(root=plugin))

    def test_setup_hint_when_layers_empty_and_stamp_when_nothing_pending(self):
        plugin = self.plugin_copy()
        (plugin / "conventions.md").unlink()
        self.assertIn(HINT, self.run_hook(root=plugin))
        self.stamp.unlink()
        self.fake_claude("2.1.290 (Claude Code)")
        self.settings.write_text(json.dumps({
            "extraKnownMarketplaces": {"forgeloop": {"source": {"source": "github", "repo": "yhadad-dn/forgeloop"}}},
            "enabledPlugins": {"forgeloop@forgeloop": True}}))
        self.assertNotIn(HINT, self.run_hook() or "")
        self.assertTrue(self.stamp.exists())

    def test_setup_hint_never_writes_settings(self):
        self.settings.write_text('{"keep": true}\n')
        before = self.settings.read_bytes()
        self.assertIn(HINT, self.run_hook())
        self.assertEqual(self.settings.read_bytes(), before)
        files = sorted(str(p.relative_to(self.home)) for p in self.home.rglob("*") if p.is_file())
        self.assertEqual(files, [".claude/forgeloop/setup-stamp", ".claude/settings.json"])

    def test_setup_hint_off_and_fail_open(self):
        self.assertNotIn(HINT, self.run_hook(FORGELOOP_SETUP_HINT="off") or "")
        self.assertFalse(self.stamp.exists())
        self.assertNotIn(HINT, self.run_hook(FORGELOOP_SETUP_HINT="No") or "")
        self.assertIsNone(self.run_hook(FORGELOOP_CONVENTIONS="off"))
        # missing claude: no hint, exit 0
        self.assertNotIn(HINT, self.run_hook(path=str(self.bin / "none")) or "")
        # broken setup module: no hint, exit 0
        plugin = self.plugin_copy()
        (plugin / "skills" / "setup" / "forgeloop_setup.py").write_text("raise RuntimeError('x')\n")
        self.assertNotIn(HINT, self.run_hook(root=plugin) or "")



if __name__ == "__main__":
    unittest.main()
