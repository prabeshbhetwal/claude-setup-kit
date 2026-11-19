#!/usr/bin/env python3
"""Daily token report: yesterday vs the same weekday last week, plus the estimated saving since the change day (see token-compare.py).

  python3 ~/.claude/hooks/token-daily.py [YYYY-MM-DD] [--notify]     # day defaults to yesterday
  python3 ~/.claude/hooks/token-daily.py selftest

Tokens = context read per request (input + cache_read + cache_creation), deduped by message.id, counted on the day
the request was made. Saving is an estimate: for each session type, (median first-request context in the frozen
before-period) minus (median since the trim), times that type's requests on the day. "Without the trim" = used + saving.
"""
import glob
import importlib.machinery
import importlib.util
import json
import os
import statistics as st
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta

_loader = importlib.machinery.SourceFileLoader("token_compare", os.path.expanduser("~/.claude/hooks/token-compare.py"))
TC = importlib.util.module_from_spec(importlib.util.spec_from_loader("token_compare", _loader))
_loader.exec_module(TC)  # reuse its transcript reader, strata and frozen baseline

OUT = os.path.join(TC.OUT, "daily")
MIN_N = 5


def scan(day):
    """Per-day totals for `day` and the same weekday a week earlier, and post-trim session facts per stratum."""
    days = {day: defaultdict(int), day - timedelta(days=7): defaultdict(int)}
    by_type = defaultdict(int)          # requests on `day` from sessions started after the trim, per stratum
    firsts = defaultdict(list)          # first-request context of every session started after the trim
    seen = set()                        # message ids already counted from other files (resumed or forked sessions)
    floor = (day - timedelta(days=8)).timestamp()
    for kind, pattern in (("main", "/*/*.jsonl"), ("sub", "/*/*/subagents/*.jsonl")):
        for f in glob.glob(TC.P + pattern):
            if os.path.getmtime(f) < min(floor, TC.AFTER[0].timestamp()):
                continue
            whole = TC.requests(f)  # the session's own first request, even when an earlier file holds a copy of it
            if not whole:
                continue
            key = (kind, whole[0][3], TC.fam(whole[0][1]))
            post = whole[0][0] >= TC.AFTER[0]
            if post:
                firsts[key].append(TC.ctx(whole[0][2]))
            reqs = TC.requests(f, seen)  # usage totals: each message once across all files
            for t, _, u, _ in reqs:
                d = days.get(t.replace(hour=0, minute=0, second=0, microsecond=0))
                if d is None:
                    continue
                d["requests"] += 1
                d["tokens"] += TC.ctx(u)
                d["output"] += u.get("output_tokens") or 0
                d[kind] += 1
                if post and d is days[day]:
                    by_type[key] += 1
    return days, by_type, firsts


def saving(by_type, firsts, baseline):
    """(estimated tokens saved on the day, requests covered, requests on the day from post-trim sessions)."""
    base = defaultdict(list)
    for r in baseline:
        base[(r["kind"], r["ep"], r["fam"])].append(r["first"])
    saved = covered = 0
    for key, n in by_type.items():
        if len(base[key]) >= MIN_N and len(firsts[key]) >= MIN_N:
            saved += (st.median(base[key]) - st.median(firsts[key])) * n
            covered += n
    return saved, covered, sum(by_type.values())


def pct(new, old):
    return f"{100 * (new - old) / old:+.0f}%" if old else "n/a"


def render(day, days, est):
    y, w = days[day], days[day - timedelta(days=7)]
    saved, covered, post = est
    L = [f"# Tokens on {day:%a %d %b %Y} vs {day - timedelta(days=7):%a %d %b}", "",
         f"| | {day:%a %d %b} | {day - timedelta(days=7):%a %d %b} | Change |", "|---|---|---|---|"]
    for label, k in (("Tokens read as context", "tokens"), ("Requests", "requests"), ("Output tokens", "output")):
        show = TC.fm if k != "requests" else str
        L.append(f"| {label} | {show(y[k])} | {show(w[k])} | {pct(y[k], w[k])} |")
    per = [d["tokens"] / d["requests"] if d["requests"] else 0 for d in (y, w)]
    L.append(f"| Average context per request | {TC.fm(per[0])} | {TC.fm(per[1])} | {pct(per[0], per[1])} |")
    L.append("")
    if covered:
        L += [f"**Estimated saved by the trim: {TC.fm(saved)} tokens** "
              f"({100 * saved / (y['tokens'] + saved):.1f}% of the {TC.fm(y['tokens'] + saved)} it would have used without it).",
              f"Estimate covers {covered} of {y['requests']} requests; a negative figure means first requests grew."]
    else:
        L.append(f"**Saving: not enough data yet.** Needs {MIN_N}+ sessions of one type started since "
                 f"{TC.AFTER[0]:%d %b} ({post} requests from such sessions on this day).")
    L.append("The day-to-day change follows how much you worked; the saving line is the part the setup explains.")
    return "\n".join(L)


def summary(day, days, est):
    y, w = days[day], days[day - timedelta(days=7)]
    s = f"saved est. {TC.fm(est[0])}" if est[1] else "saving: not enough data yet"
    return f"{day:%a %d %b}: {TC.fm(y['tokens'])} tokens ({pct(y['tokens'], w['tokens'])} vs last {day:%a}), {s}"


def selftest():
    day = datetime(2026, 11, 20)
    days = {day: defaultdict(int, tokens=900, requests=10, output=5), day - timedelta(days=7): defaultdict(int, tokens=1000, requests=10, output=5)}
    key = ("main", "cli", "opus")
    est = saving({key: 10}, {key: [90] * 5}, [{"kind": "main", "ep": "cli", "fam": "opus", "first": 100}] * 5)
    assert est == (100, 10, 10), est  # (100 - 90) x 10 requests
    text = render(day, days, est)
    assert "-10%" in text and "10.0% of the 1.0k" in text, text
    assert saving({key: 10}, {key: [90] * 2}, [])[1] == 0  # too few sessions: no estimate
    import tempfile, json, glob as _g  # a resumed session's transcript repeats message m1: the daily total counts it once
    d = tempfile.mkdtemp()
    for name in ("a", "b"):
        os.makedirs(os.path.join(d, name))
        open(os.path.join(d, name, "s.jsonl"), "w").write(json.dumps({"type": "assistant", "timestamp": "2026-11-20T01:00:00Z", "message": {"id": "m1", "model": "claude-opus-5", "usage": {"input_tokens": 7}}}) + "\n")
    TC.P = d
    assert scan(datetime(2026, 11, 20))[0][datetime(2026, 11, 20)]["tokens"] == 7, "a copied message must count once"
    print("selftest ok")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--notify"]
    if args == ["selftest"]:
        selftest()
        sys.exit(0)
    day = datetime.strptime(args[0], "%Y-%m-%d") if args else (datetime.now() - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    days, by_type, firsts = scan(day)
    baseline = json.load(open(TC.SNAP)) if os.path.exists(TC.SNAP) else []
    est = saving(by_type, firsts, baseline)
    text = render(day, days, est)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{day:%Y-%m-%d}.md")
    open(path, "w").write(text + "\n")
    print(text)
    if "--notify" in sys.argv and sys.platform == "darwin":  # osascript notification is macOS-only
        # Text goes in as argv, never into the script, so quotes or backslashes in it can't break or inject AppleScript.
        sub = "Full report: " + path.replace(os.path.expanduser("~"), "~")
        subprocess.run(["osascript", "-e", "on run argv", "-e", 'display notification (item 1 of argv) with title "Claude tokens" subtitle (item 2 of argv)',
                        "-e", "end run", summary(day, days, est), sub], check=False)
