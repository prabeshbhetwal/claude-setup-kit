#!/usr/bin/env python3
"""House rules: learn the user's lasting preferences (UI/UX first) from their own words, for their approval.
  house-rules.py mine [--days N] [--no-jev]   # scan transcripts, add or update candidates (nothing becomes a rule here)
  house-rules.py review [--all]               # candidates worth a decision, plus rules unused for 8 weeks
  house-rules.py approve <cid> ["rule text"] [--tags a,b]   # candidate -> active rule (rewrite it in one sentence if needed)
  house-rules.py reject <cid> | retire <rid> | rules
  house-rules.py replay [--days N] [--no-jev] [--ui-only] [--rules FILE] # run recall over real past prompts: trigger rate, size, latency, samples
Store: ~/.claude/house-rules (git-versioned). Hook: ~/.claude/hooks/house-rules-recall.py.
"""
import glob
import hashlib
import os
import re
import statistics as st
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import monitor_collect as C  # noqa: E402
import monitor_scan as S  # noqa: E402
import house_rules_store as T  # noqa: E402

EXPLICIT = re.compile(r"\b(i (really )?(prefer|like|love|hate|dislike|don'?t (like|want)|want (it|them|this|the|a|more|less))"
                      r"|always|never|don'?t (use|add|put|make|ever)|stop (using|adding|making)|avoid|no more|(too|so|very) (busy|much|many|big|"
                      r"small|bright|dark|cramped|loud|generic|plain|flashy|cluttered|bland)|(looks?|feels?) (cheap|generic|off|cluttered|"
                      r"like ai|vibe|dated|busy|amateur|boring)|remember (that|this)|from now on|by default|my (style|taste|preference))\b", re.I)
DESIGN_SKILLS = re.compile(r"impeccable|no-vibe|blueprint|frontend-design|design:|product-ui|ui-sdk|hairline|cinematic", re.I)
QUESTION = "Does this message state a lasting preference about how the user wants design, UI, copy or work done in future, not a one-off instruction for the current task?"


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if 12 <= len(s.strip()) <= 300]


def mine(days, use_jev=True):
    since = time.time() - days * 86400
    found, seen = [], set()  # (sentence, kind, date, session)
    for f in sorted(glob.glob(C.PROJECTS + "/*/*.jsonl"), key=os.path.getmtime):
        if os.path.getmtime(f) < since:
            continue
        r = S.scan(f, since, seen=seen)
        if C.is_headless(r["cwd"]) or r["automated"]:
            continue
        ui_session = r["ui_edits"] > 0 or any(n == "Skill" and DESIGN_SKILLS.search(str(i.get("skill"))) for n, i, _ in r["tools"].values())
        sid = os.path.basename(f)[:8]
        for t, text, _, _ in r["turns"]:
            if len(text) > 1500:
                continue  # pasted material, not the user's own phrasing
            corr = S.is_correction(text)
            for s in sentences(text):
                ui = T.is_ui(s) or (ui_session and T.is_ui(text))
                if EXPLICIT.search(s) and ui:
                    found.append((s, "explicit", t, sid))
                elif corr and ui_session and T.is_ui(s):
                    found.append((s, "correction", t, sid))
    probs = None
    if use_jev and found:
        probs = T.jev_probs("house-rules-mine", QUESTION, [T.redact(s) for s, *_ in found], "", timeout=120)
    cands, rules = T.load(T.CANDS), T.load(T.RULES)
    added = 0
    for i, (s, kind, t, sid) in enumerate(found):
        p = probs[i] if probs else None
        if p is not None and p < 0.5:
            continue
        added += merge(cands, rules, s, kind, t, sid, p)
    T.save(T.CANDS, cands, f"mine: {len(found)} matches, {added} new candidates")
    print(f"{len(found)} matching sentences, jev {'on' if probs else 'off'}, {added} new candidates, {len(cands)} total")


def merge(cands, rules, s, kind, t, sid, p):
    ev = {"date": datetime.fromtimestamp(t).strftime("%Y-%m-%d"), "session": sid, "quote": s[:200]}
    rule = next((r for r in rules if T.jaccard(s, r["rule"]) >= 0.5), None)
    for c in cands:
        if T.jaccard(s, c["rule"]) >= 0.5:
            if not any(e["session"] == sid and e["quote"] == ev["quote"] for e in c["evidence"]):
                c["evidence"].append(ev)
                c["count"] = len({e["quote"].lower() for e in c["evidence"]})  # distinct wordings: a copied prompt is not a repeat
            c["last_seen"] = max(c.get("last_seen", 0), int(t))
            c["p"] = max(c.get("p") or 0, p or 0) or c.get("p")
            if rule and t > rule.get("added", 0):
                c["after_rule"] = rule["id"]
            return 0
    cid = "c" + hashlib.sha1(s.lower().encode()).hexdigest()[:6]
    cands.append({"id": cid, "rule": s[:200], "kind": kind, "tags": T.tags_of(s), "keywords": sorted(set(T.words(s)))[:8],
                  "evidence": [ev], "count": 1, "p": p, "first_seen": int(time.time()), "last_seen": int(t), "status": "pending",
                  **({"after_rule": rule["id"]} if rule and t > rule.get("added", 0) else {})})
    return 1


def worth(c):
    return c["status"] == "pending" and (c["count"] >= 2 or (c["kind"] == "explicit" and (c.get("p") is None or c["p"] >= 0.7)))


def review(show_all=False):
    cands = sorted(T.load(T.CANDS), key=lambda c: (-c["count"], -(c.get("p") or 0)))
    rows = [c for c in cands if show_all and c["status"] == "pending" or worth(c)]
    print(f"{len(rows)} candidates to decide (approve <id> [\"rewritten rule\"], reject <id>):")
    for c in rows[:40]:
        p = f"p={c['p']:.2f}" if c.get("p") is not None else "p=-"
        print(f"  {c['id']} [{c['kind']}, {c['count']} sessions, {p}, {','.join(c['tags'])}] {c['rule']}")
        for e in c["evidence"][1:3]:
            print(f"      also {e['date']}: {e['quote'][:100]}")
    used = {i for line in (open(T.RECALL) if os.path.exists(T.RECALL) else []) for i in __import__("json").loads(line)["ids"]
            if __import__("json").loads(line)["ts"] > time.time() - 56 * 86400}
    stale = [r for r in T.load(T.RULES) if r.get("status", "active") == "active" and r["added"] < time.time() - 56 * 86400 and r["id"] not in used]
    for r in stale:
        print(f"  retire? {r['id']} not injected in 8 weeks: {r['rule']}")


def decide(cid, status, text=None, tags=None):
    cands, rules = T.load(T.CANDS), T.load(T.RULES)
    c = next((x for x in cands if x["id"] == cid), None)
    if not c:
        sys.exit(f"no candidate {cid}")
    c["status"], c["decided"] = status, int(time.time())
    if status == "approved":
        rid = f"r{len(rules) + 1}"
        rule = (text or c["rule"]).strip()
        rules.append({"id": rid, "rule": rule, "tags": tags or T.tags_of(rule), "keywords": sorted(set(T.words(rule) + c["keywords"]))[:10],
                      "evidence": c["evidence"][:5], "added": int(time.time()), "status": "active", "from": cid})
        T.save(T.RULES, rules)
        T.render()
        print(f"{rid} active: {rule}\nSupermemory (optional): add_memory \"House rule {rid}: {rule}\"")
    T.save(T.CANDS, cands, f"{status} {cid}")


def retire(rid):
    rules = T.load(T.RULES)
    for r in rules:
        if r["id"] == rid:
            r["status"] = "retired"
    T.save(T.RULES, rules, f"retire {rid}")
    T.render()


def replay(days, use_jev=True, ui_only=False, rules_path=None):
    since = time.time() - days * 86400
    rules, seen = T.load(rules_path or T.RULES), set()
    n = fired = 0
    sizes, ms, samples = [], [], []
    for f in sorted(glob.glob(C.PROJECTS + "/*/*.jsonl"), key=os.path.getmtime):
        if os.path.getmtime(f) < since:
            continue
        r = S.scan(f, since, seen=seen)
        if C.is_headless(r["cwd"]) or r["automated"] or (ui_only and not r["ui_edits"]):
            continue
        for t, text, _, _ in r["turns"]:
            n += 1
            t0 = time.time()
            hit = T.recall(text, rules, use_jev)
            ms.append(1000 * (time.time() - t0))
            if hit:
                fired += 1
                sizes.append(len(T.note(hit)))
                if len(samples) < 12:
                    samples.append((text.strip().replace("\n", " ")[:90], [h["id"] for h in hit]))
    q = lambda xs, k: sorted(xs)[int(k * (len(xs) - 1))] if xs else 0
    print(f"{n} prompts, {len(rules)} rules: fired on {fired} ({100 * fired / max(n, 1):.1f}%); injected chars median "
          f"{st.median(sizes) if sizes else 0:.0f} (~{(st.median(sizes) if sizes else 0) / 4:.0f} tok), max {max(sizes, default=0)}; "
          f"latency p50 {q(ms, .5):.1f} ms, p95 {q(ms, .95):.1f} ms, max {max(ms, default=0):.0f} ms")
    for s, ids in samples:
        print(f"  {ids} <- {s}")


def main(a):
    cmd = a[1] if len(a) > 1 else "review"
    opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d
    jev = "--no-jev" not in a
    if cmd == "mine":
        mine(float(opt("--days", 30)), jev)
    elif cmd == "review":
        review("--all" in a)
    elif cmd in ("approve", "reject"):
        text = a[3] if len(a) > 3 and not a[3].startswith("--") else None
        decide(a[2], "approved" if cmd == "approve" else "rejected", text, opt("--tags", "") and opt("--tags").split(","))
    elif cmd == "retire":
        retire(a[2])
    elif cmd == "rules":
        T.render()
        print(open(T.VIEW).read())
    elif cmd == "replay":
        replay(float(opt("--days", 14)), jev, "--ui-only" in a, opt("--rules"))
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)
