#!/usr/bin/env python3
"""Keeps each session's title a short label of what the session is doing NOW (optional kit tool: "Dynamic session titles").

`session-title.py prompt` (UserPromptSubmit):
  - title missing, or not the one Claude last set (app auto-title, manual rename) -> ask Claude to set it
  - every RECHECK prompts -> ask Claude to re-state the title for the current activity (same title is fine)
`session-title.py stop` (Stop):
  - if this turn was asked and Claude did not call set_session_title, or the title breaks the rules
    (>4 words, punctuation, US spelling), block the stop once so it fixes it.
    Second refusal (stop_hook_active) is let through; the next prompt asks again.

The app asks the user to approve renaming a title they set themselves, so manual titles stay under user control.
State: ~/.claude/cache/session-title/<session_id>.json. Settings: ~/.claude/kit/session-title.json
  {"recheck": 5, "spelling": "au"}   recheck = prompts between checks; spelling = au (default), us or none.
Needs the desktop app's session tools (mcp__ccd_session_mgmt__set_session_title). Reverse: delete this file and its two
settings.json entries (the doctor lists them); the state folder is harmless.
"""
import json
import os
import pathlib
import re
import sys

CONF = pathlib.Path.home() / ".claude" / "kit" / "session-title.json"
SPELLING = {"au": "Australian English (-ise not -ize), ", "us": "American English (-ize not -ise), ", "none": ""}
TOOL = "set_session_title"
MAX_MISSES = 2  # unanswered requests in a row before the hook goes quiet for the session (no title tool)
STATE_DIR = pathlib.Path.home() / ".claude" / "cache" / "session-title"


def settings():
    """(recheck, spelling) from the settings file; anything missing or unreadable falls back to 5 and au."""
    try:
        c = json.loads(CONF.read_text())
    except (OSError, ValueError):
        c = {}
    n = c.get("recheck")
    n = n if isinstance(n, int) and not isinstance(n, bool) and n >= 1 else 5
    sp = c.get("spelling")
    return n, sp if sp in SPELLING else "au"


def rules(spelling):
    return (
        "Name what the session is doing NOW, not where it started: if the work has moved on within the same "
        "theme, name the current part (\"Onboarding\" -> \"Onboarding design\" -> \"Onboarding copy\"). "
        f"1 to 4 words, {SPELLING[spelling]}no project name, no sentence, no punctuation. "
        "Call mcp__ccd_session_mgmt__set_session_title with session_id \"self\" (load it with ToolSearch if "
        "deferred); do not mention it in your reply."
    )


def load(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {"count": 0}


def transcript_lines(path, offset=0):
    try:
        with open(path, encoding="utf-8") as f:
            f.seek(offset)
            yield from f
    except OSError:
        return


def current_title(path):
    title = None
    for line in transcript_lines(path):
        if '"custom-title"' in line:
            try:
                title = json.loads(line).get("customTitle") or title
            except ValueError:
                pass
    return title


def title_set_since(path, offset):
    """Title Claude passed to set_session_title after `offset`, or None if it never called it."""
    found = None
    for line in transcript_lines(path, offset):
        if TOOL not in line:
            continue
        try:
            blocks = json.loads(line).get("message", {}).get("content", [])
        except ValueError:
            continue
        for b in blocks if isinstance(blocks, list) else []:
            if b.get("type") == "tool_use" and b.get("name", "").endswith(TOOL):
                found = b.get("input", {}).get("title") or found
    return found


def on_prompt(data, state):
    recheck, spelling = settings()
    state["count"] = state.get("count", 0) + 1
    if state.get("misses", 0) >= MAX_MISSES:  # no title tool here (command line): stop asking this session
        state["pending"] = False
        return None
    tpath = data.get("transcript_path", "")
    title = current_title(tpath)
    if not title or title != state.get("ours"):
        message = "Session title: before your reply, set this session's title. " + rules(spelling)
    elif state["count"] % recheck == 0:
        message = (
            f"Session title check: the title is \"{title}\". Call the title tool now with the label that fits "
            "the current activity (re-sending the same title is fine if it still fits). " + rules(spelling)
        )
    else:
        state["pending"] = False
        return None
    state["pending"] = True
    try:
        state["offset"] = os.path.getsize(tpath)
    except OSError:
        state["offset"] = 0
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": message}}


US_SPELLING = re.compile(
    r"\b\w*(?<!s)(?:iz(?:e|es|ed|ing|ation|ations|er|ers)|yz(?:e|es|ed|ing))\b"
    r"|\b(?:color|behavior|center|favor|honor|labor|flavor|catalog|analog)s?\b",
    re.I,
)
US_OK = {"size", "sizes", "sized", "sizing", "resize", "resizing", "prize", "prizes", "seize", "citizen"}


def problems(title, spelling="au"):
    """Mechanical checks of the title rules; returns a list of problems (empty if fine)."""
    found = []
    if len(title.split()) > 4:
        found.append("more than 4 words")
    if re.search(r"[,;:!?\"']|\.(?!\d)", title):  # dots allowed in versions (Release 1.3.5)
        found.append("contains punctuation")
    for m in US_SPELLING.finditer(title) if spelling == "au" else ():  # only the Australian profile is checked
        w = m.group(0).lower()
        if w not in US_OK:
            found.append(f"US spelling \"{m.group(0)}\"")
    return found


def on_stop(data, state):
    if not state.get("pending"):
        return None
    title = title_set_since(data.get("transcript_path", ""), state.get("offset", 0))
    spelling = settings()[1]
    issues = problems(title, spelling) if title else ["requested this turn but not set"]
    state["misses"] = 0 if title else state.get("misses", 0) + 1
    if not title and state["misses"] >= MAX_MISSES:
        state["pending"] = False  # never block where the tool does not exist
        return None
    if not issues:
        state.update(pending=False, ours=title)
        return None
    if data.get("stop_hook_active"):
        state["pending"] = False  # don't loop; next prompt asks again
        if title:
            state["ours"] = title
        return None
    return {"decision": "block", "reason": f"Session title: {'; '.join(issues)}. Set it again. " + rules(spelling)}


def selftest():
    assert problems("Onboarding design") == [] and problems("Release 1.3.5") == []
    assert any("words" in p for p in problems("one two three four five"))
    assert any("punctuation" in p for p in problems("Fix: login"))
    assert any("US spelling" in p for p in problems("Optimizing queries")) and problems("Optimising queries") == []
    assert problems("Optimizing queries", "us") == [] and problems("Resize images") == []
    assert "Australian" in rules("au") and "American" in rules("us") and "English" not in rules("none")
    st = {}
    out = on_prompt({"transcript_path": "/nonexistent"}, st)  # no title yet -> asks, and marks the turn pending
    assert "set this session's title" in out["hookSpecificOutput"]["additionalContext"] and st["pending"]
    assert on_stop({"transcript_path": "/nonexistent"}, st)["decision"] == "block"  # asked, never set -> blocked once
    assert on_stop({"transcript_path": "/nonexistent", "stop_hook_active": True}, st) is None  # second miss: let through
    assert on_prompt({"transcript_path": "/nonexistent"}, st) is None  # two misses: quiet for the session
    assert on_stop({"transcript_path": "/nonexistent"}, st) is None
    print("selftest ok")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "prompt"
    if mode == "selftest":
        return selftest()
    data = json.load(sys.stdin)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / f"{data.get('session_id', 'x')}.json"
    state = load(path)
    out = on_stop(data, state) if mode == "stop" else on_prompt(data, state)
    path.write_text(json.dumps(state))
    if out:
        print(json.dumps(out))


if __name__ == "__main__":
    main()
