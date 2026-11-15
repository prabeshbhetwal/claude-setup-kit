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
fi
if has indexes; then
  [ -f "$CL/hooks/ensure-indexes.sh" ] && pass "ensure-indexes.sh" || fail "ensure-indexes.sh missing"
  selftest python3 "$CL/hooks/codegraph-gate.py" --test
  hook_on SessionStart "ensure-indexes.sh" "index build/refresh"
  hook_on Stop "ensure-indexes.sh" "index refresh after each turn"
  hook_on UserPromptSubmit "codegraph-gate.py" "CodeGraph context"
fi
if has measure; then
  selftest python3 "$CL/hooks/token-compare.py" selftest
  selftest python3 "$CL/hooks/token-daily.py" selftest
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
  grep -q '^LLM_API_KEY=.' "$HOME/.cognee/.env" 2>/dev/null && pass "Cognee LLM_API_KEY set" || warn "Cognee: no LLM_API_KEY in ~/.cognee/.env yet"
  code=$(curl -s -m 10 -o /dev/null -w '%{http_code}' http://127.0.0.1:8011/health)
  [ "$code" = 200 ] && pass "Cognee server answers on :8011 (any Cognee server on this Mac counts)" || warn "Cognee server not answering on :8011 (starts with the first Claude session after the key is set)"
fi
if has agentmemory; then
  plugin_on agentmemory@agentmemory
  code=$(curl -s -m 5 -o /dev/null -w '%{http_code}' http://localhost:3111/agentmemory/livez)
  [ "$code" = 200 ] && pass "agentmemory server answers" || warn "agentmemory server not running (npx -y @agentmemory/agentmemory@latest)"
fi
has remember && plugin_on remember@claude-plugins-official

# routing
if has routing; then
  sh "$CL/hooks/routing-card.sh" | grep -q 'MODEL ROUTING ACTIVE' && pass "routing card prints" || fail "routing-card.sh does not print the card"
  hook_on SessionStart "routing-card.sh" "routing card"
  for a in haiku-lean sonnet-lean; do [ -f "$CL/agents/$a.md" ] && pass "agent $a" || fail "agent $a missing"; done
fi

if has model-selector; then
  for p in model-selector model-router handoff cache-clock; do plugin_on "$p@claude-model-selector"; done
fi

# judge
if has jev; then
  exe "$BIN/jev" "jev"; exe "$BIN/jev-gate" "jev-gate"
  hook_on PostToolUse "jev-hooks.py" "Jev tool-output triage (shadow)"
  key=$(python3 -c "import sys;sys.path.insert(0,'$CL/hooks');from typesafe_key import get_key;print('y' if get_key() else '')" 2>/dev/null)
  [ "$key" = y ] && pass "TypeSafe key found" || warn "no TypeSafe key yet (Keychain item typesafe-api-key or TYPESAFE_API_KEY); jev exits 2 until then"
fi
if has mjudge; then
  exe "$BIN/mjudge" "mjudge"
  { [ -n "${GEMINI_API_KEY:-}" ] || grep -q '^GEMINI_API_KEY=.' "$HOME/.config/watch/.env" 2>/dev/null; } && pass "GEMINI_API_KEY found" || warn "no GEMINI_API_KEY yet"
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
[ $nfail = 0 ]
