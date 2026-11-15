#!/usr/bin/env python3
"""Monthly token scorecard: python3 ~/.claude/hooks/token-scorecard.py [days=30]. Not wired to any hook.
Usage is deduped by message.id (each content-block line repeats it). Context = input + cache_read + cache_creation."""
import glob, json, os, statistics as st, sys, time
from collections import Counter, defaultdict
from datetime import datetime

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 30
CUT = time.time() - DAYS * 86400
P = os.path.expanduser("~/.claude/projects")
FAMS = ("opus", "sonnet", "haiku", "fable")


def fam(m):
    m = (m or "").lower()
    return next((f for f in FAMS if f in m), "other")


def ts(o):
    try:
        return datetime.fromisoformat(o["timestamp"].replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0


def scan(path):
    """Unique-by-message.id requests (sorted), tool uses, gate-denied tool_use ids."""
    reqs, tools, denials = {}, {}, set()
    for line in open(path, errors="ignore"):
        gate = "Fact-Forcing Gate" in line
        if not gate and '"assistant"' not in line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        if ts(o) < CUT:
            continue
        msg = o.get("message") if isinstance(o.get("message"), dict) else {}
        if o.get("type") == "assistant" and msg.get("usage"):
            u, mid = msg["usage"], msg.get("id") or o.get("uuid")
            old = reqs.get(mid)
            if not old or (u.get("output_tokens") or 0) >= (old[2].get("output_tokens") or 0):
                reqs[mid] = (ts(o), msg.get("model"), u)
            for c in msg.get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    tools[c.get("id")] = (c.get("name") or "", c.get("input") or {})
        elif gate and o.get("type") == "user":
            for c in msg.get("content") if isinstance(msg.get("content"), list) else []:
                if isinstance(c, dict) and c.get("type") == "tool_result" and "Fact-Forcing Gate" in json.dumps(c):
                    denials.add(c.get("tool_use_id"))
    return sorted(reqs.values(), key=lambda r: r[0]), tools, denials


def ctx(u):
    return (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)


def fm(x):
    return f"{x / 1e6:.1f}M" if x >= 1e6 else f"{x / 1e3:.0f}k"


mains = [f for f in glob.glob(P + "/*/*.jsonl") if os.path.getmtime(f) >= CUT]
subs = [f for f in glob.glob(P + "/*/*/subagents/*.jsonl") if os.path.getmtime(f) >= CUT]
reqn = {"main": Counter(), "sub": Counter()}
runs = Counter()
tok = defaultdict(lambda: [0, 0, 0])  # family -> cache_read, fresh (input+cache_creation), output
mainctx, first = [], {"main": [], "sub": []}
miss = chg = 0
den, tools = set(), Counter()
for kind, files in (("main", mains), ("sub", subs)):
    for f in files:
        reqs, tl, d = scan(f)
        den |= d
        if not reqs:
            continue
        runs[(kind, fam(reqs[0][1]))] += 1
        first[kind].append(ctx(reqs[0][2]))
        prev = None
        for i, (t, m, u) in enumerate(reqs):
            fa = fam(m)
            if fa != "other":
                reqn[kind][fa] += 1
                r, c = u.get("cache_read_input_tokens") or 0, ctx(u)
                tok[fa][0] += r
                tok[fa][1] += (u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
                tok[fa][2] += u.get("output_tokens") or 0
                if kind == "main":
                    mainctx.append(c)
                    if i and c > 100_000 and r < 0.1 * c:
                        miss += 1
                        chg += prev is not None and prev != m
            prev = m
        for name, inp in tl.values():
            if name.startswith("mcp__"):
                tools["mcp:" + name.split("__")[1][:30]] += 1
            elif name == "Skill":
                tools["skill:" + str(inp.get("skill"))] += 1
            elif name in ("Agent", "Task"):
                tools["agent:" + str(inp.get("subagent_type") or "general")] += 1


def top(prefix, k=8):
    return ", ".join(f"{a[len(prefix):]} {b}" for a, b in [x for x in tools.most_common() if x[0].startswith(prefix)][:k]) or "none"


L = [f"TOKEN SCORECARD last {DAYS}d ({datetime.now():%Y-%m-%d}), usage deduped by message.id",
     f"main sessions {len(mains)} | subagent runs {len(subs)}"]
for fa in FAMS:
    if reqn["main"][fa] or reqn["sub"][fa]:
        L.append(f"  {fa:7} sess {runs[('main', fa)]:4} subruns {runs[('sub', fa)]:4} | reqs main {reqn['main'][fa]:6} sub {reqn['sub'][fa]:6}"
                 f" | read {fm(tok[fa][0]):>6} fresh {fm(tok[fa][1]):>6} out {fm(tok[fa][2]):>6}")
if mainctx:
    L.append(f"main request context: avg {fm(st.mean(mainctx))}; above 250k: {100 * sum(c > 250_000 for c in mainctx) / len(mainctx):.0f}% of requests,"
             f" {100 * sum(c for c in mainctx if c > 250_000) / sum(mainctx):.0f}% of context tokens")
for k, lab in (("main", "main sessions"), ("sub", "subagents")):
    if first[k]:
        L.append(f"median first-request context, {lab}: {fm(st.median(first[k]))}")
L += [f"mid-session cache misses (ctx>100k, <10% cached): {miss}; after a model change: {chg}",
      f"GateGuard 'Fact-Forcing Gate' denials: {len(den)}",
      "MCP calls: " + top("mcp:"), "Skills: " + top("skill:"), "Agent types: " + top("agent:")]
print("\n".join(L[:39]))
