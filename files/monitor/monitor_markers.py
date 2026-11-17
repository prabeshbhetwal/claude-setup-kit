"""Marker definitions and report rendering for setup-monitor.py."""
import statistics as st

import monitor_collect as C

# id, name, better (lower/higher/info), unit
DEF = [
    ("W1", "Work sessions share of sessions", "info", "%"),
    ("T1", "Start-up load, main (median first request)", "lower", "tok"),
    ("T2", "Start-up load, subagent (median first request)", "lower", "tok"),
    ("T3", "Context per turn (median)", "lower", "tok"),
    ("T4", "Requests per turn (median)", "lower", ""),
    ("T5", "Cache re-read share of context", "info", "%"),
    ("T6", "Mid-session cache misses per 100 turns", "lower", ""),
    ("T7", "Main requests above 250k context", "lower", "%"),
    ("T8", "Compactions per 100 turns", "lower", ""),
    ("T9", "Prompt-hook injection per turn (median)", "lower", "tok"),
    ("T10", "Output per turn (median)", "info", "tok"),
    ("C1", "Cost per turn (median)", "lower", "$"),
    ("C1w", "Cost per turn, work sessions (median)", "lower", "$"),
    ("C1c", "Cost per turn, chat sessions (median)", "lower", "$"),
    ("C2", "Cost per work session (median, incl. subagents)", "lower", "$"),
    ("C3", "Cost per chat session (median)", "lower", "$"),
    ("C4", "Total cost (API-equivalent)", "info", "$"),
    ("C5", "Subagent share of cost", "info", "%"),
    ("C6", "Opus + Fable share of cost", "info", "%"),
    ("S1", "RTK tokens saved", "higher", "tok"),
    ("S2", "context-mode kept out (bytes/4)", "higher", "tok"),
    ("Q1", "Corrections per 100 turns", "lower", ""),
    ("Q2", "Interrupts per 100 turns", "info", ""),
    ("Q3", "Tool errors per 100 tool calls", "lower", ""),
    ("Q4", "Blocked tool calls per 100 tool calls", "info", ""),
    ("Q5", "Test runs passing", "higher", "%"),
    ("Q6", "Test re-runs after a failure, per work session", "lower", ""),
    ("Q7", "Findings per review", "info", ""),
    ("G1", "Rework commits (revert/fix of <24h-old change)", "lower", "%"),
    ("H1", "Hook timeouts + errors per 100 sessions", "lower", ""),
    ("H2", "Jev fail-opens", "lower", ""),
    ("P1", "Taste injections per 100 prompts", "info", ""),
    ("P2", "Taste tokens per injection (median)", "lower", "tok"),
    ("P3", "Active rules used in last 4 weeks", "higher", "%"),
    ("P4", "Taste candidates proposed / approved / rejected", "info", ""),
    ("P5", "Repeat corrections after a rule was approved", "lower", ""),
]
NAME = {d[0]: d for d in DEF}
MIN_N = 20


def pct(a, b):
    return round(100 * a / b, 1) if b else None


def per100(a, b):
    return round(100 * a / b, 2) if b else None


def med(xs):
    return round(st.median(xs), 4) if xs else None


def markers(w, extra, week, partial=False):
    c = w["c"]
    turns, tools = c["turns"], c["tool_calls"]
    git_total, git_rw = extra["git"]
    m = {
        "W1": pct(c["sessions_work"], c["sessions"]), "T1": med(w["first_main"]), "T2": med(w["first_sub"]),
        "T3": med(w["turn_ctx"]), "T4": med(w["turn_reqs"]), "T5": pct(c["cache_read"], c["ctx"]),
        "T6": per100(c["cache_miss"], turns), "T7": pct(c["long_reqs"], c["main_reqs"]), "T8": per100(c["compacts"], turns),
        "T9": round(med(w["hook_chars"]) / 4) if w["hook_chars"] else None, "T10": med(w["turn_out"]),
        "C1": med(w["turn_usd"]), "C1w": med(w["turn_usd_work"]), "C1c": med(w["turn_usd_chat"]),
        "C2": med(w["session_usd_work"]), "C3": med(w["session_usd_chat"]), "C4": round(c["usd"], 2),
        "C5": pct(c["usd_sub"], c["usd"]), "C6": pct(c["usd_top"], c["usd"]),
        "S1": extra["rtk_saved"], "S2": round(extra["ctx_kept_bytes"] / 4) if extra["ctx_kept_bytes"] is not None else None,
        "Q1": per100(c["corrections"], turns), "Q2": per100(c["interrupts"], turns), "Q3": per100(c["tool_err"], tools),
        "Q4": per100(c["tool_blocked"], tools), "Q5": pct(c["test_pass"], c["test_runs"]),
        "Q6": round(c["test_retry"] / c["sessions_work"], 2) if c["sessions_work"] else None,
        "Q7": round(sum(w["findings"]) / len(w["findings"]), 1) if w["findings"] else None,
        "G1": pct(git_rw, git_total), "H1": per100(c["hook_fail"], c["sessions"]), "H2": extra["jev_failopen"],
    }
    n = {"turns": int(turns), "turns_work": c["turns_work"], "turns_chat": c["turns_chat"], "sessions": c["sessions"],
         "sessions_work": c["sessions_work"], "sessions_ui": c["sessions_ui"], "tool_calls": tools, "test_runs": c["test_runs"],
         "commits": git_total, "subagent_runs": len(w["first_sub"]), "reviews": len(w["findings"]),
         "headless_sessions": c["headless"], "headless_usd": round(c["usd_headless"], 2)}
    n = {k: int(v) if isinstance(v, float) and k != "headless_usd" else v for k, v in n.items()}
    try:
        import taste_store
        a, b = C.week_bounds(week)
        m.update(taste_store.week_markers(a, b, turns))
    except Exception:
        pass
    return {"week": week, "partial": partial, "markers": m, "n": n, "examples": {"Q1": list(w["correction_examples"])}}


def size(mid, rec):
    """Units behind a marker, for the 'n small' rule."""
    n = rec["n"]
    if mid in ("T1", "C2", "C3", "W1", "H1"):
        return {"C2": n["sessions_work"], "C3": n["sessions"] - n["sessions_work"]}.get(mid, n["sessions"])
    if mid in ("T2",):
        return n["subagent_runs"]
    if mid in ("Q3", "Q4"):
        return n["tool_calls"]
    if mid in ("Q5",):
        return n["test_runs"]
    if mid == "G1":
        return n["commits"]
    if mid == "C1w":
        return n["turns_work"]
    if mid == "C1c":
        return n["turns_chat"]
    return n["turns"]


def fmt(v, unit):
    if v is None:
        return "-"
    if isinstance(v, str):
        return v
    if unit == "$":
        return f"${v:.3f}" if v < 10 else f"${v:,.0f}"
    if unit == "tok":
        return f"{v / 1e6:.1f}M" if v >= 1e6 else f"{v / 1e3:.1f}k" if v >= 1e3 else f"{v:.0f}"
    if unit == "%":
        return f"{v:.1f}%"
    return f"{v:g}"


def baseline(mid, week, weeks):
    prev = [weeks[k]["markers"].get(mid) for k in sorted(weeks) if k < week and not weeks[k].get("partial")][-4:]
    prev = [x for x in prev if isinstance(x, (int, float))]
    return st.median(prev) if prev else None


def bad_move(mid, v, base):
    better = NAME[mid][2]
    if better == "info" or not isinstance(v, (int, float)) or not base:
        return False
    d = (v - base) / abs(base)
    return d > 0.15 if better == "lower" else d < -0.15


def weekly_md(week, weeks, changes):
    rec = weeks[week]
    prev_week = max([k for k in weeks if k < week], default=None)
    ch = [x for x in changes if x["week"] == week]
    L = [f"# Setup scorecard, week {week}" + (" (partial)" if rec.get("partial") else ""), "",
         f"Units: {rec['n']['turns']} turns ({rec['n']['turns_work']} in work sessions), {rec['n']['sessions']} sessions"
         f" ({rec['n']['sessions_work']} work, {rec['n']['sessions_ui']} touched UI files), {rec['n']['tool_calls']} tool calls,"
         f" {rec['n']['commits']} commits. Cost is API-equivalent (plan usage, not money).",
         f"Left out: {rec['n'].get('headless_sessions', 0)} headless/eval sessions (temp folders), ${rec['n'].get('headless_usd', 0):,.2f}.", "",
         "Setup changes this week: " + ("; ".join(x["text"] for x in ch) if ch else "none logged")
         + (" (mixed week: more than one change, moves cannot be pinned on one)" if len(ch) > 1 else ""), "",
         "| # | Marker | This week | 4-week median | Move | Flag |", "|---|---|---|---|---|---|"]
    for mid, name, better, unit in DEF:
        v, base = rec["markers"].get(mid), baseline(mid, week, weeks)
        move = f"{100 * (v - base) / abs(base):+.0f}%" if isinstance(v, (int, float)) and base else "-"
        small = size(mid, rec) < MIN_N and mid[0] in "TCQG"
        flag = "n small" if small else ""
        if not small and bad_move(mid, v, base) and prev_week and bad_move(mid, weeks[prev_week]["markers"].get(mid), baseline(mid, prev_week, weeks)):
            flag = "WORSE 2 wks"
        elif not small and bad_move(mid, v, base):
            flag = "watch"
        L.append(f"| {mid} | {name} ({better}) | {fmt(v, unit)} | {fmt(base, unit)} | {move} | {flag} |")
    ex = rec.get("examples", {}).get("Q1") or []
    if ex:
        L += ["", "Q1 matches (check precision):"] + [f"- {e}" for e in ex]
    L += ["", "Limits: before/after evidence, not proof; weekly numbers follow workload (see W1 and the per-stratum C1 rows).",
          "Causal tests: mods/model-pilot/eval/live (A/B harness)."]
    return "\n".join(L) + "\n"


def trend_md(weeks, changes):
    ks = sorted(weeks)[-6:]
    L = ["# Setup scorecard trend", "", "| # | Marker | " + " | ".join(ks) + " |", "|---|---|" + "---|" * len(ks)]
    for mid, name, better, unit in DEF:
        L.append(f"| {mid} | {name} ({better}) | " + " | ".join(fmt(weeks[k]["markers"].get(mid), unit) for k in ks) + " |")
    L += ["", "Turns: " + ", ".join(f"{k} {weeks[k]['n']['turns']}" for k in ks), "", "Changes:"]
    L += [f"- {x['week']}: {x['text']}" for x in changes if x["week"] >= ks[0]] if ks else []
    L += ["", "A change helped when its week's cost markers (C1, C1w, C2, T1, T3) fell and Q1, Q3, Q5, G1 did not get worse."]
    return "\n".join(L) + "\n"


def headline(week, weeks):
    rec = weeks.get(week)
    if not rec:
        return "no data"
    m = rec["markers"]
    return f"{week}: cost/turn {fmt(m.get('C1'), '$')}, start-up {fmt(m.get('T1'), 'tok')}, corrections {fmt(m.get('Q1'), '')}/100 turns, tests {fmt(m.get('Q5'), '%')}"
