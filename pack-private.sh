#!/bin/bash
# Packs YOUR running Model Selector pack (with your own changes) into private/, for your own machines only.
#   ./pack-private.sh   -> private/claude-model-selector.zip  +  ../claude-setup-kit-private.zip (kit + pack)
# The pack is Ben AI's work with no licence: private/ is gitignored and the bundle must never be published.
# Reads ~/.claude/local-marketplaces/claude-model-selector; changes nothing there. Logs are left out.
set -eu
cd "$(dirname "$0")"
KIT=$(pwd)
SRC="$HOME/.claude/local-marketplaces/claude-model-selector"
[ -f "$SRC/.claude-plugin/marketplace.json" ] || { echo "No Model Selector pack at $SRC"; exit 1; }
mkdir -p private
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
cp -R "$SRC" "$tmp/claude-model-selector"
find "$tmp" \( -name mods-logs -o -name node_modules -o -name .git \) -type d -prune -exec rm -rf {} +
find "$tmp" -name .DS_Store -delete
rm -f private/claude-model-selector.zip
(cd "$tmp" && zip -qr "$KIT/private/claude-model-selector.zip" claude-model-selector)
echo "pack:   private/claude-model-selector.zip ($(du -h private/claude-model-selector.zip | cut -f1))"

# Kit at HEAD (committed files only) + private/, ready to copy to your laptop.
git diff --quiet HEAD || echo "note: uncommitted changes are NOT in the bundle; commit first"
out="$(dirname "$KIT")/claude-setup-kit-private.zip"; rm -f "$out"
git archive --format=zip --prefix=claude-setup-kit/ -o "$out" HEAD
mkdir -p "$tmp/b/claude-setup-kit" && cp -R private "$tmp/b/claude-setup-kit/"
(cd "$tmp/b" && zip -qr "$out" claude-setup-kit/private)
echo "bundle: $out  (private: do not publish or share)"
