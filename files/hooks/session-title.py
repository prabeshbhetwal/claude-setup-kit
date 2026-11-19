#!/usr/bin/env python3
"""Keeps each desktop-app session's title a short label of what the session is doing NOW (optional kit tool).

`session-title.py prompt` (UserPromptSubmit):
  - title missing, or not the one Claude last set (app auto-title, manual rename) -> ask Claude to set it
  - every RECHECK prompts -> ask Claude to re-state the title for the current activity (same title is fine)
`session-title.py stop` (Stop):
  - if this turn was asked and Claude did not set a title for THIS session, or the title breaks the rules
    (>4 words, punctuation, US spelling), block the stop once so it fixes it.
    Second refusal (stop_hook_active) is let through; the next prompt asks again.
  - if Claude asked but the app did not apply it (the user declined a rename of their own title), the
    user's title is accepted as is.

Desktop app only (CLAUDE_CODE_ENTRYPOINT=claude-desktop): elsewhere the title tool does not exist.
Any internal error exits 0 silently, so the hook can never block work.
State: ~/.claude/cache/session-title/<session_id>.json (pruned after 30 days).
Settings: ~/.claude/kit/session-title.json  {"recheck": 5, "spelling": "au"}  (recheck = prompts between checks;
spelling = au (default, checked), us or none (asked for in the instructions, not checked)).
Reverse: delete this file and its two settings.json entries.
`session-title.py selftest` runs the checks below without the desktop app.
"""
import json
import os
import pathlib
import re
import sys
import time

CONF = pathlib.Path.home() / ".claude" / "kit" / "session-title.json"
SPELLING = {"au": "Australian English (-ise not -ize), ", "us": "American English (-ize not -ise), ", "none": ""}
PRUNE_DAYS = 30
TOOL = "mcp__ccd_session_mgmt__set_session_title"



def settings():
    """(recheck, spelling) from the settings file; anything missing or unreadable falls back to 5 and au."""
    try:
        c = json.loads(CONF.read_text())
        c = c if isinstance(c, dict) else {}
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
        f"Call {TOOL} with session_id \"self\" (load it with ToolSearch if deferred); do not mention it in your reply."
    )

STATE_DIR = pathlib.Path.home() / ".claude" / "cache" / "session-title"

# US spellings. Australian names that look American ("Labor" party, electricity "meter") are deliberately absent.
US_SPELLING = re.compile(
    r"\b\w*(?:iz(?:e|es|ed|ing|er|ers|able|ation|ations|ational)|yz(?:e|es|ed|ing|er|ers))\b"
    r"|\b(?:color|behavior|center|favor|honor|flavor|humor|neighbor|rumor|vapor|harbor|armor|endeavor|odor"
    r"|parlor|valor|vigor|savior)(?:s|ed|ing|ful|ite|ites|al|ist|ists|hood|hoods|less|able)?\b"
    r"|\b(?:catalog|analog|defense|offense|gray|theater|fiber|liter|aluminum|skeptic)s?\b"
    r"|\b(?:cancel|travel|label|model|fuel|signal|channel|level|marvel|quarrel|counsel)(?:ed|ing|er|ers)\b",
    re.I,
)
US_OK = {"size", "sizes", "sized", "sizing", "resize", "resized", "resizing", "downsize", "prize", "prizes",
         "prized", "prizing", "seize", "seizes", "seized", "seizing", "maize", "citizen", "citizens"}
# Dots inside a token are fine (Release 1.3.5, Next.js, Python 3.x); any other non-word character is punctuation.
INNER_DOT = re.compile(r"(?<=\w)\.(?=\w)")


def problems(title, spelling="au"):
    """Mechanical checks of the title rules; returns a list of problems (empty if fine)."""
    if not isinstance(title, str) or not title.strip():
        return ["empty title"]
    found = []
    if len(title.split()) > 4:
        found.append("more than 4 words")
    if any(not (c.isalnum() or c.isspace() or c == "-") for c in INNER_DOT.sub("", title)):
        found.append("contains punctuation")
    for m in US_SPELLING.finditer(title) if spelling == "au" else ():  # only the Australian profile is checked
        if m.group(0).lower() not in US_OK:
            found.append(f"US spelling \"{m.group(0)}\"")
    return found


def records(path, offset=0):
    """Parsed transcript lines (dicts only) from byte `offset`; restarts from 0 if the file shrank."""
    try:
        if offset > os.path.getsize(path):
            offset = 0
        with open(path, "rb") as f:
            f.seek(offset)
            for raw in f:
                line = raw.decode("utf-8", errors="replace")
                if '"custom-title"' not in line and "set_session_title" not in line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    yield obj
    except (OSError, TypeError):
        return


def current_title(path):
    """Last title record in the transcript ('' if cleared, None if never titled)."""
    title = None
    for obj in records(path):
        if obj.get("type") == "custom-title":
            value = obj.get("customTitle")
            title = value if isinstance(value, str) else title
    return title


def title_requested_since(path, offset, own_ids):
    """Title Claude asked for THIS session after `offset`, or None if it never called the tool."""
    found = None
    for obj in records(path, offset):
        message = obj.get("message")
        blocks = message.get("content") if isinstance(message, dict) else None
        for b in blocks if isinstance(blocks, list) else []:
            if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                continue
            name, args = b.get("name", ""), b.get("input")
            if (name == TOOL or name.endswith("__set_session_title")) and isinstance(args, dict) \
                    and args.get("session_id") in own_ids and isinstance(args.get("title"), str):
                found = args["title"]
    return found


def on_prompt(data, state):
    recheck, spelling = settings()
    state["count"] = state.get("count", 0) + 1
    tpath = data.get("transcript_path") or ""
    title = current_title(tpath)
    if not title or title != state.get("ours"):
        message = "Session title: before your reply, set this session's title. " + rules(spelling)
    elif state["count"] % recheck == 0:
        message = (
            f"Session title check: the title is \"{title}\". Call the title tool now with the label that fits "
            "the current activity (re-sending the same title is fine if it still fits). " + rules(spelling)
        )
    else:
        state["pending"] = False  # title is current; drop any request left open by an interrupted turn
        return None
    if not state.get("pending"):  # keep the earliest offset while a request is open
        try:
            state["offset"] = os.path.getsize(tpath)
        except (OSError, TypeError):
            state["offset"] = 0
    state["pending"] = True
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": message}}


def on_stop(data, state):
    if not state.get("pending"):
        return None
    tpath = data.get("transcript_path") or ""
    own_ids = {"self", data.get("session_id"), os.environ.get("CLAUDE_CODE_HOST_SESSION_ID")} - {None, ""}
    asked = title_requested_since(tpath, state.get("offset", 0), own_ids)
    actual = current_title(tpath)
    if asked is not None and actual != asked:
        # The app did not apply it (the user declined renaming their own title): respect the user's title.
        state.update(pending=False, ours=actual)
        return None
    spelling = settings()[1]
    issues = problems(asked, spelling) if asked is not None else ["requested this turn but not set"]
    if not issues:
        state.update(pending=False, ours=asked)
        return None
    if data.get("stop_hook_active"):
        state["pending"] = False
        return None  # don't loop; `ours` stays unchanged so the next prompt asks again
    return {"decision": "block", "reason": f"Session title: {'; '.join(issues)}. Set it again. " + rules(spelling)}


def prune():
    cutoff = time.time() - PRUNE_DAYS * 86400
    for p in STATE_DIR.iterdir():
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
        except OSError:
            pass


def selftest():
    assert problems("Onboarding design") == [] and problems("Release 1.3.5") == [] and problems("Next.js upgrade") == []
    assert problems("") == ["empty title"] and any("words" in x for x in problems("one two three four five"))
    assert any("punctuation" in x for x in problems("Fix: login"))
    assert any("US spelling" in x for x in problems("Optimizing queries")) and problems("Optimising queries") == []
    assert problems("Optimizing queries", "us") == [] and problems("Resize images") == [] and problems("Labor policy") == []
    assert "Australian" in rules("au") and "American" in rules("us") and "English" not in rules("none")
    st = {}
    out = on_prompt({"transcript_path": "/nonexistent"}, st)  # no title yet -> asks, and marks the turn pending
    assert "set this session's title" in out["hookSpecificOutput"]["additionalContext"] and st["pending"]
    assert on_stop({"transcript_path": "/nonexistent", "session_id": "s"}, st)["decision"] == "block"
    assert on_stop({"transcript_path": "/nonexistent", "session_id": "s", "stop_hook_active": True}, st) is None
    print("selftest ok")


def main():
    if sys.argv[1:] == ["selftest"]:
        return selftest()
    if os.environ.get("CLAUDE_CODE_ENTRYPOINT") != "claude-desktop":
        return  # no title tool outside the desktop app
    mode = sys.argv[1] if len(sys.argv) > 1 else "prompt"
    data = json.load(sys.stdin)
    if not isinstance(data, dict):
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / f"{data.get('session_id') or 'x'}.json"
    try:
        state = json.loads(path.read_text())
        state = state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        state = {}
    out = on_stop(data, state) if mode == "stop" else on_prompt(data, state)
    if mode != "stop" and state.get("count") == 1:
        prune()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    os.replace(tmp, path)  # atomic: a timeout kill can't leave a half-written state file
    if out:
        print(json.dumps(out))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # never let a hook bug block or break a session
        sys.exit(0)
