#!/usr/bin/env python3
"""Per-tool lines for the monthly token report (token-monthly.py loads this). Measured and estimated stay in separate columns.

  python3 ~/.claude/hooks/token-tools.py selftest

  Caveman      - output tokens its own log (~/.claude/.caveman-history.jsonl) attributes to a Caveman mode. It logs
                 no without-Caveman comparison, so no saving is claimed.
  context-mode - bytes it kept out of context, from its own records: sandbox_bytes - returned_bytes per event in
                 ~/.context-mode/projects/*/context.db, plus kept_out in older stats-pid-*.json files dated before
                 the first database event. The token figure beside it is an estimate (4 bytes per token).
  CodeGraph, Graphify - calls found in the transcripts and the size of what they returned. No saving is estimated:
                 nothing records what the searches and file reads they replaced would have cost.
None of these is added to the report's totals: RTK and context-mode both trim shell output.
"""
import glob
import importlib.machinery
import importlib.util
import json
import os
import pathlib
import sqlite3
import sys
import tempfile
from datetime import datetime

_l = importlib.machinery.SourceFileLoader("token_compare", os.path.join(os.path.dirname(os.path.abspath(__file__)), "token-compare.py"))
TC = importlib.util.module_from_spec(importlib.util.spec_from_loader("token_compare", _l))
_l.exec_module(TC)  # its transcript folder and number format


def caveman(start, end, path=None):
    """(output tokens written in a Caveman mode, sessions) from Caveman's own log, latest snapshot per session; None without a log."""
    path = path or os.path.expanduser("~/.claude/.caveman-history.jsonl")
    if not os.path.exists(path):
        return None
    last = {}
    for line in open(path, errors="ignore"):
        try:
            o = json.loads(line)
            if start <= datetime.fromtimestamp(o["ts"] / 1000) < end:
                last[o.get("session_id")] = o
        except Exception:
            continue
    on = [sum(v for m, v in (o.get("output_tokens_by_mode") or {}).items() if m not in ("none", "off")) for o in last.values()]
    return sum(on), sum(1 for v in on if v)


def context_mode(start, end, home=None):
    """Bytes context-mode's own records say it kept out of context in the month; None when it left no records."""
    home = home or os.path.expanduser("~")
    lo, hi = start.timestamp() * 1000, end.timestamp() * 1000
    dbs = glob.glob(os.path.join(home, ".context-mode", "projects", "*", "context.db"))
    old = glob.glob(os.path.join(home, ".claude", "context-mode*", "sessions", "stats-pid-*.json"))
    if not dbs and not old:
        return None
    kept, first = 0, float("inf")
    for db in dbs:
        try:
            con = sqlite3.connect(pathlib.Path(db).as_uri() + "?mode=ro", uri=True)  # read-only: never touches a live database
            first = min(first, con.execute("select min(created_at) from events").fetchone()[0] or first)
            kept += con.execute("select coalesce(sum(max(sandbox_bytes - returned_bytes, 0)), 0) from events"
                                " where created_at >= ? and created_at < ?", (lo, hi)).fetchone()[0]
            con.close()
        except Exception:
            continue
    for f in old:  # older versions: one file per server process; counted only before the databases start, so nothing is counted twice
        try:
            o = json.load(open(f))
            if lo <= (o.get("updated_at") or 0) < min(hi, first):
                kept += o.get("kept_out") or 0
        except Exception:
            continue
    return kept


def which(name, inp):
    text = str(inp.get("command") or inp.get("file_path") or inp.get("file") or inp.get("path") or inp.get("pattern") or "")
    if "codegraph" in name or (name == "Bash" and "codegraph explore" in text):
        return "codegraph"
    if name not in ("Write", "Edit") and "graphify-out" in text:
        return "graphify"
    return None


def tool_calls(start, end, root=None):
    """CodeGraph and Graphify use in the month's transcripts: {tool: [calls, bytes returned to context]}."""
    n = {"codegraph": [0, 0], "graphify": [0, 0]}
    root, seen = root or TC.P, set()  # seen: resumed sessions copy earlier lines into a new file
    for f in glob.glob(root + "/*/*.jsonl") + glob.glob(root + "/*/*/subagents/*.jsonl"):
        if os.path.getmtime(f) < start.timestamp():
            continue
        pending = {}
        for line in open(f, errors="ignore"):
            call = '"tool_use"' in line and ("codegraph" in line or "graphify-out" in line)
            if not call and not ('"tool_result"' in line and any(i in line for i in pending)):
                continue
            try:
                o = json.loads(line)
                t = datetime.fromisoformat(o["timestamp"].replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
                blocks = o["message"]["content"]
            except Exception:
                continue
            for b in blocks if isinstance(blocks, list) else []:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use" and start <= t < end and b.get("id") not in seen:
                    tool = which(b.get("name") or "", b.get("input") or {})
                    if tool:
                        seen.add(b.get("id"))
                        pending[b.get("id")] = tool
                        n[tool][0] += 1
                elif b.get("type") == "tool_result" and b.get("tool_use_id") in pending:
                    c = b.get("content")
                    text = c if isinstance(c, str) else "".join(x.get("text") or "" for x in c or [] if isinstance(x, dict))
                    n[pending.pop(b["tool_use_id"])][1] += len(text.encode())
    return n


def fb(x):
    return f"{x / 1e6:.1f} MB" if x >= 1e6 else f"{x / 1e3:.1f} KB"


def lines(tools):
    cav, kept = tools["caveman"], tools["context-mode"]
    L = ["", "| Per tool (not added to the totals) | Measured | Estimated saving |", "|---|---|---|",
         f"| Caveman | {TC.fm(cav[0])} output tokens written in a Caveman mode, {cav[1]} sessions (its own log) | none: its log has no without-Caveman comparison |"
         if cav else "| Caveman | no Caveman log found | none |",
         f"| context-mode | {fb(kept)} of tool output kept out of context (its own count) | ~{TC.fm(kept / 4)} tokens, at 4 bytes per token, each byte counted once |"
         if kept is not None else "| context-mode | no context-mode records found | none |"]
    for key, label in (("codegraph", "CodeGraph"), ("graphify", "Graphify")):
        calls, size = tools[key]
        L.append(f"| {label} | {calls} {'calls' if key == 'codegraph' else 'reads of graphify-out'}, {fb(size)} returned | none: nothing records what the searches and file reads it replaced would have cost |")
    return L


def collect(start, end):
    return {"caveman": caveman(start, end), "context-mode": context_mode(start, end), **tool_calls(start, end)}


def selftest():
    start, end = datetime(2026, 12, 1), datetime(2027, 1, 1)
    ms = lambda day: datetime(2026, 12, day).timestamp() * 1000
    with tempfile.TemporaryDirectory() as d:
        hist = os.path.join(d, "history.jsonl")  # two snapshots of one session (latest wins), one from another month
        rows = [{"ts": ms(2), "session_id": "a", "output_tokens_by_mode": {"ultracave": 50}},
                {"ts": ms(3), "session_id": "a", "output_tokens_by_mode": {"ultracave": 700, "none": 300}},
                {"ts": ms(4), "session_id": "b", "output_tokens_by_mode": {"none": 90}},
                {"ts": datetime(2026, 11, 30).timestamp() * 1000, "session_id": "c", "output_tokens_by_mode": {"ultracave": 9}}]
        open(hist, "w").write("\n".join(map(json.dumps, rows)) + "\nnot json\n")
        assert caveman(start, end, hist) == (700, 1) and caveman(start, end, hist + ".missing") is None
        assert context_mode(start, end, d) is None
        os.makedirs(os.path.join(d, ".context-mode", "projects", "p"))
        con = sqlite3.connect(os.path.join(d, ".context-mode", "projects", "p", "context.db"))
        con.execute("create table events (sandbox_bytes, returned_bytes, created_at)")
        con.executemany("insert into events values (?, ?, ?)", [(5000, 1000, ms(10)), (100, 400, ms(11)), (9000, 0, datetime(2027, 1, 2).timestamp() * 1000)])
        con.commit()
        con.close()
        os.makedirs(os.path.join(d, ".claude", "context-mode.old", "sessions"))
        for pid, day in ((1, 5), (2, 20)):  # the second is dated after the first database event, so it is skipped
            json.dump({"updated_at": ms(day), "kept_out": 2000}, open(os.path.join(d, ".claude", "context-mode.old", "sessions", f"stats-pid-{pid}.json"), "w"))
        assert context_mode(start, end, d) == 6000, context_mode(start, end, d)
        os.makedirs(os.path.join(d, "projects", "x"))
        use = lambda i, name, inp, ts="2026-12-05T02:00:00Z": json.dumps({"timestamp": ts, "message": {"content": [{"type": "tool_use", "id": i, "name": name, "input": inp}]}})
        res = lambda i, text: json.dumps({"timestamp": "2026-12-05T02:00:01Z", "message": {"content": [{"type": "tool_result", "tool_use_id": i, "content": [{"type": "text", "text": text}]}]}})
        rows = [use("t1", "mcp__codegraph__codegraph_explore", {"query": "q"}), res("t1", "x" * 300),
                 use("t2", "Read", {"file_path": "/r/graphify-out/GRAPH_REPORT.md"}), res("t2", "y" * 40),
                 use("t3", "Write", {"file_path": "/r/graphify-out/x.md"}), use("t4", "Bash", {"command": "codegraph explore q"}, "2026-10-01T02:00:00Z")]
        for name in ("s1.jsonl", "s2.jsonl"):  # s2 is a resumed copy: the same ids must not count twice
            open(os.path.join(d, "projects", "x", name), "w").write("\n".join(rows) + "\n")
            os.utime(os.path.join(d, "projects", "x", name), (ms(6) / 1000,) * 2)  # files untouched since before the month are skipped
        calls = tool_calls(start, end, os.path.join(d, "projects"))
        assert calls == {"codegraph": [1, 300], "graphify": [1, 40]}, calls
    tools = {"caveman": (700, 1), "context-mode": 6000, **calls}
    text = "\n".join(lines(tools))
    assert "~1.5k tokens" in text and "| Graphify | 1 reads of graphify-out, 0.0 KB returned" in text, text
    return tools


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
        print("selftest ok")
