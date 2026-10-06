#!/usr/bin/env python3
"""ForgeLoop setup: show, check and apply the few user-scope settings ForgeLoop can use.

Commands: plan (print the exact diff), apply (back up, then write), --check (print one
line per item; exit 1 when something is pending), --team-snippet (print the JSON for a
repo's .claude/settings.json). Writes user scope only: ~/.claude/settings.json and
~/.claude/forgeloop/style. With the opt-in --durable it also writes two more locations:
the VS Code remote machine settings file (~/.vscode-server/data/Machine/settings.json,
key claudeCode.claudeProcessWrapper, only when absent) and the copies
~/.claude/forgeloop/vscode-wrapper.sh and ~/.claude/forgeloop/forgeloop_tmux.py. Never
project or managed settings. Each existing file written is backed up first.
Python 3 standard library only.
"""

import argparse
import json
import os
import re
import shutil
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
WRAPPER_KEY = "claudeCode.claudeProcessWrapper"
PLUGIN_ROOT = Path(__file__).resolve().parents[2]
DURABLE_COPIES = (  # (source relative to plugin root, name under ~/.claude/forgeloop/, mode)
    ("scripts/forgeloop-vscode-wrapper.sh", "vscode-wrapper.sh", 0o755),
    ("skills/tmux-session/forgeloop_tmux.py", "forgeloop_tmux.py", 0o644),
)
MARKETPLACE_ENTRY = {"source": {"source": "github", "repo": REPO}}


@dataclass(frozen=True)
class Change:
    item: str          # "env-flag" | "ste-style" | "marketplace" | "enabled-plugin"
                       # | "durable-wrapper" | "durable-setting"
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


def machine_settings_path(home):
    return Path(home) / ".vscode-server" / "data" / "Machine" / "settings.json"


def wrapper_path(home):
    return Path(home) / ".claude" / "forgeloop" / "vscode-wrapper.sh"


def durable_manual_line(home):
    return (f'Add this line by hand to {machine_settings_path(home)}:\n'
            f'  "{WRAPPER_KEY}": "{wrapper_path(home)}"')


def _copy_dest(home, name):
    return Path(home) / ".claude" / "forgeloop" / name


def _stale_copies(home):
    """Return (stale destination list, missing source list)."""
    stale, missing = [], []
    for rel, name, _mode in DURABLE_COPIES:
        src = PLUGIN_ROOT / rel
        dst = _copy_dest(home, name)
        if not src.is_file():
            missing.append(str(src))
        elif not dst.is_file() or dst.read_bytes() != src.read_bytes():
            stale.append(str(dst))
    return stale, missing


def _ensure_private_dir(home):
    d = Path(home) / ".claude" / "forgeloop"
    created = not d.exists()
    d.mkdir(parents=True, exist_ok=True)
    if created:
        os.chmod(d, 0o700)
    return d


def _perm_warning(home):
    """Return a warning when the forgeloop dir or a copy in it is writable by others or not ours."""
    d = Path(home) / ".claude" / "forgeloop"
    bad = []
    for p in [d] + [_copy_dest(home, n) for _r, n, _m in DURABLE_COPIES]:
        try:
            st = p.stat()
        except OSError:
            continue
        if st.st_mode & 0o022 or st.st_uid != os.getuid():
            bad.append(str(p))
    if not bad:
        return ""
    return ("; WARNING: group/world-writable or not owned by you: " + ", ".join(bad)
            + " (the wrapper runs as you; fix with chmod go-w and check the owner)")


def durable_changes(home):
    changes = []
    wp = str(wrapper_path(home))
    stale, missing = _stale_copies(home)
    warn = _perm_warning(home)
    if missing:
        changes.append(Change("durable-wrapper", wp, None, None,
                              "plugin source file missing: " + ", ".join(missing)
                              + " (durable sessions need the plugin install; scripts/install.sh does not ship scripts/)"
                              + warn, "unknown"))
    elif stale:
        changes.append(Change("durable-wrapper", wp, None, "copy",
                              "copies the wrapper and its helper to ~/.claude/forgeloop/ (new or changed)" + warn, "pending"))
    else:
        changes.append(Change("durable-wrapper", wp, "copy", "copy", "already up to date" + warn, "ok"))

    mp = machine_settings_path(home)
    data, err = load_settings(mp)
    if missing:
        changes.append(Change("durable-setting", str(mp), None, None,
                              "wrapper source missing (durable sessions need the plugin install, "
                              "not scripts/install.sh); not set. " + durable_manual_line(home), "unknown"))
    elif data is None:
        changes.append(Change("durable-setting", str(mp), None, None,
                              f"{mp} is not strict JSON ({err}); skipped, nothing changed. "
                              + durable_manual_line(home), "unknown"))
    elif WRAPPER_KEY not in data:
        changes.append(Change("durable-setting", f"{mp}:{WRAPPER_KEY}", None, wp,
                              "makes VS Code start Claude sessions through the wrapper", "pending"))
    elif data[WRAPPER_KEY] == wp:
        changes.append(Change("durable-setting", f"{mp}:{WRAPPER_KEY}", wp, wp, "already set", "ok"))
    else:
        changes.append(Change("durable-setting", f"{mp}:{WRAPPER_KEY}", data[WRAPPER_KEY], data[WRAPPER_KEY],
                              "set to a different value; left alone (change it yourself to use ForgeLoop's wrapper)",
                              "unknown"))
    return changes


def compute_changes(settings, home, cli_version, want_ste, want_durable=False):
    changes = _user_changes(settings, home, cli_version, want_ste)
    if want_durable:
        changes += durable_changes(home)
    return changes


def _user_changes(settings, home, cli_version, want_ste):
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
        out.append(f"{c.status:8} {c.item:15} {c.target}")
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


def _backup(path):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = path.with_name(f"{path.name}.forgeloop-bak-{stamp}")
    shutil.copy2(path, bak)
    return str(bak)


def _apply_durable(home, pending, backups):
    for c in pending:
        if c.item == "durable-wrapper":
            for rel, name, mode in DURABLE_COPIES:
                src = PLUGIN_ROOT / rel
                dst = _copy_dest(home, name)
                if dst.is_file() and dst.read_bytes() == src.read_bytes():
                    continue
                _ensure_private_dir(home)
                if dst.exists():
                    backups.append(_backup(dst))
                fd, tmp = tempfile.mkstemp(dir=str(dst.parent), prefix=dst.name + ".tmp")
                try:
                    with os.fdopen(fd, "wb") as f:
                        f.write(src.read_bytes())
                    os.chmod(tmp, mode)
                    os.replace(tmp, dst)
                except BaseException:
                    if os.path.exists(tmp):
                        os.unlink(tmp)
                    raise
        elif c.item == "durable-setting":
            mp = Path(os.path.realpath(machine_settings_path(home)))
            data, err = load_settings(mp)
            if data is None:
                raise ValueError(err)
            if mp.exists():
                backups.append(_backup(mp))
            data[WRAPPER_KEY] = c.after
            _atomic_write(mp, json.dumps(data, indent=2) + "\n")


def apply_changes(settings_path, home, changes):
    pending = [c for c in changes if c.status == "pending"]
    if not pending:
        return ""
    backups = []
    settings_items = [c for c in pending if c.item in ("env-flag", "marketplace", "enabled-plugin")]
    if settings_items:
        settings, err = load_settings(settings_path)
        if settings is None:
            raise ValueError(err)
        sp = Path(os.path.realpath(settings_path))
        if sp.exists():
            backups.append(_backup(sp))
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
            _ensure_private_dir(home)
            _atomic_write(c.target, "ste\n")
    _apply_durable(home, pending, backups)
    return ", ".join(backups)


def manual_lines():
    return ("Your settings file is not strict JSON, so nothing was changed. Add these keys by hand:\n"
            + team_snippet() + f'\nAnd, only on a Claude Code older than 2.1.287, under "env": "{FLAG}": "1"')


def main(argv):
    ap = argparse.ArgumentParser(prog="forgeloop_setup.py", description=__doc__.splitlines()[0])
    ap.add_argument("command", nargs="?", choices=["plan", "apply"], default="plan")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--team-snippet", action="store_true")
    ap.add_argument("--ste", action="store_true")
    ap.add_argument("--durable", action="store_true")
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
    broken = settings is None
    if broken:
        print(f"error: cannot parse {settings_path}: {err}")
        print(manual_lines())
        if not args.durable:
            return 2
        settings = {}
    cli = parse_version(args.cli_version) if args.cli_version else detect_cli_version()
    if broken:  # only the machine-file items may proceed; user-settings items change nothing
        changes = durable_changes(home)
    else:
        changes = compute_changes(settings, home, cli, args.ste, args.durable)

    if args.check:
        for c in changes:
            print(f"{c.status} {c.item}: {c.reason}")
        return 2 if broken else 1 if any(c.status == "pending" for c in changes) else 0
    print(render_diff(changes))
    if args.command == "apply":
        try:
            backup = apply_changes(settings_path, home, changes)
        except (OSError, ValueError) as e:
            print(f"error: {e}")
            return 2
        if broken:
            print(f"backup: {backup}" if backup else "durable items already up to date")
            return 2
        print(f"backup: {backup}" if backup else "nothing written to settings.json" if not
              any(c.status == "pending" for c in changes) else "applied (no existing settings file to back up)")
    else:
        print("\nTeam snippet for a repo's .claude/settings.json (printed only):")
        print(team_snippet())
    return 2 if broken else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
