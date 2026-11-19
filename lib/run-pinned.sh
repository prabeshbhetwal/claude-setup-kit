#!/bin/bash
# run-pinned.sh NAME SHELL: download the pinned script NAME (rtk, brew or claude), check its sha256, run it.
# Refuses to run anything that does not match the pin in pins.sh.
here="$(cd "$(dirname "$0")" && pwd)"
. "$here/pins.sh"
name=$1; sh=${2:-bash}
case "$name" in
  rtk) url=$PIN_RTK_URL; want=$PIN_RTK_SHA ;;
  brew) url=$PIN_BREW_URL; want=$PIN_BREW_SHA ;;
  claude) url=$PIN_CLAUDE_URL; want=$PIN_CLAUDE_SHA ;;
  *) echo "run-pinned: unknown script '$name'" >&2; exit 2 ;;
esac
[ "${KIT_TESTING:-}" = 1 ] && url=${KIT_PIN_URL:-$url}  # the audit points this at a local file
f=$(mktemp "${TMPDIR:-/tmp}/kit-pinned.XXXXXX") || exit 1
trap 'rm -f "$f"' EXIT
curl -fsSL "$url" -o "$f" || { echo "could not download $url" >&2; exit 1; }
got=$(shasum -a 256 "$f" | cut -d' ' -f1)
if [ "$got" != "$want" ]; then
  echo "NOT RUN: $url no longer matches the checksum this kit pinned." >&2
  echo "  pinned $want" >&2
  echo "  got    $got" >&2
  echo "  Read the script, run it yourself if you trust it, then update lib/pins.sh." >&2
  exit 1
fi
"$sh" "$f"
