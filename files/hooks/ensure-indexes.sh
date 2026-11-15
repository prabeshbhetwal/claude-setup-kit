#!/bin/sh
# SessionStart + Stop hook: keep a CodeGraph index and a graphify graph current for the
# current git repo. Missing indexes are built; existing ones are refreshed whenever the
# working tree changed since the last refresh (edits, commits, branch switches, merges).
# Everything runs in the background so sessions and turns never wait on it.
# Usage: ensure-indexes.sh          (SessionStart: prints a one-line notice)
#        ensure-indexes.sh stop     (Stop: silent refresh after each turn)
#        ensure-indexes.sh fg       (hourly job: silent, waits, exit code = refresh result)
# Logs: ~/.claude/cache/index-builds/<repo-path>.log
mode=${1:-start}
CG="$HOME/.local/bin/codegraph"; GF="$HOME/.local/bin/graphify"   # pinned: older graphify copies sit earlier on some PATHs
[ -x "$CG" ] || CG=$(command -v codegraph || echo "$CG")            # Windows: npm/uv put codegraph.cmd / graphify.exe elsewhere
[ -x "$GF" ] || GF=$(command -v graphify || echo "$GF")
PY=$(command -v python3 || command -v python)                       # Windows has python, often no python3
SHA=$(command -v shasum || command -v sha1sum)
TO=$(command -v timeout 2>/dev/null || echo "$HOME/.claude/hooks/kit-timeout")   # macOS has no GNU timeout

# Hooks get the session dir as JSON on stdin; fall back to $PWD when run by hand.
if [ ! -t 0 ]; then
  cwd=$("$PY" -c 'import json,sys; print(json.load(sys.stdin).get("cwd",""))' 2>/dev/null)
  [ -n "$cwd" ] && cd "$cwd" 2>/dev/null
fi

r=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0   # not a repo: plain conversation, nothing to index
[ "$r" = "$HOME" ] && exit 0                                # never index the whole home dir

# Both indexes only pay off on real code. Below this many tracked source files,
# reading files directly is cheaper than the index (and its per-prompt context).
MIN_SOURCE_FILES=10
n=$(git -C "$r" ls-files | grep -cE '\.(swift|py|ts|tsx|js|jsx|mjs|go|rs|java|kt|rb|c|cc|cpp|h|hpp|m|mm|cs|php|scala|sh|sql|vue|svelte|dart|lua|zig)$')
[ "$n" -lt "$MIN_SOURCE_FILES" ] && exit 0

logdir="$HOME/.claude/cache/index-builds"
mkdir -p "$logdir"
key=$(printf %s "$r" | tr / _)
log="$logdir/$key.log"
stamp="$logdir/$key.stamp"

# Keep both outputs out of `git status` without touching tracked files.
ex=$(git -C "$r" rev-parse --path-format=absolute --git-path info/exclude 2>/dev/null)
if [ -n "$ex" ]; then
  mkdir -p "$(dirname "$ex")"
  for p in .codegraph/ graphify-out/; do
    grep -qxF "$p" "$ex" 2>/dev/null || echo "$p" >> "$ex"
  done
fi

# mkdir is atomic: a second session opening the same repo won't start a duplicate build.
# A lock older than 45 min (past the 40 min of timeouts below) belongs to a killed build; clear it so refreshes never stop for good.
# Every command is wrapped in timeout (600 s sync, 1800 s build): a hung tool exits 124, the stamp
# stays unwritten, and the next turn or hourly run retries — nothing can block refreshes forever.
build() { # $1 = lock name, $2 = shell command
  lock="$logdir/$key.$1.lock"
  find "$lock" -maxdepth 0 -mmin +45 -exec rmdir {} \; 2>/dev/null
  mkdir "$lock" 2>/dev/null || return 0
  if [ "$mode" = fg ]; then   # hourly job (token-stack-health.sh): wait, report failure via exit code
    ( cd "$r" && { echo "[$(date '+%F %T')] $2"; sh -c "$2"; } >> "$log" 2>&1 ) </dev/null; rc=$?
    rmdir "$lock"; return $rc
  fi
  ( cd "$r" && { echo "[$(date '+%F %T')] $2"; sh -c "$2"; } >> "$log" 2>&1; rmdir "$lock" ) </dev/null >/dev/null 2>&1 &   # detach: hook must not wait on the build
}

if [ ! -d "$r/.codegraph" ]; then
  [ "$mode" = start ] && echo "No .codegraph/ in $r: building CodeGraph index in background (log: $log)."
  build codegraph "$TO 1800 $CG init -y '$r'"
fi

if [ ! -d "$r/graphify-out" ]; then
  [ "$mode" = start ] && echo "No graphify-out/ in $r: building graphify graph in background (log: $log)."
  build graphify "$TO 1800 $GF update '$r'"
  exit $?
fi
[ "$mode" = start ] && echo "graphify-out/ present: read $r/graphify-out/GRAPH_REPORT.md (or wiki/index.md) before architecture/spec/doc questions."
[ -d "$r/.codegraph" ] || exit 0

# Tree signature: HEAD plus every changed/untracked path with its mtime and size, so a second
# edit to an already-modified file still counts. Unchanged since the last refresh: nothing to do.
sig=$( { git -C "$r" rev-parse HEAD 2>/dev/null
         git -C "$r" status --porcelain -uall 2>/dev/null | while IFS= read -r line; do
           echo "$line"; { stat -c '%Y %s' "$r/${line#???}" || stat -f '%m %z' "$r/${line#???}"; } 2>/dev/null   # GNU (Git Bash) first; BSD rejects -c
         done; } | "$SHA" | cut -c1-40 )
[ "$sig" = "$(cat "$stamp" 2>/dev/null)" ] && exit 0

# The stamp is written only after both refreshes succeed, so a failed run is retried next time.
build refresh "$TO 600 $CG sync '$r' && $TO 1800 $GF update '$r' && echo '$sig' > '$stamp'"
exit $?
