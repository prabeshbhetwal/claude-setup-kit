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
            if any(match in x.get("command", "") for g in groups for x in g.get("hooks", [])):
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


def main(path: str, frag_path: str, components: list) -> None:
    path = os.path.realpath(path)  # write through a symlink (stow, chezmoi), never replace it
    settings = json.load(open(path)) if os.path.exists(path) and os.path.getsize(path) else {}
    fragment = json.load(open(frag_path))
    changes = merge(settings, fragment, [c for c in components if c in fragment])
    if not changes:
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
        print("  + " + c)


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
    f3 = {"g": {"deny": ["Read(.env)", "Bash(git reset --hard *)"], "settings": {"sandbox": {"enabled": True}}}}
    s3 = {"permissions": {"allow": ["Bash(ls *)"], "deny": ["Read(.env)"]}, "sandbox": {"enabled": False}}
    assert merge(s3, f3, ["g"]) == ["deny Bash(git reset --hard *)"], s3
    assert s3["permissions"] == {"allow": ["Bash(ls *)"], "deny": ["Read(.env)", "Bash(git reset --hard *)"]}, s3
    assert s3["sandbox"] == {"enabled": False}, "an existing sandbox choice must be kept"
    assert merge(s3, f3, ["g"]) == [], "deny merge must be idempotent"
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
    else:
        main(sys.argv[1], sys.argv[2], sys.argv[3:])
