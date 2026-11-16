#!/bin/bash
# Secret + personal-data scan over the whole kit. Exit 0 = clean. Run before every commit or share.
#   ./scan.sh                 scan this folder
#   ./scan.sh --also WORD     add a banned word (literal, case-insensitive; repeatable), e.g. your name or email
# Checks: API keys and tokens (common formats), private keys, email addresses, absolute home paths,
# assigned secrets (any case: api_key = ..., "apiKey": ..., password: ...), and any --also words.
# A line ending in `scan:allow (reason)` is skipped: use it only for fake test values, and say why.
set -u
cd "$(dirname "$0")"
EXTRA=()
while [ $# -gt 0 ]; do
  case "$1" in
    --also) EXTRA+=("${2:?--also needs a word}"); shift ;;
    *) echo "Unknown option: $1"; exit 2 ;;
  esac
  shift
done

# Exactly what git would publish (tracked + new, minus .gitignore); outside a git repo, every file but private/.
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  files=$(git ls-files --cached --others --exclude-standard | grep -v '^scan.sh$' | sed 's|^|./|' | sort)
else
  files=$(find . -type f ! -path './.git/*' ! -path './private/*' ! -name scan.sh | sort)
fi
hits=0
check() { # check LABEL PATTERN [grep flags]
  local out rc
  out=$(printf '%s\n' "$files" | tr '\n' '\0' | xargs -0 grep -nIE ${3:-} -e "$2" 2>&1 | grep -v 'scan:allow'); rc=$?
  # xargs reports 123 when a grep exits 1 (no match) and 125/126/127 or grep 2 on a real error.
  if printf '%s' "$out" | grep -q '^grep:'; then printf 'FAIL  %s: grep error\n%s\n' "$1" "$out"; hits=$((hits + 1))
  elif [ -n "$out" ]; then printf 'FAIL  %s\n%s\n' "$1" "$(printf '%s\n' "$out" | head -20 | cut -c1-200)"; hits=$((hits + 1))
  else printf 'pass  %s\n' "$1"; fi
  : "$rc"
}
check "Anthropic / OpenAI / OpenRouter keys" 'sk-(ant|or|proj|svcacct|[a-z]+)-[A-Za-z0-9_-]{16,}|sk-[A-Za-z0-9]{32,}'
check "xAI / Google / GitHub / GitLab / Slack / AWS tokens" 'xai-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{22,}|glpat-[A-Za-z0-9_-]{20}|xox[abpr]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}'
check "Private keys" '-----BEGIN [A-Z ]*PRIVATE KEY( BLOCK)?-----'
check "Assigned secrets (key/token/secret/password = value)" '(api[_-]?key|secret|token|passw(or)?d|_key)["'"'"']?[[:space:]]*[:=][[:space:]]*["'"'"']?[A-Za-z0-9_./+=-]{12,}' -i
check "Email addresses" '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
check "Absolute home paths" '/Users/[A-Za-z0-9._-]+|/home/[a-z][a-z0-9_-]+/'
for w in "${EXTRA[@]+"${EXTRA[@]}"}"; do check "Banned word: $w" "$w" -iF; done
echo ""
if [ $hits = 0 ]; then echo "SCAN CLEAN ($(printf '%s\n' "$files" | wc -l | tr -d ' ') files)"; else echo "SCAN FAILED: $hits check(s) with hits"; fi
[ $hits = 0 ]
