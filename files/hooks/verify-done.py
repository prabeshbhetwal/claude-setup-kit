#!/usr/bin/env python3
"""Automatic "done" checks, per project. Does nothing until a project opts in.

  PostToolUse (Edit|Write|MultiEdit):  verify-done.py edit  -> runs <project>/.claude/lint FILE
  Stop:                                verify-done.py stop  -> runs <project>/.claude/verify, only if Claude edited files this turn
  verify-done.py selftest

A check is the first of: .claude/<name> (executable), .claude/<name>.sh.
Example .claude/verify:  #!/bin/sh
                         npm test --silent
A failing check exits 2: its last lines go back to Claude, which fixes the failure before finishing.
Stop retries are capped at 3 per session so a check Claude cannot fix never loops forever.
"""
import json
import os
import subprocess
import sys
import tempfile

STATE = os.path.join(tempfile.gettempdir(), "claude-verify-done")
TAIL = 40
MAX_RETRIES = 3


def find(project, name):
    base = os.path.join(project, ".claude", name)
    if os.path.isfile(base) and os.access(base, os.X_OK):
        return [base]
    if os.path.isfile(base + ".sh"):
        return ["sh", base + ".sh"]
    return None


def run(cmd, project, timeout):
    try:
        p = subprocess.run(cmd, cwd=project, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr)
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"
    except OSError as e:
        return 0, f"could not run ({e}); skipped"  # a broken check must not trap Claude


def fail(label, code, out):
    lines = out.strip().splitlines()[-TAIL:]
    sys.stderr.write(f"{label} failed (exit {code}). Fix this before finishing:\n" + "\n".join(lines) + "\n")
    return 2


def main(mode, data, state=STATE):
    project = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    sid = str(data.get("session_id") or "nosession").replace(os.sep, "_")
    os.makedirs(state, exist_ok=True)
    edited, tries = os.path.join(state, sid + ".edited"), os.path.join(state, sid + ".tries")
    if mode == "edit":
        open(edited, "w").close()
        cmd = find(project, "lint")
        path = (data.get("tool_input") or {}).get("file_path") or ""
        if not cmd or not path:
            return 0
        code, out = run(cmd + [path], project, 60)
        return fail(".claude/lint " + os.path.basename(path), code, out) if code else 0
    if mode == "stop":
        if not os.path.exists(edited):
            return 0
        n = int(open(tries).read() or 0) if os.path.exists(tries) else 0
        if data.get("stop_hook_active") and n >= MAX_RETRIES:
            for f in (edited, tries):
                os.remove(f)
            return 0
        cmd = find(project, "verify")
        if not cmd:
            os.remove(edited)
            return 0
        code, out = run(cmd, project, 600)
        if code:
            open(tries, "w").write(str(n + 1))
            return fail(".claude/verify", code, out)
        for f in (edited, tries):
            if os.path.exists(f):
                os.remove(f)
    return 0


def selftest():
    d = tempfile.mkdtemp()
    st = os.path.join(d, "state")
    os.makedirs(os.path.join(d, ".claude"))
    os.environ["CLAUDE_PROJECT_DIR"] = d
    ev = {"session_id": "s1"}
    assert main("stop", ev, st) == 0, "no edits -> no check"
    assert main("edit", {**ev, "tool_input": {"file_path": "x.py"}}, st) == 0, "no lint -> pass"
    assert main("stop", ev, st) == 0, "no verify -> pass"
    v = os.path.join(d, ".claude", "verify.sh")
    open(v, "w").write("echo boom; exit 1\n")
    main("edit", ev, st)
    assert main("stop", ev, st) == 2, "failing verify must block"
    for _ in range(MAX_RETRIES - 1):
        assert main("stop", {**ev, "stop_hook_active": True}, st) == 2
    assert main("stop", {**ev, "stop_hook_active": True}, st) == 0, "retry cap must release"
    open(v, "w").write("exit 0\n")
    main("edit", ev, st)
    assert main("stop", ev, st) == 0 and not os.listdir(st), "passing verify clears state"
    open(os.path.join(d, ".claude", "lint.sh"), "w").write('case "$1" in *bad*) echo lint-err; exit 1;; esac\n')
    assert main("edit", {**ev, "tool_input": {"file_path": "bad.py"}}, st) == 2
    assert main("edit", {**ev, "tool_input": {"file_path": "ok.py"}}, st) == 0
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
        sys.exit(0)
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "", payload))
