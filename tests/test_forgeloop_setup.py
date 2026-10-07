"""Tests for skills/setup/forgeloop_setup.py (scratch HOME only; never the real one)."""

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def cli(self, *args, version="2.1.284", env=None):
        cmd = [sys.executable, str(SCRIPT), *args, "--settings", str(self.settings),
               "--home", str(self.home)]
        if version:
            cmd += ["--cli-version", version]
        full = {k: v for k, v in os.environ.items()
                if k not in ("SSH_CONNECTION", "REMOTE_CONTAINERS", "CODESPACES", "WSL_DISTRO_NAME")}
        full.update(env or {})
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20, env=full)

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
        self.assertEqual(merged["permissions"]["allow"], [load_module().session_rule(ROOT)])
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

    def test_ste_default_on_and_flag_pins_it(self):
        style = self.home / ".claude" / "forgeloop" / "style"
        self.cli("apply")
        self.assertFalse(style.exists())                 # default on: nothing to write
        p = self.cli("plan")
        self.assertRegex(p.stdout, r"(?s)ste-style[^\n]*\n\s*on by default")
        self.assertNotIn("not requested", p.stdout)
        self.assertEqual(self.cli("--check").returncode, 0)
        self.assertEqual(self.cli("--check", "--ste").returncode, 1)   # --ste still pins the file
        self.assertFalse(style.exists())
        self.assertEqual(self.cli("apply", "--ste").returncode, 0)
        self.assertEqual(style.read_text().strip(), "ste")
        self.assertEqual(self.cli("--check", "--ste").returncode, 0)   # idempotent
        self.assertEqual(self.cli("apply", "--ste").returncode, 0)
        self.assertEqual(style.read_text().strip(), "ste")
        style.write_text("off\n")
        self.assertEqual(self.cli("--check").returncode, 0)            # user's off is respected
        self.assertEqual(style.read_text().strip(), "off")
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
        # the session items are still reported on this early-return path
        self.assertEqual(self.status(ch, "session-allow-rule"), ["pending"])
        self.assertEqual(self.status(ch, "retire-session-hook"), ["ok"])
        self.settings.write_text(json.dumps({"enabledPlugins": {"forgeloop@gpu-team": True},
                                            "permissions": {"allow": [m.session_rule(m.PLUGIN_ROOT)]}}))
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
        self.assertIn(load_module().session_rule(ROOT), data["permissions"]["allow"])
        self.assertEqual(len(list(real_dir.glob("settings.json.forgeloop-bak-*"))), 1)
        self.assertEqual(list(self.settings.parent.glob("*.forgeloop-bak-*")), [])

    # ---- session picker items (allow rule, retire old hook) ----

    OLD_CMD = "python3 /home/u/.claude/hooks/session-continuity/session_start.py"

    def rule(self):
        m = load_module()
        return m.session_rule(m.PLUGIN_ROOT)

    def test_session_rule_pending_then_ok_after_apply(self):
        m = load_module()
        h = str(self.home)
        self.assertEqual(m.session_rule(Path("/x/y")), "Bash(python3 /x/y/hooks/session_state.py:*)")
        ch = m.compute_changes({}, h, (2, 1, 290), False)
        c = [c for c in ch if c.item == "session-allow-rule"][0]
        self.assertEqual((c.status, c.after, c.target), ("pending", self.rule(), "permissions.allow"))
        self.settings.write_text(json.dumps({"permissions": {"allow": ["Bash(ls:*)"], "deny": ["x"]}}))
        self.assertEqual(self.cli("apply", version="2.1.290").returncode, 0)
        data = json.loads(self.settings.read_text())
        self.assertEqual(data["permissions"], {"allow": ["Bash(ls:*)", self.rule()], "deny": ["x"]})
        ch = m.compute_changes(data, h, (2, 1, 290), False)
        self.assertEqual(self.status(ch, "session-allow-rule"), ["ok"])

    def test_session_rule_blocked_on_wrong_type_or_space_in_root(self):
        m = load_module()
        h = str(self.home)
        for bad in ({"permissions": "x"}, {"permissions": {"allow": "x"}}, {"permissions": []},
                    {"permissions": {"allow": None}}, {"permissions": {"allow": {}}}):
            ch = m.compute_changes(bad, h, (2, 1, 290), False)
            self.assertEqual(self.status(ch, "session-allow-rule"), ["blocked"], bad)
            self.settings.write_text(json.dumps(bad))
            self.assertEqual(self.cli("apply", version="2.1.290").returncode, 0)
            self.assertEqual(json.loads(self.settings.read_text()).get("permissions"), bad["permissions"])
        with mock.patch.object(m, "PLUGIN_ROOT", Path("/with space/plugin")):
            ch = m.compute_changes({}, h, (2, 1, 290), False)
            self.assertEqual(self.status(ch, "session-allow-rule"), ["blocked"])
            m.apply_changes(str(self.settings), h, ch)
        self.assertNotIn("with space", self.settings.read_text())

    def test_retire_old_hook_removes_only_old_command(self):
        m = load_module()
        h = str(self.home)
        keep = {"type": "command", "command": "python3 /plugin/hooks/session_start.py"}
        other_group = {"matcher": "startup", "hooks": [keep]}
        mixed = {"hooks": [{"type": "command", "command": self.OLD_CMD}, keep]}
        only_old = {"hooks": [{"type": "command", "command": self.OLD_CMD}]}
        settings = {"hooks": {"SessionStart": [other_group, mixed, only_old], "Stop": [{"hooks": []}]},
                    "permissions": {"allow": [self.rule()]}}
        ch = m.compute_changes(settings, h, (2, 1, 290), False)
        c = [c for c in ch if c.item == "retire-session-hook"][0]
        self.assertEqual((c.status, c.target), ("pending", "hooks.SessionStart"))
        self.assertEqual(c.after, [other_group, {"hooks": [keep]}])
        self.settings.write_text(json.dumps(settings))
        self.assertEqual(self.cli("apply", version="2.1.290").returncode, 0)
        data = json.loads(self.settings.read_text())
        self.assertEqual(data["hooks"]["SessionStart"], [other_group, {"hooks": [keep]}])
        self.assertEqual(data["hooks"]["Stop"], [{"hooks": []}])
        # removing the last entry deletes the key
        self.settings.write_text(json.dumps({"hooks": {"SessionStart": [only_old], "Stop": []},
                                             "permissions": {"allow": [self.rule()]}}))
        self.cli("apply", version="2.1.290")
        self.assertEqual(json.loads(self.settings.read_text())["hooks"], {"Stop": []})
        ch = m.compute_changes(json.loads(self.settings.read_text()), h, (2, 1, 290), False)
        self.assertEqual(self.status(ch, "retire-session-hook"), ["ok"])

    def test_apply_is_idempotent_and_writes_backup(self):
        original = {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": self.OLD_CMD}]}]},
                    "enabledPlugins": {"forgeloop@forgeloop": True},
                    "extraKnownMarketplaces": {"forgeloop": {}}}
        self.settings.write_text(json.dumps(original))
        p = self.cli("apply", version="2.1.290")
        self.assertEqual(p.returncode, 0, p.stderr)
        baks = list(self.settings.parent.glob("settings.json.forgeloop-bak-*"))
        self.assertEqual(len(baks), 1)
        self.assertEqual(json.loads(baks[0].read_text()), original)
        data = json.loads(self.settings.read_text())
        self.assertNotIn("SessionStart", data["hooks"])
        self.assertEqual(data["permissions"]["allow"], [self.rule()])
        before = self.settings.read_bytes()
        p2 = self.cli("apply", version="2.1.290")
        self.assertEqual(p2.returncode, 0, p2.stderr)
        self.assertEqual(self.settings.read_bytes(), before)
        self.assertEqual(len(list(self.settings.parent.glob("settings.json.forgeloop-bak-*"))), 1)

    def test_check_exits_1_when_session_items_pending(self):
        self.settings.write_text(json.dumps({
            "enabledPlugins": {"forgeloop@forgeloop": True},
            "extraKnownMarketplaces": {"forgeloop": {}},
            "env": {"CLAUDE_CODE_ENABLE_FUNCTION_HOOKS": "1"}}))
        p = self.cli("--check", version="2.1.290")
        self.assertEqual(p.returncode, 1)
        self.assertIn("pending session-allow-rule", p.stdout)
        self.settings.write_text(json.dumps({
            "enabledPlugins": {"forgeloop@forgeloop": True},
            "extraKnownMarketplaces": {"forgeloop": {}},
            "permissions": {"allow": [self.rule()]},
            "hooks": {"SessionStart": [{"hooks": [{"command": self.OLD_CMD}]}]}}))
        p = self.cli("--check", version="2.1.290")
        self.assertEqual(p.returncode, 1)
        self.assertIn("pending retire-session-hook", p.stdout)
        self.assertEqual(self.cli("plan", version="2.1.290").stdout.count("session-allow-rule"), 1)

    def test_session_items_present_on_other_marketplace_path(self):
        m = load_module()
        settings = {"enabledPlugins": {"forgeloop@gpu-team": True},
                    "hooks": {"SessionStart": [{"hooks": [{"command": self.OLD_CMD}]}]}}
        ch = m.compute_changes(settings, str(self.home), (2, 1, 290), False)
        self.assertEqual(self.status(ch, "session-allow-rule"), ["pending"])
        self.assertEqual(self.status(ch, "retire-session-hook"), ["pending"])
        self.assertEqual(self.status(ch, "marketplace"), ["ok"])

    def test_retire_blocked_on_malformed_hooks(self):
        m = load_module()
        h = str(self.home)
        cases = [{"hooks": "x"}, {"hooks": {"SessionStart": "x"}}, {"hooks": {"SessionStart": ["x"]}},
                 {"hooks": {"SessionStart": [{"hooks": "x"}]}},
                 {"hooks": {"SessionStart": [{"hooks": ["x", {"command": self.OLD_CMD}]}]}}]
        for bad in cases:
            bad["permissions"] = {"allow": [self.rule()]}
            ch = m.compute_changes(bad, h, (2, 1, 290), False)
            self.assertEqual(self.status(ch, "retire-session-hook"), ["blocked"], bad)
            self.settings.write_text(json.dumps(bad))
            before = self.settings.read_bytes()
            self.assertEqual(self.cli("apply", version="2.1.290").returncode, 0)
            data = json.loads(self.settings.read_text())
            self.assertEqual(data["hooks"], bad["hooks"])
            self.settings.write_bytes(before)

    def test_apply_raises_on_unknown_item(self):
        m = load_module()
        self.settings.write_text("{}")
        bad = m.Change("bogus-item", "t", None, None, "r", "pending")
        with self.assertRaises(ValueError):
            m.apply_changes(str(self.settings), str(self.home), [bad])
        self.assertEqual(self.settings.read_text(), "{}")
        self.assertEqual(list(self.settings.parent.glob("*bak*")), [])

    def test_updated_existing_tests_still_cover_hint_and_check(self):
        # render_diff keeps columns aligned with the longest item name
        m = load_module()
        ch = m.compute_changes({}, str(self.home), (2, 1, 290), False)
        out = m.render_diff(ch)
        self.assertRegex(out, r"(?m)^pending  retire-session-hook|^ok       retire-session-hook")
        self.assertRegex(out, r"(?m)^pending  session-allow-rule {3}permissions\.allow")

    def test_skill_contract(self):
        text = SKILL.read_text()
        self.assertRegex(text, r"(?m)^name: setup$")
        for word in ("plan", "apply", "--check", "session-allow-rule", "retire-session-hook"):
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


class DurableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        (self.home / ".claude").mkdir(parents=True)
        self.settings = self.home / ".claude" / "settings.json"
        self.machine = self.home / ".vscode-server" / "data" / "Machine" / "settings.json"
        self.wrapper = self.home / ".claude" / "forgeloop" / "vscode-wrapper.sh"
        self.helper = self.home / ".claude" / "forgeloop" / "forgeloop_tmux.py"

    def tearDown(self):
        self.tmp.cleanup()

    cli = SetupTests.cli
    status = SetupTests.status

    def key(self):
        return json.loads(self.machine.read_text()).get("claudeCode.claudeProcessWrapper")

    def test_durable_plan_apply_idempotent(self):
        m = load_module()
        self.machine.parent.mkdir(parents=True)
        self.machine.write_text(json.dumps({"editor.fontSize": 12}))
        ch = m.compute_changes({}, str(self.home), (2, 1, 290), False, True)
        self.assertEqual(self.status(ch, "durable-wrapper"), ["pending"])
        self.assertEqual(self.status(ch, "durable-setting"), ["pending"])
        p = self.cli("plan", "--durable", version="2.1.290")
        self.assertIn("durable-setting", p.stdout)
        self.assertFalse(self.wrapper.exists())
        p = self.cli("apply", "--durable", version="2.1.290")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.key(), str(self.wrapper))
        self.assertEqual(json.loads(self.machine.read_text())["editor.fontSize"], 12)
        baks = list(self.machine.parent.glob("settings.json.forgeloop-bak-*"))
        self.assertEqual(len(baks), 1)
        self.assertEqual(json.loads(baks[0].read_text()), {"editor.fontSize": 12})
        self.assertEqual(self.wrapper.read_bytes(), (ROOT / "scripts" / "forgeloop-vscode-wrapper.sh").read_bytes())
        self.assertEqual(self.helper.read_bytes(), (ROOT / "skills" / "tmux-session" / "forgeloop_tmux.py").read_bytes())
        self.assertTrue(os.access(self.wrapper, os.X_OK))
        snap = {str(x): x.read_bytes() for x in self.home.rglob("*") if x.is_file()}
        p2 = self.cli("apply", "--durable", version="2.1.290")
        self.assertEqual(p2.returncode, 0, p2.stderr)
        self.assertEqual(snap, {str(x): x.read_bytes() for x in self.home.rglob("*") if x.is_file()})
        self.assertEqual(self.cli("--check", "--durable", version="2.1.290").returncode, 0)
        self.helper.write_text("stale")  # an upgrade refreshes the copy
        self.assertEqual(self.cli("--check", "--durable", version="2.1.290").returncode, 1)
        self.cli("apply", "--durable", version="2.1.290")
        self.assertEqual(self.helper.read_bytes(), (ROOT / "skills" / "tmux-session" / "forgeloop_tmux.py").read_bytes())

    def test_durable_jsonc_refused(self):
        self.machine.parent.mkdir(parents=True)
        bad = '{\n  // comment\n  "a": 1,\n}\n'
        self.machine.write_text(bad)
        p = self.cli("apply", "--durable", version="2.1.290")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('"claudeCode.claudeProcessWrapper": "%s"' % self.wrapper, p.stdout)
        self.assertIn(str(self.machine), p.stdout)
        self.assertEqual(self.machine.read_text(), bad)
        self.assertEqual(list(self.machine.parent.glob("*bak*")), [])
        self.assertTrue(json.loads(self.settings.read_text())["enabledPlugins"]["forgeloop@forgeloop"])
        c = self.cli("--check", "--durable", version="2.1.290")
        self.assertRegex(c.stdout, r"unknown durable-setting")

    def test_durable_missing_machine_file_created(self):
        self.assertFalse(self.machine.parent.exists())
        p = self.cli("apply", "--durable", version="2.1.290")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.key(), str(self.wrapper))

    def test_durable_existing_different_value_kept(self):
        self.machine.parent.mkdir(parents=True)
        self.machine.write_text(json.dumps({"claudeCode.claudeProcessWrapper": "/other/w.sh"}))
        before = self.machine.read_bytes()
        p = self.cli("apply", "--durable", version="2.1.290")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.machine.read_bytes(), before)
        self.assertRegex(self.cli("--check", "--durable", version="2.1.290").stdout, r"unknown durable-setting")

    def test_durable_not_planned_without_flag(self):
        m = load_module()
        ch = m.compute_changes({}, str(self.home), (2, 1, 290), False)
        self.assertFalse([c for c in ch if c.item.startswith("durable")])
        self.cli("apply", version="2.1.290")
        self.assertFalse((self.home / ".vscode-server").exists())
        self.assertFalse(self.wrapper.exists())
        self.assertNotIn("durable", self.cli("--check", version="2.1.290").stdout)

    def test_durable_broken_user_settings_does_not_block_machine_item(self):
        bad = '{ // c\n}'
        self.settings.write_text(bad)
        p = self.cli("apply", "--durable", version="2.1.290")
        self.assertEqual(p.returncode, 2)
        self.assertEqual(self.settings.read_text(), bad)
        self.assertEqual(self.key(), str(self.wrapper))
        self.assertTrue(self.wrapper.exists())


    def test_missing_plugin_source_makes_setting_unknown(self):
        m = load_module()
        empty = Path(self.tmp.name) / "plugin-no-scripts"
        empty.mkdir()
        with mock.patch.object(m, "PLUGIN_ROOT", empty):
            ch = m.durable_changes(str(self.home))
            self.assertEqual(self.status(ch, "durable-wrapper"), ["unknown"])
            self.assertEqual(self.status(ch, "durable-setting"), ["unknown"])
            setting = [c for c in ch if c.item == "durable-setting"][0]
            self.assertIn(m.WRAPPER_KEY, setting.reason)
            m.apply_changes(str(self.settings), str(self.home), ch)
        self.assertFalse(self.machine.exists())
        self.assertFalse(self.wrapper.exists())

    def test_forgeloop_dir_created_private(self):
        self.cli("apply", "--durable", version="2.1.290")
        d = self.home / ".claude" / "forgeloop"
        self.assertEqual(d.stat().st_mode & 0o777, 0o700)

    def test_group_writable_dir_warns_but_proceeds(self):
        d = self.home / ".claude" / "forgeloop"
        d.mkdir()
        os.chmod(d, 0o775)
        p = self.cli("plan", "--durable", version="2.1.290")
        self.assertIn("writable", p.stdout)
        self.assertEqual(self.status(load_module().durable_changes(str(self.home)), "durable-wrapper"), ["pending"])
        c = self.cli("--check", "--durable", version="2.1.290")
        self.assertIn("writable", c.stdout)


VM = {"SSH_CONNECTION": "1.2.3.4 5 6.7.8.9 22"}


class VmDefaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        (self.home / ".claude").mkdir(parents=True)
        self.settings = self.home / ".claude" / "settings.json"
        self.machine = self.home / ".vscode-server" / "data" / "Machine" / "settings.json"

    def tearDown(self):
        self.tmp.cleanup()

    cli = SetupTests.cli
    status = SetupTests.status

    def end_rule(self):
        return f"Bash(python3 {self.home}/.claude/forgeloop/forgeloop_tmux.py end-current)"

    def test_default_durable_classification(self):
        m = load_module()
        h = str(self.home)
        self.assertTrue(m.default_durable(h, VM))
        self.assertFalse(m.default_durable(h, {}))
        other = dict(VM, CODESPACES="true")
        self.assertFalse(m.default_durable(h, other))
        d = self.home / ".claude" / "forgeloop"
        d.mkdir()
        (d / "durable").write_text("yes\n")
        self.assertTrue(m.default_durable(h, other))
        (d / "durable").write_text("no\n")
        self.assertFalse(m.default_durable(h, other))

    def test_vm_plan_includes_durable_items_by_default(self):
        p = self.cli("plan", env=VM)
        self.assertIn("durable-wrapper", p.stdout)
        self.assertIn("durable-setting", p.stdout)
        self.assertIn("tmux-end-rule", p.stdout)
        self.assertEqual(self.cli("--check", env=VM).returncode, 1)

    def test_no_durable_skips_and_non_vm_unchanged(self):
        p = self.cli("plan", "--no-durable", env=VM)
        for item in ("durable-wrapper", "durable-setting", "tmux-end-rule"):
            self.assertNotIn(item, p.stdout)
        p = self.cli("plan")
        for item in ("durable-wrapper", "durable-setting", "tmux-end-rule"):
            self.assertNotIn(item, p.stdout)
        p = self.cli("plan", "--durable")
        self.assertIn("durable-wrapper", p.stdout)
        self.assertIn("tmux-end-rule", p.stdout)
        p = self.cli("plan", "--durable", "--no-durable", env=VM)
        self.assertIn("durable-wrapper", p.stdout)  # --durable forces on

    def test_vm_apply_writes_everything_idempotent(self):
        p = self.cli("apply", env=VM)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(self.machine.exists())
        self.assertIn(self.end_rule(), json.loads(self.settings.read_text())["permissions"]["allow"])
        self.assertEqual(self.cli("--check", env=VM).returncode, 0)
        snap = {str(x): x.read_bytes() for x in self.home.rglob("*") if x.is_file()}
        self.assertEqual(self.cli("apply", env=VM).returncode, 0)
        self.assertEqual(snap, {str(x): x.read_bytes() for x in self.home.rglob("*") if x.is_file()})

    def test_end_rule_states(self):
        m = load_module()
        h = str(self.home)
        rule = self.end_rule()
        c = [c for c in m.compute_changes({}, h, (2, 1, 290), False, True) if c.item == "tmux-end-rule"]
        self.assertEqual([(x.status, x.after, x.target) for x in c], [("pending", rule, "permissions.allow")])
        ok = {"permissions": {"allow": [rule]}}
        self.assertEqual(self.status(m.compute_changes(ok, h, (2, 1, 290), False, True), "tmux-end-rule"), ["ok"])
        for bad in ({"permissions": []}, {"permissions": {"allow": "x"}}):
            self.assertEqual(self.status(m.compute_changes(bad, h, (2, 1, 290), False, True), "tmux-end-rule"),
                             ["blocked"])
        spaced = str(self.home) + " x"
        self.assertEqual(self.status(m.compute_changes({}, spaced, (2, 1, 290), False, True), "tmux-end-rule"),
                         ["blocked"])
        self.assertEqual(self.status(m.compute_changes({}, h, (2, 1, 290), False, False), "tmux-end-rule"), [])

    def test_end_rule_unsafe_chars_blocked_and_reason(self):
        m = load_module()
        for bad in ("/home/u$x", "/home/u;x", "/home/u'x", "/home/u`x", "/home/u(x)"):
            self.assertEqual(self.status(m.compute_changes({}, bad, (2, 1, 290), False, True), "tmux-end-rule"),
                             ["blocked"], bad)
        c = [c for c in m.compute_changes({}, "/home/u", (2, 1, 290), False, True) if c.item == "tmux-end-rule"][0]
        self.assertEqual(c.status, "pending")
        self.assertIn("~/.claude/forgeloop/forgeloop_tmux.py", c.reason)
        self.assertIn("idle checkpoint", c.reason)
        self.assertIn("fl- tmux session", c.reason)
        self.assertIn("without a prompt", c.reason)


if __name__ == "__main__":
    unittest.main()
