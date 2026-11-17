"""Weekly aggregation for setup-monitor.py: transcripts -> one dict of markers per ISO week. No network, no Claude tokens."""
import glob
import os
import re
import sqlite3
import statistics as st
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import monitor_scan as S

HOME = os.path.expanduser("~")
PROJECTS = os.path.join(HOME, ".claude/projects")
REWORK = re.compile(r"\b(fix|fixes|fixed|revert|redo|undo|oops|again|broken|regression|restore)\b", re.I)


def week_of(t):
    y, w, _ = datetime.fromtimestamp(t).isocalendar()
    return f"{y}-W{w:02d}"


def week_bounds(week):
    y, w = week.split("-W")
    start = datetime.fromisocalendar(int(y), int(w), 1)
    return start.timestamp(), (start + timedelta(days=7)).timestamp()


def med(xs):
    return round(st.median(xs), 4) if xs else None


def is_headless(cwd):
    """Scripted runs: eval harnesses in temp folders and the app's scratch workspaces (summarisers, memory jobs)."""
    return not cwd or cwd.startswith(("/var/folders", "/private/var/folders", "/tmp", "/private/tmp")) or "/scratch-" in cwd


def new_week():
    return defaultdict(list) | {"c": defaultdict(float)}


def collect(since, files=None):
    """{week: {"c": counters, list markers...}} for everything from `since` (epoch s)."""
    W = defaultdict(new_week)
    mains = files if files is not None else [f for f in glob.glob(PROJECTS + "/*/*.jsonl") if os.path.getmtime(f) >= since]
    subs_by_parent = defaultdict(list)
    for f in glob.glob(PROJECTS + "/*/*/subagents/*.jsonl") if files is None else []:
        if os.path.getmtime(f) >= since:
            subs_by_parent[os.path.dirname(os.path.dirname(f))].append(f)
    cwds, seen = set(), set()
    for f in sorted(mains, key=os.path.getmtime):
        try:
            r = S.scan(f, since, seen=seen)
        except OSError:
            continue
        if r["cwd"]:
            cwds.add(r["cwd"])
        sub_cost, sub_first = 0.0, []
        for sf in [] if is_headless(r["cwd"]) or r.get("automated") else subs_by_parent.get(os.path.splitext(f)[0], []):
            try:
                sr = S.scan(sf, since, sub=True, seen=seen)
            except OSError:
                continue
            reqs = sorted(sr["reqs"].values(), key=lambda x: x[0])
            if reqs:
                sub_first.append((reqs[0][0], S.ctx(reqs[0][2])))
            for t, m, u in reqs:
                c = S.cost(m, u)
                sub_cost += c
                w = W[week_of(t)]["c"]
                w["usd_sub"] += c
                w["usd"] += c
                w["usd_top"] += c if S.fam(m) in ("opus", "fable") else 0
            add_tools(W, sr, sub=True)
            for t, c in sub_first:
                W[week_of(t)]["first_sub"].append(c)
            sub_first = []
        fold_main(W, r, sub_cost)
    return W, cwds


def add_tools(W, r, sub=False):
    by_id = {}
    for tid, err, blocked, t in r["results"]:
        by_id[tid] = (err, blocked)
    test_failed = False
    for tid, (name, inp, t) in sorted(r["tools"].items(), key=lambda x: x[1][2]):
        c = W[week_of(t)]["c"]
        c["tool_calls"] += 1
        err, blocked = by_id.get(tid, (False, False))
        c["tool_err"] += err
        c["tool_blocked"] += blocked
        if name == "Bash" and S.TEST_CMD.search(str(inp.get("command", ""))):
            c["test_runs"] += 1
            c["test_pass"] += not err
            c["test_retry"] += test_failed
            test_failed = err


def fold_main(W, r, sub_cost):
    reqs = r["reqs"]
    if not reqs and not r["turns"]:
        return
    if is_headless(r["cwd"]) or r.get("automated") or not reqs:  # eval harnesses and scripted runs: counted apart so they never skew the markers
        t0 = min(v[0] for v in reqs.values()) if reqs else r["turns"][0][0]
        k = W[week_of(t0)]["c"]
        k["headless"] += 1
        k["usd_headless"] += sum(S.cost(m, u) for _, m, u in reqs.values()) + sub_cost
        return
    work = bool(r["edits"])
    kind = "work" if work else "chat"
    per_turn = defaultdict(lambda: [0, 0, 0, 0.0])  # ctx, reqs, out, usd
    session_usd, first = sub_cost, None
    prev = None
    for mid, (t, m, u) in sorted(reqs.items(), key=lambda x: x[1][0]):
        c, usd, w = S.ctx(u), S.cost(m, u), W[week_of(t)]
        first = first if first is not None else c
        session_usd += usd
        k = w["c"]
        k["usd"] += usd
        k["usd_top"] += usd if S.fam(m) in ("opus", "fable") else 0
        k["main_reqs"] += 1
        k["ctx"] += c
        k["cache_read"] += u.get("cache_read_input_tokens") or 0
        k["long_reqs"] += c > 250_000
        if prev is not None and c > 100_000 and (u.get("cache_read_input_tokens") or 0) < 0.1 * c:
            k["cache_miss"] += 1
        prev = c
        ti = r["req_turn"].get(mid)
        if ti is not None:
            p = per_turn[ti]
            p[0] += c; p[1] += 1; p[2] += u.get("output_tokens") or 0; p[3] += usd
    for i, (t, text, hook_chars, interrupted) in enumerate(r["turns"]):
        w = W[week_of(t)]
        k = w["c"]
        k["turns"] += 1
        k["turns_" + kind] += 1
        k["interrupts"] += interrupted
        if S.is_correction(text):
            k["corrections"] += 1
            if len(w["correction_examples"]) < 5:
                w["correction_examples"].append(text.strip().replace("\n", " ")[:120])
        w["hook_chars"].append(hook_chars)
        if i in per_turn:
            p = per_turn[i]
            w["turn_ctx"].append(p[0]); w["turn_reqs"].append(p[1]); w["turn_out"].append(p[2])
            w["turn_usd"].append(p[3]); w["turn_usd_" + kind].append(p[3])
    start = min([v[0] for v in reqs.values()] + [x[0] for x in r["turns"]])
    w = W[week_of(start)]
    w["c"]["sessions"] += 1
    w["c"]["sessions_" + kind] += 1
    w["c"]["sessions_ui"] += r["ui_edits"] > 0
    if first is not None:
        w["first_main"].append(first)
    w["session_usd_" + kind].append(session_usd)
    for t in r["compact"]:
        W[week_of(t)]["c"]["compacts"] += 1
    for t in r["hook_fail"]:
        W[week_of(t)]["c"]["hook_fail"] += 1
    for n in r["findings"]:
        w["findings"].append(n)
    add_tools(W, r)


def git_rework(repos, a, b):
    """(commits, rework commits) across repos between epoch a and b."""
    total = rework = 0
    for repo in repos:
        try:
            out = subprocess.run(["git", "-C", repo, "log", "--no-merges", f"--since={int(a) - 86400}", f"--until={int(b)}",
                                 "--format=@%at|%s", "--name-only"], capture_output=True, text=True, timeout=30).stdout
        except Exception:
            continue
        commits = []
        for block in out.split("\n@")[0:]:
            head, *files = block.lstrip("@").split("\n")
            if "|" not in head:
                continue
            at, subj = head.split("|", 1)
            commits.append((int(at), subj, {f for f in files if f.strip()}))
        commits.sort()
        for i, (at, subj, files) in enumerate(commits):
            if not a <= at < b:
                continue
            total += 1
            if subj.lower().startswith("revert") or (REWORK.search(subj) and any(
                    files & f2 for at2, _, f2 in commits[:i] if at - at2 <= 86400)):
                rework += 1
    return total, rework


def repos_of(cwds):
    out = set()
    for c in cwds:
        try:
            top = subprocess.run(["git", "-C", c, "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=5).stdout.strip()
        except Exception:
            continue
        if top and "/.claude/" not in top and "/tmp" not in top and "/var/folders" not in top:
            out.add(top)
    return out


def rtk_week(a, b):
    for p in ("~/Library/Application Support/rtk/history.db", "~/.local/share/rtk/history.db"):
        p = os.path.expanduser(p)
        if os.path.exists(p):
            try:
                con = sqlite3.connect(p, timeout=2)
                iso = lambda t: datetime.fromtimestamp(t, timezone.utc).isoformat()[:19]
                saved = con.execute("select coalesce(sum(max(saved_tokens,0)),0) from commands"
                                    " where timestamp >= ? and timestamp < ?", (iso(a), iso(b))).fetchone()[0]
                con.close()
                return saved
            except sqlite3.Error:
                return None
    return None


def ctxmode_week(a, b):
    n, found = 0, False
    for db in glob.glob(os.path.join(HOME, ".context-mode/projects/*/context.db")):
        try:
            con = sqlite3.connect(db, timeout=2)
            n += con.execute("select coalesce(sum(max(sandbox_bytes - returned_bytes, 0)), 0) from events"
                             " where created_at >= ? and created_at < ?", (a * 1000, b * 1000)).fetchone()[0]
            con.close()
            found = True
        except sqlite3.Error:
            continue
    return n if found else None


def jev_failopens(a, b):
    p = os.path.join(HOME, ".claude/jev/failopen.log")
    if not os.path.exists(p):
        return None
    n = 0
    for line in open(p, errors="ignore"):
        m = re.search(r'"ts": (\d+)', line)
        n += bool(m) and a <= int(m.group(1)) < b
    return n
