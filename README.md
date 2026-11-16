# claude-setup-kit

A one-command install of a tuned Claude Code setup for macOS and Windows. It covers token savers, memory, model routing, judge tools and second opinions. The installer explains what each tool does and how it helps, then shows a checkbox list per tier: type the numbers to tick or untick, Enter to go on. You only type things that truly need you: API keys and sign-ins.

```bash
git clone <this repo> claude-setup-kit && cd claude-setup-kit
./install.sh          # explains each tool, then a checkbox list per tier
./doctor.sh           # checks the install
```

Non-interactive: `./install.sh --yes` installs the core tier only (no keys, no paid services). `--tiers core,memory,routing,judge,deliberation` picks tiers, `--only rtk,caveman` to pick single tools, and `--list` to see everything.

### Windows

Needs Git for Windows (the kit's hooks run in Git Bash), Python 3 on PATH, and Node.js for the core tier. `install.ps1` checks all of these first and changes nothing if one is missing.

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1      # explains each tool, asks per tier
.\doctor.ps1
```

Same options as on macOS: `-Yes`, `-Tiers core,memory`, `-Only rtk,caveman`, `-Skip graphify`, `-List`.

**Windows status: written and reviewed on a Mac, not yet run on Windows.** Differences from macOS:
- RTK comes from `winget` (`rtk-ai.rtk`), not Homebrew.
- The Jev key is a user environment variable (`TYPESAFE_API_KEY`); there is no Keychain lookup.
- `mjudge` cannot resize images (that needs macOS `sips`), so the Jev second opinion on PNG/JPG is skipped; Gemini still answers.
- The `rm` blocker covers Claude's Bash tool only, not its PowerShell tool.
- `token-daily.py --notify` sends no desktop notification.

## What you can install

| Tier | Tool | What it does | Needs |
|---|---|---|---|
| core | Caveman | Short, compressed replies; code and errors stay exact | — |
| core | i-have-adhd | Replies start with the next action and use short numbered steps | — |
| core | Ponytail | Smallest complete code change; reuse before writing | — |
| core | context-mode | Big command output is processed in a sandbox; only the answer enters context | Node.js |
| core | RTK | Hook that condenses the output of every shell command | Homebrew or curl |
| core | CodeGraph | Symbol graph of a repo: code, callers, blast radius in one call | Node.js |
| core | Graphify | Knowledge graph and plain-language report of a repo and its docs | uv or pipx |
| core | Safe delete | Blocks `rm` in Claude's shell; `trashmv` files things into `~/_trash/` instead | — |
| core | Auto index hooks | Builds and refreshes CodeGraph and Graphify indexes in the background | — |
| core | Token measuring scripts | Reads your local transcripts: scorecard, daily report, before/after comparison, and a monthly report (used, saved, would-have-used) that runs by itself on the 1st | — |
| core | CLAUDE.md + guides | Rules that tell Claude when to use each installed tool | 4 placeholders to fill |
| memory | Supermemory | Cross-session recall and save | Supermemory account |
| memory | Cognee (local) | Local knowledge graph of your conversations | LLM API key, paid per use |
| memory | agentmemory | Local memory server for agent sessions | You start its server |
| memory | remember | Rolling session history | — |
| routing | Routing card + lean agents | Cheapest model and effort per task; small-context helper agents | — |
| routing | Model Selector pack | Optional: model pick per prompt, sub-agent routing | Your private copy (see below) or a zip from Ben AI |
| judge | Jev (`jev`, `jev-gate`, shadow hooks) | Fast external yes/no triage over many items | TypeSafe key (paid) |
| judge | mjudge | Yes/no/score over images, video, audio, PDFs | Gemini key (free tier exists) |
| deliberation | Deliberation | Second opinions and consensus from GPT, Gemini, Grok, OpenRouter | One provider sign-in or key |

Every key, where it goes, and what still works without it: [.env.example](.env.example).

## What install.sh changes

- **Third-party tools** come from their own sources: Claude Code plugin marketplaces (`claude plugin marketplace add` + `claude plugin install`), npm (`@colbymchenry/codegraph`), uv/pipx (`graphifyy`), Homebrew or the upstream script (`rtk`). This repo bundles none of them.
- **This kit's own scripts** go to `~/.local/bin` and `~/.claude/hooks`. A differing file is backed up to `*.bak-kit-<time>` first.
- **Your own docs are never overwritten.** If `~/.claude/CLAUDE.md`, a guide or an agent already exists and differs, the kit's version lands next to it as `*.kit-new` for you to merge.
- **`~/.claude/settings.json` is merged, never replaced.** A hook is added only if no hook with the same command exists. An env key is added only if it is missing. The file is backed up to `settings.json.bak-kit-<time>` before the first change.
- It records what was installed in `~/.claude/kit/installed`; `doctor.sh` checks exactly that list.
- Re-running is safe: a second run reports `unchanged` / `already installed` and changes nothing.

At the end it prints a numbered list of what is still yours to do (keys, sign-ins, restart, placeholders).

## Measured numbers (from the author's setup, not a guarantee for yours)

All from the author's own Mac on 2026-11-15. One machine, small samples.

| What | Before | After | Note |
|---|---|---|---|
| First request of a fresh `claude -p` session (Haiku, same prompt) | 70,728 tokens | 69,136 tokens | −1,592 after removing redundant skills, agents and commands; one run each |
| `/context` total | 40.7k | 39.5k | Same trim |
| Skill-list entries | 763 | 651 | Same trim; 86 skills got their descriptions back |
| Helper agent start-up cost: all-tools agent vs `haiku-lean` | ~72k | ~14k | Why the kit ships lean agents |
| Delegating a small 3-lookup job to a cheaper model vs doing it in place | ≈ same | ≈ same | **No saving.** The main chat's own context dominates. Savings come from big tool-heavy helper jobs |

**Not measured:**
- Per-tool savings for RTK, context-mode, Caveman, CodeGraph or Graphify in isolation. They are included because they cut output size by design, not because each one was benchmarked.
- The effect of the 15 Nov 2026 trim on real weekly usage. The before/after comparison (`token-compare.py`) has no after-week data until 23 Nov 2026.
- The connector-list saving in the desktop app (an **estimate** of about 3k tokens per session).

Measure your own: `python3 ~/.claude/hooks/token-scorecard.py 30`, and `python3 ~/.claude/hooks/token-compare.py` a week after installing.

**Monthly report.** `token-monthly.py` runs at 09:00 on the 1st (launchd on macOS, Task Scheduler on Windows; no Claude tokens) and writes `~/.claude/cache/token-compare/monthly/YYYY-MM.md`; on macOS it also shows a notification. It reports tokens used, tokens saved and what you would have used without the kit. Saved has two parts, kept apart: **measured** (RTK's own count of shell output it cut; a floor) and **estimated** (how much smaller sessions start since install, per session type, times the month's requests). Four more tools get one line each, from `token-tools.py`, with measured and estimated kept in separate columns and none of it added to the totals (RTK and context-mode both trim shell output, so adding them would count some of it twice). **Caveman**: output tokens its own log attributes to a Caveman mode; no saving is claimed, because the log has no without-Caveman comparison. **context-mode**: bytes it kept out of context, from its own records (measured), with a token estimate beside it at 4 bytes per token. **CodeGraph** and **Graphify**: calls found in your transcripts and the size of what they returned; no saving is estimated, because nothing records what the searches and file reads they replaced would have cost. Run it by hand: `python3 ~/.claude/hooks/token-monthly.py 2026-12`.

## What it costs to run

| Tier | Cost |
|---|---|
| core | Free. Needs a Claude Code plan as usual |
| memory | Supermemory: account required (pricing not checked by this kit). Cognee: every saved turn is sent to the LLM in `~/.cognee/.env` and billed per use on that account. Set a monthly spend limit in the provider console. agentmemory, remember: free |
| routing | Free |
| judge | TypeSafe: paid account (pricing not checked). Gemini: free tier available; free-tier inputs may be used for training |
| deliberation | Each second opinion uses that provider's tokens or plan (ChatGPT/Codex, Gemini, xAI, OpenRouter) |

Every hook also adds a little latency. The Jev shadow hooks are async and fail open. `jev-gate` is the exception: it runs before every Skill call, synchronously, with a 20 s timeout, and adds one verdict line to context.

## Known limits

- **Tested on macOS only.** The Windows installer (`install.ps1`) has not been run on Windows yet; see the Windows section. Linux is not supported: `install.sh` stops unless `KIT_ALLOW_NON_MAC=1` is set (untested).
- **The model router saved nothing on a small job** (see Measured numbers). Routing pays off only when large, tool-heavy work goes to lean helpers.
- **Trim savings are unmeasured until 23 Nov 2026.**
- **Model Selector pack is not in the public repo.** It is Ben AI's and carries no licence, so it cannot be redistributed. For your own machines, `./pack-private.sh` packs the copy you run (with your changes) into `private/` (gitignored, skipped by `scan.sh`) and builds `../claude-setup-kit-private.zip`; the installers use `private/claude-model-selector.zip` automatically. Never publish that zip. Otherwise pass `--model-selector-zip PATH`. Its own install notes say Mac; on Windows it is untested.
- **Jev shadow hooks only log.** They write to `~/.claude/jev/decisions.jsonl` and never block or inject. `jev-gate` (before Skill calls) does add a verdict line and can delay a Skill call by up to 20 s.
- **RTK's hook gets rtk's full path** at install time, because Claude Code's hook PATH may not include `~/.local/bin` or Homebrew. If you move rtk, re-run `install.sh`. Other tools (`trashmv`, `jev`, `codegraph`, `graphify`) live in `~/.local/bin`, which must be on your PATH.
- **Index hooks skip small repos.** They only index git repos with 10 or more source files, and never your home folder.
- **Licences of the installed tools differ.** context-mode is Elastic-2.0, so it cannot be offered as a managed service. RTK's default build includes a BUSL-1.1 engine, free for your own use; `RTK_EDITION=oss` gives the Apache-2.0-only build. remember uses a community licence with no commercial redistribution. The rest are MIT or Apache-2.0.

## Licences

This repo: MIT ([LICENSE](LICENSE)). Installed from their own sources:

| Tool | Source | Licence |
|---|---|---|
| Caveman | `JuliusBrussee/caveman` | Apache-2.0 |
| i-have-adhd | `ayghri/i-have-adhd` | MIT |
| Ponytail | `DietrichGebert/ponytail` | MIT |
| context-mode | `mksglu/context-mode` | Elastic-2.0 |
| RTK | `rtk-ai/rtk` | Apache-2.0 + BUSL-1.1 (engine) |
| CodeGraph | npm `@colbymchenry/codegraph` | MIT |
| Graphify | PyPI `graphifyy` (`Graphify-Labs/graphify`) | Apache-2.0 |
| Supermemory plugin | `supermemoryai/claude-supermemory` | MIT (per plugin manifest) |
| Cognee plugin | `topoteretes/cognee-integrations` | Apache-2.0 |
| agentmemory | `rohitg00/agentmemory` | Apache-2.0 |
| remember | `anthropics/claude-plugins-official` | Community licence |
| Deliberation | `antonbabenko/agent-plugins` | MIT |

## Files

```
install.sh        macOS installer (tiers, per-tool choice, idempotent)
doctor.sh         macOS check of what install.sh recorded; --quick skips the MCP check
install.ps1       Windows installer (same tiers and options)
doctor.ps1        Windows check; -Quick skips the MCP check
scan.sh           secret / personal-data scan; run before every commit
pack-private.sh   packs your own Model Selector copy into private/ (never published)
.env.example      every key, where it goes, what works without it
lib/              catalogue, hook fragments, settings merger
files/            this kit's own scripts, hooks, agents, guides and CLAUDE.md template
```

Before you publish a fork, run `./scan.sh --also "<your name>" --also "<your email>"`.
