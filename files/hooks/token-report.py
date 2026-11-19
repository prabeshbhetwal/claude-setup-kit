#!/usr/bin/env python3
"""Token report: what you used, what the kit saved, and what you would have used without it. No Claude tokens.

  python3 ~/.claude/hooks/token-report.py                       # the last finished period you chose (default: month)
  python3 ~/.claude/hooks/token-report.py --period week|fortnight|month [YYYY-MM | YYYY-MM-DD]
  python3 ~/.claude/hooks/token-report.py --set week|fortnight|month|off   # how often the scheduled report runs
  python3 ~/.claude/hooks/token-report.py --scheduled --notify  # what the daily 09:00 job runs: writes a report only
                                                                # when a period has finished and has none yet
  python3 ~/.claude/hooks/token-report.py --turns [N]          # the last N turns (default 10): used and saved, per prompt
  python3 ~/.claude/hooks/token-report.py selftest

Periods end at local midnight: a week runs Monday to Sunday, a fortnight is two such weeks (counted from 5 Jan 2026),
a month is a calendar month. Reports go to ~/.claude/cache/token-compare/reports/<period>-<first day>.md.
Turn by turn: token-ledger.py (a Stop hook) writes one line per finished turn; the report adds those lines up.
Used = context read per request (input + cache_read + cache_creation), deduped by message.id, plus output tokens.
Saved has two parts, reported apart:
  measured  - RTK's own count of shell-output tokens it cut that month (`rtk gain -m`). A floor: cut output would
              also have been re-read as context on every later turn.
  estimated - per session type, (median first-request context in the frozen 30 days before install) minus (median since
              install), times that type's requests in the month; the same method as token-daily.py.
Without the kit ~= used + measured + estimated. Totals follow how much you worked; the saving lines are the kit's part.
Per tool: one line each for Caveman, context-mode, CodeGraph, Graphify and model-pilot, from token-tools.py; never added to the totals.
Not used this month: installed on-demand tools with no sign of use (token-tools.unused), so you can drop what you do not use.
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
T = _load("token_tools", "token-tools.py")  # per-tool lines: Caveman, context-mode, CodeGraph, Graphify
L_ = _load("token_ledger", "token-ledger.py")  # the per-turn ledger and RTK's per-command history
OUT = os.path.join(TC.OUT, "reports")
PERIOD_FILE = os.path.expanduser("~/.claude/kit/report-period")
PERIODS = ("week", "fortnight", "month")
EPOCH = datetime(2026, 1, 5)  # a Monday: fortnights are counted from here, so they never shift


def bounds(period, arg=None, today=None):
    """(start, end) of the period: the one starting on arg (YYYY-MM or YYYY-MM-DD), else the last finished one."""
    today = (today or datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "month":
        if arg:
            return month_bounds(arg[:7])
        return month_bounds((today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m"))
    days = 7 if period == "week" else 14
    if arg:
        start = datetime.strptime(arg, "%Y-%m-%d")
        return start, start + timedelta(days=days)
    end = today - timedelta(days=today.weekday())  # this week's Monday
    if period == "fortnight" and (end - EPOCH).days % 14:
        end -= timedelta(days=7)
    return end - timedelta(days=days), end


def label(period, start):
    return f"{start:%B %Y}" if period == "month" else f"{'week' if period == 'week' else 'fortnight'} from {start:%-d %b %Y}"


def ledger(start, end, path=None):
    """Sums of the per-turn ledger lines that ended in the window, or None when there are none."""
    path = path or L_.LEDGER
    if not os.path.exists(path):
        return None
    s = defaultdict(float)
    seen = {k: False for k in ("rtk_saved", "ctx_saved_bytes", "pilot_saved_usd")}
    for line in open(path, errors="ignore"):
        try:
            d = json.loads(line)
            t = L_.when(d["ts"]).astimezone().replace(tzinfo=None)
        except (ValueError, KeyError):
            continue
        if not start <= t < end:
            continue
        s["turns"] += 1
        s["used"] += (d.get("context") or 0) + (d.get("output") or 0)
        for k in seen:
            if d.get(k) is not None:
                seen[k] = True
                s[k] += d[k]
    if not s["turns"]:
        return None
    return {**s, **{k: (s[k] if seen[k] else None) for k in seen}}


def month_bounds(ym):
    start = datetime.strptime(ym, "%Y-%m")
    end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    return start, end


def scan(start, end):
    """Totals for the month, per-model-family split, and post-install session facts per stratum."""
    tot, fams = defaultdict(int), defaultdict(int)
    by_type, firsts, seen = defaultdict(int), defaultdict(list), set()  # seen: message ids, once across all files
    for kind, pattern in (("main", "/*/*.jsonl"), ("sub", "/*/*/subagents/*.jsonl")):
        for f in glob.glob(TC.P + pattern):
            if os.path.getmtime(f) < min(start.timestamp(), TC.AFTER[0].timestamp()):
                continue
            reqs = TC.requests(f, seen)
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


def rtk_saved(ym, start=None, end=None):
    """RTK's measured saving in the window, from its per-command history; falls back to `rtk gain -m` for the month."""
    if start is not None:
        n = L_.rtk_saved(start.astimezone(), end.astimezone())
        if n is not None:
            return n
    rtk = shutil.which("rtk") or next((p for p in (os.path.expanduser("~/.local/bin/rtk"), os.path.expanduser("~/.local/bin/rtk.exe")) if os.path.exists(p)), None)
    if not rtk:
        return None
    try:
        out = subprocess.run([rtk, "gain", "-m", "-f", "json"], capture_output=True, text=True, timeout=60).stdout
        rows = json.loads(out).get("monthly") or []
    except Exception:
        return None
    return next((r.get("saved_tokens") or 0 for r in rows if r.get("month") == ym), 0)


def routed(start, end):
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
        try:
            t = L_.when(o.get("ts")).astimezone().replace(tzinfo=None)
        except (ValueError, TypeError):
            continue
        n += o.get("mod") == "model-router" and start <= t < end
    return n


def render(title, tot, fams, est, rtk, router, tools, idle=None, led=None, period="month"):
    saved, covered, post = est
    used = tot["tokens"] + tot["output"]
    measured = rtk or 0
    estimated = saved if covered else 0
    without = used + measured + estimated
    fm = TC.fm
    L = [f"# Claude tokens, {title}", "",
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
    if led:
        n = led["turns"]
        parts = [f"RTK {fm(led['rtk_saved'])} (measured)" if led["rtk_saved"] is not None else None,
                 f"context-mode ~{fm(led['ctx_saved_bytes'] / 4)} (its bytes / 4)" if led["ctx_saved_bytes"] is not None else None,
                 f"Model pilot ~${led['pilot_saved_usd']:.2f} (estimate)" if led["pilot_saved_usd"] is not None else None]
        L += [f"| Turns recorded by the ledger hook | {int(n)}: {fm(led['used'])} used, {fm(led['used'] / n)} a turn |",
              f"| Saved in those turns | {', '.join(x for x in parts if x) or 'no saving source installed'} |"]
    if router is not None:
        L.append(f"| Sub-agent tasks moved to a cheaper model (model-router) | {router} |")
    L += T.lines(tools)
    if idle:
        L.append(f"| Not used this {period} | {', '.join(idle)}: no tool call, command or log line of theirs. Keep them only if you still want them |")
    L += ["", "Notes:",
          f"- The estimate covers {covered} of {tot['requests']} requests (session types with {D.MIN_N}+ sessions before and after install)."
          if covered else f"- Estimate needs {D.MIN_N}+ sessions of one type both in the 30 days before install and since; {post} requests qualify so far.",
          "- RTK's figure is a floor: output it cut would also have been re-read on later turns.",
          "- A negative estimate means sessions got bigger since install; it is shown, not hidden.",
          "- Per-tool lines stay out of the totals: RTK and context-mode both trim shell output, so adding them would count some of it twice.",
          "- context-mode's bytes are also a floor: kept-out output would have been re-read on later turns."]
    return "\n".join(L)


def summary(title, tot, est, rtk):
    s = (rtk or 0) + (est[0] if est[1] else 0)
    return f"{title}: used {TC.fm(tot['tokens'] + tot['output'])}, saved {TC.fm(s)}"


def selftest():
    tot = defaultdict(int, tokens=900, output=100, requests=10, main=8, sub=2)
    tools = T.selftest()
    led = {"turns": 4, "used": 800, "rtk_saved": 120, "ctx_saved_bytes": 4000, "pilot_saved_usd": 0.5}
    text = render("December 2026", tot, {"opus": 900}, (100, 10, 10), 500, 3, tools, ["mjudge"], led)
    assert "| Not used this month | mjudge:" in text and "# Claude tokens, December 2026" in text, text
    assert "| Turns recorded by the ledger hook | 4: 0.8k used, 0.2k a turn |" in text and "context-mode ~1.0k" in text and "~$0.50" in text, text
    assert "| Caveman | 0.7k output tokens" in text and "6.0 KB of tool output kept out" in text and "~1.5k tokens" in text, text
    assert "| CodeGraph | 1 calls, 0.3 KB returned" in text and "| Graphify | 1 reads of graphify-out" in text, text
    assert "| Used (context read + output) | 1.0k |" in text, text
    assert "**1.6k**" in text and "(37.5%)" in text, text  # 1000 used + 500 RTK + 100 estimated; 600 / 1600
    none = {"caveman": None, "context-mode": None, "codegraph": [0, 0], "graphify": [0, 0]}
    text = render("December 2026", tot, {}, (0, 0, 4), None, None, none)
    assert "not enough data yet" in text and "no Caveman log found" in text and "no context-mode records found" in text
    assert month_bounds("2026-12")[1] == datetime(2027, 1, 1)
    wed = datetime(2026, 11, 18, 15)  # a Wednesday
    assert bounds("week", today=wed) == (datetime(2026, 11, 9), datetime(2026, 11, 16))
    assert bounds("month", today=wed) == (datetime(2026, 10, 1), datetime(2026, 11, 1))
    f = bounds("fortnight", today=wed)  # 16 Nov is 45 weeks after 5 Jan: odd, so the last fortnight ended 9 Nov
    assert f == (datetime(2026, 10, 26), datetime(2026, 11, 9)) and (f[1] - EPOCH).days % 14 == 0, f
    assert bounds("fortnight", today=datetime(2026, 11, 24)) == (datetime(2026, 11, 9), datetime(2026, 11, 23))
    assert bounds("week", "2026-11-02") == (datetime(2026, 11, 2), datetime(2026, 11, 9))
    assert label("fortnight", datetime(2026, 11, 9)) == "fortnight from 9 Nov 2026"
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "l.jsonl")
        open(p, "w").write("\n".join(json.dumps(x) for x in [
            {"ts": "2026-11-10T01:00:00Z", "context": 100, "output": 10, "rtk_saved": 5, "ctx_saved_bytes": None, "pilot_saved_usd": 0.1},
            {"ts": "2026-11-11T01:00:00Z", "context": 200, "output": 20, "rtk_saved": None, "ctx_saved_bytes": None, "pilot_saved_usd": None},
            {"ts": "2026-10-01T01:00:00Z", "context": 9999, "output": 0}]) + "\nnot json\n")
        s = ledger(datetime(2026, 11, 9), datetime(2026, 11, 16), p)
        assert (s["turns"], s["used"], s["rtk_saved"], s["ctx_saved_bytes"]) == (2, 330, 5, None), s
        assert ledger(datetime(2025, 1, 1), datetime(2025, 2, 1), p) is None
        t = turns(5, p)
        assert t.count("\n| ") == 3 and "| 0.1k | 0.0k | - | $0.10 |" in t and "| 0.2k | - | - | - |" in t, t
        assert "No turns recorded yet" in turns(5, p + "x")
        TC.P = d  # a resumed session's transcript repeats message m1: the report counts it once
        for name in ("a", "b"):
            os.makedirs(os.path.join(d, name))
            open(os.path.join(d, name, "s.jsonl"), "w").write(json.dumps({"type": "assistant", "timestamp": "2026-11-10T01:00:00Z", "message": {"id": "m1", "usage": {"input_tokens": 7}}}) + "\n")
        assert scan(datetime(2026, 11, 9), datetime(2026, 11, 16))[0]["tokens"] == 7
    print("selftest ok")


def turns(n=10, path=None):
    """Table of the last n ledger lines: one row per prompt, newest last."""
    path = path or L_.LEDGER
    rows = []
    if os.path.exists(path):
        for line in open(path, errors="ignore"):
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    if not rows:
        return "No turns recorded yet: the ledger hook writes one line after each finished turn."
    fm = TC.fm
    L = ["| Ended | Requests | Used (context + output) | RTK saved | context-mode kept out | Model pilot |", "|---|---|---|---|---|---|"]
    for d in rows[-n:]:
        try:
            t = L_.when(d["ts"]).astimezone()
        except (KeyError, ValueError):
            continue
        cm, usd = d.get("ctx_saved_bytes"), d.get("pilot_saved_usd")
        L.append(f"| {t:%d %b %H:%M} | {d.get('requests', 0)} | {fm((d.get('context') or 0) + (d.get('output') or 0))} |"
                 f" {fm(d['rtk_saved']) if d.get('rtk_saved') is not None else '-'} | {f'~{fm(cm / 4)}' if cm is not None else '-'} |"
                 f" {f'${usd:.2f}' if usd is not None else '-'} |")
    return "\n".join(L + ["", "'-' = that tool is not installed. RTK is measured; context-mode is its bytes / 4; Model pilot is an estimate."])


def chosen():
    try:
        p = open(PERIOD_FILE).read().strip()
    except OSError:
        return "month"
    return p if p in PERIODS + ("off",) else "month"


if __name__ == "__main__":
    argv = sys.argv[1:]
    if argv == ["selftest"]:
        selftest()
        sys.exit(0)
    if "--turns" in argv:
        k = argv.index("--turns")
        print(turns(int(argv[k + 1]) if len(argv) > k + 1 and argv[k + 1].isdigit() else 10))
        sys.exit(0)
    if "--set" in argv:
        p = argv[argv.index("--set") + 1] if len(argv) > argv.index("--set") + 1 else ""
        if p not in PERIODS + ("off",):
            sys.exit("--set takes week, fortnight, month or off")
        os.makedirs(os.path.dirname(PERIOD_FILE), exist_ok=True)
        open(PERIOD_FILE, "w").write(p + "\n")
        print(f"Scheduled token report: {p}" if p != "off" else "Scheduled token report: off (run it by hand any time)")
        sys.exit(0)
    period = argv[argv.index("--period") + 1] if "--period" in argv else chosen()
    if period == "off":
        if "--scheduled" in argv:
            sys.exit(0)
        period = "month"  # run by hand while the schedule is off
    if period not in PERIODS:
        sys.exit("--period takes week, fortnight or month")
    rest = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] not in ("--period", "--set"))]
    start, end = bounds(period, rest[0] if rest else None)
    path = os.path.join(OUT, f"{period}-{start:%Y-%m-%d}.md")
    if "--scheduled" in argv and (os.path.exists(path) or end <= TC.CHANGE):
        sys.exit(0)  # already written, or the period ended before the install; the daily job checks again tomorrow
    title = label(period, start)
    tot, fams, by_type, firsts = scan(start, end)
    baseline = json.load(open(TC.SNAP)) if os.path.exists(TC.SNAP) else []
    est = D.saving(by_type, firsts, baseline)
    rtk = rtk_saved(start.strftime("%Y-%m"), start, end)
    tools = T.collect(start, end)
    inst = os.path.expanduser("~/.claude/kit/installed")
    idle = T.unused(open(inst).read().split(), tools, rtk, T.signs(start, end)) if os.path.exists(inst) else None
    text = render(title, tot, fams, est, rtk, routed(start, end), tools, idle, ledger(start, end), period)
    os.makedirs(OUT, exist_ok=True)
    open(path, "w").write(text + "\n")
    print(text)
    if "--notify" in argv and sys.platform == "darwin":  # osascript notification is macOS-only
        msg = summary(title, tot, est, rtk).replace('"', "'")
        subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "Claude tokens" subtitle "Full report: {path.replace(os.path.expanduser("~"), "~")}"'], check=False)
