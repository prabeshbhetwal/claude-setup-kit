# Pinned upstream downloads (sourced by install.sh). Nothing the installer fetches floats on "latest" or HEAD.
# To bump one: read what changed upstream, then edit the version, or the commit in the URL plus its sha256
# (curl -fsSL URL | shasum -a 256). lib/audit.py fails if an installer download is not pinned here.
PIN_CODEGRAPH="@colbymchenry/codegraph@1.6.3"   # npm
PIN_GRAPHIFY="graphifyy==0.9.113"               # PyPI (uv tool / pipx)
PIN_SKILLS="skills@1.9.0"                       # npm, runs Grill Me's fetch
PIN_RTK_URL="https://raw.githubusercontent.com/rtk-ai/rtk/85239c4db239567bdd5fd29dbe6880103552095f/install.sh"
PIN_RTK_SHA="85ae798116fa0dda42a627333b36903b71291785c7395ad3634f8419f7adaeb5"
PIN_BREW_URL="https://raw.githubusercontent.com/Homebrew/install/eaa2af62ca1d5349c9743f82b1b0c4e5d365fb2d/install.sh"
PIN_BREW_SHA="8fd2f1a5287a7c2e3d7362924c677edcc04c5a0e16448c77132d056bc88cf1ed"
# Anthropic does not version this script, so its hash can go stale: a mismatch stops the install and says so.
PIN_CLAUDE_URL="https://claude.ai/install.sh"
PIN_CLAUDE_SHA="2c5506d110560bf618bbe88f678f2c2a0047c86a9c6585fc84976120b1de0b44"
