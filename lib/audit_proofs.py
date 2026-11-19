#!/usr/bin/env python3
"""Proofs lib/audit.py cannot get from a plain install: they stand in a fake `claude` command, a keyboard and a clock.

  python3 lib/audit_proofs.py        exit 1 if any proof fails (lib/audit.py runs it too)

1. Another model selector is switched off only AFTER Model pilot installed; a failed install leaves it on.
2. Re-running the installer refreshes the kit's own plugins (marketplace update, then plugin update).
3. Each per-prompt and per-command hook finishes quickly (timed; slow ones fail).
Everything runs in a throwaway HOME under $TMPDIR; the real `claude`, settings and launchd are never touched.
"""
import json, os, shutil, subprocess, sys, tempfile, time

KIT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
bad = []
T = tempfile.mkdtemp(prefix="kit-proofs-", dir=os.environ.get("TMPDIR"))

FAKE = r'''#!/bin/sh
# Fake claude CLI: logs every call; behaviour comes from env FAKE_INSTALL (ok|fail) and FAKE_PILOT (absent|enabled).
echo "$*" >> "$FAKE_LOG"
case "$*" in
  "--version") echo "2.1.400 (Claude Code)" ;;
  "plugin marketplace list --json") echo '[{"name": "claude-setup-kit"}]' ;;
  "plugin list --json") case "$FAKE_PILOT" in
      enabled) echo '[{"id": "model-pilot@claude-setup-kit", "enabled": true}]' ;;
      absent) if [ -f "$FAKE_LOG.installed" ]; then echo '[{"id": "model-pilot@claude-setup-kit", "enabled": true}]'; else echo '[]'; fi ;;
      disabled) echo '[{"id": "model-pilot@claude-setup-kit", "enabled": false}]' ;;
      *) echo '[]' ;; esac ;;
  "plugin install"*) [ "$FAKE_INSTALL" = ok ] && : > "$FAKE_LOG.installed" ;;
  *) exit 0 ;;
esac
'''


def run(home, args, env, answers=None):
    """install.sh with the fake claude first on PATH; `answers` feeds a pty (script) so questions get a keyboard."""
    e = {"HOME": home, "PATH": f"{T}/bin:/usr/bin:/bin:/usr/sbin:/sbin", "TMPDIR": os.environ.get("TMPDIR", "/tmp"), **env}
    cmd = ["bash", os.path.join(KIT, "install.sh"), *args]
    if answers is not None:
        cmd = ["script", "-q", "/dev/null", *cmd]
    r = subprocess.run(cmd, cwd=KIT, env=e, input=answers or "", capture_output=True, text=True, timeout=300)
    return r.stdout + r.stderr


def fresh(name, other_selector):
    home = os.path.join(T, name)
    os.makedirs(os.path.join(home, ".claude"))
    s = {"enabledPlugins": {"other@claude-model-selector": True}} if other_selector else {}
    json.dump(s, open(os.path.join(home, ".claude/settings.json"), "w"))
    log = os.path.join(home, "claude.log")
    open(log, "w").close()
    return home, log


os.makedirs(os.path.join(T, "bin"))
open(os.path.join(T, "bin/claude"), "w").write(FAKE)
os.chmod(os.path.join(T, "bin/claude"), 0o755)

# 1. order of install and switch-off, through a real keyboard (pty): "y" to every question
for outcome in ("fail", "ok"):
    home, log = fresh(f"sel-{outcome}", True)
    out = run(home, ["--only", "model-pilot"], {"FAKE_LOG": log, "FAKE_INSTALL": outcome, "FAKE_PILOT": "absent"}, "y\n" * 40)
    calls = open(log).read().splitlines()
    inst = next((i for i, c in enumerate(calls) if c.startswith("plugin install model-pilot")), None)
    off = next((i for i, c in enumerate(calls) if c.startswith("plugin disable other@claude-model-selector")), None)
    if inst is None:
        bad.append(f"selector ({outcome}): Model pilot install was never attempted; installer said: {out[-300:]}")
    elif outcome == "fail" and off is not None:
        bad.append("selector: the other selector was switched off although Model pilot failed to install")
    elif outcome == "ok" and (off is None or off < inst):
        bad.append(f"selector: after a good install the other selector must be switched off, after the install (calls: {calls})")

# 2. re-run refreshes an installed kit plugin
home, log = fresh("refresh", False)
run(home, ["--only", "model-pilot"], {"FAKE_LOG": log, "FAKE_INSTALL": "ok", "FAKE_PILOT": "enabled"})
calls = open(log).read().splitlines()
mu = next((i for i, c in enumerate(calls) if c == "plugin marketplace update claude-setup-kit"), None)
pu = next((i for i, c in enumerate(calls) if c == "plugin update model-pilot@claude-setup-kit"), None)
if mu is None or pu is None or pu < mu:
    bad.append(f"refresh: a re-run must update the marketplace, then the plugin (calls: {calls})")

# 2b. Model pilot installed but switched off: the other selector must stay on
home, log = fresh("sel-disabled", True)
run(home, ["--only", "model-pilot"], {"FAKE_LOG": log, "FAKE_INSTALL": "ok", "FAKE_PILOT": "disabled"}, "y\n" * 40)
if any(c.startswith("plugin disable other@claude-model-selector") for c in open(log).read().splitlines()):
    bad.append("selector: Model pilot is switched off, yet the other selector was switched off too (none left on)")

# 2c. the Model pilot settings writer keeps a symlinked settings.json and its 0600 mode
home, log = fresh("symlink", False)
real = os.path.join(home, "dotfiles-settings.json")
os.replace(os.path.join(home, ".claude/settings.json"), real)
os.symlink(real, os.path.join(home, ".claude/settings.json"))
os.chmod(real, 0o600)
run(home, ["--only", "model-pilot", "--yes"], {"FAKE_LOG": log, "FAKE_INSTALL": "ok", "FAKE_PILOT": "absent"})
link = os.path.join(home, ".claude/settings.json")
if not os.path.islink(link) or (os.stat(real).st_mode & 0o777) != 0o600 or "pluginConfigs" not in open(real).read():
    bad.append("settings: Model pilot's writer replaced the symlink or widened the 0600 permissions")
elif '"jev": false' not in open(real).read():
    bad.append("consent: Model pilot must be written with jev off when nobody said yes")

# 3. hook timing: what runs on every prompt or shell command, from a kit install in a throwaway HOME
home, log = fresh("timing", False)
run(home, ["--only", "safety,verify,session-title,measure", "--yes"], {"FAKE_LOG": log, "FAKE_INSTALL": "ok"})
H = os.path.join(home, ".claude/hooks")
cases = [("block-rm.py", [], {"tool_name": "Bash", "tool_input": {"command": "ls -la"}}),
         ("verify-done.py", ["edit"], {"session_id": "t", "cwd": home, "tool_input": {"file_path": "a.py"}}),
         ("session-title.py", ["prompt"], {"session_id": "t", "transcript_path": os.path.join(home, "none.jsonl")}),
         ("house-rules-recall.py", [], {"prompt": "fix the login page layout", "cwd": home})]
for script, args, event in cases:
    path = os.path.join(H, script)
    if not os.path.exists(path):
        bad.append(f"timing: {script} was not installed")
        continue
    best = 9e9
    for _ in range(3):
        t0 = time.perf_counter()
        subprocess.run([sys.executable, path, *args], input=json.dumps(event), capture_output=True, text=True,
                       env={"HOME": home, "PATH": "/usr/bin:/bin", "CLAUDE_CODE_ENTRYPOINT": "claude-desktop"}, timeout=30)
        best = min(best, time.perf_counter() - t0)
    print(f"timing {script:24} {best * 1000:6.0f} ms")
    if best > 1.0:
        bad.append(f"timing: {script} took {best:.2f} s (limit 1 s)")

shutil.rmtree(T, ignore_errors=True)  # only the throwaway folder this run made
for b in bad:
    print("FAIL", b)
print(f"{len(bad)} failing proof(s)")
sys.exit(1 if bad else 0)
