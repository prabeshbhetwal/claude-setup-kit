"""Transcript scanning for setup-monitor.py: one pass per file, no network, no Claude tokens.

A turn starts at a prompt the person typed (see typed()); requests, tool calls and hook output after it belong to it.
Usage is deduped by message.id (each content block repeats it). Context = input + cache_read + cache_creation.
Cost = API-equivalent USD from the price card in mods/model-pilot/hooks/prices.ts (cache write 1.25x for 5-minute,
2x for 1-hour entries). Plan usage, not money.
"""
import json
import re
from datetime import datetime

# USD per million tokens: in, out, cache read (mods/model-pilot/hooks/prices.ts)
PRICE = {"haiku": (0.1, 0.5, 0.01), "sonnet": (2, 10, 0.1), "opus": (4, 20, 0.2), "fable": (8, 40, 0.2)}
HAIKU_LONG = (0.5, 2.5, 0.05)  # haiku prompts above 100k
FAMS = tuple(PRICE)
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
UI_EXT = re.compile(r"\.(tsx|jsx|vue|svelte|css|scss|sass|less|html|astro|swift|xib|storyboard)$", re.I)
TEST_CMD = re.compile(r"(^|[;&|]\s*|\s)(pytest|python3? -m (pytest|unittest)|(npm|pnpm|yarn|bun)( run)? test|vitest|jest"
                      r"|go test|cargo test|swift test|xcodebuild[^|;&]* test|make (test|check)|\./gradlew [^|;&]*test)\b")
CORRECTION = re.compile(r"^\s*(no[,. !]|nope|wrong|that'?s (not|wrong)|not what i|redo|undo|revert|roll ?back|try again"
                        r"|still (broken|wrong|not|doesn'?t|failing)|you (broke|missed|forgot|didn'?t)|why did you|stop |don'?t do"
                        r"|i said|i told you|again[,.]? |this is wrong|doesn'?t work|didn'?t work|not working)", re.I)
BLOCKED = re.compile(r"Fact-Forcing Gate|blocked by|PreToolUse:.*(denied|block)|Permission to use .* (was )?denied"
                     r"|user (doesn't|does not) want to proceed|requires approval|Operation not permitted", re.I)
AUTOMATED = ("Below is a conversation log", "You are a memory", "Summarize the following", "Summarise the following")
SKIP_PREFIX = ("<task-notification", "<command-", "<local-command", "<system-reminder", "[Request interrupted", "<bash-",
               "Caveat:", "<user-prompt-submit-hook", "This session is being continued from a previous conversation")


def fam(model):
    m = (model or "").lower()
    return next((f for f in FAMS if f in m), None)


def ts(o):
    try:
        return datetime.fromisoformat(o["timestamp"].replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def ctx(u):
    return (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)


def cost(model, u):
    f = fam(model)
    if not f:
        return 0.0
    i, o, r = HAIKU_LONG if f == "haiku" and ctx(u) > 100_000 else PRICE[f]
    cc = u.get("cache_creation") or {}
    w5, w1 = cc.get("ephemeral_5m_input_tokens"), cc.get("ephemeral_1h_input_tokens")
    if w5 is None and w1 is None:
        w5, w1 = 0, u.get("cache_creation_input_tokens") or 0  # unknown split: the main chat's 1-hour cache
    return ((u.get("input_tokens") or 0) * i + (u.get("output_tokens") or 0) * o + (u.get("cache_read_input_tokens") or 0) * r
            + (w5 or 0) * i * 1.25 + (w1 or 0) * i * 2) / 1e6


def prompt_text(o):
    """The typed text of a user entry, or None when it is not a typed prompt."""
    if o.get("type") != "user" or o.get("isMeta") or o.get("toolUseResult") is not None or o.get("isSidechain"):
        return None
    c = (o.get("message") or {}).get("content")
    if isinstance(c, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
            return None
        c = "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    if not isinstance(c, str) or not c.strip() or c.lstrip().startswith(SKIP_PREFIX):
        return None
    return c


def is_correction(text):
    return len(text) <= 300 and bool(CORRECTION.search(text))


def scan(path, since, sub=False, seen=None):
    """Requests, turns and events of one transcript from `since` (epoch s). Returns a dict, see keys below.
    `seen` (a set shared across files) drops requests and prompts a forked or resumed session copied from another file."""
    seen = set() if seen is None else seen
    reqs = {}          # message.id -> [t, model, usage]
    turns = []         # [t, text, hook_chars, interrupted]
    tools = {}         # tool_use id -> (name, input, t)
    results = []       # (tool_use id, is_error, blocked, t)
    ev = {"compact": [], "hook_fail": [], "findings": [], "cost_state": None, "cwd": None, "edits": [], "ui_edits": 0}
    order = []         # (t, kind, ref): request ids and turn starts in file order, to tie requests to turns
    for line in open(path, errors="ignore"):
        if '"api-request' in line[:60] or '"file-history' in line[:60]:
            continue
        try:
            o = json.loads(line)
        except ValueError:
            continue
        typ = o.get("type")
        if typ == "cost-state":
            ev["cost_state"] = o.get("totalCostUSD")
            continue
        t = ts(o)
        if t is None or t < since:
            continue
        ev["cwd"] = ev["cwd"] or o.get("cwd")
        msg = o.get("message") if isinstance(o.get("message"), dict) else {}
        if typ == "assistant" and msg.get("usage"):
            mid = msg.get("id") or o.get("uuid")
            old = reqs.get(mid)
            if not old and mid in seen:
                continue
            seen.add(mid)
            if not old:
                order.append((t, "req", mid))
            if not old or (msg["usage"].get("output_tokens") or 0) >= (old[2].get("output_tokens") or 0):
                reqs[mid] = [old[0] if old else t, msg.get("model"), msg["usage"]]
            for c in msg.get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    inp = c.get("input") or {}
                    tools[c.get("id")] = (c.get("name") or "", inp, t)
                    if c.get("name") in EDIT_TOOLS:
                        p = str(inp.get("file_path") or inp.get("notebook_path") or "")
                        ev["edits"].append(p)
                        ev["ui_edits"] += bool(UI_EXT.search(p))
                    elif c.get("name") == "mcp__ccd_review__ReportFindings" or c.get("name") == "ReportFindings":
                        ev["findings"].append(len(inp.get("findings") or []))
        elif typ == "user" and not sub:
            text = prompt_text(o)
            c = msg.get("content")
            key = ("p", o.get("timestamp"), text[:80]) if text is not None else None
            if text is not None and key not in seen:
                seen.add(key)
                turns.append([t, text, 0, False])
                order.append((t, "turn", len(turns) - 1))
            elif isinstance(c, list):
                for b in c:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "tool_result":
                        body = json.dumps(b.get("content"))[:4000]
                        results.append((b.get("tool_use_id"), bool(b.get("is_error")), bool(BLOCKED.search(body)), t))
                    elif b.get("type") == "text" and b.get("text", "").startswith("[Request interrupted") and turns:
                        turns[-1][3] = True
        elif typ == "user" and sub:
            for b in msg.get("content") if isinstance(msg.get("content"), list) else []:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    body = json.dumps(b.get("content"))[:4000]
                    results.append((b.get("tool_use_id"), bool(b.get("is_error")), bool(BLOCKED.search(body)), t))
        elif typ == "attachment":
            a = o.get("attachment") or {}
            k = a.get("type")
            if k == "hook_additional_context" and a.get("hookEvent") == "UserPromptSubmit" and turns:
                turns[-1][2] += len(json.dumps(a.get("content"))) - 2
            elif k in ("hook_cancelled", "hook_non_blocking_error"):
                ev["hook_fail"].append(t)
        elif typ == "system" and o.get("subtype") == "compact_boundary":
            ev["compact"].append(t)
    # tie each request to the turn before it
    req_turn, cur = {}, None
    for t, kind, ref in sorted(order, key=lambda x: x[0]):
        if kind == "turn":
            cur = ref
        else:
            req_turn[ref] = cur
    ev["automated"] = bool(turns) and turns[0][1].lstrip().startswith(AUTOMATED)
    return {"reqs": reqs, "req_turn": req_turn, "turns": turns, "tools": tools, "results": results, **ev}
