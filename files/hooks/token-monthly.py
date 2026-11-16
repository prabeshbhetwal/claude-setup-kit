#!/usr/bin/env python3
"""Monthly token report: what you used, what the kit saved, and what you would have used without it.

  python3 ~/.claude/hooks/token-monthly.py [YYYY-MM] [--notify]    # month defaults to last month
  python3 ~/.claude/hooks/token-monthly.py selftest

install.sh / install.ps1 schedule it for 09:00 on the 1st of each month (launchd / Task Scheduler). No Claude tokens.
Used = context read per request (input + cache_read + cache_creation), deduped by message.id, plus output tokens.
Saved has two parts, reported apart:
  measured  - RTK's own count of shell-output tokens it cut that month (`rtk gain -m`). A floor: cut output would
              also have been re-read as context on every later turn.
  estimated - per session type, (median first-request context in the frozen before-week) minus (median since
              install), times that type's requests in the month; the same method as token-daily.py.
Without the kit ~= used + measured + estimated. Totals follow how much you worked; the saving lines are the kit's part.
"""
import glob
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta


def _load(name, file):
    loader = importlib.machinery.SourceFileLoader(name, os.path.join(os.path.dirname(os.path.abspath(__file__)), file))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(mod)
    return mod


D = _load("token_daily", "token-daily.py")  # its saving() and, through it, token-compare's reader and baseline
TC = D.TC
OUT = os.path.join(TC.OUT, "monthly")


def month_bounds(ym):
    start = datetime.strptime(ym, "%Y-%m")
    end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    return start, end


def scan(start, end):
    """Totals for the month, per-model-family split, and post-install session facts per stratum."""
    tot, fams = defaultdict(int), defaultdict(int)
    by_type, firsts = defaultdict(int), defaultdict(list)
    for kind, pattern in (("main", "/*/*.jsonl"), ("sub", "/*/*/subagents/*.jsonl")):
        for f in glob.glob(TC.P + pattern):
            if os.path.getmtime(f) < min(start.timestamp(), TC.AFTER[0].timestamp()):
                continue
            reqs = TC.requests(f)
            if not reqs:
                continue
            key = (kind, reqs[0][3], TC.fam(reqs[0][1]))
            post = reqs[0][0] >= TC.AFTER[0]
            if post:
                firsts[key].append(TC.ctx(reqs[0][2]))
            for t, model, u, _ in reqs:
                if not start <= t < end:
                    continue
                c = TC.ctx(u)
                tot["requests"] += 1
                tot["tokens"] += c
                tot["output"] += u.get("output_tokens") or 0
                tot[kind] += 1
                fams[TC.fam(model)] += c
                if post:
                    by_type[key] += 1
    return tot, fams, by_type, firsts


def rtk_saved(ym):
    """RTK's measured saving for the month, or None when rtk or its history is missing."""
    rtk = shutil.which("rtk") or next((p for p in (os.path.expanduser("~/.local/bin/rtk"), os.path.expanduser("~/.local/bin/rtk.exe")) if os.path.exists(p)), None)
    if not rtk:
        return None
    try:
        out = subprocess.run([rtk, "gain", "-m", "-f", "json"], capture_output=True, text=True, timeout=60).stdout
        rows = json.loads(out).get("monthly") or []
    except Exception:
        return None
    return next((r.get("saved_tokens") or 0 for r in rows if r.get("month") == ym), 0)


def routed(ym):
    """Sub-agent tasks the Model Selector pack's model-router moved to a cheaper model (count only; it logs no token figure)."""
    p = os.path.expanduser("~/.claude/mods-logs/savings.jsonl")
    if not os.path.exists(p):
        return None
    n = 0
    for line in open(p, errors="ignore"):
        try:
            o = json.loads(line)
        except Exception:
            continue
        n += o.get("mod") == "model-router" and str(o.get("ts", "")).startswith(ym)
    return n


def render(ym, tot, fams, est, rtk, router):
    saved, covered, post = est
    used = tot["tokens"] + tot["output"]
    measured = rtk or 0
    estimated = saved if covered else 0
    without = used + measured + estimated
    fm = TC.fm
    L = [f"# Claude tokens, {datetime.strptime(ym, '%Y-%m'):%B %Y}", "",
         "| | Tokens |", "|---|---|",
         f"| Used (context read + output) | {fm(used)} |",
         f"| Saved, measured (RTK shell output) | {fm(measured) if rtk is not None else 'RTK not installed'} |",
         f"| Saved, estimated (smaller sessions since install) | {fm(estimated) if covered else 'not enough data yet'} |",
         f"| **Would have used without the kit** | **{fm(without)}** |",
         f"| **Saved in total** | **{fm(measured + estimated)} ({100 * (measured + estimated) / without:.1f}%)** |" if without else "| Saved in total | n/a |",
         "", "| Detail | |", "|---|---|",
         f"| Requests (main / sub-agent) | {tot['requests']} ({tot['main']} / {tot['sub']}) |",
         f"| Average context per request | {fm(tot['tokens'] / tot['requests']) if tot['requests'] else 'n/a'} |",
         f"| Context by model | {', '.join(f'{k} {fm(v)}' for k, v in sorted(fams.items(), key=lambda x: -x[1]) if v) or 'none'} |"]
    if router is not None:
        L.append(f"| Sub-agent tasks moved to a cheaper model (model-router) | {router} |")
    L += ["", "Notes:",
          f"- The estimate covers {covered} of {tot['requests']} requests (session types with {D.MIN_N}+ sessions before and after install)."
          if covered else f"- Estimate needs {D.MIN_N}+ sessions of one type both in the week before install and since; {post} requests qualify so far.",
          "- RTK's figure is a floor: output it cut would also have been re-read on later turns.",
          "- A negative estimate means sessions got bigger since install; it is shown, not hidden.",
          "- Not counted: Caveman, context-mode, CodeGraph and Graphify savings (no per-month counter exists for them)."]
    return "\n".join(L)


def summary(ym, tot, est, rtk):
    s = (rtk or 0) + (est[0] if est[1] else 0)
    return f"{ym}: used {TC.fm(tot['tokens'] + tot['output'])}, saved {TC.fm(s)}"


def selftest():
    tot = defaultdict(int, tokens=900, output=100, requests=10, main=8, sub=2)
    text = render("2026-12", tot, {"opus": 900}, (100, 10, 10), 500, 3)
    assert "| Used (context read + output) | 1.0k |" in text, text
    assert "**1.6k**" in text and "(37.5%)" in text, text  # 1000 used + 500 RTK + 100 estimated; 600 / 1600
    assert "not enough data yet" in render("2026-12", tot, {}, (0, 0, 4), None, None)
    assert month_bounds("2026-12")[1] == datetime(2027, 1, 1)
    print("selftest ok")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--notify"]
    if args == ["selftest"]:
        selftest()
        sys.exit(0)
    ym = args[0] if args else (datetime.now().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")  # last month
    start, end = month_bounds(ym)
    tot, fams, by_type, firsts = scan(start, end)
    baseline = json.load(open(TC.SNAP)) if os.path.exists(TC.SNAP) else []
    est = D.saving(by_type, firsts, baseline)
    rtk = rtk_saved(ym)
    text = render(ym, tot, fams, est, rtk, routed(ym))
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{ym}.md")
    open(path, "w").write(text + "\n")
    print(text)
    if "--notify" in sys.argv and sys.platform == "darwin":  # osascript notification is macOS-only
        msg = summary(ym, tot, est, rtk).replace('"', "'")
        subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "Claude tokens this month" subtitle "Full report: {path.replace(os.path.expanduser("~"), "~")}"'], check=False)
