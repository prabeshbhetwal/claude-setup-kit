#!/usr/bin/env python3
"""Setup monitor: weekly scorecard of cost and quality markers for this Claude Code setup. No network, no Claude tokens.
  setup-monitor.py collect [--weeks N]   # scan transcripts, git, RTK, context-mode, Jev; write weeks/<YYYY-Www>.json
  setup-monitor.py report [--week W]     # weekly report (default: last finished week) -> reports/week-<W>.md
  setup-monitor.py trend                 # every stored week side by side -> reports/trend-<date>.md
  setup-monitor.py weekly [--notify]     # what launchd runs on Mondays: collect 2 weeks, report, trend, house-rules mine
  setup-monitor.py note "text"           # log a setup change, shown against the week it happened in
  setup-monitor.py selftest
Data lives in ~/.claude/monitor (SETUP_MONITOR_HOME).
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import monitor_collect as C  # noqa: E402
import monitor_markers as M  # noqa: E402

HOME = os.environ.get("SETUP_MONITOR_HOME") or os.path.expanduser("~/.claude/monitor")
WEEKS, REPORTS, CHANGES = (os.path.join(HOME, x) for x in ("weeks", "reports", "changes.jsonl"))


def changes():
    if not os.path.exists(CHANGES):
        return []
    return [json.loads(line) for line in open(CHANGES) if line.strip()]


def stored():
    os.makedirs(WEEKS, exist_ok=True)
    return {f[:-5]: json.load(open(os.path.join(WEEKS, f))) for f in sorted(os.listdir(WEEKS)) if f.endswith(".json")}


def collect(weeks):
    now = time.time()
    this = C.week_of(now)
    a0, _ = C.week_bounds(this)
    since = a0 - 7 * 86400 * weeks
    raw, cwds = C.collect(since)
    repos = C.repos_of(cwds)
    os.makedirs(WEEKS, exist_ok=True)
    out = []
    for week, w in sorted(raw.items()):
        a, b = C.week_bounds(week)
        if a < since:
            continue
        extra = {"rtk_saved": C.rtk_week(a, b), "ctx_kept_bytes": C.ctxmode_week(a, b), "jev_failopen": C.jev_failopens(a, b),
                 "git": C.git_rework(repos, a, b)}
        rec = M.markers(w, extra, week, partial=b > now)
        json.dump(rec, open(os.path.join(WEEKS, week + ".json"), "w"), indent=1)
        out.append(week)
    return out, repos


def last_finished():
    return C.week_of(time.time() - 7 * 86400)


def report(week=None):
    weeks = stored()
    week = week or last_finished()
    if week not in weeks:
        return None
    md = M.weekly_md(week, weeks, changes())
    os.makedirs(REPORTS, exist_ok=True)
    p = os.path.join(REPORTS, f"week-{week}.md")
    open(p, "w").write(md)
    return p


def trend():
    md = M.trend_md(stored(), changes())
    os.makedirs(REPORTS, exist_ok=True)
    p = os.path.join(REPORTS, f"trend-{datetime.now():%Y-%m-%d}.md")
    open(p, "w").write(md)
    return p


def notify(text):
    subprocess.run(["osascript", "-e", f'display notification {json.dumps(text)} with title "Setup monitor"'], timeout=10)


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "report"
    opt = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
    if cmd == "collect":
        weeks, repos = collect(int(opt("--weeks", 2)))
        print(f"collected {len(weeks)} weeks ({', '.join(weeks)}), {len(repos)} repos")
    elif cmd == "report":
        print(report(opt("--week")) or "no data for that week: run collect")
    elif cmd == "trend":
        print(trend())
    elif cmd == "note":
        os.makedirs(HOME, exist_ok=True)
        open(CHANGES, "a").write(json.dumps({"ts": int(time.time()), "week": C.week_of(time.time()), "text": " ".join(argv[2:])}) + "\n")
        print("noted")
    elif cmd == "weekly":
        collect(2)
        p, t = report(), trend()
        try:
            subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.realpath(__file__)), "house-rules.py"), "mine", "--days", "8"],
                           timeout=900)
        except Exception as e:
            print("house-rules mine failed:", e)
        print(p, t)
        if "--notify" in argv and p:
            notify(M.headline(last_finished(), stored()))
    elif cmd == "selftest":
        import monitor_selftest
        monitor_selftest.run()
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)
