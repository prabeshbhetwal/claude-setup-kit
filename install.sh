#!/bin/bash
# claude-setup-kit installer. macOS. Idempotent: a second run changes nothing that is already in place.
#
#   ./install.sh                      explain every tool, then ask which to install (recommended)
#   ./install.sh --yes                no questions: core tier only (no keys, no paid services)
#   ./install.sh --tiers core,guard,memory,routing,judge,deliberation   (no questions)
#   ./install.sh --only caveman,rtk   just these tools (dependencies are added)
#   ./install.sh --list               print the catalogue and exit
# Other options: --skip id,id  --caveman-mode lite|full|ultra  --handoff auto|250k|500k|750k|never  --confirm-fable yes|no
#   --report week|fortnight|month|off   how often the token report runs (default month)
#   --install-missing   install missing prerequisites (Homebrew, Node.js, uv, Claude Code CLI) without asking
#
# Never overwrites: settings.json is merged (backup first); your own CLAUDE.md, guides and agents are
# kept, and the kit's version is written next to them as *.kit-new. Third-party plugins and CLIs are
# installed from their own sources; nothing third-party is bundled here.
set -u
KIT="$(cd "$(dirname "$0")" && pwd)"
CL="$HOME/.claude"
BIN="$HOME/.local/bin"
TS=$(date +%Y%m%d-%H%M%S)
CAT="$KIT/lib/catalog.txt"
TIERS_ALL="core guard memory routing judge deliberation"
SELECTED=" "
TODO=""
FAILED=""
MODE=ask; TIERS=""; ONLY=""; SKIP=""; HANDOFF=""; CONFIRM_FABLE=""; REPORT=""; PILOT_OFF=""; CAVEMODE=""; INSTALL_MISSING=""
TTY=0; { : </dev/tty; } 2>/dev/null && TTY=1   # a keyboard to answer questions on

say()  { printf '%s\n' "$*"; }
ok()   { printf '  ok    %s\n' "$*"; }
info() { printf '  ..    %s\n' "$*"; }
warn() { printf '  WARN  %s\n' "$*"; }
fail() { printf '  FAIL  %s\n' "$*"; FAILED="$FAILED  - $*
"; }
todo() { TODO="$TODO$1
"; }
has()  { case "$SELECTED" in *" $1 "*) return 0 ;; esac; return 1; }
add()  { has "$1" || SELECTED="$SELECTED$1 "; }
short() { local t="~"; printf '%s' "${1/#$HOME/$t}"; }
drop() { SELECTED=$(printf '%s' "$SELECTED" | sed "s/ $1 / /"); }
field() { awk -F'|' -v id="$1" -v n="$2" '$1==id {print $n}' "$CAT"; }
tier_ids() { awk -F'|' -v t="$1" '!/^#/ && $2==t {print $1}' "$CAT"; }
csv() { printf '%s' "$1" | tr ',' ' '; }

usage() { awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"; exit 0; }

val() { [ -n "${2:-}" ] && [ "${2#--}" = "$2" ] || { say "$1 needs a value (see --help)"; exit 2; }; }
while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y) MODE=yes ;;
    --tiers) val "$1" "${2:-}"; TIERS=$(csv "$2"); MODE=yes; shift ;;
    --only) val "$1" "${2:-}"; ONLY=$(csv "$2"); shift ;;
    --skip) val "$1" "${2:-}"; SKIP=$(csv "$2"); shift ;;
    --caveman-mode) val "$1" "${2:-}"; CAVEMODE=$2; shift ;;
    --handoff) val "$1" "${2:-}"; HANDOFF=$2; shift ;;
    --confirm-fable) val "$1" "${2:-}"; CONFIRM_FABLE=$2; shift ;;
    --report) val "$1" "${2:-}"; REPORT=$2; shift ;;
    --install-missing) INSTALL_MISSING=1 ;;
    --list) awk -F'|' '!/^#/ {printf "%-15s %-13s %s\n    %s\n", $1, $2, $3, $5}' "$CAT"; exit 0 ;;
    -h|--help) usage ;;
    *) say "Unknown option: $1"; exit 2 ;;
  esac
  shift
done

# Questions come from the terminal even when stdin is a pipe; no terminal -> defaults.
ask() { # ask "question" default(y|n) -> 0 for yes
  local a d=$2
  if [ "$MODE" = yes ] || ! { : </dev/tty; } 2>/dev/null; then [ "$d" = y ]; return; fi
  printf '%s [%s] ' "$1" "$([ "$d" = y ] && echo Y/n || echo y/N)"
  read -r a </dev/tty
  a=${a:-$d}
  case "$a" in y|Y|yes) return 0 ;; esac
  return 1
}

# Checkbox menu for one group: shows [x]/[ ] per tool, toggles by number until Enter.
pick_ids() { # pick_ids "IDS" "IDS ticked at start"
  local ids on a w id i m
  ids=$1; on=" $2 "
  while :; do
    i=0; say ""
    for id in $ids; do
      i=$((i + 1)); case "$on" in *" $id "*) m=x ;; *) m=' ' ;; esac
      printf '  [%s] %d. %s\n' "$m" "$i" "$(field "$id" 3)"
    done
    printf '  Type numbers to tick/untick (e.g. 1 3), a = all, n = none, Enter = done: '
    read -r a </dev/tty || a=""
    [ -z "$a" ] && break
    for w in $a; do
      case "$w" in
        a) on=" $ids " ;;
        n) on=" " ;;
        *[!0-9]*) say "  '$w' is not a number" ;;
        *) id=$(printf '%s\n' $ids | sed -n "${w}p")
           if [ -z "$id" ]; then say "  no tool $w"
           else case "$on" in *" $id "*) on=${on/ $id / } ;; *) on="$on$id " ;; esac; fi ;;
      esac
    done
  done
  for id in $on; do add "$id"; done
}

describe() { # describe ID [NUMBER]
  printf '\n  %s%s  (%s)\n' "${2:+$2. }" "$(field "$1" 3)" "$(field "$1" 4)"
  printf '    What:  %s\n    Helps: %s\n    Needs: %s\n' "$(field "$1" 5)" "$(field "$1" 6)" "$(field "$1" 7)"
}

# Tools that need an API key or an account: asked about first, in one group, so nobody is surprised by a key later.
KEY_IDS="supermemory jev mjudge deliberation"
is_key() { case " $KEY_IDS " in *" $1 "*) return 0 ;; esac; return 1; }
tier_title() {
  case "$1" in
    keys) echo "FIRST, THE TOOLS THAT NEED AN API KEY OR AN ACCOUNT. Each one says which key and what it costs; you add the keys after the install, which lists where each goes. Tick the ones you want." ;;
    core) echo "CORE: the token savers and safety net. Free: no keys, no accounts. Recommended for everyone." ;;
    guard) echo "SAFETY RULES AND CHECKS: decide what Claude may never do, and check its work automatically. Free." ;;
    memory) echo "MEMORY: Claude remembers past chats and decisions. No key needed here (Supermemory, which needs an account, was in the first group)." ;;
    routing) echo "MODEL ROUTING: uses cheaper models where they do the job just as well. Free." ;;
    judge) echo "JUDGE TOOLS: fast outside yes/no checks over long lists and media. Need API keys (one paid, one with a free tier)." ;;
    deliberation) echo "PLAN CHECKS: test a plan before you build it. Free (Deliberation, which needs other AI accounts, was in the first group)." ;;
  esac
}

# ---------------------------------------------------------------- selection
if [ -n "$ONLY" ]; then
  for id in $ONLY; do [ -n "$(field "$id" 1)" ] && add "$id" || { say "Unknown tool: $id (see --list)"; exit 2; }; done
elif [ "$MODE" = yes ]; then
  for t in ${TIERS:-core}; do
    case " $TIERS_ALL " in *" $t "*) ;; *) say "Unknown tier: $t (tiers: $TIERS_ALL)"; exit 2 ;; esac
    for id in $(tier_ids "$t"); do add "$id"; done
  done
else
  say "claude-setup-kit: each tool is explained below; you choose what to install."
  say "Nothing is changed until all questions are answered."
  for t in keys $TIERS_ALL; do
    if [ "$t" = keys ]; then ids=$KEY_IDS
    else ids=$(for id in $(tier_ids "$t"); do is_key "$id" || echo "$id"; done); fi
    ids=$(echo $ids); [ -n "$ids" ] || continue  # a tier whose tools were all in the first group
    say ""; say "=== $(tier_title "$t")"
    i=0; for id in $ids; do i=$((i + 1)); describe "$id" "$i"; done
    case $t in core) d=$ids ;; guard) d="guard verify" ;; keys) d="supermemory" ;; memory) d="remember" ;; *) d="" ;; esac  # ticked at start
    if { : </dev/tty; } 2>/dev/null; then pick_ids "$ids" "$d"
    else for id in $d; do add "$id"; done; fi
  done
fi
# Skips first: a skipped tool also removes whatever needs it, so dependencies never pull it back in.
for id in $SKIP; do
  [ -n "$(field "$id" 1)" ] || { say "Unknown tool in --skip: $id (see --list)"; exit 2; }
  drop "$id"
  for pair in indexes:codegraph indexes:graphify mjudge:jev; do
    a=${pair%%:*}; b=${pair#*:}
    [ "$b" = "$id" ] && has "$a" && { drop "$a"; SKIP="$SKIP $a"; info "$(field "$a" 3) skipped too (needs $(field "$b" 3))"; }
  done
done
# Dependencies: asked, not silently added. Saying no leaves out the tool that needs it.
for pair in indexes:codegraph indexes:graphify mjudge:jev; do
  a=${pair%%:*}; b=${pair#*:}
  has "$a" && ! has "$b" || continue
  say ""
  if ask "$(field "$a" 3) only works together with $(field "$b" 3). Add $(field "$b" 3) as well? (No = leave out $(field "$a" 3))" y; then
    add "$b"; info "$(field "$b" 3) added"
  else drop "$a"; info "$(field "$a" 3) left out"; fi
done
[ "$SELECTED" = " " ] && { say "Nothing selected. Nothing changed."; exit 0; }
if has caveman && [ -z "$CAVEMODE" ]; then
  CAVEMODE=ultra
  if [ "$MODE" = ask ] && { : </dev/tty; } 2>/dev/null; then
    printf '\n  Caveman strength: lite (light trim), full, ultra (fragments only). [ultra] '; read -r CAVEMODE </dev/tty
    CAVEMODE=${CAVEMODE:-ultra}
  fi
fi
case "$CAVEMODE" in ''|lite|full|ultra) ;; *) info "Caveman mode '$CAVEMODE' not known: using ultra"; CAVEMODE=ultra ;; esac

# ---------------------------------------------------------------- the changes, each asked for first (--yes: all yes)
DO_SETTINGS=1; DO_SCHED=1
if has rules; then
  say ""
  say "Rules file: Claude reads ~/.claude/CLAUDE.md at the start of every chat. The kit's version tells it when"
  say "to use each tool you picked; without it Claude often forgets they exist. Five short guides go in ~/.claude/guides/."
  [ -f "$CL/CLAUDE.md" ] && say "You already have a CLAUDE.md: it is kept as it is, and the kit's version is saved next to it as CLAUDE.md.kit-new for you to merge."
  ask "Write the rules file and guides?" y || { drop rules; info "rules file left out"; }
fi
for id in rtk safety indexes routing cognee jev measure guard sandbox verify; do
  has $id || continue
  say ""
  say "Hooks: small scripts Claude Code runs at set moments (when a chat starts, before a shell command)."
  say "RTK, safe delete, auto indexes, the routing card, the per-turn token record, deny rules and done checks only work through them. They are added to"
  say "~/.claude/settings.json: the file is backed up first, nothing in it is removed or changed, only missing entries are added."
  ask "Add the kit's hooks to settings.json?" y || { DO_SETTINGS=0; info "hooks not added: those tools stay installed but inactive until you re-run and say yes"; }
  break
done
if has measure && [ -z "$REPORT" ]; then
  REPORT=month
  if [ "$MODE" = ask ] && { : </dev/tty; } 2>/dev/null; then
    say ""
    say "Token report: how much Claude used, how much the kit saved, and what you would have used without it."
    say "It compares against your own last 30 days before this install, and adds up a small record written after"
    say "every turn. It reads local files only and uses no Claude tokens; a notification says when one is ready."
    say "  1. Weekly (every Monday)   2. Fortnightly (every second Monday)   3. Monthly (on the 1st)   4. Off"
    printf '  How often? [3]: '; read -r a </dev/tty || a=""
    case "$a" in 1) REPORT=week ;; 2) REPORT=fortnight ;; 4) REPORT=off ;; *) REPORT=month ;; esac
  fi
fi
case "$REPORT" in ''|week|fortnight|month) ;; off) DO_SCHED=0 ;; *) info "Report choice '$REPORT' not known: using month"; REPORT=month ;; esac
if has model-pilot && [ "$(uname -s)" != Darwin ]; then drop model-pilot; info "Model pilot left out: it is macOS only"; fi
if has model-badge && [ "$(uname -s)" != Darwin ]; then drop model-badge; info "Model badge left out: it is macOS only for now"; fi
if has model-pilot; then
  # Two selectors would each pick a model for the same prompt. Only one can be on.
  OTHER=$(python3 -c 'import json,sys
try: print(" ".join(k for k, v in json.load(open(sys.argv[1])).get("enabledPlugins", {}).items() if v is True and k.endswith("@claude-model-selector")))
except Exception: pass' "$CL/settings.json" 2>/dev/null)
  if [ -n "$OTHER" ]; then
    say ""
    say "Model pilot: another model selector is switched on ($OTHER)."
    say "Two selectors would each pick a model for the same prompt, so only one can be on. Switching the other"
    say "one off does not remove it: 'claude plugin enable <name>' brings it back."
    if ask "Switch the other one off and use Model pilot? (No = leave Model pilot out)" y; then PILOT_OFF=$OTHER
    else drop model-pilot; info "Model pilot left out"; fi
  fi
fi
if has model-pilot && [ -z "$HANDOFF" ]; then
  HANDOFF=auto
  if [ "$MODE" = ask ] && { : </dev/tty; } 2>/dev/null; then
    say ""
    say "Model pilot: when should it offer you a fresh chat? A chat that grows long costs more at every step,"
    say "because Claude re-reads all of it each time, and it keeps track of early details less well. A new chat"
    say "that starts from a written summary is cheaper and sharper, but whatever the summary leaves out is gone."
    say "Model pilot can offer to write that summary when the chat reaches the size you choose here."
    say "It only ever offers. It never starts a new chat for you."
    say "  1) auto   at 500k tokens when the model's window is 1 million, at 250k on a smaller window (recommended:"
    say "            deep enough that a summary pays, early enough that the chat is not yet slow and costly)"
    say "  2) 250k   earliest: lowest cost per step, most restarts"
    say "  3) 500k"
    say "  4) 750k   latest: fewest restarts, highest cost per step"
    say "  5) never"
    printf '  Choose 1-5 [1] '; read -r a </dev/tty
    case "$a" in 2) HANDOFF=250k ;; 3) HANDOFF=500k ;; 4) HANDOFF=750k ;; 5) HANDOFF=never ;; *) HANDOFF=auto ;; esac
    say "  Change it any time in Claude Code: /config, under Model pilot."
  fi
fi
case "$HANDOFF" in ''|auto|250k|500k|750k|never) ;; *) info "Fresh-chat choice '$HANDOFF' not known: using auto"; HANDOFF=auto ;; esac
if has model-pilot && [ -z "$CONFIRM_FABLE" ]; then
  say ""
  say "Model pilot: Fable is the most capable model and the dearest. When the pilot (not you) picks it,"
  say "it can ask first, with the reason, the effort and the cost against Opus. Say no if cost does not"
  say "matter to you (for example on a top plan) and Fable should run without a question."
  if ask "Ask before the pilot runs a prompt on Fable?" y; then CONFIRM_FABLE=yes; else CONFIRM_FABLE=no; fi
fi
case "$CONFIRM_FABLE" in ''|yes|no) ;; *) info "Fable choice '$CONFIRM_FABLE' not known: asking"; CONFIRM_FABLE=yes ;; esac
[ "$SELECTED" = " " ] && { say "Nothing selected. Nothing changed."; exit 0; }
say ""; say "Ready to install:"
for id in $SELECTED; do say "  - $(field "$id" 3)"; done
ask "Go ahead?" y || { say "Stopped. Nothing changed."; exit 0; }
say ""; say "Installing:$SELECTED"

# ---------------------------------------------------------------- preflight (before any change)
if [ "$(uname -s)" != Darwin ]; then
  say "This kit is tested on macOS only (it uses the Keychain, osascript, BSD stat and Homebrew)."
  say "Set KIT_ALLOW_NON_MAC=1 to try anyway."; [ "${KIT_ALLOW_NON_MAC:-}" = 1 ] || exit 1
fi
# Prerequisites. Each missing one is explained, and offered to be installed for you (in order: Apple tools,
# Homebrew, then the rest). Nothing of the kit itself is installed until all of them are present.
# Override the install commands with KIT_CMD_<NAME> (used by the tests).
CMD_CLT=${KIT_CMD_CLT:-"xcode-select --install"}
CMD_BREW=${KIT_CMD_BREW:-'/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'}
CMD_CLAUDE=${KIT_CMD_CLAUDE:-"curl -fsSL https://claude.ai/install.sh | bash"}
CMD_NODE=${KIT_CMD_NODE:-"brew install node"}
CMD_UV=${KIT_CMD_UV:-"brew install uv"}
uses_claude() { for id in caveman adhd ponytail context-mode codegraph supermemory cognee remember model-pilot model-badge deliberation; do has $id && return 0; done; return 1; }
uses_node() { has context-mode || has codegraph || has grill-me; }
check_prereqs() { # fills LACK with "key|name|why" lines, in install order
  LACK=""
  # /usr/bin/python3 and git exist on every Mac but are stubs until Apple's Command Line Tools are installed.
  python3 -c pass >/dev/null 2>&1 && git --version >/dev/null 2>&1 || LACK="$LACK
CLT|Apple Command Line Tools|gives your Mac python3 and git; every script in this kit uses them (free, from Apple)"
  if { uses_node && ! command -v node >/dev/null 2>&1; } || { has graphify && ! command -v uv >/dev/null 2>&1 && ! command -v pipx >/dev/null 2>&1; }; then
    command -v brew >/dev/null 2>&1 || LACK="$LACK
BREW|Homebrew|the standard free installer for Mac developer tools; used here to get Node.js and uv (it asks for your Mac password)"
  fi
  uses_claude && ! command -v claude >/dev/null 2>&1 && LACK="$LACK
CLAUDE|Claude Code command-line tool|lets this installer add plugins for you; the Claude app and the terminal share it"
  uses_node && ! command -v node >/dev/null 2>&1 && LACK="$LACK
NODE|Node.js|runs context-mode and CodeGraph, and fetches Grill Me"
  has graphify && ! command -v uv >/dev/null 2>&1 && ! command -v pipx >/dev/null 2>&1 && LACK="$LACK
UV|uv|installs Graphify (a Python tool) in its own space, so it cannot clash with anything else"
  [ -z "$LACK" ]
}
fix_one() { # fix_one KEY: run its install command, then put the new tool on PATH for the rest of this run
  local cmd; eval "cmd=\$CMD_$1"
  say "  running: $cmd"
  if [ "$TTY" = 1 ]; then bash -c "$cmd" </dev/tty; else bash -c "$cmd"; fi || { say "  that did not finish cleanly"; return 1; }
  case "$1" in
    CLT) [ "$TTY" = 1 ] || { say "  Finish the Apple window that opened, then run the installer again."; return 1; }
         while ! { python3 -c pass >/dev/null 2>&1 && git --version >/dev/null 2>&1; }; do
           printf '  A window from Apple opened. Click Install, wait until it says it is done, then press Enter (q to stop): '
           read -r a </dev/tty; [ "$a" = q ] && return 1
         done ;;
    BREW) for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do [ -x "$b" ] && eval "$("$b" shellenv)"; done ;;
    CLAUDE) PATH="$HOME/.local/bin:$PATH" ;;
  esac
}
if ! check_prereqs; then
  say ""; say "Before the kit can install, this Mac needs:"
  printf '%s\n' "$LACK" | while IFS='|' read -r k n w; do [ -n "$k" ] && say "  - $n: $w"; done
  if { [ "$MODE" = ask ] && [ "$TTY" = 1 ]; } || [ "$INSTALL_MISSING" = 1 ]; then
    for k in $(printf '%s\n' "$LACK" | cut -d'|' -f1); do
      check_prereqs && break
      case "$LACK" in *"$k|"*) ;; *) continue ;; esac  # installed by an earlier step
      n=$(printf '%s\n' "$LACK" | grep "^$k|" | cut -d'|' -f2)
      if [ "$INSTALL_MISSING" = 1 ] || ask "Install $n for you now?" y; then fix_one "$k" || say "  $n is still missing."
      else say "  Skipped $n."; fi
    done
  fi
  if ! check_prereqs; then
    say ""; say "Still missing:"
    printf '%s\n' "$LACK" | while IFS='|' read -r k n w; do [ -n "$k" ] && { eval "c=\$CMD_$k"; say "  - $n   install with: $c"; }; done
    say "Install these (or run ./install.sh again and answer yes), then re-run. Nothing of the kit was changed."
    exit 1
  fi
  ok "all prerequisites present"
fi
mkdir -p "$CL/hooks" "$CL/agents" "$CL/guides" "$CL/rules" "$BIN" "$CL/kit"; export KIT_RTK=rtk

# ---------------------------------------------------------------- helpers
# copy_file SRC DST exec|data replace|keep
#   replace: differing DST is backed up to DST.bak-kit-<time>, then replaced (kit-owned scripts)
#   keep:    differing DST is left alone; the kit's copy goes to DST.kit-new (your own docs)
copy_file() {
  local src=$1 dst=$2 kind=$3 pol=$4
  if [ -f "$dst" ] && cmp -s "$src" "$dst"; then ok "unchanged $(short "$dst")"; return; fi
  if [ -f "$dst" ] && [ "$pol" = keep ]; then
    cp "$src" "$dst.kit-new"; warn "kept your $(short "$dst"); kit version at $(short "$dst").kit-new"
    todo "Compare $(short "$dst") with $(short "$dst").kit-new and merge what you want."
    return
  fi
  [ -f "$dst" ] && cp -p "$dst" "$dst.bak-kit-$TS"
  cp "$src" "$dst"; [ "$kind" = exec ] && chmod +x "$dst"
  ok "installed $(short "$dst")"
}

# Exact-match lookups on the CLI's JSON output (the human-readable list is not a stable format).
mp_has() { claude plugin marketplace list --json 2>/dev/null |
  python3 -c 'import json,sys; sys.exit(0 if any(m.get("name") == sys.argv[1] for m in json.load(sys.stdin)) else 1)' "$1"; }
pl_state() { claude plugin list --json 2>/dev/null |   # prints enabled | disabled | (nothing)
  python3 -c 'import json,sys; print(next(("enabled" if p.get("enabled") else "disabled" for p in json.load(sys.stdin) if p.get("id") == sys.argv[1]), ""))' "$1"; }
plugin() { # plugin MARKETPLACE_SOURCE MARKETPLACE_NAME PLUGIN
  local src=$1 mp=$2 id="$3@$2" st
  if ! mp_has "$mp"; then
    info "adding marketplace $src"
    claude plugin marketplace add "$src" >/dev/null 2>&1 || { fail "marketplace add $src"; return 1; }
  fi
  st=$(pl_state "$id")
  case "$st" in
    enabled) ok "plugin $id already installed"; return 0 ;;
    disabled) warn "plugin $id is installed but disabled; left as you set it (claude plugin enable $id)"; return 0 ;;
  esac
  if claude plugin install "$id" --scope user >/dev/null 2>&1; then ok "plugin $id"
  else fail "plugin install $id (run: claude plugin install $id)"; return 1; fi
}

# ---------------------------------------------------------------- rules + guides (first: later tools append to CLAUDE.md)
if has rules; then
  rendered=$(mktemp)
  python3 - "$KIT/files/CLAUDE.template.md" "$rendered" $SELECTED $(cat "$CL/kit/installed" 2>/dev/null) <<'PY'
import re, sys
src, out, keep = sys.argv[1], sys.argv[2], set(sys.argv[3:])
text = open(src).read()
# Drop each <!-- kit:ID --> block whose tool was not installed; keep the rest without the markers.
text = re.sub(r"<!-- kit:([\w-]+) -->\n(.*?)<!-- /kit:\1 -->\n",
              lambda m: m.group(2) if m.group(1) in keep else "", text, flags=re.S)
open(out, "w").write(text)
PY
  # Current when: the kit's render is the same as last run (your edits since then are yours), or the file starts with
  # the render (tools such as graphify append their own section). Otherwise copy_file keeps yours and writes .kit-new.
  prev="$CL/kit/CLAUDE.rendered.md"
  if [ -f "$CL/CLAUDE.md" ] && { cmp -s "$rendered" "$prev" ||
       head -c "$(wc -c < "$rendered" | tr -d ' ')" "$CL/CLAUDE.md" | cmp -s - "$rendered"; }; then ok "unchanged ~/.claude/CLAUDE.md"
  else copy_file "$rendered" "$CL/CLAUDE.md" data keep; fi
  cp "$rendered" "$prev"
  grep -q '{{' "$CL/CLAUDE.md" 2>/dev/null &&
    todo "Fill the {{...}} placeholders in ~/.claude/CLAUDE.md (Identity section): your name, place and time zone, form of address, English variant."
  for f in coding connectors-and-skills knowledge-and-projects token-tools; do
    copy_file "$KIT/files/guides/$f.md" "$CL/guides/$f.md" data keep
  done
  has routing && copy_file "$KIT/files/guides/agents-and-models.md" "$CL/guides/agents-and-models.md" data keep
  copy_file "$KIT/files/rules/coding-hard-rules.md" "$CL/rules/coding-hard-rules.md" data keep
fi

# ---------------------------------------------------------------- core
if has caveman; then
  plugin JuliusBrussee/caveman caveman caveman
  if [ ! -f "$HOME/.config/caveman/config.json" ]; then
    mkdir -p "$HOME/.config/caveman"
    printf '{\n  "defaultMode": "%s"\n}\n' "$CAVEMODE" > "$HOME/.config/caveman/config.json"; ok "Caveman default mode: $CAVEMODE"
  else ok "kept existing ~/.config/caveman/config.json"; fi
fi
if has adhd; then
  plugin ayghri/i-have-adhd i-have-adhd i-have-adhd && touch "$CL/.i-have-adhd-always" && ok "i-have-adhd always on (delete ~/.claude/.i-have-adhd-always to turn off)"
fi
has ponytail && plugin DietrichGebert/ponytail ponytail ponytail
has context-mode && plugin mksglu/context-mode context-mode context-mode
if has rtk; then
  if command -v rtk >/dev/null 2>&1 || [ -x "$BIN/rtk" ]; then ok "rtk already installed"
  elif [ "${KIT_RTK_METHOD:-}" != script ] && command -v brew >/dev/null 2>&1; then
    brew install rtk >/dev/null 2>&1 && ok "rtk (Homebrew)" || fail "brew install rtk (run it yourself to see why)"
  else
    # Upstream's documented installer (github.com/rtk-ai/rtk). RTK_EDITION=oss gives the Apache-2.0-only build.
    curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh >/dev/null 2>&1 \
      && ok "rtk (install script)" || fail "rtk install script"
  fi
  # The hook gets rtk's absolute path: Claude Code's hook PATH may not include ~/.local/bin or Homebrew.
  KIT_RTK=$(command -v rtk 2>/dev/null || { [ -x "$BIN/rtk" ] && echo "$BIN/rtk"; } || echo rtk); export KIT_RTK
fi
if has codegraph; then
  if [ -x "$BIN/codegraph" ]; then ok "codegraph already installed"
  else npm install -g --prefix "$HOME/.local" @colbymchenry/codegraph >/dev/null 2>&1 && ok "codegraph (npm)" || fail "npm install @colbymchenry/codegraph"; fi
  if claude mcp get codegraph >/dev/null 2>&1; then ok "codegraph MCP server already registered"
  else claude mcp add -s user codegraph -- "$BIN/codegraph" serve --mcp >/dev/null 2>&1 && ok "codegraph MCP server registered" || fail "claude mcp add codegraph"; fi
fi
if has graphify; then
  if [ -x "$BIN/graphify" ]; then ok "graphify already installed"
  elif command -v uv >/dev/null 2>&1; then uv tool install graphifyy >/dev/null 2>&1 && ok "graphify (uv)" || fail "uv tool install graphifyy"
  else pipx install graphifyy >/dev/null 2>&1 && ok "graphify (pipx)" || fail "pipx install graphifyy"; fi
  if [ -f "$CL/skills/graphify/SKILL.md" ]; then ok "graphify skill already installed"
  elif [ -x "$BIN/graphify" ]; then "$BIN/graphify" install --platform claude >/dev/null 2>&1 && ok "graphify skill" || fail "graphify install --platform claude"; fi
fi
if has safety; then
  copy_file "$KIT/files/bin/trashmv" "$BIN/trashmv" exec replace
  copy_file "$KIT/files/hooks/block-rm.py" "$CL/hooks/block-rm.py" exec replace
fi
if has verify; then
  copy_file "$KIT/files/hooks/verify-done.py" "$CL/hooks/verify-done.py" exec replace
  todo "Done checks: in each project you want checked, add an executable .claude/verify (e.g. '#!/bin/sh' then 'npm test --silent'); optionally .claude/lint, which gets the edited file's path."
fi
if has indexes; then
  copy_file "$KIT/files/hooks/ensure-indexes.sh" "$CL/hooks/ensure-indexes.sh" exec replace
  copy_file "$KIT/files/hooks/codegraph-gate.py" "$CL/hooks/codegraph-gate.py" exec replace
  copy_file "$KIT/files/hooks/index-first.py" "$CL/hooks/index-first.py" exec replace
  copy_file "$KIT/files/hooks/kit-timeout" "$CL/hooks/kit-timeout" exec replace
fi
if has measure; then
  for f in token-scorecard.py token-compare.py token-daily.py token-report.py token-tools.py token-ledger.py; do copy_file "$KIT/files/hooks/$f" "$CL/hooks/$f" exec replace; done
  mkdir -p "$CL/cache/token-compare/reports" "$CL/monitor/bin"
  # Setup monitor (weekly scorecard) and house rules: docs/setup-monitor-design.md
  for f in "$KIT"/files/monitor/*.py; do copy_file "$f" "$CL/monitor/bin/$(basename "$f")" exec replace; done
  copy_file "$KIT/files/hooks/house-rules-recall.py" "$CL/hooks/house-rules-recall.py" exec replace
  [ -f "$CL/cache/token-compare/change-date" ] || date +%F > "$CL/cache/token-compare/change-date"
  # Freeze the 30 days before install now, while those transcripts still exist (Claude Code prunes old ones).
  [ -f "$CL/cache/token-compare/before-week.json" ] || { python3 "$CL/hooks/token-compare.py" >/dev/null 2>&1 && ok "token baseline frozen (30 days before install)"; }
  b=$(python3 "$CL/hooks/token-compare.py" baseline 2>/dev/null) && [ -n "$b" ] && info "$b"
  python3 "$CL/hooks/token-report.py" --set "${REPORT:-month}" >/dev/null && ok "token report: ${REPORT:-month} (change any time: python3 ~/.claude/hooks/token-report.py --set week|fortnight|month|off)"
  # A daily 09:00 job; the script writes a report only when a chosen period has finished and has none yet,
  # so a Mac that was asleep catches up at the next run. No Claude tokens.
  LA="$HOME/Library/LaunchAgents"; OLD="$LA/com.claude-setup-kit.token-monthly.plist"
  if [ -f "$OLD" ]; then  # earlier kit versions: monthly job under another name
    [ "$HOME" = "$(eval echo "~$(id -un)")" ] && launchctl bootout "gui/$(id -u)/com.claude-setup-kit.token-monthly" >/dev/null 2>&1
    mv "$OLD" "$OLD.bak-kit-$TS" && ok "old monthly job replaced (kept as $(short "$OLD").bak-kit-$TS)"
  fi
  if [ "$DO_SCHED" = 0 ]; then info "token report off: nothing scheduled (run it by hand: python3 ~/.claude/hooks/token-report.py)"; else
  LBL=com.claude-setup-kit.token-report; PL="$LA/$LBL.plist"; mkdir -p "$LA"
  cat > "$PL.tmp" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LBL</string>
  <key>ProgramArguments</key><array><string>$(command -v python3)</string><string>$CL/hooks/token-report.py</string><string>--scheduled</string><string>--notify</string></array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>$CL/cache/token-compare/reports/launchd.log</string>
  <key>StandardErrorPath</key><string>$CL/cache/token-compare/reports/launchd.log</string>
</dict></plist>
PLIST
  if cmp -s "$PL.tmp" "$PL"; then rm -f "$PL.tmp"; ok "token report job already scheduled (daily check, 09:00)"
  else
    mv "$PL.tmp" "$PL"
    # launchd is per user, not per HOME: only load it for the real home, never for a test HOME.
    if [ "$HOME" = "$(eval echo "~$(id -un)")" ]; then
      launchctl bootout "gui/$(id -u)/$LBL" >/dev/null 2>&1
      launchctl bootstrap "gui/$(id -u)" "$PL" >/dev/null 2>&1 && ok "token report job scheduled (daily check at 09:00; writes a report when your period ends)" || fail "launchctl bootstrap $PL"
    else info "test HOME: report job written to $PL, not loaded"; fi
  fi
  LBL=com.claude-setup-kit.setup-monitor; PL="$LA/$LBL.plist"
  cat > "$PL.tmp" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LBL</string>
  <key>ProgramArguments</key><array><string>$(command -v python3)</string><string>$CL/monitor/bin/setup-monitor.py</string><string>weekly</string><string>--notify</string></array>
  <key>StartCalendarInterval</key><dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>15</integer></dict>
  <key>StandardOutPath</key><string>$CL/monitor/launchd.log</string>
  <key>StandardErrorPath</key><string>$CL/monitor/launchd.log</string>
</dict></plist>
PLIST
  if cmp -s "$PL.tmp" "$PL"; then rm -f "$PL.tmp"; ok "setup monitor already scheduled (Mondays 08:15)"
  else
    mv "$PL.tmp" "$PL"
    if [ "$HOME" = "$(eval echo "~$(id -un)")" ]; then
      launchctl bootout "gui/$(id -u)/$LBL" >/dev/null 2>&1
      launchctl bootstrap "gui/$(id -u)" "$PL" >/dev/null 2>&1 && ok "setup monitor scheduled (Mondays 08:15: scorecard, trend, house-rule candidates)" || fail "launchctl bootstrap $PL"
    else info "test HOME: setup monitor job written to $PL, not loaded"; fi
  fi
  fi
fi

# ---------------------------------------------------------------- memory
if has supermemory; then
  plugin supermemoryai/claude-supermemory supermemory-plugins supermemory &&
    todo "Supermemory: start Claude Code and complete the Supermemory sign-in it opens (or set SUPERMEMORY_CC_API_KEY, see .env.example)."
fi
if has cognee; then
  plugin topoteretes/cognee-integrations cognee cognee-memory &&
    todo "Cognee builds its local server on the first session (a few minutes; needs Python 3.10+). Pick how it pays for the AI that builds its map: (a) your Claude plan: do nothing, it uses the claude command and counts towards your plan's usage limits; or (b) your own API key: put LLM_PROVIDER, LLM_MODEL and LLM_API_KEY in ~/.cognee/.env (see .env.example), billed per use, so set a spend limit. Codex can share the same memory: see github.com/topoteretes/cognee-integrations."
fi
has remember && plugin anthropics/claude-plugins-official claude-plugins-official remember

# ---------------------------------------------------------------- routing
if has routing; then
  copy_file "$KIT/files/hooks/routing-card.sh" "$CL/hooks/routing-card.sh" exec replace
  for f in "$KIT"/files/agents/*.md; do copy_file "$f" "$CL/agents/$(basename "$f")" data keep; done
fi
if has model-pilot || has model-badge; then
  # Copied, so this kit folder can be moved or removed later. Files are added or replaced, never removed.
  dest="$CL/local-marketplaces/claude-setup-kit"; mkdir -p "$dest"
  cp -R "$KIT/mods/." "$dest/" && ok "kit mods in $dest" || fail "copy $KIT/mods to $dest"
fi
if has model-badge; then
  plugin "$dest" claude-setup-kit model-badge &&
    todo "Model badge: in a new chat, start a helper agent; its row shows the model it ran on."
fi
if has model-pilot; then
  for p in $PILOT_OFF; do
    claude plugin disable "$p" >/dev/null 2>&1 && ok "switched off $p (to go back: claude plugin enable $p, and switch Model pilot off)" || fail "could not switch off $p (run: claude plugin disable $p)"
  done
  plugin "$dest" claude-setup-kit model-pilot
  if [ "$HANDOFF" != auto ] || [ "$CONFIRM_FABLE" = no ]; then
    python3 - "$CL/settings.json" "$HANDOFF" "$CONFIRM_FABLE" "$TS" <<'PY' && ok "Model pilot: fresh-chat offer $HANDOFF, ask before Fable: ${CONFIRM_FABLE:-yes}" || fail "could not save the Model pilot choices (set them in /config, under Model pilot)"
import json, os, shutil, sys
path, handoff, fable, ts = sys.argv[1:5]
d = json.load(open(path)) if os.path.exists(path) else {}
opts = d.setdefault("pluginConfigs", {}).setdefault("model-pilot@claude-setup-kit", {}).setdefault("options", {})
want = dict(opts)
if handoff != "auto":
    want["handoff"] = handoff
if fable == "no":
    want["confirmFable"] = False
if want != opts:
    if os.path.exists(path):
        shutil.copy2(path, f"{path}.bak-kit-{ts}")
    opts.clear(); opts.update(want)
    json.dump(d, open(path, "w"), indent=2)
PY
  fi
  todo "Model pilot: after the restart, type /pilot status in Claude Code. The row above the prompt shows each pick and what really ran; /pilot cost compares a helper agent, doing it in place and a fresh chat."
fi

# ---------------------------------------------------------------- judge
if has jev; then
  for f in jev jev-gate; do copy_file "$KIT/files/bin/$f" "$BIN/$f" exec replace; done
  for f in jev_lib.py jev-hooks.py typesafe_key.py; do copy_file "$KIT/files/hooks/$f" "$CL/hooks/$f" data replace; done
  mkdir -p "$CL/jev"; copy_file "$KIT/files/jev/policy.json" "$CL/jev/policy.json" data keep
  todo "Jev: store your TypeSafe key in the macOS Keychain: security add-generic-password -s typesafe-api-key -a \"\$USER\" -w   (it prompts for the key; nothing lands in a file)."
fi
if has mjudge; then
  copy_file "$KIT/files/bin/mjudge" "$BIN/mjudge" exec replace
  todo "mjudge: put GEMINI_API_KEY=... in ~/.config/watch/.env (chmod 600), or export it in your shell."
fi

# ---------------------------------------------------------------- deliberation
if has deliberation; then
  plugin antonbabenko/agent-plugins antonbabenko deliberation &&
    todo "Deliberation: set up at least one provider, then run /deliberation:setup in Claude Code. GPT: npm i -g @openai/codex && codex login. Grok: XAI_API_KEY. OpenRouter: OPENROUTER_API_KEY. Gemini: the agy CLI."
fi

if has grill-me; then
  # Fetched from the author's repo, never copied into this kit. Skills already there are left as they are.
  if [ -e "$CL/skills/grill-me" ] && [ -e "$CL/skills/grilling" ] && [ -e "$CL/skills/grill-with-docs" ]; then ok "Grill Me already installed"
  elif (cd "$CL" && npx --yes skills add mattpocock/skills -g -a claude-code -s grill-me -s grilling -s grill-with-docs -y) >/dev/null 2>&1; then ok "Grill Me (grill-me, grilling, grill-with-docs from mattpocock/skills)"
  else fail "Grill Me (run: npx skills add mattpocock/skills -g -a claude-code -s grill-me -s grilling -s grill-with-docs)"; fi
  todo "Grill Me: type /grill-me before you build something; /grill-with-docs also writes down decisions and terms."
fi

# ---------------------------------------------------------------- settings.json (merge, never overwrite)
if [ "$DO_SETTINGS" = 1 ]; then
  say ""; say "Merging hooks into ~/.claude/settings.json (backup written first if anything changes):"
  python3 "$KIT/lib/merge_settings.py" "$CL/settings.json" "$KIT/lib/hooks.json" $SELECTED || fail "settings merge"
else todo "Hooks were not added (you said no): re-run ./install.sh and say yes to activate RTK, safe delete, auto indexes and the routing card."; fi
for id in rtk codegraph graphify safety jev mjudge; do
  has $id || continue
  case ":$PATH:" in *":$BIN:"*) ;; *) todo "Add ~/.local/bin to PATH (in ~/.zprofile: export PATH=\"\$HOME/.local/bin:\$PATH\"), then open a new terminal. trashmv, jev, codegraph and graphify live there." ;; esac
  break
done
# Remember what is installed, for doctor.sh (union with earlier runs).
{ cat "$CL/kit/installed" 2>/dev/null; printf '%s\n' $SELECTED; } | sort -u | grep . > "$CL/kit/installed.tmp" && mv "$CL/kit/installed.tmp" "$CL/kit/installed"

# ---------------------------------------------------------------- report
say ""
if [ -n "$FAILED" ]; then say "Finished with problems:"; printf '%s' "$FAILED"; else say "Install finished with no errors."; fi
say ""
say "Still to do by hand:"
todo "Restart Claude Code (quit and reopen the desktop app, or start a new 'claude' session) so plugins and hooks load."
todo "Check the install: $KIT/doctor.sh"
printf '%s' "$TODO" | awk 'NF {printf "  %d. %s\n", ++n, $0}'
[ -z "$FAILED" ]
