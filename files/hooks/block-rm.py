#!/usr/bin/env python3
"""PreToolUse hook (Bash): block `rm`/`rmdir` unless every target is in a temp dir.

Enforces the CLAUDE.md rule "never permanently delete: move to _trash/".
Run `python3 block-rm.py --test` for the self-check.
Also caught: rm behind sudo, command, env, nohup, exec, time, nice, xargs (with their options and VAR=x
assignments), `bash -c "..."`, inside loops, conditionals, braces, backticks, $( ) and after `!`; paths
that only look temporary (/tmp/../etc/x is checked as /etc/x, a symlinked parent is resolved first) and
targets the hook cannot resolve ($VAR, globs, braces, backticks) count as non-temp.
Not caught (a regex guard, not a shell parser): `find -delete`, `unlink`, `rsync --delete`, `git clean -f`
and deletes inside scripts; the CLAUDE.md rule and the deny rules cover some of those.
"""
import json
import os
import re
import shlex
import sys

TEMP_PREFIXES = ("/tmp/", "/private/tmp/", "/var/folders/", "/private/var/folders/")
# command start: line start, an operator, a quote/backtick/brace/$(/!, or a shell keyword
START = r"(?:^|[;&|(\n\"'`{!]|\b(?:then|do|else|elif|if|while|until)\b)"
# wrappers with their options (a short option may take one argument) and VAR=value assignments
WRAP = (r"(?:(?:/usr)?(?:/bin/)?(?:sudo|doas|command|env|nohup|exec|time|nice)"
        r"(?:\s+(?:-[ugCDhprtTUaSPn]\s+[^-\s;&|]\S*|-\S*|\w+=\S*))*\s+|\w+=\S*\s+|xargs\s+(?:-\S+\s+)*)")
RM = re.compile(START + r"\s*" + WRAP + r"*\\?(?:/usr)?(?:/bin/)?(rm|rmdir)\b")
UNRESOLVED = re.compile(r"[$`*?{\[~]")
REASON = ("Blocked by your rule: never permanently delete. Move it instead: "
          "trashmv <path>... (files into ~/_trash/<project>/<date>/<original sub-folders>, outside iCloud, logged in moves.tsv). "
          "Temp folders (/tmp, /private/tmp, /var/folders) are exempt.")


def targets(segment):
    try:
        words = shlex.split(segment)
    except ValueError:
        return None  # unparseable quoting → treat as unsafe
    if any(w.startswith("-") and UNRESOLVED.search(w) for w in words[1:]):
        return None  # -f`printf ...`: the shell turns an "option" into more targets
    return [w for w in words[1:] if not w.startswith("-")]


def is_temp(path):
    if UNRESOLVED.search(path):
        return False  # $VAR, glob, brace or backtick: the shell decides, so the hook cannot vouch for it
    p = os.path.normpath(path)  # /tmp/../etc/x is /etc/x, not a temp path
    # Resolve the path as written: a symlink in the middle is followed BEFORE any `..` (/tmp/link/../x leaves /tmp when link does).
    base = os.path.basename(path.rstrip("/"))
    real = os.path.realpath(path) if base in ("", ".", "..") else os.path.join(os.path.realpath(os.path.dirname(path.rstrip("/")) or "."), base)
    return p.startswith(TEMP_PREFIXES) and real.startswith(TEMP_PREFIXES)


def blocked(command):
    plain = re.sub(r"[\"'\\]", "", command)  # r''m, "r"m and r\m are rm to the shell
    if plain != command and RM.search(plain) and not RM.search(command):
        return True  # an rm that only appears once quotes are removed: written to be missed
    for m in RM.finditer(command):
        quote = command[m.start(1) - 1] if m.start(1) and command[m.start(1) - 1] in "\"'" else ""
        segment = re.split(r"[;&|)\n" + quote + "]", command[m.start(1):], maxsplit=1)[0]  # not at ` or }: later targets must stay checked  # bash -c "rm x": stop at the quote
        paths = targets(segment)
        if not paths or not all(is_temp(p) for p in paths):
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
    # loops, conditionals, braces, backticks, $( ), negation
    for cmd in ("for f in a b; do rm $f; done", "for f in a; do rm x; done", "if true; then rm x; fi",
                "if x; then :; else rm x; fi", "while true; do rm x; done", "{ rm x; }", "echo `rm x`",
                "echo $(rm x)", "! rm x", "if rm x; then :; fi"):
        assert blocked(cmd), cmd
    # wrappers with options or assignments
    for cmd in ("sudo -u me rm x", "sudo -n rm x", "env FOO=1 rm x", "FOO=1 rm x", "A=1 B=2 rm x",
                "/usr/bin/env rm x", "exec -a x rm y", "command -p rm x", "time -p rm x", "nice -n 5 rm x",
                "sudo -u me env FOO=1 rm x"):
        assert blocked(cmd), cmd
    # unresolved targets count as non-temp, even under /tmp
    for cmd in ("rm -rf /tmp/$X", "rm -rf /tmp/*", "rm -rf /tmp/{a,../../etc}", "rm -rf /tmp/`whoami`"):
        assert blocked(cmd), cmd
    assert not blocked("for f in a; do echo $f; done") and not blocked("{ echo x; }")
    assert not blocked("sudo -u me ls && env FOO=1 git rm x")
    assert not blocked("if true; then rm -f /tmp/claude-501/x; fi")
    # a symlinked parent is resolved before the temp exemption
    import tempfile
    base = tempfile.mkdtemp()
    link = os.path.join(base, "link")
    os.symlink("/etc/block-rm-selftest-not-temp", link)  # fixed non-temp target: independent of HOME
    try:
        assert blocked(f"rm -rf {shlex.quote(link + '/proj')}"), "symlinked parent outside temp must block"
        if re.fullmatch(r"[\w./-]+", base):  # an odd TMPDIR (quotes, &) defeats this regex guard's quoting
            assert not blocked(f"rm -rf {base}/plain")
    finally:
        os.unlink(link)
        os.rmdir(base)
    import tempfile
    d = tempfile.mkdtemp(prefix="rm-link-")
    os.symlink("/etc", os.path.join(d, "link"))  # a link under /tmp that leads out of it
    assert blocked(f"rm {d}/link/hosts"), "a symlink out of /tmp"
    assert blocked(f"rm -rf {d}/link/../important"), "the link is followed before .., so this leaves /tmp"
    assert not blocked(f"rm {d}/plain.txt")
    assert blocked("rm -rf /tmp/build-`id -u` /etc/project"), "a backtick must not hide the targets after it"
    assert blocked("rm -rf /tmp/{a,b} /etc/x")
    assert blocked("rm -f`printf${IFS}'v /etc/project'` /tmp/x"), "an expansion inside an option can add targets"
    assert blocked("r''m important.txt") and blocked('"r"m x') and blocked("r\\m x") and blocked("'rm' x")
    assert not blocked("echo 'it''s fine'") and not blocked('git commit -m "tidy up"')
    print("block-rm self-check: ok")


if __name__ == "__main__":
    test() if "--test" in sys.argv else main()
