#!/usr/bin/env python3
"""Audit of claude-setup-kit: checks that what the README promises is what the scripts do. Run it after any change.

  python3 lib/audit.py            exit 1 if any check fails (see docs/checking-changes.md)

Static: catalog <-> README <-> hooks.json <-> install.sh <-> doctor.sh agree. Dynamic: each tool without prerequisites is
installed into a throwaway HOME, doctor must pass, a second run must change nothing, flags must be rejected or accepted.
Never touches the real home: every run sets HOME to a folder under $TMPDIR and a PATH without claude, node or brew.
"""
import json, os, re, shutil, subprocess, sys, tempfile

KIT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
bad = []


def fail(msg):
    bad.append(msg)
    print("FAIL", msg)


def read(p):
    return open(os.path.join(KIT, p)).read()


def sh(cmd, home, stdin="", **env):
    e = {"HOME": home, "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "TMPDIR": os.environ.get("TMPDIR", "/tmp"), **env}
    r = subprocess.run(cmd, cwd=KIT, env=e, input=stdin, capture_output=True, text=True, timeout=300)
    return r.returncode, r.stdout + r.stderr


# ---------------------------------------------------------------- static
cat = [l.rstrip("\n").split("|") for l in read("lib/catalog.txt").splitlines() if l and not l.startswith("#")]
ids = {c[0]: c for c in cat}
install, doctor, readme = read("install.sh"), read("doctor.sh"), read("README.md")
tiers = re.search(r'TIERS_ALL="([^"]+)"', install).group(1).split()
hooks = json.load(open(os.path.join(KIT, "lib/hooks.json")))

for c in cat:
    if len(c) < 8:
        fail(f"catalog {c[0]}: {len(c)} fields, need 8")
    if c[1] not in tiers:
        fail(f"catalog {c[0]}: tier {c[1]} is not in TIERS_ALL {tiers}")
    if re.split(r"[ (+]", c[2])[0].lower() not in readme.lower():
        fail(f"catalog {c[0]}: '{c[2]}' is not mentioned in the README")
for t in tiers:
    if not any(c[1] == t for c in cat):
        fail(f"tier {t} has no tools")
m = re.search(r"`core guard memory[^`]*`", readme)
if m and m.group(0).strip("`").split() != tiers:
    fail(f"README tier list {m.group(0)} differs from install.sh {tiers}")
for h in hooks:
    if h not in ids:
        fail(f"hooks.json fragment '{h}' is not a catalog id")
    for e in hooks[h].get("hooks", []):
        cmd, match = e["command"], e.get("match", "")
        if match and match not in cmd.replace("__RTK__", "rtk"):
            fail(f"hooks.json {h}: match '{match}' not in command {cmd}")
        s = re.search(r'\.claude/hooks/([\w.-]+)', cmd)
        if s and not os.path.exists(os.path.join(KIT, "files/hooks", s.group(1))):
            fail(f"hooks.json {h}: script {s.group(1)} not in files/hooks")
for src in re.findall(r'"\$KIT/(files/[^"]+)"', install):
    if "$" not in src.replace("$KIT", "") and not os.path.exists(os.path.join(KIT, src)):
        fail(f"install.sh copies missing file {src}")
copied = set(re.findall(r"files/hooks/([\w.-]+)", install))
for f in os.listdir(os.path.join(KIT, "files/hooks")):
    if f not in copied and f != "__pycache__" and f"files/hooks/{f}" not in install and f not in install:
        fail(f"files/hooks/{f} is never copied or named by install.sh")
for link in re.findall(r"\]\(((?!http|#)[^)]+)\)", readme):
    if not os.path.exists(os.path.join(KIT, link.split("#")[0])):
        fail(f"README links to missing {link}")
parsed = set(re.findall(r"^\s+(--[a-z-]+)[)|]", install, re.M)) | set(re.findall(r"\|(--[a-z-]+)\)", install))
for flag in set(re.findall(r"`(--[a-z-]+)[ `]", readme)):
    if flag not in parsed:
        fail(f"README documents {flag}, install.sh does not parse it")
for flag in parsed - {"--help", "--list", "--yes"}:
    if flag not in readme:
        fail(f"install.sh parses {flag}, the README never mentions it")
for i in ids:
    if i in re.findall(r"^if has (\S+); then", doctor, re.M) or i in ("rules", "safety", "routing"):
        continue
    if not re.search(rf"has {re.escape(i)}\b", doctor) and i not in ("remember", "grill-me", "adhd", "ponytail", "caveman"):
        print(f"note  doctor.sh has no 'has {i}' check")
# order: the macOS check must come before the first question; python3 must not run before the prerequisite check
first_q = install.find("# ---------------------------------------------------------------- selection")
if install.find("uname -s") > first_q:
    fail("macOS check comes after the first question")
pre = install[: install.find("check_prereqs()")]
for ln, line in enumerate(pre.splitlines(), 1):
    if re.search(r"\bpython3 -c|\bpython3 -$|\bpython3 \"", line) and "xcode-select" not in line and not line.lstrip().startswith("#"):
        print(f"note  install.sh:{ln} runs python3 before the prerequisite check: {line.strip()[:90]}")

# ---------------------------------------------------------------- dynamic
for cmd in (["bash", "-n", "install.sh"], ["bash", "-n", "doctor.sh"], ["bash", "-n", "scan.sh"], ["bash", "-n", "pack-private.sh"]):
    rc, out = sh(cmd, "/nonexistent")
    if rc:
        fail(" ".join(cmd) + ": " + out[:200])
PY39 = "/usr/bin/python3" if os.path.exists("/usr/bin/python3") else sys.executable  # Apple's 3.9: what users have
for root, _, files in os.walk(KIT):
    if {".git", "graphify-out", ".codegraph", "worktrees", "node_modules"} & set(os.path.relpath(root, KIT).split(os.sep)):
        continue  # parts below the kit only: a kit inside .claude/worktrees/ must still be compiled
    for f in files:
        if f.endswith(".py"):
            rc, out = sh([PY39, "-c", "import sys; compile(open(sys.argv[1]).read(), sys.argv[1], 'exec')", os.path.join(root, f)], "/nonexistent")
            if rc:
                fail(f"py_compile {f}: {out[:200]}")
rc, out = sh([sys.executable, "lib/merge_settings.py", "selftest"], "/nonexistent")
if "selftest ok" not in out:
    fail("merge_settings selftest: " + out[-200:])
rc, out = sh(["bash", "scan.sh"], "/nonexistent")
if rc:
    fail("scan.sh: " + out[-300:])

T = tempfile.mkdtemp(prefix="kit-audit-", dir=os.environ.get("TMPDIR"))
H = lambda n: os.path.join(T, n)
for args, want in ((["--tiers", "bogus"], 2), (["--only", "bogus"], 2), (["--skip", "bogus", "--only", "safety"], 2), (["--nope"], 2),
                   (["--tiers"], 2), (["--list"], 0), (["--help"], 0)):
    rc, out = sh(["bash", "install.sh", *args], H("h-flags"), "")
    if rc != want:
        fail(f"install.sh {' '.join(args)}: exit {rc}, want {want}")
shim = os.path.join(T, "shim"); os.makedirs(shim)
open(os.path.join(shim, "uname"), "w").write("#!/bin/sh\necho Linux\n"); os.chmod(os.path.join(shim, "uname"), 0o755)
rc, out = subprocess.run(["bash", "install.sh", "--tiers", "core"], cwd=KIT, input="", capture_output=True, text=True,
                         env={"HOME": H("h-linux"), "PATH": f"{shim}:/usr/bin:/bin"}).returncode, ""
if rc != 1:
    fail(f"non-macOS run exited {rc}, want 1 before any question")

FREE = [i for i in ids if i in ("safety", "measure", "routing", "guard", "sandbox", "verify", "session-title")]  # remember needs the claude CLI, so it stops at the prerequisite check
for i in FREE:
    home = H(f"h-{i}")
    os.makedirs(os.path.join(home, ".claude"), exist_ok=True)
    rc, out1 = sh(["bash", "install.sh", "--only", i, "--yes"], home)
    if rc != 0 or "FAIL" in out1:
        fail(f"install --only {i}: exit {rc}: {out1[-300:]}")
        continue
    rc, d = sh(["bash", "doctor.sh"], home)
    if not re.search(r"^doctor: 0 fail", d, re.M):  # not "10 fail"
        fail(f"doctor after --only {i}: {[l for l in d.splitlines() if 'FAIL' in l][:3]}")
    rc, out2 = sh(["bash", "install.sh", "--only", i, "--yes"], home)
    changed = [l for l in out2.splitlines() if l.startswith("  + ") or "replaced" in l or "backup of" in l]
    if changed:
        fail(f"second run of {i} changed things: {changed[:3]}")
    s = os.path.join(home, ".claude/settings.json")
    if os.path.exists(s):
        try:
            json.load(open(s))
        except ValueError:
            fail(f"{i}: settings.json is not valid JSON")
    print("ok   ", i)

home = H("h-reportoff"); os.makedirs(home, exist_ok=True)
rc, out = sh(["bash", "install.sh", "--only", "measure", "--report", "off"], home)
la = os.path.join(home, "Library/LaunchAgents")
have = sorted(os.listdir(la)) if os.path.isdir(la) else []
want_jobs = ["com.claude-setup-kit.setup-monitor.plist", "com.claude-setup-kit.token-report.plist"]
period = open(os.path.join(home, ".claude/kit/report-period")).read().strip() if os.path.exists(os.path.join(home, ".claude/kit/report-period")) else ""
if have != want_jobs or period != "off":  # off: both jobs exist, the report job does nothing, so --set turns it back on
    fail(f"--report off: want both jobs and period 'off', found {have}, period '{period}'")

# ---------------------------------------------------------------- regressions: each replays a problem an outside review found
def hook(script, event, *args):
    r = subprocess.run([sys.executable, os.path.join(KIT, "files/hooks", script), *args], input=json.dumps(event),
                       capture_output=True, text=True, env={**{k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}, "KIT_VERIFY_ALLOW": os.path.join(T, "none")})
    return r.returncode, r.stdout + r.stderr


for cmd in ("rm -rf /tmp/../etc/x", "time rm x", "nice -n 5 rm x", 'bash -c "rm x"', "sh -c 'rm -rf build'", "ls | xargs -n 1 rm",
            "find . -exec rm {} +", "RM -rf src", "timeout 5 rm x", "rm /tmp/x; r''m -rf src"):
    if "deny" not in hook("block-rm.py", {"tool_name": "Bash", "tool_input": {"command": cmd}})[1]:
        fail(f"regression: rm blocker lets through: {cmd}")
if "deny" not in subprocess.run([PY39, os.path.join(KIT, "files/hooks/block-rm.py")], input="not json", capture_output=True, text=True).stdout:
    fail("regression: the rm blocker must deny when it cannot read its input")
if "deny" in hook("block-rm.py", {"tool_name": "Bash", "tool_input": {"command": "rm -rf /tmp/claude-x/probe"}})[1]:
    fail("regression: rm blocker blocks a temp folder")
proj = os.path.join(T, "proj"); os.makedirs(os.path.join(proj, ".claude"))
open(os.path.join(proj, ".claude/verify"), "w").write("#!/bin/sh\nexit 1\n"); os.chmod(os.path.join(proj, ".claude/verify"), 0o755)
hook("verify-done.py", {"session_id": "r", "cwd": proj, "tool_input": {"file_path": "a"}}, "edit")
if hook("verify-done.py", {"session_id": "r", "cwd": proj}, "stop")[0] != 0:
    fail("regression: done checks ran in a project nobody allowed")
rc, out = sh(["bash", "install.sh"], H("h-nokb"), "")
if rc != 2:
    fail(f"regression: no terminal and no options must stop (exit 2), got {rc}")
rc, out = sh(["bash", "install.sh", "--skip", "typo", "--tiers", "core"], H("h-skip"), "")
if rc != 2 or "Ready to install" in out:
    fail("regression: a bad --skip must stop before anything is shown")
hk = json.load(open(os.path.join(KIT, "lib/hooks.json")))
deny = " ".join(hk["guard"]["deny"])
if "Read(.env.*)" in hk["guard"]["deny"]:
    fail("regression: a .env.* deny rule also blocks .env.example (deny wins over allow)")
for pat in ("Read(**/.env)", "Read(.env.local)", "Read(**/.env.production)", "*.pem", "git push * +*", "git -C * reset --hard", "git checkout -- .", "git restore .", "git stash clear", "find-generic-password"):
    if pat not in deny:
        fail(f"regression: deny list lacks {pat}")
for txt, label in ((readme, "README"), (open(os.path.join(KIT, "lib/catalog.txt")).read(), "catalog")):
    for phrase in ("Claude can never read", "runs by itself on the 1st", "five short guides", "Five short guides"):
        if phrase in txt:
            fail(f"regression: {label} again says {phrase}.")
rc, out = sh(["bash", "install.sh", "--only", "mjudge", "--yes"], H("h-mj"), "")
if os.path.exists(H("h-mj/.claude/hooks/jev-hooks.py")):
    fail("regression: --only mjudge with nobody to ask pulled in paid Jev")
home = H("h-jev"); os.makedirs(home)
rc, out = sh(["bash", "install.sh", "--only", "jev", "--yes"], home, "")
pol = os.path.join(home, ".claude/jev/policy.json")
if not os.path.exists(pol) or not {"house-rules-recall", "house-rules-mine"} <= set(json.load(open(pol)).get("sites_off", [])):
    fail("regression: Jev installs with its data flows on instead of off")
if os.path.exists(os.path.join(home, ".claude/settings.json")) and "jev-hooks.py" in open(os.path.join(home, ".claude/settings.json")).read():
    fail("regression: Jev background hooks added without a yes")
home = H("h-claudemd"); os.makedirs(home)
sh(["bash", "install.sh", "--only", "rules", "--yes"], home, "")
cm = os.path.join(home, ".claude/CLAUDE.md")
if not os.path.exists(cm):
    fail("regression: rules install wrote no CLAUDE.md")
else:
    open(cm, "w").write("my own edit\n" + open(cm).read())  # an edit inside the kit-written part (text added after it is treated as a tool's)
    tpl = os.path.join(KIT, "files/CLAUDE.template.md"); orig = open(tpl).read()
    try:
        open(tpl, "w").write(orig + "\nnew kit line\n")
        sh(["bash", "install.sh", "--only", "rules", "--yes"], home, "")
    finally:
        open(tpl, "w").write(orig)
    if "my own edit" not in open(cm).read() or not os.path.exists(cm + ".kit-new"):
        fail("regression: an edited CLAUDE.md must be kept and the kit's version offered as .kit-new")
home = H("h-setmonth"); os.makedirs(home)
sh(["bash", "install.sh", "--only", "measure", "--report", "off"], home, "")
if not os.path.exists(os.path.join(home, "Library/LaunchAgents/com.claude-setup-kit.token-report.plist")):
    fail("regression: --set month after off needs the report job to exist")
rc, out = sh([sys.executable, os.path.join(home, ".claude/hooks/token-report.py"), "--set", "month"], home)
if "month" not in open(os.path.join(home, ".claude/kit/report-period")).read():
    fail("regression: token-report.py --set month did not record the period")
tipsrc = open(os.path.join(KIT, "mods/model-pilot/hooks/policy.ts")).read()
if "start-up is small next to re-reading" in tipsrc:
    fail("regression: the long Model pilot tip text is back (the app clips it)")

home = H("h-uninstall"); os.makedirs(os.path.join(home, ".claude"))
open(os.path.join(home, ".claude/settings.json"), "w").write('{"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}}')
rc, out = sh(["bash", "install.sh", "--only", "session-title", "--yes"], home)
if "This is what would change in settings.json" not in out:
    fail("regression: install must show the settings.json diff before writing")
rc, out = sh(["bash", "install.sh", "--uninstall", "session-title"], home)
cfg = json.load(open(os.path.join(home, ".claude/settings.json")))
if cfg != {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}} or os.path.exists(os.path.join(home, ".claude/hooks/session-title.py")):
    fail("regression: uninstall must remove only the kit's entries and the script, and keep the user's hooks")
if sh(["bash", "install.sh", "--uninstall", "session-title"], home)[1].count("removed hook"):
    fail("regression: a second uninstall must change nothing")
home = H("h-secret"); os.makedirs(os.path.join(home, ".claude"))
json.dump({"env": {"ANTHROPIC_API_" + "KEY": "fake-value-redact-me-000"}}, open(os.path.join(home, ".claude/settings.json"), "w"))
rc, out = sh(["bash", "install.sh", "--only", "session-title", "--yes"], home)
if "fake-value-redact-me" in out:
    fail("regression: the settings.json preview printed a secret")
home = H("h-jevrevoke"); os.makedirs(home)
sh(["bash", "install.sh", "--only", "jev", "--yes", "--jev-hooks", "yes"], home)
sh(["bash", "install.sh", "--only", "jev", "--yes", "--jev-hooks", "no"], home)
st = os.path.join(home, ".claude/settings.json")
if os.path.exists(st) and "jev-hooks.py" in open(st).read():
    fail("regression: saying no to Jev's background hooks left the earlier ones in settings.json")
pol = json.load(open(os.path.join(home, ".claude/jev/policy.json")))
if not {"codegraph-gate", "jev-gate", "model-pilot", "house-rules-recall", "house-rules-mine"} <= set(pol.get("sites_off", [])):
    fail(f"regression: with no consent every Jev site must be off, got {pol.get('sites_off')}")
home = H("h-period"); os.makedirs(home)
sh(["bash", "install.sh", "--only", "measure", "--report", "week"], home)
sh(["bash", "install.sh", "--only", "measure", "--yes"], home)
if open(os.path.join(home, ".claude/kit/report-period")).read().strip() != "week":
    fail("regression: an unattended re-run reset the report period")
rc, out = sh(["bash", "install.sh", "--jev-share", "typo", "--tiers", "core"], H("h-badshare"))
if rc != 2 or "Ready to install" in out:
    fail("regression: a bad --jev-share must stop before anything is shown")
home = os.path.join(T, "it's & <odd> home"); os.makedirs(home)
sh(["bash", "install.sh", "--only", "safety,measure", "--yes"], home)
rc, out = sh(["bash", "doctor.sh"], home)
if not re.search(r"^doctor: 0 fail", out, re.M):
    fail("regression: doctor fails for a HOME with a quote: " + " | ".join(l for l in out.splitlines() if "FAIL" in l)[:300])
for plist in ("com.claude-setup-kit.token-report.plist", "com.claude-setup-kit.setup-monitor.plist"):
    pth = os.path.join(home, "Library/LaunchAgents", plist)
    if not os.path.exists(pth) or subprocess.run(["plutil", "-lint", pth], capture_output=True).returncode:
        fail(f"regression: {plist} is not a valid plist when HOME has & or <")
home = H("h-title05"); os.makedirs(os.path.join(home, ".claude"))
open(os.path.join(home, ".claude/settings.json"), "w").write("{not json")
rc, out = sh(["bash", "install.sh", "--only", "session-title", "--yes", "--title-recheck", "05"], home)
if "Could not read ~/.claude/settings.json" not in out or "nothing would change" in out:
    fail("regression: an unreadable settings.json must not be previewed as 'nothing would change'")
try:
    json.load(open(os.path.join(home, ".claude/kit/session-title.json")))
except (OSError, ValueError) as e:
    fail(f"regression: --title-recheck 05 wrote an unreadable session-title.json: {e}")
pr = subprocess.run([sys.executable, os.path.join(KIT, "lib/audit_proofs.py"), KIT], capture_output=True, text=True, timeout=900)
print(pr.stdout.strip())
if pr.returncode:
    fail("proofs (fake claude, keyboard, timing): " + " | ".join(l for l in pr.stdout.splitlines() if l.startswith("FAIL")))
shutil.rmtree(T, ignore_errors=True)  # only the throwaway folder this run made
print(f"\n{len(bad)} failing check(s)")
sys.exit(1 if bad else 0)
