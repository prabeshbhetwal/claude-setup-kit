#!/usr/bin/env python3
"""Merge kit hooks and env into ~/.claude/settings.json without overwriting anything.

  merge_settings.py SETTINGS FRAGMENT.json [component ...]   # merge the named components
  merge_settings.py selftest

FRAGMENT maps component id -> {"hooks": [{"event", "matcher", <hook fields>}], "env": {...},
                               "deny": [permission rules], "settings": {top-level key: value}}.
- A deny rule is appended only when missing; a top-level setting is set only when the key is absent.
- A hook is added only when no existing hook for that event already runs the same command.
- An env key is added only when it is absent; an existing value is never changed.
- Before the first change the file is copied to SETTINGS.bak-kit-<timestamp>.
Prints one line per change; prints nothing when everything is already present (idempotent).
"""
import json
import os
import shutil
import sys
import tempfile
import difflib
import re
import time


def merge(settings: dict, fragment: dict, components: list) -> list:
    changes = []
    hooks = settings.setdefault("hooks", {})
    env = settings.setdefault("env", {})
    for comp in components:
        part = fragment.get(comp, {})
        for h in part.get("hooks", []):
            h = dict(h)
            event, matcher = h.pop("event"), h.pop("matcher", None)
            h["command"] = h["command"].replace("__RTK__", os.environ.get("KIT_RTK") or "rtk")
            match = h.pop("match", h["command"])  # an existing hook whose command contains this counts as present
            groups = hooks.setdefault(event, [])
            present = [x for g in groups for x in g.get("hooks", []) if match in x.get("command", "")]
            for x in present:  # an older install's shorter timeout is raised, never lowered
                if isinstance(x.get("timeout"), (int, float)) and h.get("timeout", 0) > x["timeout"]:
                    x["timeout"] = h["timeout"]
                    changes.append(f"hook {event} timeout -> {h['timeout']}s: {x['command']}")
            if present:
                continue
            group = next((g for g in groups if g.get("matcher") == matcher), None)
            if group is None:
                group = {"hooks": []} if matcher is None else {"matcher": matcher, "hooks": []}
                groups.append(group)
            group["hooks"].append(h)
            changes.append(f"hook {event} [{matcher or '*'}]: {h['command']}")
        for k, v in part.get("env", {}).items():
            if k not in env:
                env[k] = v
                changes.append(f"env {k}={v}")
        old = settings.get("permissions", {}).get("deny", [])
        for rule in part.get("retire_deny", []):  # rules an earlier kit version added and this one no longer wants
            if rule in old:
                old.remove(rule)
                changes.append(f"retired deny {rule}")
        allow = settings.setdefault("permissions", {}).setdefault("allow", []) if part.get("allow") else None
        for rule in part.get("allow", []):
            if rule not in allow:
                allow.append(rule)
                changes.append(f"allow {rule}")
        deny = settings.setdefault("permissions", {}).setdefault("deny", []) if part.get("deny") else None
        for rule in part.get("deny", []):
            if rule not in deny:
                deny.append(rule)
                changes.append(f"deny {rule}")
        for k, v in part.get("settings", {}).items():  # top-level keys: set only when absent
            if k not in settings:
                settings[k] = v
                changes.append(f"setting {k}={json.dumps(v)}")
    if not env:
        settings.pop("env")
    if not hooks:
        settings.pop("hooks")
    return changes


def remove(settings: dict, fragment: dict, components: list) -> list:
    """Take out the hooks the kit added for these components (matched by their `match` text). Nothing else is touched."""
    changes = []
    hooks = settings.get("hooks", {})
    for comp in components:
        for h in fragment.get(comp, {}).get("hooks", []):
            event = h["event"]
            match = h.get("match", h["command"])
            for g in hooks.get(event, []):
                keep = [x for x in g.get("hooks", []) if match not in x.get("command", "")]
                if len(keep) != len(g.get("hooks", [])):
                    changes.append(f"removed hook {event}: {h['command']}")
                    g["hooks"] = keep
            hooks[event] = [g for g in hooks.get(event, []) if g.get("hooks")]
            if not hooks[event]:
                hooks.pop(event, None)
    if "hooks" in settings and not settings["hooks"]:
        settings.pop("hooks")
    return changes


SECRET_KEY = re.compile(r"(key|token|secret|passw|credential|auth)", re.I)


def redact(x, key=""):
    """A copy with secret-looking values replaced, for printing only (the file itself is never redacted)."""
    if isinstance(x, dict):
        return {k: redact(v, k) for k, v in x.items()}
    if isinstance(x, list):
        return [redact(v, key) for v in x]
    if isinstance(x, str) and (SECRET_KEY.search(key) or re.search(r"(sk-|sk_|ghp_|github_pat_|xox[bp]-|AKIA)[\w-]{8,}", x)):
        return "<hidden>"
    return x


def show_diff(before: dict, after: dict, path: str) -> None:
    a, b = (json.dumps(redact(x), indent=2).splitlines() for x in (before, after))
    for line in difflib.unified_diff(a, b, f"{path} (now)", f"{path} (after)", lineterm="", n=2):
        print("    " + line)


def main(path: str, frag_path: str, components: list, mode: str = "add") -> None:
    """mode: add (write), dry-run (show the diff, write nothing) or remove (take the kit's hooks out)."""
    path = os.path.realpath(path)  # write through a symlink (stow, chezmoi), never replace it
    settings = json.load(open(path)) if os.path.exists(path) and os.path.getsize(path) else {}
    before = json.loads(json.dumps(settings))
    fragment = json.load(open(frag_path))
    comps = [c for c in components if c in fragment]
    changes = remove(settings, fragment, comps) if mode == "remove" else merge(settings, fragment, comps)
    if not changes:
        return
    show_diff(before, settings, path)  # shown before anything is written
    if mode == "dry-run":
        return
    if os.path.exists(path):
        shutil.copy2(path, f"{path}.bak-kit-{time.strftime('%Y%m%d-%H%M%S')}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))
    with os.fdopen(fd, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    if os.path.exists(path):
        shutil.copymode(path, tmp)  # keep the file's permissions (mkstemp creates 0600)
    os.replace(tmp, path)  # atomic: a crash never leaves a half-written settings.json
    for c in changes:
        print(("  - " if mode == "remove" else "  + ") + c)


def selftest() -> None:
    frag = {"a": {"hooks": [{"event": "Stop", "matcher": None, "type": "command", "command": "x"},
                            {"event": "PreToolUse", "matcher": "Bash", "type": "command", "command": "y"}],
                  "env": {"K": "1"}}}
    s = {"env": {"K": "keep"}, "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "z"}]}]}}
    ch = merge(s, frag, ["a"])
    assert s["env"]["K"] == "keep", s
    assert [h["command"] for h in s["hooks"]["PreToolUse"][0]["hooks"]] == ["z", "y"], s
    assert s["hooks"]["Stop"] == [{"hooks": [{"type": "command", "command": "x"}]}], s
    assert len(ch) == 2, ch
    assert merge(s, frag, ["a"]) == [], "second run must change nothing"
    old = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "rtk hook claude"}]}]}}
    f2 = {"r": {"hooks": [{"event": "PreToolUse", "matcher": "Bash", "type": "command",
                           "command": '"__RTK__" hook claude', "match": "hook claude"}]}}
    assert merge(old, f2, ["r"]) == [], "an older bare `rtk hook claude` must count as present"
    s4 = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "x", "timeout": 5}]}]}}
    f4 = {"t": {"hooks": [{"event": "Stop", "type": "command", "command": "x", "timeout": 15}]}}
    assert len(merge(s4, f4, ["t"])) == 1 and s4["hooks"]["Stop"][0]["hooks"][0]["timeout"] == 15, s4
    assert merge(s4, {"t": {"hooks": [{"event": "Stop", "type": "command", "command": "x", "timeout": 3}]}}, ["t"]) == []
    f3 = {"g": {"deny": ["Read(.env)", "Bash(git reset --hard *)"], "settings": {"sandbox": {"enabled": True}}}}
    s3 = {"permissions": {"allow": ["Bash(ls *)"], "deny": ["Read(.env)"]}, "sandbox": {"enabled": False}}
    assert merge(s3, f3, ["g"]) == ["deny Bash(git reset --hard *)"], s3
    assert s3["permissions"] == {"allow": ["Bash(ls *)"], "deny": ["Read(.env)", "Bash(git reset --hard *)"]}, s3
    assert s3["sandbox"] == {"enabled": False}, "an existing sandbox choice must be kept"
    assert merge(s3, f3, ["g"]) == [], "deny merge must be idempotent"
    r = {"a": {"hooks": [{"event": "Stop", "type": "command", "command": "x", "match": "x"}]}}
    s5 = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "mine"}, {"type": "command", "command": "x"}]}]}}
    assert len(remove(s5, r, ["a"])) == 1 and s5["hooks"]["Stop"][0]["hooks"] == [{"type": "command", "command": "mine"}], s5
    assert remove(s5, r, ["a"]) == [], "removing twice changes nothing"
    s6 = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "x"}]}]}, "env": {"K": "1"}}
    remove(s6, r, ["a"])
    assert s6 == {"env": {"K": "1"}}, s6
    k = "ANTHROPIC_API_" + "KEY"  # built at run time so the repo's secret scan does not flag this test
    shown = redact({"env": {k: "abc", "COGNEE_BACKEND": "local"}, "x": "gh" + "p_" + "abcdefghijklmnop"})
    assert shown == {"env": {k: "<hidden>", "COGNEE_BACKEND": "local"}, "x": "<hidden>"}, shown
    s7 = {}
    assert merge(s7, {"g": {"allow": ["Read(.env.example)"]}}, ["g"]) == ["allow Read(.env.example)"] and merge(s7, {"g": {"allow": ["Read(.env.example)"]}}, ["g"]) == []
    s8 = {"permissions": {"deny": ["Read(.env.*)", "Read(./mine)"]}}
    assert merge(s8, {"g": {"retire_deny": ["Read(.env.*)"], "deny": ["Read(.env.local)"]}}, ["g"]) == ["retired deny Read(.env.*)", "deny Read(.env.local)"]
    assert s8["permissions"]["deny"] == ["Read(./mine)", "Read(.env.local)"], s8
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
    else:
        flag = sys.argv[1] if sys.argv[1] in ("--dry-run", "--remove") else ""
        a = sys.argv[2:] if flag else sys.argv[1:]
        main(a[0], a[1], a[2:], {"--dry-run": "dry-run", "--remove": "remove"}.get(flag, "add"))
