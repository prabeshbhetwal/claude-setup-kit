#!/usr/bin/env python3
"""UserPromptSubmit gate for `codegraph prompt-hook`.

codegraph injects ~10-20 KB of symbol context on almost any prompt in an indexed
repo, including plain conversation and questions about Claude's own tooling.
This gate forwards the prompt only when it is about the repo's code. Skipped
prompts lose nothing: the model can still call the codegraph_explore MCP tool.

Self-check: python3 codegraph-gate.py --test
"""
import json
import os
import re
import shutil
import subprocess
import sys

CODE_EXT = r"swift|py|ts|tsx|js|jsx|mjs|go|rs|java|kt|rb|c|cc|cpp|h|hpp|m|mm|cs|php|scala|sh|sql|vue|svelte|dart|lua|zig"

# Words that look like identifiers but are product names, not repo symbols.
BRANDS = {"codegraph", "graphify", "github", "gitlab", "claude", "claudecode", "openai",
          "chatgpt", "javascript", "typescript", "macos", "iphone", "ipad", "youtube",
          "supermemory", "loopalternative", "superpowers", "rufl", "ruflo"}

STRONG = [  # +2 each: unmistakable code references
    r"`[^`]+`",                                    # inline code
    rf"[\w./-]+\.(?:{CODE_EXT})\b(?::\d+)?",      # file path, optionally :line
    r"\b\w+\(\)",                                  # call syntax foo()
    r"\b[a-z]+_[a-z0-9_]+\b",                      # snake_case
    r"Traceback|Exception\b|\berror:|fatal:|panic:|SIGABRT|EXC_BAD",
]
WEAK = [  # +1 each: code-work vocabulary
    r"\bbugs?\b", r"\bcrash", r"\bfix", r"\brefactor", r"\bimplement", r"\bfunction",
    r"\bmethod", r"\bclass(es)?\b", r"\bstruct", r"\benum\b", r"\bprotocol", r"\bmodule",
    r"\bendpoint", r"\btests?\b", r"\bcompil", r"\bbuild (fails|error|broke)", r"\bcallers?\b",
    r"\brename", r"\bsignature", r"\bregression", r"\bcodebase\b", r"\bdead code\b", r"\bblast radius\b",
]
LOCATE = [  # +2 each: "find it in the code" questions, codegraph's best case
    r"\bhow does\b", r"\bwhere (is|are|does|do)\b", r"\bwhich files?\b", r"\bwhat calls\b",
    r"\bimpact of\b",
]
META = [  # -2 each: talk about Claude's own setup or the conversation, not repo code
    r"settings\.json", r"claude\.md", r"\bhooks?\b", r"\bplugins?\b", r"\bmcp\b", r"\bskills?\b",
    r"\bcaveman\b", r"\brtk\b", r"\bcodegraph\b", r"\bgraphify\b", r"context[- ]mode",
    r"\bconversation\b", r"\bsession\b", r"\bclaude[- ]flow\b",
]


def camel_identifiers(prompt):
    words = re.findall(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+\b|\b[a-z]+[A-Z]\w*\b", prompt)
    return [w for w in words if w.lower() not in BRANDS]


def score(prompt):
    s = sum(2 for pat in STRONG if re.search(pat, prompt))
    s += 2 if camel_identifiers(prompt) else 0
    low = prompt.lower()
    s += sum(1 for pat in WEAK if re.search(pat, low))
    s += sum(2 for pat in LOCATE if re.search(pat, low))
    s -= sum(2 for pat in META if re.search(pat, low))
    return s


def is_code_prompt(prompt):
    # Harness traffic (other sessions' messages, idle notices, task results) quotes paths and
    # commit text but is not a request about the code.
    if prompt.lstrip().startswith(("<cross-session-message", "[Cross-session", "<task-notification", "<ci-monitor-event")):
        return False
    return len(prompt.split()) >= 3 and score(prompt) >= 2


def jev_says_code(prompt, cwd):
    """Second opinion after the regex: Jev drops false triggers (paths quoted in chat, tool names).
    Fail-open: Jev unavailable -> True, so the regex alone decides as before."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import jev_lib
        ok = jev_lib.keep("codegraph-gate", "Is this message asking about, or asking to change, source code "
                          "in the current repository?", [prompt[:3000]], "codegraph_min", cwd=cwd)
        return ok is None or ok[0]
    except Exception:
        return True


def main():
    raw = sys.stdin.read()
    try:
        prompt = json.loads(raw).get("prompt", "")
    except ValueError:
        return
    if not is_code_prompt(prompt) or not jev_says_code(prompt, json.loads(raw).get("cwd", "")):
        return
    try:
        out = subprocess.run([shutil.which("codegraph") or "codegraph", "prompt-hook"], input=raw, capture_output=True,
                             text=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return
    sys.stdout.write(cap(out))


# ponytail: fixed char budget (~2k tokens); raise it if source keeps getting omitted.
CAP = 8000
CLOSE = "</codegraph_context>"


def cap(out, limit=CAP):
    """Keep the summary and whole per-file source blocks, in order, while under budget."""
    if len(out) <= limit:
        return out
    body = out.rstrip()
    if body.endswith(CLOSE):
        body = body[:-len(CLOSE)]
    head, *files = re.split(r"(?m)^(?=\*\*`)", body)  # file blocks start with **`path`**
    kept, dropped = head, []
    for block in files:
        if not dropped and len(kept) + len(block) <= limit:
            kept += block
        else:
            dropped.append(block.split(" — ", 1)[0].strip("*\n "))
    if dropped:
        kept += f"\n_Source omitted for budget: {', '.join(dropped)}. Call codegraph_explore if needed._\n"
    return kept + CLOSE + "\n"


def test():
    run = ["fix the crash in SettingsModel when the ring opens",
           "where is the snap speed preset applied?",
           "why does `applyLayout()` ignore the gap setting",
           "InputService.swift:164 throws a fatal: index out of range",
           "refactor the tiling function and add tests"]
    skip = ["yes go ahead", "commit it",
            "make sure the model scans the project or the conversation; codegraph and "
            "graphify should be smart, same for RTK, context mode and caveman",
            "remove claude-flow from the mcp settings.json",
            "what do you think about the colour of the ring in dark mode?",
            "thanks, that looks good",
            '<cross-session-message from="x">fixed MyApp/UI/OverlayPane.swift and `applyPreview()`</cross-session-message>']
    for p in run:
        assert is_code_prompt(p), (p, score(p))
    for p in skip:
        assert not is_code_prompt(p), (p, score(p))
    small = "<codegraph_context>\n**Exploration: x**\n</codegraph_context>\n"
    assert cap(small) == small
    big = ("<codegraph_context>\n**Exploration: x**\n" + "**`a.swift`** — f(calls)\n```swift\n" + "a" * 50
           + "\n```\n" + "**`b.swift`** — g(calls)\n```swift\n" + "b" * 500 + "\n```\n" + CLOSE + "\n")
    capped = cap(big, limit=200)
    assert "a" * 50 in capped and "b" * 500 not in capped, capped
    assert "`b.swift`" in capped and capped.endswith(CLOSE + "\n") and capped.count("```") % 2 == 0
    print("ok")


if __name__ == "__main__":
    test() if sys.argv[1:] == ["--test"] else main()
