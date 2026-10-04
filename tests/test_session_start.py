"""Tests for hooks/session_start.py (conventions layering)."""

import json
import os
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
                   CLAUDE_PROJECT_DIR=str(self.project), **env_extra)
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

    def test_off_switch(self):
        self.assertIsNone(self.run_hook(FORGELOOP_CONVENTIONS="off"))


if __name__ == "__main__":
    unittest.main()
