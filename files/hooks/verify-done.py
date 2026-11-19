#!/usr/bin/env python3
"""Automatic "done" checks, per project. Does nothing until you allow a project, so a cloned repo you do not
trust can never get its own scripts run by shipping a .claude/verify or .claude/lint.

  PostToolUse (Edit|Write|MultiEdit):  verify-done.py edit  -> runs <project>/.claude/lint FILE
  Stop:                                verify-done.py stop  -> runs <project>/.claude/verify, only if Claude edited files this turn
  verify-done.py allow [DIR]           allow checks in DIR (default: this folder); listed in ~/.claude/kit/verify-projects
  verify-done.py list                  the allowed projects
  verify-done.py selftest

A check is the first of: .claude/<name> (executable), .claude/<name>.sh.
Example .claude/verify:  #!/bin/sh
                         npm test --silent
A failing check exits 2: its last lines go back to Claude, which fixes the failure before finishing.
Stop retries are capped at 3 per session so a check Claude cannot fix never loops forever.
When a check cannot run (not executable, missing interpreter) or is still failing at the cap, the hook lets the turn
end but tells you so with a {"systemMessage": ...} line on stdout: that work is not verified.
An edit marker older than the turn's prompt (left by an interrupted turn) is dropped, not verified.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime

STATE = os.path.join(tempfile.gettempdir(), "claude-verify-done")
TAIL = 40
MAX_RETRIES = 3


def allow_file():
    return os.environ.get("KIT_VERIFY_ALLOW") or os.path.expanduser("~/.claude/kit/verify-projects")


def fingerprint(project):
    """sha256 over the check scripts as they are now, so a `git pull` that changes one is not trusted."""
    h = hashlib.sha256()
    for name in ("verify", "verify.sh", "lint", "lint.sh"):
        p = os.path.join(project, ".claude", name)
        if os.path.isfile(p):
            h.update(name.encode() + b"\0" + open(p, "rb").read() + b"\0")
    return h.hexdigest()


def allowed():
    """{project: fingerprint of its scripts when you allowed it}; a line without one (older file) matches nothing."""
    out = {}
    try:
        for line in open(allow_file()):
            path, _, fp = line.rstrip("\n").partition("\t")
            if path.strip():
                out[path.strip()] = fp.strip()
    except OSError:
        pass
    return out


def allow(d, quiet=False):
    d = os.path.realpath(d)
    entries = allowed()
    old, entries[d] = entries.get(d), fingerprint(d)
    os.makedirs(os.path.dirname(allow_file()), exist_ok=True)
    with open(allow_file(), "w") as f:
        f.writelines(f"{p}\t{fp}\n" for p, fp in sorted(entries.items()))
    if not quiet:
        print(f"done checks {'unchanged' if old == entries[d] else 'allowed'} in {d} "
              "(its .claude/verify and .claude/lint will run; allow again after you change them)")


def find(project, name):
    base = os.path.join(project, ".claude", name)
    if os.path.isfile(base) and os.access(base, os.X_OK):
        return [base]
    if os.path.isfile(base + ".sh"):
        return ["sh", base + ".sh"]
    return None


def note(msg):
    print(json.dumps({"systemMessage": "verify-done: " + msg}))


def run(cmd, project, timeout):
    try:
        p = subprocess.run(cmd, cwd=project, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr)
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"
    except OSError as e:
        return None, f"could not run ({e})"  # a broken check must not trap Claude; the caller says so


def fail(label, code, out):
    lines = out.strip().splitlines()[-TAIL:]
    sys.stderr.write(f"{label} failed (exit {code}). Fix this before finishing:\n" + "\n".join(lines) + "\n")
    return 2


def prompt_time(transcript):
    """When the user typed this turn's prompt (epoch s), from the transcript's tail; 0 when unknown."""
    try:
        with open(transcript, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - (1 << 20)))
            lines = f.read().split(b"\n")
    except (OSError, TypeError, ValueError):
        return 0
    for raw in reversed(lines):
        try:
            o = json.loads(raw) if b'"user"' in raw else {}
            c = (o.get("message") or {}).get("content")
            blocks = [b.get("type") for b in c if isinstance(b, dict)] if isinstance(c, list) else []
            if o.get("type") == "user" and not o.get("isMeta") and o.get("toolUseResult") is None and (
                    isinstance(c, str) and not c.startswith("<") or "text" in blocks and "tool_result" not in blocks):
                return datetime.fromisoformat(o["timestamp"].replace("Z", "+00:00")).timestamp()
        except (ValueError, KeyError, AttributeError, TypeError):
            continue
    return 0


def main(mode, data, state=STATE):
    project = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    rp = os.path.realpath(project)
    entries = allowed()
    if rp not in entries:
        return 0  # not allowed: never run a project's own scripts unasked
    trusted = entries[rp] == fingerprint(project)  # false once a check script changed after you allowed it
    sid = str(data.get("session_id") or "nosession").replace(os.sep, "_")
    os.makedirs(state, exist_ok=True)
    edited, tries = os.path.join(state, sid + ".edited"), os.path.join(state, sid + ".tries")
    if mode == "edit":
        open(edited, "w").close()
        if not trusted:
            return 0
        cmd = find(project, "lint")
        path = (data.get("tool_input") or {}).get("file_path") or ""
        if not cmd or not path:
            return 0
        code, out = run(cmd + [path], project, 60)
        if code is None:
            note(f".claude/lint {out}; {os.path.basename(path)} not linted")
            return 0
        return fail(".claude/lint " + os.path.basename(path), code, out) if code else 0
    if mode == "stop":
        if not os.path.exists(edited):
            return 0
        if os.path.getmtime(edited) < prompt_time(data.get("transcript_path")):
            for f in (edited, tries):  # stale: an earlier, interrupted turn edited; this one did not
                if os.path.exists(f):
                    os.remove(f)
            return 0
        if not trusted:
            os.remove(edited)
            note(f"the check scripts in {rp} changed since you allowed them, so they did not run; this work is NOT "
                 f"verified. Read them, then run: verify-done.py allow {rp}")
            return 0
        n = int(open(tries).read() or 0) if os.path.exists(tries) else 0
        if data.get("stop_hook_active") and n >= MAX_RETRIES:
            for f in (edited, tries):
                os.remove(f)
            note(f".claude/verify still failing after {MAX_RETRIES} tries; this work is NOT verified")
            return 0
        cmd = find(project, "verify")
        if not cmd:
            os.remove(edited)
            if os.path.isfile(os.path.join(project, ".claude", "verify")):
                note(".claude/verify is not executable (chmod +x it, or name it verify.sh); this work is NOT verified")
            return 0
        code, out = run(cmd, project, 600)
        if code is None:
            os.remove(edited)
            note(f".claude/verify {out}; this work is NOT verified")
            return 0
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
    os.environ["KIT_VERIFY_ALLOW"] = os.path.join(d, "allow")
    ev = {"session_id": "s1"}
    open(os.path.join(d, ".claude", "verify.sh"), "w").write("exit 1\n")
    main("edit", ev, st)
    assert main("stop", ev, st) == 0, "a project not allowed never runs its checks"
    os.remove(os.path.join(d, ".claude", "verify.sh"))
    allow(d)
    assert os.path.realpath(d) in allowed()
    assert main("stop", ev, st) == 0, "no edits -> no check"
    assert main("edit", {**ev, "tool_input": {"file_path": "x.py"}}, st) == 0, "no lint -> pass"
    assert main("stop", ev, st) == 0, "no verify -> pass"
    v = os.path.join(d, ".claude", "verify.sh")
    open(v, "w").write("echo boom; exit 1\n")
    main("edit", ev, st)
    assert main("stop", ev, st) == 0, "a script changed after allow must not run"
    allow(d, True)  # you read it and allowed it again
    main("edit", ev, st)
    assert main("stop", ev, st) == 2, "failing verify must block"
    for _ in range(MAX_RETRIES - 1):
        assert main("stop", {**ev, "stop_hook_active": True}, st) == 2
    assert main("stop", {**ev, "stop_hook_active": True}, st) == 0, "retry cap must release"
    open(v, "w").write("exit 0\n")
    allow(d, True)
    main("edit", ev, st)
    assert main("stop", ev, st) == 0 and not os.listdir(st), "passing verify clears state"
    open(os.path.join(d, ".claude", "lint.sh"), "w").write('case "$1" in *bad*) echo lint-err; exit 1;; esac\n')
    allow(d, True)
    assert main("edit", {**ev, "tool_input": {"file_path": "bad.py"}}, st) == 2
    assert main("edit", {**ev, "tool_input": {"file_path": "ok.py"}}, st) == 0
    # an interrupted turn left the marker; the next turn (prompt typed later, no edits) must not verify
    open(v, "w").write("echo boom; exit 1\n")
    allow(d, True)
    tr = os.path.join(d, "t.jsonl")
    line = lambda ts: json.dumps({"type": "user", "timestamp": ts, "message": {"role": "user", "content": "next task"}})
    main("edit", ev, st)
    open(tr, "w").write(line("2999-01-01T00:00:00Z") + "\n")
    assert main("stop", {**ev, "transcript_path": tr}, st) == 0 and not os.listdir(st), "stale marker verified"
    main("edit", ev, st)
    open(tr, "w").write(line("2000-01-01T00:00:00Z") + "\n")
    assert main("stop", {**ev, "transcript_path": tr}, st) == 2, "this turn's edit must still verify"
    # a check that cannot run, or still fails at the cap, must tell the user (JSON on stdout), never pass silently
    import contextlib
    import io

    def said(ev2):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main("stop", {**ev, **ev2}, st)
        return rc, buf.getvalue()
    vp = os.path.join(d, ".claude", "verify")
    os.remove(v)
    open(vp, "w").write("exit 0\n")  # exists, not executable, no .sh name
    allow(d, True)
    main("edit", ev, st)
    rc, out = said({})
    assert rc == 0 and "not executable" in json.loads(out)["systemMessage"], out
    os.chmod(vp, 0o755)
    open(vp, "w").write("#!/no/such/interpreter\nexit 0\n")
    main("edit", ev, st)
    rc, out = said({})
    assert rc == 0 and "changed since you allowed" in json.loads(out)["systemMessage"], out
    allow(d, True)
    main("edit", ev, st)
    rc, out = said({})
    assert rc == 0 and "could not run" in json.loads(out)["systemMessage"], out
    open(vp, "w").write("#!/bin/sh\nexit 1\n")
    allow(d, True)
    for f in os.listdir(st):  # fresh retry count
        os.remove(os.path.join(st, f))
    main("edit", ev, st)
    for _ in range(MAX_RETRIES):
        assert said({"stop_hook_active": True})[0] == 2
    rc, out = said({"stop_hook_active": True})
    assert rc == 0 and "NOT verified" in json.loads(out)["systemMessage"], out
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
        sys.exit(0)
    if sys.argv[1:2] == ["allow"]:
        sys.exit(allow(sys.argv[2] if len(sys.argv) > 2 else os.getcwd()))
    if sys.argv[1:2] == ["list"]:
        print("\n".join(sorted(allowed())) or "no projects allowed yet")
        sys.exit(0)
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "", payload))
