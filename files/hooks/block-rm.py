#!/usr/bin/env python3
"""PreToolUse hook (Bash): block `rm`/`rmdir` unless every target is in a temp dir.

Enforces the CLAUDE.md rule "never permanently delete — move to _trash/".
Run `python3 block-rm.py --test` for the self-check.
Also caught: rm behind sudo, command, env, nohup, exec, time, nice, xargs and `bash -c "..."`, and paths
that only look temporary (/tmp/../etc/x is checked as /etc/x).
Not caught (a regex guard, not a shell parser): `find -delete`, `unlink`, `rsync --delete`, `git clean -f`
and deletes inside scripts; the CLAUDE.md rule and the deny rules cover some of those.
"""
import json
import os
import re
import shlex
import sys

TEMP_PREFIXES = ("/tmp/", "/private/tmp/", "/var/folders/", "/private/var/folders/")
RM = re.compile(r"(?:^|[;&|(\n\"'])\s*(?:(?:sudo|command|env|nohup|exec|time|nice(?:\s+-n\s*-?\d+|\s+-\d+)?)\s+|xargs\s+(?:-\S+\s+)*)*\\?(?:/usr)?(?:/bin/)?(rm|rmdir)\b")
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
        quote = command[m.start(1) - 1] if m.start(1) and command[m.start(1) - 1] in "\"'" else ""
        segment = re.split(r"[;&|)\n" + quote + "]", command[m.start(1):], maxsplit=1)[0]  # bash -c "rm x": stop at the quote
        paths = targets(segment)
        # normpath first: /tmp/../etc/x is /etc/x, not a temp path
        if not paths or not all(os.path.normpath(p).startswith(TEMP_PREFIXES) for p in paths):
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
    assert blocked("rm -rf /tmp/../etc/x/proj")     # only looks temporary
    assert blocked("time rm x") and blocked("nice rm x") and blocked("nice -n 5 rm x")
    assert blocked('bash -c "rm x"') and blocked("sh -c 'rm -rf build'")
    assert not blocked('bash -c "rm -rf /tmp/claude-501/x"')
    assert not blocked("rm -rf /tmp/foo/")
    assert blocked("rm -rf /tmp")                     # the temp folder itself
    print("block-rm self-check: ok")


if __name__ == "__main__":
    test() if "--test" in sys.argv else main()
