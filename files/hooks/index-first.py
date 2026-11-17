#!/usr/bin/env python3
"""Index first: make Claude use the CodeGraph and Graphify indexes a repo already has.

  PreToolUse  Grep|Glob|Bash|Read : index-first.py pre
  PostToolUse mcp__codegraph__.*   : index-first.py post
  UserPromptSubmit                 : index-first.py prompt
  index-first.py selftest

In a folder with a .codegraph/ index (nearest ancestor, never $HOME):
- Grep, or a Bash code search (grep -r, rg, ag, ack, git grep), before any successful
  codegraph call this session in this repo -> denied, with the exact call to make instead.
  Searches limited to non-code files (docs, logs, config) pass. After 2 denials the
  search passes with a warning, so a broken CodeGraph server never traps the agent.
- Glob, or Read of a code file before any codegraph call and before any edit -> one nudge
  (Read must stay allowed: Edit needs it).
With graphify-out/GRAPH_REPORT.md present, an architecture-style prompt gets a pointer to it.
Any error -> allow (fail open). Decisions go to ~/.claude/cache/index-first.jsonl.
"""
import json
import os
import re
import sys
import tempfile
import time

HOME = os.path.expanduser("~")
STATE = os.path.join(tempfile.gettempdir(), "claude-index-first")
LOG = os.path.join(HOME, ".claude", "cache", "index-first.jsonl")
MAX_DENIALS = 2
BURST_S = 5  # parallel calls within this window count as one denial
CODE = re.compile(r"\.(swift|py|ts|tsx|js|jsx|mjs|cjs|go|rs|java|kt|rb|c|cc|cpp|h|hpp|m|mm|cs|php|scala|vue|svelte|dart|lua|zig|astro)$")
NONCODE = re.compile(r"\.(md|mdx|txt|json|jsonl|ya?ml|toml|ini|cfg|conf|env|log|csv|tsv|html?|css|scss|xml|plist|lock|sql|sh)\b|\b(md|txt|json|yaml|yml|toml|log|css|html)\b$")
BASH_SEARCH = re.compile(r"(^|[;&|(]\s*)(rtk\s+)?(rg|ag|ack|git\s+grep|grep\s+(-\w*[rR]\w*|--recursive))\b")
ARCH = re.compile(r"\b(architecture|overview|big picture|structure|how (does|do) .{1,60} (fit|work|connect|relate)|"
                  r"why (does|is|do) |dependenc|data ?flow|module(s)? map|how is .{1,40} (organi[sz]ed|laid out))", re.I)


def root_of(path):
    p = os.path.realpath(path or "")
    while p and p not in ("/", HOME):
        if os.path.isdir(os.path.join(p, ".codegraph")):
            return p
        p = os.path.dirname(p)
    return None


def key(data, root):
    sid = str(data.get("session_id") or "nosession")
    return os.path.join(STATE, re.sub(r"[^\w.-]", "_", f"{sid}-{root}"))


def log(entry):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a") as f:
            f.write(json.dumps({"t": int(time.time()), **entry}) + "\n")
    except OSError:
        pass


def out(event, **fields):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, **fields}}))


def explore_call(root):
    return f'codegraph_explore(query="<symbols or question>", projectPath="{root}")'


def pre(data):
    tool, inp = data.get("tool_name", ""), data.get("tool_input") or {}
    root = root_of(data.get("cwd") or os.getcwd())
    if not root:
        return
    k = key(data, root)
    if os.path.exists(k + ".used"):
        return
    target = inp.get("path") or inp.get("file_path") or ""
    if target and not os.path.realpath(os.path.join(root, target)).startswith(root):
        return  # outside this repo
    if tool == "Read":
        if not CODE.search(target) or os.path.exists(k + ".edited") or os.path.exists(k + ".nudged"):
            return
        open(k + ".nudged", "w").close()
        log({"tool": tool, "root": root, "act": "nudge"})
        return out("PreToolUse", additionalContext=f"Index first: {root} has a CodeGraph index. For 'where is / how does / who calls' "
                   f"questions call {explore_call(root)} instead of reading files one by one; it returns the relevant source in one call.")
    if tool == "Glob":
        if os.path.exists(k + ".nudged"):
            return
        open(k + ".nudged", "w").close()
        log({"tool": tool, "root": root, "act": "nudge"})
        return out("PreToolUse", additionalContext=f"Index first: to find code by meaning, call {explore_call(root)}; Glob is fine for file names.")
    if tool == "Grep":
        scope = " ".join(str(inp.get(x) or "") for x in ("glob", "type", "path"))
        if NONCODE.search(scope):
            return
    elif tool == "Bash":
        cmd = inp.get("command", "")
        if not BASH_SEARCH.search(cmd) or (NONCODE.search(cmd) and not CODE.search(cmd)):
            return
    else:
        return
    n, last = 0, 0.0
    if os.path.exists(k + ".denied"):
        n, last = (float(x) for x in open(k + ".denied").read().split())
    if n >= MAX_DENIALS:
        log({"tool": tool, "root": root, "act": "allow-capped"})
        return out("PreToolUse", additionalContext="Index first: search allowed after 2 reminders. If codegraph_explore is failing, say so to the user.")
    now = time.time()
    if now - last > BURST_S:
        n += 1
    with open(k + ".denied", "w") as f:
        f.write(f"{int(n)} {now}")
    log({"tool": tool, "root": root, "act": "deny"})
    out("PreToolUse", permissionDecision="deny", permissionDecisionReason=(
        f"Index first: {root} has a CodeGraph index, and this session has not used it yet. Call {explore_call(root)} "
        "first: it returns the matching source and call paths in one call. Text searches of docs, logs or config are not blocked, "
        "and after one CodeGraph call this search is allowed."))


def post(data):
    root = root_of(data.get("cwd") or os.getcwd())
    if not root:
        return
    resp = json.dumps(data.get("tool_response") or "")[:2000].lower()
    tool = data.get("tool_name", "")
    if tool.startswith("mcp__codegraph__"):
        if '"is_error": true' in resp or "no .codegraph" in resp or "not indexed" in resp:
            return log({"tool": tool, "root": root, "act": "cg-error"})
        open(key(data, root) + ".used", "w").close()
        log({"tool": tool, "root": root, "act": "cg-used"})
    elif tool in ("Edit", "Write", "MultiEdit"):
        open(key(data, root) + ".edited", "w").close()


def prompt(data):
    root = root_of(data.get("cwd") or os.getcwd()) or ""
    cwd = data.get("cwd") or os.getcwd()
    base = root or cwd
    report = os.path.join(base, "graphify-out", "GRAPH_REPORT.md")
    if os.path.isfile(report) and ARCH.search(data.get("prompt") or ""):
        log({"tool": "prompt", "root": base, "act": "graphify-pointer"})
        out("UserPromptSubmit", additionalContext=f"Index first: this looks like an architecture question. Read {report} "
            f"(then graphify-out/wiki/index.md) before opening source files; follow its edges, don't guess.")


def main(mode, data):
    os.makedirs(STATE, exist_ok=True)
    {"pre": pre, "post": post, "prompt": prompt}.get(mode, lambda d: None)(data)


def selftest():
    import io
    import contextlib
    global STATE, LOG
    d = tempfile.mkdtemp()
    STATE, LOG = os.path.join(d, "state"), os.path.join(d, "log.jsonl")
    repo = os.path.join(d, "repo")
    os.makedirs(os.path.join(repo, ".codegraph"))
    os.makedirs(os.path.join(repo, "graphify-out"))
    open(os.path.join(repo, "graphify-out", "GRAPH_REPORT.md"), "w").close()

    def run(mode, **ev):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(mode, {"session_id": "s", "cwd": repo, **ev})
        s = buf.getvalue().strip()
        return json.loads(s)["hookSpecificOutput"] if s else {}

    grep = {"tool_name": "Grep", "tool_input": {"pattern": "login"}}
    assert run("pre", **grep).get("permissionDecision") == "deny", "code grep before codegraph -> deny"
    assert run("pre", **grep).get("permissionDecision") == "deny", "parallel burst counts once"
    assert run("pre", tool_name="Grep", tool_input={"pattern": "x", "glob": "*.md"}) == {}, "doc search passes"
    assert run("pre", tool_name="Bash", tool_input={"command": "ls -la"}) == {}, "plain bash passes"
    assert run("pre", tool_name="Bash", tool_input={"command": "grep -rn TODO notes.log"}) == {}, "log search passes"
    assert run("pre", tool_name="Bash", tool_input={"command": "rtk rg handleLogin src"}).get("permissionDecision") == "deny"
    r = run("pre", tool_name="Read", tool_input={"file_path": os.path.join(repo, "a.ts")})
    assert "additionalContext" in r and "permissionDecision" not in r, "Read nudges, never blocks"
    assert run("pre", tool_name="Read", tool_input={"file_path": os.path.join(repo, "b.ts")}) == {}, "nudge once"
    assert run("pre", tool_name="Grep", tool_input={"pattern": "x", "path": "/etc"}) == {}, "outside repo passes"
    run("post", tool_name="mcp__codegraph__codegraph_explore", tool_response={"is_error": True})
    assert run("pre", **grep).get("permissionDecision") == "deny", "failed codegraph call does not unlock"
    run("post", tool_name="mcp__codegraph__codegraph_explore", tool_response="source...")
    assert run("pre", **grep) == {}, "after a codegraph call, grep passes"
    # cap: a fresh session whose codegraph never works is released after 2 denials
    k = key({"session_id": "s2"}, os.path.realpath(repo))
    open(k + ".denied", "w").write(f"{MAX_DENIALS} 0")
    capped = run("pre", session_id="s2", **grep)
    assert "permissionDecision" not in capped and "additionalContext" in capped, "cap releases"
    assert "GRAPH_REPORT" in run("prompt", prompt="How does the auth module fit into the architecture?").get("additionalContext", "")
    assert run("prompt", prompt="rename this variable") == {}
    plain = os.path.join(d, "plain")
    os.makedirs(plain)
    assert run("pre", cwd=plain, **grep) == {}, "no index -> no gate"
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
        sys.exit(0)
    try:
        main(sys.argv[1] if len(sys.argv) > 1 else "", json.load(sys.stdin))
    except Exception as e:  # fail open: a broken gate must never block work
        log({"act": "error", "err": str(e)[:200]})
    sys.exit(0)
