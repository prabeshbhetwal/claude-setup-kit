#!/bin/bash
# claude-setup-kit doctor: checks every tool install.sh recorded in ~/.claude/kit/installed.
# Uses no Claude tokens. Exit 0 = no FAIL (WARN lines are steps still waiting on you, e.g. a key).
#   ./doctor.sh           all checks, including `claude mcp list` (starts MCP servers, up to ~2 min)
#   ./doctor.sh --quick   skip the MCP connection check
set -u
CL="$HOME/.claude"; BIN="$HOME/.local/bin"
export PATH="$BIN:/opt/homebrew/bin:/usr/local/bin:$PATH"
QUICK=0; [ "${1:-}" = --quick ] && QUICK=1
nfail=0; nwarn=0
pass() { printf '  PASS  %s\n' "$*"; }
warn() { printf '  WARN  %s\n' "$*"; nwarn=$((nwarn+1)); }
fail() { printf '  FAIL  %s\n' "$*"; nfail=$((nfail+1)); }

[ -f "$CL/kit/installed" ] || { echo "No ~/.claude/kit/installed: run install.sh first."; exit 1; }
INSTALLED=" $(tr '\n' ' ' < "$CL/kit/installed")"
has() { case "$INSTALLED" in *" $1 "*) return 0 ;; esac; return 1; }
echo "Checking:$INSTALLED"

S="$CL/settings.json"
plugin_on() { # plugin_on id@marketplace
  python3 - "$S" "$1" <<'PY' && pass "plugin $1 enabled" || fail "plugin $1 not enabled (claude plugin enable $1)"
import json, sys
try:
    sys.exit(0 if json.load(open(sys.argv[1])).get("enabledPlugins", {}).get(sys.argv[2]) is True else 1)
except Exception:
    sys.exit(1)
PY
}
hook_on() { # hook_on EVENT NEEDLE WHAT
  python3 - "$S" "$1" "$2" <<'PY' && pass "hook $1: $3" || fail "hook $1 missing: $3 ($2) - re-run install.sh"
import json, sys
s = json.load(open(sys.argv[1]))
cmds = " ".join(h.get("command", "") for g in s.get("hooks", {}).get(sys.argv[2], []) for h in g.get("hooks", []))
sys.exit(0 if sys.argv[3] in cmds else 1)
PY
}
exe() { [ -x "$1" ] && pass "$2" || fail "$2 missing ($1)"; }
selftest() { out=$("$@" 2>&1) && pass "self-test: $*" || fail "self-test failed: $* -> $(printf '%s' "$out" | tail -1)"; }

python3 -c "import json;json.load(open('$S'))" 2>/dev/null && pass "settings.json is valid JSON" || fail "settings.json unreadable"

# core
if has caveman; then
  plugin_on caveman@caveman
  [ -f "$HOME/.config/caveman/config.json" ] && pass "Caveman mode: $(python3 -c "import json;print(json.load(open('$HOME/.config/caveman/config.json')).get('defaultMode'))")" || warn "no ~/.config/caveman/config.json (plugin default mode applies)"
fi
if has adhd; then
  plugin_on i-have-adhd@i-have-adhd
  [ -f "$CL/.i-have-adhd-always" ] && pass "i-have-adhd always on" || warn "i-have-adhd always-on flag missing (~/.claude/.i-have-adhd-always)"
fi
has ponytail && plugin_on ponytail@ponytail
has context-mode && plugin_on context-mode@context-mode
if has rtk; then
  if command -v rtk >/dev/null 2>&1; then
    pass "rtk $(rtk --version 2>/dev/null | awk '{print $2}')"
    # Run the hook command exactly as settings.json has it, with a bare PATH: Claude Code's hook PATH may lack
    # ~/.local/bin and Homebrew, so a hook that only works from this shell's PATH is a FAIL, not a PASS.
    hc=$(python3 -c "import json;print(next((h['command'] for g in json.load(open('$S')).get('hooks',{}).get('PreToolUse',[]) for h in g.get('hooks',[]) if 'hook claude' in h.get('command','')),''))")
    out=$(printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git status"}}' | env -i HOME="$HOME" PATH=/usr/bin:/bin sh -c "$hc" 2>/dev/null)
    if grep -q 'rtk git status' <<< "$out"; then pass "RTK hook rewrites commands with a bare PATH ($hc)"
    elif printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git status"}}' | sh -c "$hc" 2>/dev/null | grep -q 'rtk git status'; then
      warn "RTK hook works only if Claude Code's PATH finds rtk ($hc). Safer: set that hook's command to \"$(command -v rtk)\" hook claude"
    else fail "RTK hook is not rewriting commands ($hc)"; fi
  else fail "rtk not on PATH"; fi
  hook_on PreToolUse "hook claude" "RTK"
fi
if has codegraph; then
  exe "$BIN/codegraph" "codegraph $("$BIN/codegraph" --version 2>/dev/null)"
fi
if has graphify; then
  exe "$BIN/graphify" "graphify CLI"
  [ -f "$CL/skills/graphify/SKILL.md" ] && pass "graphify skill" || fail "graphify skill missing (graphify install --platform claude)"
fi
if has safety; then
  exe "$BIN/trashmv" "trashmv"; selftest python3 "$BIN/trashmv" --test
  selftest python3 "$CL/hooks/block-rm.py" --test
  hook_on PreToolUse "block-rm.py" "rm blocker"
  hook_on SessionStart "apply-hook-timeouts.py" "plugin hook time limits (15 s)"
  command -v trashmv >/dev/null 2>&1 && pass "trashmv on your PATH" || warn "trashmv is not on your PATH, so Claude cannot run it: add ~/.local/bin to PATH in your shell profile"
fi
if has guard; then
  n=$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(sum(r in d.get("permissions",{}).get("deny",[]) for r in ("Read(.env)","Bash(git reset --hard *)","Bash(git push --force *)")))' "$CL/settings.json" 2>/dev/null)
  [ "$n" = 3 ] && pass "deny rules (.env, git reset --hard, force push)" || fail "deny rules missing from settings.json (re-run the installer)"
fi
if has sandbox; then
  s=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("sandbox",{}).get("enabled"))' "$CL/settings.json" 2>/dev/null)
  [ "$s" = True ] && pass "Bash sandbox on" || warn "Bash sandbox is off in settings.json (you chose that earlier, or run /sandbox)"
fi
if has verify; then
  selftest python3 "$CL/hooks/verify-done.py" selftest
  hook_on PostToolUse "verify-done.py" "lint after each edit"
  hook_on Stop "verify-done.py" "done check before finishing"
fi
if has session-title; then
  selftest python3 "$CL/hooks/session-title.py" selftest
  hook_on UserPromptSubmit "session-title.py" "session title request"
  hook_on Stop "session-title.py" "session title check before finishing"
fi
if has indexes; then
  [ -f "$CL/hooks/ensure-indexes.sh" ] && pass "ensure-indexes.sh" || fail "ensure-indexes.sh missing"
  selftest python3 "$CL/hooks/codegraph-gate.py" --test
  hook_on SessionStart "ensure-indexes.sh" "index build/refresh"
  hook_on Stop "ensure-indexes.sh" "index refresh after each turn"
  hook_on UserPromptSubmit "codegraph-gate.py" "CodeGraph context"
  selftest python3 "$CL/hooks/index-first.py" selftest
  hook_on PreToolUse "index-first.py" "index first (CodeGraph before Grep)"
fi
if has measure; then
  selftest python3 "$CL/hooks/token-compare.py" selftest
  selftest python3 "$CL/hooks/token-daily.py" selftest
  selftest python3 "$CL/hooks/token-report.py" selftest
  selftest python3 "$CL/hooks/token-ledger.py" selftest
  hook_on Stop "token-ledger.py" "per-turn token ledger"
  [ -f "$CL/cache/token-compare/ledger.jsonl" ] && pass "ledger has $(wc -l < "$CL/cache/token-compare/ledger.jsonl" | tr -d ' ') turns" || warn "ledger empty so far (it fills after your next Claude turn)"
  per=$(cat "$CL/kit/report-period" 2>/dev/null || echo month)
  PL="$HOME/Library/LaunchAgents/com.claude-setup-kit.token-report.plist"
  if [ "$per" = off ]; then pass "token report off (your choice; python3 ~/.claude/hooks/token-report.py --set month to turn on)"
  elif [ ! -f "$PL" ]; then fail "token report not scheduled ($PL missing): re-run install.sh"
  elif launchctl print "gui/$(id -u)/com.claude-setup-kit.token-report" >/dev/null 2>&1; then pass "token report: $per (daily check, 09:00)"
  else warn "token report job exists but is not loaded: launchctl bootstrap gui/$(id -u) $PL"; fi
  PM="$HOME/Library/LaunchAgents/com.claude-setup-kit.setup-monitor.plist"
  [ -f "$PM" ] && pass "weekly scorecard job (Mondays 08:15)" || fail "weekly scorecard not scheduled ($PM missing): re-run install.sh"
  hook_on UserPromptSubmit "house-rules-recall.py" "house rules recall"
fi
if has rules; then
  [ -f "$CL/CLAUDE.md" ] && pass "~/.claude/CLAUDE.md present" || fail "~/.claude/CLAUDE.md missing"
  grep -q '{{' "$CL/CLAUDE.md" 2>/dev/null && warn "~/.claude/CLAUDE.md still has {{...}} placeholders"
  for g in coding token-tools; do [ -f "$CL/guides/$g.md" ] && pass "guide $g.md" || fail "guide $g.md missing"; done
fi

# memory
has supermemory && plugin_on supermemory@supermemory-plugins
if has cognee; then
  plugin_on cognee-memory@cognee
  hook_env=$(python3 -c "import json;print(json.load(open('$S')).get('env',{}).get('COGNEE_BACKEND',''))")
  [ "$hook_env" = local ] && pass "COGNEE_BACKEND=local" || fail "COGNEE_BACKEND is not local in settings.json env"
  grep -q '^LLM_API_KEY=.' "$HOME/.cognee/.env" 2>/dev/null && pass "Cognee LLM_API_KEY set" || pass "Cognee: no LLM_API_KEY, so it runs on your Claude plan (counts towards its usage limits)"
  code=$(curl -s -m 10 -o /dev/null -w '%{http_code}' http://127.0.0.1:8011/health)
  [ "$code" = 200 ] && pass "Cognee server answers on :8011 (any Cognee server on this Mac counts)" || warn "Cognee server not answering on :8011 (starts with the first Claude session after the key is set)"
fi
has remember && plugin_on remember@claude-plugins-official

# routing
if has routing; then
  sh "$CL/hooks/routing-card.sh" | grep -q 'MODEL ROUTING ACTIVE' && pass "routing card prints" || fail "routing-card.sh does not print the card"
  hook_on SessionStart "routing-card.sh" "routing card"
  for a in haiku-lean sonnet-lean; do [ -f "$CL/agents/$a.md" ] && pass "agent $a" || fail "agent $a missing"; done
fi

if has model-pilot; then
  plugin_on "model-pilot@claude-setup-kit"
  v=$(claude --version 2>/dev/null | awk '{print $1}')
  if [ -n "$v" ] && [ "$(printf '%s\n' 2.1.325 "$v" | sort -V | head -1)" != 2.1.325 ]; then fail "Model pilot needs Claude Code 2.1.325 or newer; you have $v (claude update)"; fi
  [ -f "$CL/local-marketplaces/claude-setup-kit/model-pilot/hooks/register.tsx" ] && pass "model pilot files" || fail "model pilot files missing (re-run ./install.sh)"
  other=$(python3 -c 'import json,sys
try: print(" ".join(k for k, v in json.load(open(sys.argv[1])).get("enabledPlugins", {}).items() if v is True and k.endswith("@claude-model-selector")))
except Exception: pass' "$S" 2>/dev/null)
  [ -z "$other" ] && pass "model pilot is the only model selector switched on" || fail "another model selector is also on ($other): two would each pick a model (claude plugin disable <name>)"
fi

# judge
if has jev; then
  exe "$BIN/jev" "jev"; exe "$BIN/jev-gate" "jev-gate"
  if [ "$(cat "$CL/kit/jev-hooks" 2>/dev/null)" = yes ]; then hook_on PostToolUse "jev-hooks.py" "Jev background hooks (you said yes)"
  else pass "Jev background hooks off (your choice; ./install.sh --only jev --jev-hooks yes adds them)"; fi
  key=$(python3 -c "import sys;sys.path.insert(0,'$CL/hooks');from typesafe_key import get_key;print('y' if get_key() else '')" 2>/dev/null)
  [ "$key" = y ] && pass "TypeSafe key found" || warn "no TypeSafe key yet (Keychain item typesafe-api-key or TYPESAFE_API_KEY); jev exits 2 until then"
fi
if has mjudge; then
  exe "$BIN/mjudge" "mjudge"
  { [ -n "${GEMINI_API_KEY:-}" ] || grep -q '^GEMINI_API_KEY=.' "$HOME/.config/watch/.env" 2>/dev/null; } && pass "GEMINI_API_KEY found" || warn "no GEMINI_API_KEY yet"
fi

if has model-badge; then
  plugin_on "model-badge@claude-setup-kit"
fi
if has grill-me; then
  for s in grill-me grilling grill-with-docs; do [ -f "$CL/skills/$s/SKILL.md" ] && pass "skill $s" || fail "skill $s missing (re-run ./install.sh)"; done
fi
# deliberation
if has deliberation; then
  plugin_on deliberation@antonbabenko
  [ -f "$HOME/.config/deliberation/config.json" ] && pass "deliberation configured" || warn "deliberation not configured yet (run /deliberation:setup in Claude Code)"
fi

# MCP servers actually connect (slow: starts each server).
if [ $QUICK = 0 ] && { has codegraph || has context-mode; }; then
  TO=$(command -v timeout 2>/dev/null || echo "$(cd "$(dirname "$0")" && pwd)/files/hooks/kit-timeout")
  out=$(cd /tmp && "$TO" 150 claude mcp list </dev/null 2>/dev/null)
  for s in codegraph plugin:context-mode:context-mode; do
    case $s in codegraph) has codegraph || continue ;; *) has context-mode || continue ;; esac
    grep -E "^$s: " <<< "$out" | grep -q Connected && pass "MCP $s connected" || fail "MCP $s not connected (claude mcp list)"
  done
fi

# A kit file you kept your own version of is not the kit's version: say so instead of passing silently.
while IFS= read -r f; do
  warn "kit version not applied: ${f%.kit-new} (yours kept; compare with ${f/#$HOME/~})"
done < <(find "$CL" -maxdepth 2 -name '*.kit-new' 2>/dev/null)

echo ""
echo "doctor: $nfail fail, $nwarn warn"
[ $nfail = 0 ] || echo "Removed a tool by hand? Delete its line from ~/.claude/kit/installed so the doctor stops checking it."
[ $nfail = 0 ]
