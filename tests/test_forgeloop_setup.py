"""Tests for skills/setup/forgeloop_setup.py (scratch HOME only; never the real one)."""

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "setup" / "forgeloop_setup.py"
SKILL = ROOT / "skills" / "setup" / "SKILL.md"


def load_module():
    spec = importlib.util.spec_from_file_location("forgeloop_setup", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        (self.home / ".claude").mkdir(parents=True)
        self.settings = self.home / ".claude" / "settings.json"

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args, version="2.1.284"):
        cmd = [sys.executable, str(SCRIPT), *args, "--settings", str(self.settings),
               "--home", str(self.home)]
        if version:
            cmd += ["--cli-version", version]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20)

    def status(self, changes, item):
        return [c.status for c in changes if c.item == item]

    def test_parse_version(self):
        m = load_module()
        self.assertEqual(m.parse_version("2.1.284 (Claude Code)"), (2, 1, 284))
        self.assertEqual(m.parse_version("2.1.287"), (2, 1, 287))
        self.assertIsNone(m.parse_version("garbage"))
        self.assertIsNone(m.parse_version(""))

    def test_flag_only_for_old_cli(self):
        m = load_module()
        h = str(self.home)
        self.assertEqual(self.status(m.compute_changes({}, h, (2, 1, 284), False), "env-flag"), ["pending"])
        self.assertEqual(self.status(m.compute_changes({}, h, (2, 1, 287), False), "env-flag"), ["ok"])
        self.assertEqual(self.status(m.compute_changes({}, h, (2, 2, 0), False), "env-flag"), ["ok"])
        unknown = m.compute_changes({}, h, None, False)
        self.assertEqual(self.status(unknown, "env-flag"), ["unknown"])
        have = {"env": {m.FLAG: "1"}}
        self.assertEqual(self.status(m.compute_changes(have, h, (2, 1, 284), False), "env-flag"), ["ok"])

    def test_entries_added_and_never_flipped(self):
        m = load_module()
        h = str(self.home)
        ch = m.compute_changes({}, h, (2, 1, 290), False)
        self.assertEqual(self.status(ch, "marketplace"), ["pending"])
        self.assertEqual(self.status(ch, "enabled-plugin"), ["pending"])
        present = {"extraKnownMarketplaces": {"forgeloop": {"source": {"source": "github", "repo": "yhadad-dn/forgeloop"}}},
                   "enabledPlugins": {"forgeloop@forgeloop": True}}
        ch = m.compute_changes(present, h, (2, 1, 290), False)
        self.assertEqual(self.status(ch, "marketplace"), ["ok"])
        self.assertEqual(self.status(ch, "enabled-plugin"), ["ok"])
        off = {"enabledPlugins": {"forgeloop@forgeloop": False}}
        ch = m.compute_changes(off, h, (2, 1, 290), False)
        self.assertEqual(self.status(ch, "enabled-plugin"), ["blocked"])
        self.assertIn("false", m.render_diff(ch))
        self.settings.write_text(json.dumps(off))
        self.assertEqual(self.cli("apply", version="2.1.290").returncode, 0)
        self.assertIs(json.loads(self.settings.read_text())["enabledPlugins"]["forgeloop@forgeloop"], False)

    def test_apply_backup_merge_idempotent(self):
        original = {"zeta": 1, "env": {"KEEP": "x"}, "alpha": {"deep": [1, 2]}}
        self.settings.write_text(json.dumps(original, indent=2))
        p = self.cli("apply")
        self.assertEqual(p.returncode, 0, p.stderr)
        backups = list(self.settings.parent.glob("settings.json.forgeloop-bak-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(json.loads(backups[0].read_text()), original)
        merged = json.loads(self.settings.read_text())
        self.assertEqual(list(merged)[:3], ["zeta", "env", "alpha"])
        self.assertEqual(merged["env"], {"KEEP": "x", "CLAUDE_CODE_ENABLE_FUNCTION_HOOKS": "1"})
        self.assertEqual(merged["alpha"], {"deep": [1, 2]})
        self.assertTrue(merged["enabledPlugins"]["forgeloop@forgeloop"])
        src = merged["extraKnownMarketplaces"]["forgeloop"]["source"]
        self.assertEqual(src, {"source": "github", "repo": "yhadad-dn/forgeloop"})
        before = self.settings.read_bytes()
        p2 = self.cli("apply")
        self.assertEqual(p2.returncode, 0, p2.stderr)
        self.assertEqual(self.settings.read_bytes(), before)
        self.assertEqual(len(list(self.settings.parent.glob("settings.json.forgeloop-bak-*"))), 1)
        self.assertEqual(self.cli("--check").returncode, 0)

    def test_malformed_settings_untouched(self):
        bad = '{\n  // comment\n  "a": 1,\n}\n'
        self.settings.write_text(bad)
        for args in (["apply"], ["plan"], ["--check"]):
            p = self.cli(*args)
            self.assertEqual(p.returncode, 2, args)
            self.assertIn("enabledPlugins", p.stdout + p.stderr)
            self.assertEqual(self.settings.read_text(), bad)
        self.assertEqual(list(self.settings.parent.glob("*bak*")), [])
        self.assertFalse((self.home / ".claude" / "forgeloop").exists())

    def test_check_exit_codes_and_no_writes(self):
        self.settings.write_text("{}")
        p = self.cli("--check")
        self.assertEqual(p.returncode, 1)
        self.assertRegex(p.stdout, r"(?m)^pending\b.*env-flag|env-flag.*pending")
        self.assertEqual(self.settings.read_text(), "{}")
        self.assertEqual(sorted(x.name for x in self.settings.parent.iterdir()), ["settings.json"])
        self.cli("apply")
        self.assertEqual(self.cli("--check").returncode, 0)
        unknown = self.cli("--check", version=None)  # real detection may fail; unknown is not pending
        self.assertIn(unknown.returncode, (0, 1))

    def test_ste_only_on_flag_and_team_snippet(self):
        style = self.home / ".claude" / "forgeloop" / "style"
        self.cli("apply")
        self.assertFalse(style.exists())
        self.assertEqual(self.cli("--check", "--ste").returncode, 1)
        self.assertFalse(style.exists())
        self.assertEqual(self.cli("apply", "--ste").returncode, 0)
        self.assertEqual(style.read_text().strip(), "ste")
        self.assertEqual(self.cli("--check", "--ste").returncode, 0)
        before = sorted(str(p) for p in self.home.rglob("*"))
        p = self.cli("--team-snippet")
        self.assertEqual(p.returncode, 0, p.stderr)
        snip = json.loads(p.stdout)
        self.assertEqual(snip["enabledPlugins"], {"forgeloop@forgeloop": True})
        self.assertEqual(snip["extraKnownMarketplaces"]["forgeloop"]["source"]["repo"], "yhadad-dn/forgeloop")
        self.assertEqual(before, sorted(str(p) for p in self.home.rglob("*")))

    def test_other_marketplace_install_not_duplicated(self):
        m = load_module()
        h = str(self.home)
        ch = m.compute_changes({"enabledPlugins": {"forgeloop@gpu-team": True}}, h, (2, 1, 290), False)
        self.assertEqual(self.status(ch, "enabled-plugin"), ["ok"])
        self.assertEqual(self.status(ch, "marketplace"), ["ok"])
        self.settings.write_text(json.dumps({"enabledPlugins": {"forgeloop@gpu-team": True}}))
        before = self.settings.read_text()
        self.assertEqual(self.cli("--check", version="2.1.290").returncode, 0)
        self.assertEqual(self.cli("apply", version="2.1.290").returncode, 0)
        self.assertEqual(self.settings.read_text(), before)
        self.assertEqual([p.name for p in self.settings.parent.iterdir()], ["settings.json"])
        # a false under another key does not count as installed
        ch = m.compute_changes({"enabledPlugins": {"forgeloop@gpu-team": False}}, h, (2, 1, 290), False)
        self.assertEqual(self.status(ch, "enabled-plugin"), ["pending"])
        # explicit false on the exact key stays blocked
        ch = m.compute_changes({"enabledPlugins": {"forgeloop@forgeloop": False}}, h, (2, 1, 290), False)
        self.assertEqual(self.status(ch, "enabled-plugin"), ["blocked"])
        ch = m.compute_changes({"enabledPlugins": "x"}, h, (2, 1, 290), False)
        self.assertEqual(self.status(ch, "enabled-plugin"), ["blocked"])

    def test_symlinked_settings_survive_apply(self):
        real_dir = Path(self.tmp.name) / "dotfiles"
        real_dir.mkdir()
        target = real_dir / "settings.json"
        target.write_text(json.dumps({"theme": "dark"}))
        self.settings.symlink_to(target)
        r = self.cli("apply", version="2.1.290")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.settings.is_symlink())
        data = json.loads(target.read_text())
        self.assertEqual(data["theme"], "dark")
        self.assertTrue(data["enabledPlugins"]["forgeloop@forgeloop"])
        self.assertEqual(len(list(real_dir.glob("settings.json.forgeloop-bak-*"))), 1)
        self.assertEqual(list(self.settings.parent.glob("*.forgeloop-bak-*")), [])

    def test_skill_contract(self):
        text = SKILL.read_text()
        self.assertRegex(text, r"(?m)^name: setup$")
        for word in ("plan", "apply", "--check"):
            self.assertIn(word, text)
        self.assertRegex(text.lower(), r"approv")
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/skills/setup/forgeloop_setup.py", text)
        self.assertNotIn(":-.claude", text)
        self.assertIn("~/.claude/plugins/cache/forgeloop/forgeloop/<version>/skills/setup/forgeloop_setup.py", text)
        self.assertRegex(text.lower(), r"empty")
        self.assertRegex(text.lower(), r"trust")
        self.assertRegex(text.lower(), r"never retr")
        self.assertRegex(text.lower(), r"denied")

    def test_docs_cover_setup_and_rollout(self):
        readme = (ROOT / "README.md").read_text()
        for needle in ("/forgeloop:setup", "FORGELOOP_SETUP_HINT", "extraKnownMarketplaces",
                       "enabledPlugins", "managed settings", "FORGELOOP_COST_BAND",
                       "FORGELOOP_COST_HEATMAP", "FORGELOOP_CONVENTIONS", "FORGELOOP_STYLE"):
            self.assertIn(needle, readme)
        self.assertIn("| Feature |", readme)
        install = (ROOT / "docs" / "installation.md").read_text()
        self.assertIn("/forgeloop:setup", install)
        self.assertIn("README.md", install)


if __name__ == "__main__":
    unittest.main()
