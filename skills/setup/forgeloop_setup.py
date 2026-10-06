#!/usr/bin/env python3
"""ForgeLoop setup: show, check and apply the few user-scope settings ForgeLoop can use.

Commands: plan (print the exact diff), apply (back up, then write), --check (print one
line per item; exit 1 when something is pending), --team-snippet (print the JSON for a
repo's .claude/settings.json). Writes user scope only: ~/.claude/settings.json and
~/.claude/forgeloop/style. Python 3 standard library only.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

FLAG = "CLAUDE_CODE_ENABLE_FUNCTION_HOOKS"
MIN_MODS_DEFAULT_ON = (2, 1, 287)
MARKETPLACE = "forgeloop"
PLUGIN_KEY = "forgeloop@forgeloop"
REPO = "yhadad-dn/forgeloop"
MARKETPLACE_ENTRY = {"source": {"source": "github", "repo": REPO}}


@dataclass(frozen=True)
class Change:
    item: str          # "env-flag" | "ste-style" | "marketplace" | "enabled-plugin"
    target: str        # settings key path or file path
    before: object
    after: object
    reason: str
    status: str        # "pending" | "ok" | "unknown" | "blocked"


def parse_version(text):
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(x) for x in m.groups()) if m else None


def detect_cli_version(timeout=2.0):
    try:
        p = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=timeout)
        return parse_version(p.stdout) if p.returncode == 0 else None
    except Exception:
        return None


def load_settings(path):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}, None
    except OSError as e:
        return None, str(e)
    try:
        data = json.loads(text) if text.strip() else {}
    except ValueError as e:
        return None, str(e)
    if not isinstance(data, dict):
        return None, "top level is not a JSON object"
    return data, None


def style_path(home):
    return Path(home) / ".claude" / "forgeloop" / "style"


def compute_changes(settings, home, cli_version, want_ste):
    changes = []
    env = settings.get("env")
    target = f"env.{FLAG}"
    if env is not None and not isinstance(env, dict):
        changes.append(Change("env-flag", target, env, "1", "settings 'env' is not an object; left alone", "blocked"))
    elif env is not None and FLAG in env:
        changes.append(Change("env-flag", target, env[FLAG], env[FLAG], "already set", "ok"))
    elif cli_version is None:
        changes.append(Change("env-flag", target, None, None,
                              "CLI version unknown; the cost band needs the flag on a CLI older than 2.1.287", "unknown"))
    elif cli_version >= MIN_MODS_DEFAULT_ON:
        changes.append(Change("env-flag", target, None, None, "CLI 2.1.287 or later loads the cost band without it", "ok"))
    else:
        changes.append(Change("env-flag", target, None, "1",
                              "CLI older than 2.1.287 needs it to load the cost band", "pending"))

    sp = style_path(home)
    current = sp.read_text(encoding="utf-8").splitlines()[:1] if sp.exists() else []
    has_ste = bool(current) and current[0].strip().lower() == "ste"
    if has_ste:
        changes.append(Change("ste-style", str(sp), "ste", "ste", "already set", "ok"))
    elif want_ste:
        changes.append(Change("ste-style", str(sp), current[0] if current else None, "ste",
                              "you asked for the ASD-STE100 answer style", "pending"))
    else:
        changes.append(Change("ste-style", str(sp), None, None, "optional; not requested (use --ste)", "ok"))

    mk = settings.get("extraKnownMarketplaces")
    ep = settings.get("enabledPlugins")
    other = isinstance(ep, dict) and any(
        isinstance(k, str) and k.startswith("forgeloop@") and v for k, v in ep.items())
    if other:
        reason = "installed via another marketplace; not duplicated"
        changes.append(Change("marketplace", "extraKnownMarketplaces.forgeloop", None, None, reason, "ok"))
        changes.append(Change("enabled-plugin", f"enabledPlugins[{PLUGIN_KEY}]", None, None, reason, "ok"))
        return changes
    if mk is not None and not isinstance(mk, dict):
        changes.append(Change("marketplace", "extraKnownMarketplaces.forgeloop", mk, None,
                              "'extraKnownMarketplaces' is not an object; left alone", "blocked"))
    elif mk is not None and MARKETPLACE in mk:
        changes.append(Change("marketplace", "extraKnownMarketplaces.forgeloop", mk[MARKETPLACE], mk[MARKETPLACE],
                              "already present; not edited", "ok"))
    else:
        changes.append(Change("marketplace", "extraKnownMarketplaces.forgeloop", None, MARKETPLACE_ENTRY,
                              "lets Claude Code find the ForgeLoop marketplace", "pending"))

    key = f"enabledPlugins[{PLUGIN_KEY}]"
    if ep is not None and not isinstance(ep, dict):
        changes.append(Change("enabled-plugin", key, ep, None, "'enabledPlugins' is not an object; left alone", "blocked"))
    elif ep is not None and PLUGIN_KEY in ep:
        if ep[PLUGIN_KEY] is False:
            changes.append(Change("enabled-plugin", key, False, False,
                                  "set to false by you; left as false (change it yourself to enable)", "blocked"))
        else:
            changes.append(Change("enabled-plugin", key, ep[PLUGIN_KEY], ep[PLUGIN_KEY], "already present", "ok"))
    else:
        changes.append(Change("enabled-plugin", key, None, True, "turns the plugin on", "pending"))
    return changes


def render_diff(changes):
    out = []
    for c in changes:
        out.append(f"{c.status:8} {c.item:14} {c.target}")
        if c.status == "pending":
            out.append(f"         - {json.dumps(c.before)}" if c.before is not None else "         - (absent)")
            out.append(f"         + {json.dumps(c.after)}")
        out.append(f"         {c.reason}")
    pending = sum(c.status == "pending" for c in changes)
    out.append(f"{pending} change(s) pending.")
    return "\n".join(out)


def team_snippet():
    return json.dumps({"extraKnownMarketplaces": {MARKETPLACE: MARKETPLACE_ENTRY},
                       "enabledPlugins": {PLUGIN_KEY: True}}, indent=2)


def _atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        if path.exists():
            os.chmod(tmp, path.stat().st_mode & 0o777)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def apply_changes(settings_path, home, changes):
    pending = [c for c in changes if c.status == "pending"]
    if not pending:
        return ""
    backup = ""
    settings_items = [c for c in pending if c.item != "ste-style"]
    if settings_items:
        settings, err = load_settings(settings_path)
        if settings is None:
            raise ValueError(err)
        sp = Path(os.path.realpath(settings_path))
        if sp.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = str(sp.with_name(f"{sp.name}.forgeloop-bak-{stamp}"))
            _atomic_write(backup, sp.read_text(encoding="utf-8"))
        for c in settings_items:
            if c.item == "env-flag":
                settings.setdefault("env", {})[FLAG] = c.after
            elif c.item == "marketplace":
                settings.setdefault("extraKnownMarketplaces", {})[MARKETPLACE] = c.after
            elif c.item == "enabled-plugin":
                settings.setdefault("enabledPlugins", {})[PLUGIN_KEY] = c.after
        _atomic_write(sp, json.dumps(settings, indent=2) + "\n")
    for c in pending:
        if c.item == "ste-style":
            _atomic_write(c.target, "ste\n")
    return backup


def manual_lines():
    return ("Your settings file is not strict JSON, so nothing was changed. Add these keys by hand:\n"
            + team_snippet() + f'\nAnd, only on a Claude Code older than 2.1.287, under "env": "{FLAG}": "1"')


def main(argv):
    ap = argparse.ArgumentParser(prog="forgeloop_setup.py", description=__doc__.splitlines()[0])
    ap.add_argument("command", nargs="?", choices=["plan", "apply"], default="plan")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--team-snippet", action="store_true")
    ap.add_argument("--ste", action="store_true")
    ap.add_argument("--settings")
    ap.add_argument("--home")
    ap.add_argument("--cli-version")
    args = ap.parse_args(argv)

    if args.team_snippet:
        print(team_snippet())
        return 0
    home = args.home or str(Path.home())
    settings_path = args.settings or str(Path(home) / ".claude" / "settings.json")
    settings, err = load_settings(settings_path)
    if settings is None:
        print(f"error: cannot parse {settings_path}: {err}")
        print(manual_lines())
        return 2
    cli = parse_version(args.cli_version) if args.cli_version else detect_cli_version()
    changes = compute_changes(settings, home, cli, args.ste)

    if args.check:
        for c in changes:
            print(f"{c.status} {c.item}: {c.reason}")
        return 1 if any(c.status == "pending" for c in changes) else 0
    print(render_diff(changes))
    if args.command == "apply":
        try:
            backup = apply_changes(settings_path, home, changes)
        except (OSError, ValueError) as e:
            print(f"error: {e}")
            return 2
        print(f"backup: {backup}" if backup else "nothing written to settings.json" if not
              any(c.status == "pending" for c in changes) else "applied (no existing settings file to back up)")
    else:
        print("\nTeam snippet for a repo's .claude/settings.json (printed only):")
        print(team_snippet())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
