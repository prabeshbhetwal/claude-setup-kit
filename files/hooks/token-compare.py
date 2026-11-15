#!/usr/bin/env python3
"""Before/after token comparison around one setup change (default: the day install.sh ran).

  python3 ~/.claude/hooks/token-compare.py            # report (freezes the before-week on first run)
  python3 ~/.claude/hooks/token-compare.py selftest

Before = the 7 full local days before the change day, after = the 7 full days after it; the change day is excluded.
A session belongs to the week it started in. Usage is deduped by message.id. Context = input + cache_read + cache_creation.
Primary metric: first-request context per session, compared inside each stratum (main/subagent x entrypoint x model family),
because total tokens follow workload, not setup. Saving = stratum delta x that stratum's after-week requests, as a range.
"""
import glob
import json
import os
import random
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime, timedelta

# Change day: TOKEN_COMPARE_CHANGE=YYYY-MM-DD, else the date install.sh wrote to change-date, else today.
_CD = os.path.expanduser("~/.claude/cache/token-compare/change-date")
CHANGE = datetime.strptime(os.environ.get("TOKEN_COMPARE_CHANGE")
                           or (open(_CD).read().strip() if os.path.exists(_CD) else datetime.now().strftime("%Y-%m-%d")),
                           "%Y-%m-%d")  # local midnight of the change day
BEFORE = (CHANGE - timedelta(days=7), CHANGE)
AFTER = (CHANGE + timedelta(days=1), CHANGE + timedelta(days=8))
P = os.path.expanduser("~/.claude/projects")
OUT = os.path.expanduser("~/.claude/cache/token-compare")
SNAP = os.path.join(OUT, "before-week.json")
FAMS = ("opus", "sonnet", "haiku", "fable")
MIN_N = 5  # sessions needed on both sides before a stratum is compared
PROBE = tuple(int(x) for x in os.environ.get("TOKEN_COMPARE_PROBE", "").split(",") if x)  # optional "before,after" from your own `claude -p` probe


def fam(m):
    m = (m or "").lower()
    return next((f for f in FAMS if f in m), "other")


def ctx(u):
    return (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)


def requests(path):
    """Unique-by-message.id requests of one transcript, oldest first: (time, model, usage, entrypoint)."""
    reqs = {}
    for line in open(path, errors="ignore"):
        if '"assistant"' not in line:
            continue
        try:
            o = json.loads(line)
            t = datetime.fromisoformat(o["timestamp"].replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
        except Exception:
            continue
        msg = o.get("message") if isinstance(o.get("message"), dict) else {}
        u = msg.get("usage")
        if o.get("type") != "assistant" or not u:
            continue
        mid = msg.get("id") or o.get("uuid")
        old = reqs.get(mid)
        if not old or (u.get("output_tokens") or 0) >= (old[2].get("output_tokens") or 0):
            reqs[mid] = (t, msg.get("model"), u, o.get("entrypoint") or "unknown")
    return sorted(reqs.values(), key=lambda r: r[0])


def session_rows():
    """One row per session or subagent run that started in the before or after week."""
    rows = []
    floor = BEFORE[0].timestamp()
    for kind, pattern in (("main", "/*/*.jsonl"), ("sub", "/*/*/subagents/*.jsonl")):
        for f in glob.glob(P + pattern):
            if os.path.getmtime(f) < floor:
                continue
            reqs = requests(f)
            if not reqs:
                continue
            start = reqs[0][0]
            week = "before" if BEFORE[0] <= start < BEFORE[1] else "after" if AFTER[0] <= start < AFTER[1] else None
            if not week:
                continue
            end = BEFORE[1] if week == "before" else AFTER[1]  # a before-week session stops counting at the change day
            used = [r for r in reqs if r[0] < end]
            rows.append({
                "week": week, "kind": kind, "ep": reqs[0][3], "fam": fam(reqs[0][1]), "first": ctx(reqs[0][2]),
                "n": len(used), "ctx": sum(ctx(r[2]) for r in used),
                "read": sum(r[2].get("cache_read_input_tokens") or 0 for r in used),
                "out": sum(r[2].get("output_tokens") or 0 for r in used),
            })
    return rows


def p10(xs):
    return sorted(xs)[max(0, int(len(xs) * 0.1) - 1)] if xs else 0


def median_delta(before, after, rounds=1000):
    """Median drop (before - after) with a 95% bootstrap interval."""
    rnd = random.Random(0)
    diffs = sorted(st.median(rnd.choices(before, k=len(before))) - st.median(rnd.choices(after, k=len(after)))
                   for _ in range(rounds))
    return st.median(before) - st.median(after), diffs[int(rounds * 0.025)], diffs[int(rounds * 0.975)]


def fm(x):
    sign = "-" if x < 0 else ""
    x = abs(x)
    return sign + (f"{x / 1e9:.2f}B" if x >= 1e9 else f"{x / 1e6:.1f}M" if x >= 1e6 else f"{x / 1e3:.1f}k")


def report(rows, now=None):
    now = now or datetime.now()
    by = defaultdict(lambda: {"before": [], "after": []})
    for r in rows:
        by[(r["kind"], r["ep"], r["fam"])][r["week"]].append(r)
    days = max(0, min(7, (now - AFTER[0]).days))
    L = [f"# Token comparison: 7 days before vs 7 days after {CHANGE:%Y-%m-%d}", "",
         f"Run {now:%Y-%m-%d %H:%M}. Before {BEFORE[0]:%d %b} to {BEFORE[1] - timedelta(days=1):%d %b}; "
         f"after {AFTER[0]:%d %b} to {AFTER[1] - timedelta(days=1):%d %b} ({days} of 7 after-days complete).", "",
         "## Fixed context per session (the part the change affects)", "",
         "| Session type | Sessions before / after | First request, median before -> after | Drop (95% range) | Drop at the low end (p10) |"
         " After-week requests | Estimated tokens saved |", "|---|---|---|---|---|---|---|"]
    lo_total = hi_total = covered = 0
    after_reqs = sum(r["n"] for r in rows if r["week"] == "after")
    for key in sorted(by, key=lambda k: -sum(r["n"] for r in by[k]["after"])):
        b, a = by[key]["before"], by[key]["after"]
        name = f"{key[0]} / {key[1]} / {key[2]}"
        if len(b) < MIN_N or len(a) < MIN_N:
            if b or a:
                L.append(f"| {name} | {len(b)} / {len(a)} | too few sessions to compare | | | {sum(r['n'] for r in a)} | |")
            continue
        fb, fa = [r["first"] for r in b], [r["first"] for r in a]
        d, lo, hi = median_delta(fb, fa)
        dp = p10(fb) - p10(fa)
        n = sum(r["n"] for r in a)
        est = sorted((d * n, dp * n))
        lo_total, hi_total, covered = lo_total + est[0], hi_total + est[1], covered + n
        L.append(f"| {name} | {len(b)} / {len(a)} | {fm(st.median(fb))} -> {fm(st.median(fa))} | {fm(d)} ({fm(lo)} to {fm(hi)}) |"
                 f" {fm(dp)} | {n} | {fm(est[0])} to {fm(est[1])} |")
    L += ["", f"**Estimated saving in the after week: {fm(lo_total)} to {fm(hi_total)} tokens**, covering "
              f"{100 * covered / after_reqs:.0f}% of after-week requests." if after_reqs else
          "**No after-week sessions yet.** The table fills in from the day after the change.",
          "A negative number means the first request got larger. Each row's estimate is its drop times its own request count,"
          " using the median drop and the low-end (p10) drop as the two ends of the range.", "",
          "## Whole-week totals (follow workload, not just setup)", "",
          "| | Before | After |", "|---|---|---|"]
    tot = {w: [r for r in rows if r["week"] == w] for w in ("before", "after")}
    for label, fn in (("Main sessions", lambda rs: len([r for r in rs if r["kind"] == "main"])),
                      ("Subagent runs", lambda rs: len([r for r in rs if r["kind"] == "sub"])),
                      ("Requests", lambda rs: sum(r["n"] for r in rs)),
                      ("Tokens read as context", lambda rs: fm(sum(r["ctx"] for r in rs))),
                      ("Average context per request", lambda rs: fm(sum(r["ctx"] for r in rs) / max(1, sum(r["n"] for r in rs)))),
                      ("Share read from cache", lambda rs: f"{100 * sum(r['read'] for r in rs) / max(1, sum(r['ctx'] for r in rs)):.0f}%"),
                      ("Output tokens", lambda rs: fm(sum(r["out"] for r in rs)))):
        L.append(f"| {label} | {fn(tot['before'])} | {fn(tot['after'])} |")
    if len(PROBE) == 2:
        L += ["", "## Controlled test (same prompt, fresh CLI session)", "",
              f"Before {PROBE[0]:,} tokens, after {PROBE[1]:,}: {PROBE[0] - PROBE[1]:,} fewer on the first request. One run each."]
    L += ["", "## Read with care", "",
          "- Anything else that changed the same week also moves these numbers; a controlled probe (TOKEN_COMPARE_PROBE) is"
          " the cleanest single number.",
          "- The first request also holds the first prompt and hook output, so it varies; the p10 column is closer to the fixed floor.",
          "- Sessions that began on the change day are left out. Savings are tokens, not dollars."]
    return "\n".join(L)


def selftest():
    rows = [{"week": w, "kind": "main", "ep": "cli", "fam": "opus", "first": f, "n": 10, "ctx": f * 10, "read": f * 9, "out": 100}
            for w, f in [("before", 100_000)] * 6 + [("after", 97_000)] * 6]
    d, lo, hi = median_delta([r["first"] for r in rows if r["week"] == "before"], [r["first"] for r in rows if r["week"] == "after"])
    assert (d, lo, hi) == (3000, 3000, 3000), (d, lo, hi)
    text = report(rows, now=AFTER[1])
    assert "180.0k to 180.0k tokens" in text and "100%" in text, text  # 3,000 x 60 requests
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
        sys.exit(0)
    rows = session_rows()
    os.makedirs(OUT, exist_ok=True)
    if os.path.exists(SNAP):  # the frozen before-week wins, so later transcript clean-up cannot change it
        rows = json.load(open(SNAP)) + [r for r in rows if r["week"] == "after"]
    else:
        json.dump([r for r in rows if r["week"] == "before"], open(SNAP, "w"))
    text = report(rows)
    open(os.path.join(OUT, f"report-{datetime.now():%Y-%m-%d}.md"), "w").write(text + "\n")
    print(text)
