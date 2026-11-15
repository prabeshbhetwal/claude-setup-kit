#!/usr/bin/env python3
"""PreToolUse hook (Bash): block `rm`/`rmdir` unless every target is in a temp dir.

Enforces the CLAUDE.md rule "never permanently delete — move to _trash/".
Run `python3 block-rm.py --test` for the self-check.
ponytail: regex guard, not a shell parser — misses `find -delete`, `unlink`, `git clean -f`
and deletes inside scripts; the CLAUDE.md rule covers those. Extend RM if one shows up.
"""
import json
import re
import shlex
import sys

TEMP_PREFIXES = ("/tmp/", "/private/tmp/", "/var/folders/", "/private/var/folders/")
RM = re.compile(r"(?:^|[;&|(\n])\s*(?:(?:sudo|command|env|nohup|exec)\s+|xargs\s+(?:-\S+\s+)*)*\\?(?:/usr)?(?:/bin/)?(rm|rmdir)\b")
REASON = ("Blocked by your rule: never permanently delete. Move it instead: "
          "trashmv <path>... (files into ~/_trash/<project>/<date>/<original sub-folders>, outside iCloud, logged in moves.tsv). "
          "Temp folders (/tmp, /private/tmp, /var/folders) are exempt.")


def targets(segment):
    try:
        words = shlex.split(segment)
    except ValueError:
        return None  # unparseable quoting → treat as unsafe
    if words and words[0] == "sudo":
        words = words[1:]
    return [w for w in words[1:] if not w.startswith("-")]


def blocked(command):
    for m in RM.finditer(command):
        segment = re.split(r"[;&|)\n]", command[m.start(1):], maxsplit=1)[0]
        paths = targets(segment)
        if not paths or not all(p.startswith(TEMP_PREFIXES) for p in paths):
            return True
    return False


def main():
    data = json.load(sys.stdin)
    if blocked(data.get("tool_input", {}).get("command", "")):
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                 "permissionDecision": "deny",
                                                 "permissionDecisionReason": REASON}}))


def test():
    assert blocked("rm notes.md")
    assert blocked("rm -rf src/old")
    assert blocked("ls && rm -f a.txt")
    assert blocked("sudo rm /etc/hosts")
    assert blocked("find . -name '*.log' | xargs rm")
    assert blocked("rm -rf /tmp/x ~/work")          # one non-temp target
    assert blocked('rm -rf "$T"')                     # unresolved variable
    assert not blocked("rm -rf /tmp/claude-501/probe")
    assert not blocked("rm /private/var/folders/ab/x.tmp")
    assert not blocked("mv old.md _trash/")
    assert not blocked('mv old.md "$HOME/_trash/MyApp/2026-11-14/"')
    assert not blocked("trashmv old.md")
    assert not blocked("git commit -m 'remove rm usage'")
    assert not blocked("echo firmware")               # 'rm' inside a word
    assert blocked("  rm stray.txt")                  # leading whitespace
    assert blocked("cd src\nrm old.ts")               # newline-separated
    assert blocked("command rm -f x")                 # builtin bypass
    assert blocked("/bin/rm -rf build")               # absolute binary
    assert blocked("\\rm old.md")                    # alias bypass
    assert blocked("env rm x && nohup rm y")
    assert not blocked("git rm --cached x")           # git rm: recoverable from git
    assert not blocked("npm run rm-cache")
    print("block-rm self-check: ok")


if __name__ == "__main__":
    test() if "--test" in sys.argv else main()
