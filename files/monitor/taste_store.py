"""Taste memory store and matching, shared by taste.py (capture, review) and hooks/taste-recall.py (recall).
Store: ~/.claude/taste (TASTE_HOME), a git repo. rules.json = approved, candidates.json = proposed, recall.jsonl = injections.
"""
import json
import math
import os
import re
import subprocess
import time

HOME = os.environ.get("TASTE_HOME") or os.path.expanduser("~/.claude/taste")
RULES, CANDS, RECALL, VIEW = (os.path.join(HOME, x) for x in ("rules.json", "candidates.json", "recall.jsonl", "RULES.md"))

TAGS = {
    "layout": "layout spacing padding margin grid bento card cards hero section whitespace density cramped align alignment sidebar column columns",
    "colour": "colour color colours colors palette gradient gradients dark light theme contrast neon purple accent background",
    "type": "font fonts typography heading headings serif sans weight size text headline",
    "motion": "animation animations motion transition transitions parallax scroll hover bounce fade",
    "copy": "copy wording words headline tagline cta microcopy tone emoji emojis jargon label labels",
    "a11y": "accessible accessibility a11y contrast keyboard screen reader focus aria",
    "ui": "ui ux design button buttons icon icons modal navbar nav menu toolbar tab tabs page landing website site screen mobile "
          "responsive component components tailwind swiftui shadcn look looks style styling visual polish vibe generic",
    "code": "code function functions test tests refactor abstraction comments typescript python swift lint",
    "workflow": "commit commits pr branch ask confirm plan explain summary report",
}
UI_WORDS = set(w for k in ("layout", "colour", "type", "motion", "copy", "a11y", "ui") for w in TAGS[k].split())
STOP = set("""a an the and or but if then else for to of in on at by with from as is are was were be been it this that these those
i you we me my our your can could should would will do does did make get use using want need please just like some any all more
most into about what how why when where which who so not no yes also one two very really""".split())


def words(text):
    return [w[:6] for w in re.findall(r"[a-z][a-z0-9+#-]{1,}", text.lower()) if w not in STOP]


def tags_of(text):
    ws = set(re.findall(r"[a-z0-9]+", text.lower()))
    return [k for k, v in TAGS.items() if ws & set(v.split())] or ["workflow"]


def is_ui(text):
    return bool(set(re.findall(r"[a-z0-9]+", text.lower())) & UI_WORDS)


def redact(text):
    text = re.sub(r"\S+@\S+\.\w+", "<email>", text)
    text = re.sub(r"https?://\S+", "<url>", text)
    text = re.sub(r"(~|/Users|/private|/var|\.{1,2})?/[\w.@-]+(/[\w.@ -]+)+", "<path>", text)
    text = re.sub(r"\b\d{4,}\b", "<num>", text)
    return text[:200]


def load(path):
    try:
        return json.load(open(path))
    except (OSError, ValueError):
        return []


def save(path, rows, msg=None):
    os.makedirs(HOME, exist_ok=True)
    tmp = path + ".tmp"
    json.dump(rows, open(tmp, "w"), indent=1, ensure_ascii=False)
    os.replace(tmp, path)
    if msg:
        commit(msg)


def commit(msg):
    """Version every change in the store's own git repo (created on first use)."""
    try:
        if not os.path.isdir(os.path.join(HOME, ".git")):
            subprocess.run(["git", "-C", HOME, "init", "-q"], timeout=10)
        subprocess.run(["git", "-C", HOME, "add", "-A"], timeout=10)
        subprocess.run(["git", "-C", HOME, "commit", "-q", "-m", msg], timeout=10, capture_output=True)
    except Exception:
        pass


def jaccard(a, b):
    a, b = set(words(a)), set(words(b))
    return len(a & b) / len(a | b) if a and b else 0.0


def rank(prompt, rules, min_score=2.5, min_hits=2):
    """BM25 of the prompt against active rules (rule text + keywords + tags). Highest first."""
    q = set(words(prompt))
    rows = [r for r in rules if r.get("status", "active") == "active"]
    if not q or not rows:
        return []
    docs = [words(r["rule"]) + words(" ".join(r.get("keywords", []))) * 2 + words(" ".join(TAGS.get(t, "") for t in r.get("tags", [])))
            for r in rows]
    n, avg = len(docs), sum(map(len, docs)) / len(docs)
    df = {w: sum(1 for d in docs if w in d) for w in q}
    out = []
    for r, d in zip(rows, docs):
        hits = [w for w in q if w in d]
        if len(hits) < min_hits:
            continue
        s = sum(math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5)) * d.count(w) * 2.2 / (d.count(w) + 1.2 * (0.25 + 0.75 * len(d) / avg))
                for w in hits)
        if s >= min_score:
            out.append((s, r))
    out.sort(key=lambda x: -x[0])
    return [dict(r, score=round(s, 2)) for s, r in out]


def render():
    rules = load(RULES)
    L = ["# Taste rules (user-approved)", "", "Generated from rules.json by taste.py; edit through `taste.py approve|retire`.", ""]
    for r in rules:
        mark = "" if r.get("status", "active") == "active" else f" ({r['status']})"
        L.append(f"- **{r['id']}**{mark} [{', '.join(r.get('tags', []))}] {r['rule']}  \n  evidence: "
                 + "; ".join(f"{e['date']} \"{e['quote'][:80]}\"" for e in r.get("evidence", [])[:3]))
    open(VIEW, "w").write("\n".join(L) + "\n")


def log_recall(ids, chars, ms):
    try:
        with open(RECALL, "a") as f:
            f.write(json.dumps({"ts": int(time.time()), "ids": ids, "chars": chars, "ms": ms}) + "\n")
    except OSError:
        pass


def week_markers(a, b, turns):
    """P1-P5 for the scorecard, for the week [a, b) (epoch s)."""
    rec = [json.loads(x) for x in open(RECALL)] if os.path.exists(RECALL) else []
    wk = [r for r in rec if a <= r["ts"] < b]
    rules, cands = load(RULES), load(CANDS)
    active = [r for r in rules if r.get("status", "active") == "active"]
    used = {i for r in rec if b - 28 * 86400 <= r["ts"] < b for i in r["ids"]}
    in_week = lambda x, k: a <= x.get(k, 0) < b
    chars = sorted(r["chars"] for r in wk)
    return {
        "P1": round(100 * len(wk) / turns, 2) if turns else None,
        "P2": round(chars[len(chars) // 2] / 4) if chars else None,
        "P3": round(100 * len([r for r in active if r["id"] in used]) / len(active), 1) if active else None,
        "P4": f"{sum(in_week(c, 'first_seen') for c in cands)} / {sum(in_week(r, 'added') for r in rules)} / "
              f"{sum(in_week(c, 'decided') for c in cands if c.get('status') == 'rejected')}",
        "P5": sum(1 for c in cands if c.get("after_rule") and in_week(c, "last_seen")),
    }


MAX_RULES, MAX_CHARS, JEV_TIMEOUT = 4, 600, 1.5


def jev_probs(site, question, items, context, timeout=JEV_TIMEOUT):
    """Jev P(yes) per item within `timeout` seconds; None when Jev is off, slow or refuses."""
    import concurrent.futures
    import sys
    sys.path.insert(0, os.path.expanduser("~/.claude/hooks"))
    try:
        import jev_lib
        ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        fut = ex.submit(jev_lib.noul, site, question, items, context)
        ex.shutdown(wait=False)
        return fut.result(timeout=timeout)
    except Exception:
        return None


def recall(prompt, rules=None, use_jev=True):
    """The rules to inject for this prompt (may be empty). Silent on short prompts and slash commands."""
    p = prompt.strip()
    if len(p.split()) < 4 or p.startswith(("/", "<")):
        return []
    p = p[:800]  # long prompts are mostly pasted material; their opening says what the task is
    hits = rank(p, load(RULES) if rules is None else rules)
    ui = is_ui(p)
    hits = [r for r in hits if ui or not set(r.get("tags", [])) <= {"layout", "colour", "type", "motion", "copy", "a11y", "ui"}]
    if hits and use_jev:  # BM25 alone fires on loose word overlap; Jev confirms every hit (only ~10% of prompts get here)
        probs = jev_probs("taste-recall", "Should an assistant apply this standing user preference while doing the request?",
                          [r["rule"] for r in hits[:8]], "Request: " + redact(p[:1500]))
        if probs is not None:
            hits = [r for r, pr in sorted(zip(hits, probs), key=lambda x: -x[1]) if pr >= 0.7]
        else:
            hits = [r for r in hits if r["score"] >= 4.0][:2]
    out, size = [], 0
    for r in hits[:MAX_RULES]:
        if size + len(r["rule"]) > MAX_CHARS:
            break
        out.append(r)
        size += len(r["rule"]) + 4
    return out


def note(rules):
    return "Taste (user-approved, apply if relevant):\n" + "\n".join(f"- {r['rule']}" for r in rules)
