#!/usr/bin/env python3
"""Give every installed plugin's Claude Code hooks at least FLOOR seconds before Claude Code gives up on them.

Why: many plugins ship 5 s hook timeouts. A hook that answers in under 2 s alone misses 5 s when several
sessions start at once (each starts its own MCP servers), and Claude Code then skips it ("A hook didn't
answer in time"): recall is lost and a guard hook does not run. Plugin updates bring the short timeouts
back, so a SessionStart hook re-runs this. The first session after an update still uses the old values.
  apply-hook-timeouts.py            patch (idempotent; prints only what changed)
  apply-hook-timeouts.py --check    exit 1 if any hook is still below the floor
  apply-hook-timeouts.py selftest
"""
import glob
import json
import os
import shutil
import sys
import tempfile

FLOOR = 15
PLUGINS = os.path.expanduser("~/.claude/plugins")


def hook_files(root):
    """The hook files Claude Code reads for one plugin: hooks/hooks.json plus what plugin.json names."""
    files = {os.path.join(root, "hooks", "hooks.json")}
    manifest = os.path.join(root, ".claude-plugin", "plugin.json")
    try:
        declared = json.load(open(manifest)).get("hooks")
    except (OSError, ValueError):
        declared = None
    if isinstance(declared, dict):
        files.add(manifest)  # inline hooks
    for rel in [declared] if isinstance(declared, str) else declared if isinstance(declared, list) else []:
        if isinstance(rel, str):
            files.add(os.path.normpath(os.path.join(root, rel)))
    inside = os.path.realpath(root) + os.sep  # a path (or symlink) that leaves the plugin folder is never ours to rewrite
    return sorted(f for f in files if os.path.isfile(f) and os.path.realpath(f).startswith(inside))


def plugin_roots():
    roots = set(glob.glob(os.path.join(PLUGINS, "cache", "*", "*", "*")))
    try:
        installed = json.load(open(os.path.join(PLUGINS, "installed_plugins.json")))
        for entries in installed.get("plugins", installed).values():
            for e in entries if isinstance(entries, list) else [entries]:
                if isinstance(e, dict) and e.get("installPath"):
                    roots.add(e["installPath"])
    except (OSError, ValueError, AttributeError):
        pass
    return sorted(r for r in roots if os.path.isdir(r))


def patch_file(path, check=False):
    d = json.load(open(path))
    if not isinstance(d, dict):
        return 0
    n = 0
    for groups in (d.get("hooks") or {}).values():
        for g in groups if isinstance(groups, list) else []:
            for h in g.get("hooks", []) if isinstance(g, dict) else []:
                t = h.get("timeout") if isinstance(h, dict) else None
                if isinstance(t, (int, float)) and not isinstance(t, bool) and t < FLOOR:
                    n += 1
                    h["timeout"] = FLOOR
    if n and not check:
        if not os.path.exists(path + ".bak-kit"):  # the plugin's own file, kept once before the first change
            shutil.copy2(path, path + ".bak-kit")
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(d, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    return n


def main(check):
    short = 0
    for root in plugin_roots():
        for path in hook_files(root):
            try:
                n = patch_file(path, check)
            except (OSError, ValueError) as e:
                print(f"skip {path}: {e}")
                continue
            if n:
                short += n
                print(f"{'short' if check else 'patched'} {n} timeout(s) -> {FLOOR}s  {path}")
    return 1 if check and short else 0


def selftest():
    global PLUGINS
    PLUGINS = tempfile.mkdtemp()
    root = os.path.join(PLUGINS, "cache", "mkt", "p", "1.0")
    os.makedirs(os.path.join(root, "hooks"))
    os.makedirs(os.path.join(root, ".claude-plugin"))
    json.dump({"hooks": "./hooks/claude.json"}, open(os.path.join(root, ".claude-plugin", "plugin.json"), "w"))
    claude = os.path.join(root, "hooks", "claude.json")
    json.dump({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"command": "x", "timeout": 5}]}],
                         "Stop": [{"hooks": [{"command": "y", "timeout": 30}, {"command": "z"}]}]}}, open(claude, "w"))
    other = os.path.join(root, "hooks", "codex.json")  # another agent's file: not ours to touch
    json.dump({"hooks": {"Stop": [{"hooks": [{"command": "c", "timeout": 5}]}]}}, open(other, "w"))
    assert hook_files(root) == [claude]
    assert main(check=True) == 1 and json.load(open(claude))["hooks"]["PreToolUse"][0]["hooks"][0]["timeout"] == 5
    assert main(check=False) == 0
    d = json.load(open(claude))["hooks"]
    assert d["PreToolUse"][0]["hooks"][0]["timeout"] == FLOOR and d["Stop"][0]["hooks"][0]["timeout"] == 30
    assert "timeout" not in d["Stop"][0]["hooks"][1], "an unset timeout stays unset"
    assert json.load(open(other))["hooks"]["Stop"][0]["hooks"][0]["timeout"] == 5
    assert main(check=True) == 0, "idempotent"
    # a manifest path that climbs out of the plugin folder (or a symlink that does) must not be rewritten; a list file is skipped
    outside = os.path.join(PLUGINS, "settings.json")
    json.dump({"hooks": {"Stop": [{"hooks": [{"command": "u", "timeout": 5}]}]}}, open(outside, "w"))
    link = os.path.join(root, "hooks", "link.json")
    os.symlink(outside, link)
    listed = os.path.join(root, "hooks", "list.json")
    json.dump([1, 2], open(listed, "w"))
    json.dump({"hooks": ["../../../../settings.json", "./hooks/link.json", "./hooks/list.json", "./hooks/claude.json"]},
              open(os.path.join(root, ".claude-plugin", "plugin.json"), "w"))
    assert hook_files(root) == [claude, listed], hook_files(root)
    assert main(check=False) == 0 and os.path.islink(link) and json.load(open(outside))["hooks"]["Stop"][0]["hooks"][0]["timeout"] == 5
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
        sys.exit(0)
    sys.exit(main("--check" in sys.argv))
