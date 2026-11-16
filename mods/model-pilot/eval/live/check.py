#!/usr/bin/env python3
"""Check a drive.py run: did every main-thread request of each turn run the pilot's pick?

Usage: check.py RUN.json [RUN.json ...]
Reads the session transcript in order. Each pilot turn line (written at turn end) owns
the main-thread API requests since the previous pilot turn line. A turn passes when all
its requests ran on the picked tier (or the menu's, when the pilot left the model alone)
and on the picked effort, if any. Sub-agents: each spawn's own transcript must show the
model the pilot picked, or the model the caller named. Exit code 1 on any failure.
"""
import glob, json, os, sys

TIERS = ["haiku", "sonnet", "opus", "fable"]


def tier_of(model):
    m = (model or "").lower()
    return "fable" if "mythos" in m else next((t for t in TIERS if t in m), None)


def rows_of(session):
    root = os.environ.get("CLAUDE_CONFIG_DIR", os.path.expanduser("~/.claude"))
    f = glob.glob(os.path.join(root, "projects", "*", session + ".jsonl"))
    return [json.loads(l) for l in open(f[0])] if f else [], os.path.dirname(f[0]) if f else ""


def check(path):
    run = json.load(open(path))
    rows, folder = rows_of(run["session"])
    reqs = sorted((r["timestamp"], r["params"].get("model"), (r["params"].get("output_config") or {}).get("effort"))
                  for r in rows if r.get("type") == "api-request")
    turns = sorted((p for p in run["pilot"] if p.get("kind") == "turn"), key=lambda p: p["ts"])
    bad, prev = 0, ""
    print(f"== {run['name']}: {len(run['turns'])} prompts sent, {len(turns)} pilot turn lines")
    for p in turns:
        mine = {(tier_of(m), e) for ts, m, e in reqs if prev < ts <= p["ts"]}
        prev = p["ts"]
        want = p.get("picked") or tier_of(p.get("menu"))
        ok = bool(mine) and (p.get("shadow") or all(t == want and (p.get("picked_effort") in (None, e)) for t, e in mine))
        bad += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'} {p['ts'][11:19]} {p.get('source'):8} pick={want}/{p.get('picked_effort')} "
              f"judge={p.get('judge')} wait={p.get('judge_wait_ms')}ms ran={sorted(mine)} ${p.get('cost_usd')}")
    # Sub-agents: the spawn record names the model; the sub-agent's transcript shows what ran.
    for meta in glob.glob(os.path.join(folder, run["session"], "subagents", "*.meta.json")):
        m = json.load(open(meta))
        ran = {json.loads(l)["message"].get("model") for l in open(meta.replace(".meta.json", ".jsonl"))
               if '"type": "assistant"' in l or '"type":"assistant"' in l}
        ok = {tier_of(x) for x in ran} == {tier_of(m.get("model"))}
        bad += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'} sub-agent {m.get('agentType')} asked={m.get('model')} ran={sorted(ran)} :: {m.get('description')}")
    errors = [r for r in run["turns"] if r["isError"]]
    bad += len(errors)
    print(f"{'PASS' if bad == 0 else 'FAIL'} {run['name']}: {bad} failure(s), {len(errors)} engine error(s)")
    return bad


if __name__ == "__main__":
    sys.exit(1 if sum(check(p) for p in sys.argv[1:]) else 0)
