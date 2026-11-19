#!/usr/bin/env python3
"""Stop hook: one ledger line per finished turn, with the tokens it used and what the kit's tools saved in it.

  (hook)  reads {"session_id", "transcript_path"} on stdin; appends to ~/.claude/cache/token-compare/ledger.jsonl
  python3 ~/.claude/hooks/token-ledger.py selftest

A turn = from the last prompt you typed to now, including helper agents (subagent transcripts) that ran in it.
  used      context read per request (input + cache_read + cache_creation, deduped by message.id) and output tokens
  rtk_saved          RTK's own count for the shell commands of this turn (its history.db): measured
  ctx_saved_bytes    bytes context-mode kept out of context in this session during the turn (its context.db): measured
                     bytes; the report turns them into tokens at 4 bytes per token (an estimate)
  pilot_saved_usd    Model pilot's estimated saving for the turn against the menu model (its log): an estimate
A source that is not installed is null, never 0. No network, no Claude tokens. Never blocks: any error exits 0.
"""
import glob
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

OUT = os.path.expanduser("~/.claude/cache/token-compare")
LEDGER = os.path.join(OUT, "ledger.jsonl")


def when(s):
    return datetime.fromisoformat(str(s).replace("Z", "+00:00"))


def rtk_db():
    for p in ("~/Library/Application Support/rtk/history.db", "~/.local/share/rtk/history.db",
              os.path.join(os.environ.get("APPDATA", "~/AppData/Roaming"), "rtk", "history.db")):
        p = os.path.expanduser(p)
        if os.path.exists(p):
            return p
    return None


def rtk_saved(start, end, cmds=None, db=None):
    """Tokens RTK saved between start and end (aware datetimes); only commands in cmds when given. None without RTK."""
    db = db or rtk_db()
    if not db:
        return None
    try:  # a plain connection: these databases use WAL, which a read-only open cannot always join
        con = sqlite3.connect(db, timeout=2)
        rows = con.execute("select timestamp, original_cmd, rtk_cmd, saved_tokens from commands where timestamp >= ?",
                           (start.astimezone(timezone.utc).isoformat()[:19],)).fetchall()
        con.close()
    except sqlite3.Error:
        return None
    n = 0
    for ts, orig, rcmd, saved in rows:
        try:
            t = when(ts)
        except ValueError:
            continue
        if start <= t < end and (cmds is None or orig.strip() in cmds or rcmd.strip() in cmds):
            n += max(saved or 0, 0)
    return n


def ctx_saved(session, start, end, home=None):
    """Bytes context-mode kept out of context for one session between start and end. None without context-mode."""
    dbs = glob.glob(os.path.join(home or os.path.expanduser("~"), ".context-mode", "projects", "*", "context.db"))
    if not dbs:
        return None
    a, b, n = start.timestamp() * 1000, end.timestamp() * 1000, 0
    for db in dbs:
        try:
            con = sqlite3.connect(db, timeout=2)
            n += con.execute("select coalesce(sum(max(sandbox_bytes - returned_bytes, 0)), 0) from events "
                             "where session_id = ? and created_at >= ? and created_at < ?", (session, a, b)).fetchone()[0]
            con.close()
        except sqlite3.Error:
            continue
    return n


def tail(path, size):
    """The last `size` bytes of a file as lines, without a cut first line (whole file when it is smaller)."""
    with open(path, "rb") as f:
        f.seek(0, 2)
        cut = f.tell() > size
        f.seek(max(0, f.tell() - size))
        # Split on JSONL's own "\n" only: splitlines() would also break records at U+2028 and friends.
        lines = [b.decode("utf-8", "replace") for b in f.read().split(b"\n") if b]
    return lines[1:] if cut else lines


def pilot_saved(session, start, end, path=None):
    """Model pilot's estimated saving (US dollars) for the session's turns that ended in the window. None without its log."""
    path = path or os.path.expanduser("~/.claude/mods-logs/model-pilot.jsonl")
    if not os.path.exists(path):
        return None
    usd = 0.0
    for line in tail(path, 1 << 20):  # this turn's lines are at the end; never re-read the whole log
        if session not in line:
            continue
        try:
            d = json.loads(line)
            if d.get("session") == session and start <= when(d["ts"]) <= end and not d.get("shadow"):
                usd += d.get("est_saving_usd") or 0
        except (ValueError, KeyError, TypeError):
            continue
    return round(usd, 6)


def typed(o):
    """True for a prompt the person typed (not a tool result, not a hook or system note)."""
    if o.get("type") != "user" or o.get("isMeta") or o.get("toolUseResult") is not None:
        return False
    c = (o.get("message") or {}).get("content")
    if isinstance(c, str):
        return not c.startswith("<")
    return any(isinstance(b, dict) and b.get("type") == "text" for b in c or []) and not any(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in c or [])


def turn(transcript, now):
    """(start, requests, context, output, by-family, bash commands) for the last typed prompt up to now."""
    # Read from the end, doubling the window until it holds the last typed prompt: a long chat is not re-read each turn.
    size, total = 1 << 20, os.path.getsize(transcript)
    while True:
        rows = []
        for line in tail(transcript, size):
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
        i = max((k for k, o in enumerate(rows) if typed(o)), default=None)
        if i is not None or size >= total:
            break
        size *= 2
    if i is None:
        return None
    start = when(rows[i]["timestamp"])
    reqs, cmds = {}, set()
    sub = os.path.join(os.path.splitext(transcript)[0], "subagents")
    extra = []
    for f in glob.glob(os.path.join(sub, "*.jsonl")):
        if os.path.getmtime(f) >= start.timestamp():
            for line in open(f, errors="ignore"):
                try:
                    extra.append(json.loads(line))
                except ValueError:
                    pass
    for o in rows[i + 1:] + extra:
        try:
            t = when(o["timestamp"])
        except (KeyError, ValueError):
            continue
        if not start <= t <= now:
            continue
        msg = o.get("message") if isinstance(o.get("message"), dict) else {}
        if o.get("type") == "assistant" and msg.get("usage"):
            reqs[msg.get("id") or o.get("uuid")] = (msg.get("model") or "", msg["usage"])
        for b in msg.get("content") or [] if isinstance(msg.get("content"), list) else []:
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Bash":
                cmds.add(str((b.get("input") or {}).get("command") or "").strip())
    ctx = out = 0
    fams = {}
    for model, u in reqs.values():
        c = (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
        ctx += c
        out += u.get("output_tokens") or 0
        f = next((x for x in ("opus", "sonnet", "haiku", "fable") if x in model.lower()), "other")
        fams[f] = fams.get(f, 0) + c
    return start, len(reqs), ctx, out, fams, cmds


def record(session, transcript, now=None, home=None, ledger=LEDGER, rtk=None, pilot=None):
    now = now or datetime.now(timezone.utc)
    t = turn(transcript, now)
    if not t or not t[1]:
        return None
    start, n, ctx, out, fams, cmds = t
    line = {"ts": now.isoformat()[:19] + "Z", "session": session, "start": start.astimezone(timezone.utc).isoformat()[:19] + "Z",
            "requests": n, "context": ctx, "output": out, "by_model": fams,
            "rtk_saved": rtk_saved(start, now, cmds, rtk) if cmds else (0 if rtk or rtk_db() else None),
            "ctx_saved_bytes": ctx_saved(session, start, now, home), "pilot_saved_usd": pilot_saved(session, start, now, pilot)}
    os.makedirs(os.path.dirname(ledger), exist_ok=True)
    with open(ledger, "a") as f:
        f.write(json.dumps(line) + "\n")
    return line


def selftest():
    import tempfile as _t
    with _t.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("aaaa\nb\u2028b\ncc\n")
    assert tail(f.name, 5) == ["cc"] and tail(f.name, 99) == ["aaaa", "b\u2028b", "cc"], tail(f.name, 99)
    os.remove(f.name)
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        tr = os.path.join(d, "s.jsonl")
        J = lambda **o: json.dumps(o)
        rows = [J(type="user", timestamp="2026-12-05T01:00:00Z", message={"content": "old prompt"}),
                J(type="assistant", timestamp="2026-12-05T01:00:05Z", message={"id": "m0", "model": "claude-opus-5-5", "usage": {"input_tokens": 999}}),
                J(type="user", timestamp="2026-12-05T02:00:00Z", message={"content": "new prompt"}),
                J(type="assistant", timestamp="2026-12-05T02:00:05Z", message={"id": "m1", "model": "claude-opus-5-5", "usage": {"input_tokens": 10, "cache_read_input_tokens": 1000, "output_tokens": 50},
                  "content": [{"type": "tool_use", "name": "Bash", "input": {"command": "rtk git status"}}]}),
                J(type="assistant", timestamp="2026-12-05T02:00:05Z", message={"id": "m1", "model": "claude-opus-5-5", "usage": {"input_tokens": 10, "cache_read_input_tokens": 1000, "output_tokens": 50}}),
                J(type="user", timestamp="2026-12-05T02:00:06Z", toolUseResult={}, message={"content": [{"type": "tool_result", "content": "x"}]}),
                J(type="user", timestamp="2026-12-05T02:00:07Z", isMeta=True, message={"content": "<hook note>"}),
                J(type="assistant", timestamp="2026-12-05T02:00:09Z", message={"id": "m2", "model": "claude-opus-5-5", "usage": {"input_tokens": 5, "cache_creation_input_tokens": 200, "output_tokens": 20}})]
        open(tr, "w").write("\n".join(rows) + "\nnot json\n")
        os.makedirs(os.path.join(d, "s", "subagents"))
        open(os.path.join(d, "s", "subagents", "a.jsonl"), "w").write(
            J(type="assistant", timestamp="2026-12-05T02:00:08Z", message={"id": "h1", "model": "claude-haiku-5-5", "usage": {"input_tokens": 300, "output_tokens": 7}}) + "\n")
        now = when("2026-12-05T02:01:00Z")
        os.utime(os.path.join(d, "s", "subagents", "a.jsonl"), (now.timestamp(),) * 2)  # helpers untouched since before the turn are skipped
        start, n, ctx, out, fams, cmds = turn(tr, now)
        assert (n, ctx, out) == (3, 1515, 77) and fams == {"opus": 1215, "haiku": 300} and cmds == {"rtk git status"}, (n, ctx, out, fams)
        db = os.path.join(d, "history.db")
        con = sqlite3.connect(db)
        con.execute("create table commands (timestamp, original_cmd, rtk_cmd, saved_tokens)")
        con.executemany("insert into commands values (?,?,?,?)", [("2026-12-05T02:00:06.1+00:00", "git status", "rtk git status", 400),
                                                                    ("2026-12-05T02:00:07+00:00", "ls", "rtk ls", 99),  # another session's command
                                                                    ("2026-12-05T00:00:00+00:00", "git status", "rtk git status", 7)])
        con.commit(); con.close()
        assert rtk_saved(start, now, cmds, db) == 400 and rtk_saved(start, now, None, db) == 499
        os.makedirs(os.path.join(d, ".context-mode", "projects", "p"))
        con = sqlite3.connect(os.path.join(d, ".context-mode", "projects", "p", "context.db"))
        con.execute("create table events (session_id, sandbox_bytes, returned_bytes, created_at)")
        ms = lambda s: when(s).timestamp() * 1000
        con.executemany("insert into events values (?,?,?,?)", [("S", 9000, 1000, ms("2026-12-05T02:00:06Z")), ("S", 10, 50, ms("2026-12-05T02:00:07Z")),
                                                                 ("T", 5000, 0, ms("2026-12-05T02:00:06Z")), ("S", 5000, 0, ms("2026-12-05T01:00:00Z"))])
        con.commit(); con.close()
        assert ctx_saved("S", start, now, d) == 8000 and ctx_saved("S", start, now, os.path.join(d, "none")) is None
        plog = os.path.join(d, "pilot.jsonl")
        open(plog, "w").write("\n".join([J(ts="2026-12-05T02:00:59Z", session="S", est_saving_usd=0.25),
                                         J(ts="2026-12-05T02:00:59Z", session="S", est_saving_usd=9, shadow=True),
                                         J(ts="2026-12-05T02:00:59Z", session="T", est_saving_usd=4)]) + "\n")
        assert pilot_saved("S", start, now, plog) == 0.25 and pilot_saved("S", start, now, plog + "x") is None
        led = os.path.join(d, "ledger.jsonl")
        line = record("S", tr, now, d, led, db, plog)
        assert line["requests"] == 3 and line["ctx_saved_bytes"] == 8000 and line["rtk_saved"] == 400 and line["pilot_saved_usd"] == 0.25 and json.loads(open(led).read())["context"] == 1515, line
        open(tr, "a").write(J(type="user", timestamp="2026-12-05T02:02:00Z", message={"content": "no reply yet"}) + "\n")
        assert record("S", tr, when("2026-12-05T02:02:01Z"), d, led, db, plog) is None  # a turn with no request writes nothing
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
        sys.exit(0)
    try:
        hook = json.load(sys.stdin)
        if hook.get("transcript_path") and os.path.exists(hook["transcript_path"]):
            record(hook.get("session_id") or "", hook["transcript_path"])
    except Exception:
        pass  # a measuring hook must never get in the way of a turn
    sys.exit(0)
