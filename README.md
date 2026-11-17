# claude-setup-kit

A guided, one-command setup that makes Claude Code cheaper to run and easier to work with, on macOS and Windows.

It installs a set of free, open-source tools that cut the tokens Claude spends, give it memory across chats, send work to cheaper models when that is safe, and stop it from permanently deleting your files. The installer explains every tool in plain words, lets you tick the ones you want, asks before each change, and installs anything your computer is missing first (with your OK).

- **Free core.** The core tier needs no accounts and no API keys.
- **Nothing hidden.** Every change is listed and asked for first. Your own files are backed up or kept, never overwritten.
- **Safe to re-run.** A second run changes nothing that is already in place.
- **Checks itself.** `doctor.sh` / `doctor.ps1` tests every installed piece and tells you what is left for you to do.

## Quick start

**macOS**
```bash
git clone https://github.com/<you>/claude-setup-kit.git
cd claude-setup-kit
./install.sh
```

**Windows** (PowerShell)
```powershell
git clone https://github.com/<you>/claude-setup-kit.git
cd claude-setup-kit
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

You need the Claude app (or a Claude Code plan) and an internet connection. Everything else the installer can install for you.

## What happens when you run it, step by step

1. **It asks first about the tools that need an API key or an account** (Supermemory, Jev, mjudge, Deliberation), in one checkbox list, so no key comes as a surprise later. Each says which key it needs and what it costs. Supermemory starts ticked; the others start unticked.
2. **Then it explains the other groups** ("tiers"): core, memory, model routing, plan checks. For every tool you see what it does, how it helps you, what it needs, and its licence.
3. **You tick what you want.** Each group shows a checkbox list:
   ```
     [x] 1. Caveman
     [x] 2. i-have-adhd
     [ ] 3. Ponytail
     Type numbers to tick/untick (e.g. 1 3), a = all, n = none, Enter = done:
   ```
   Core starts ticked (recommended for everyone), and remember in memory; the rest start unticked.
4. **It asks about anything that depends on something else.** Example: "Auto index hooks only works together with CodeGraph. Add CodeGraph as well?" Saying no leaves out the tool that needed it.
5. **It asks before each kind of change, and says why:**
   - writing the rules file `~/.claude/CLAUDE.md` (it tells Claude when to use each tool). If you already have one, yours is kept and the kit's version is saved next to it as `CLAUDE.md.kit-new`;
   - adding the kit's hooks to `~/.claude/settings.json` (backed up first; nothing in it is removed or changed);
   - how often you want the token report: weekly, fortnightly, monthly or off.
6. **It shows the full list and asks "Go ahead?"** Nothing has changed up to this point. Saying no stops cleanly.
7. **It checks your computer for what the tools need** and offers to install anything missing, one at a time, with a plain explanation:

   | Missing | Why it is needed | How it is installed (macOS / Windows) |
   |---|---|---|
   | Apple Command Line Tools / Python 3 + Git | every kit script uses python3 and git | `xcode-select --install` / `winget` |
   | Homebrew (macOS only) | the standard Mac installer, used for Node.js and uv | brew.sh's official script (asks for your Mac password) |
   | Claude Code command-line tool | lets the installer add plugins | `claude.ai/install.sh` / `install.ps1` |
   | Node.js | runs context-mode and CodeGraph, fetches Grill Me | `brew install node` / `winget` |
   | uv | installs Graphify in its own space | `brew install uv` / `winget` |

   Say no to any of them and the installer stops, prints the exact command, and changes nothing of the kit.
8. **It installs.** Third-party tools come from their own official sources (Claude Code plugin marketplaces, npm, PyPI, Homebrew/winget); this repo bundles none of them. The kit's own small scripts go to `~/.local/bin` and `~/.claude/hooks`.
8. **It prints a short numbered to-do list** of the things only you can do: restart Claude, run the doctor, sign in or add keys for the tools you picked, fill four placeholders in `CLAUDE.md`.

## After the install

1. Quit and reopen the Claude app (or start a new `claude` session), so the new plugins and hooks load.
2. Run `./doctor.sh` (Windows: `.\doctor.ps1`). Aim for `0 fail`. A `WARN` is a step still waiting on you, usually a key.
3. Work through the to-do list. Keys are never typed into Claude's chat: each one says exactly where it goes (see [.env.example](.env.example)).
4. Open `~/.claude/CLAUDE.md` and fill in the four `{{...}}` placeholders: your name, city and time zone, how Claude should address you, and your English variant.

What you will notice in your next chat:
- replies are shorter and start with the next action (Caveman, i-have-adhd);
- long command output is condensed (RTK, context-mode);
- in any git project with 10+ source files, a code map builds in the background (CodeGraph, Graphify);
- `rm` is blocked; deleted files go to `~/_trash/<project>/<date>/` instead;
- on the 1st of each month at 09:00, a token report appears (see below).

## Let Claude install it for you

Inside Claude the installer has no keyboard to answer questions, so it picks the tiers from the command line. Open this folder in Claude Code and paste:

```
Install the claude-setup-kit in this folder.
1. Read README.md and .env.example.
2. Run ./install.sh --tiers core,memory,routing --install-missing  (on Windows: .\install.ps1 -Tiers core,memory,routing -InstallMissing).
   Anything that needs my password or a window click (Apple tools, Homebrew): tell me the exact command and wait for me.
3. Run the doctor script and fix every FAIL, re-running it until there are none.
4. Walk me through the to-do list one item at a time. Never ask me to paste an API key into this chat.
5. Remind me to restart the Claude app at the end.
Never delete files, never print a secret.
```

Pick the tiers you want; `--list` prints every tool.

## Options

| macOS | Windows | What it does |
|---|---|---|
| `--yes` | `-Yes` | No questions: core tier only |
| `--tiers core,memory` | `-Tiers core,memory` | No questions: these tiers (`core guard memory routing judge deliberation`) |
| `--only rtk,caveman` | `-Only rtk,caveman` | Just these tools |
| `--skip graphify` | `-Skip graphify` | Leave tools out (and anything that needs them) |
| `--install-missing` | `-InstallMissing` | Install missing prerequisites without asking |
| `--caveman-mode lite` | `-CavemanMode lite` | Caveman strength: lite, full, ultra |
| `--handoff 500k` | macOS only | Model pilot: when to offer a fresh chat (`auto`, `250k`, `500k`, `750k`, `never`) |
| `--report week` | `-Report week` | Token report: `week`, `fortnight`, `month` (default) or `off` |
| `--list` | `-List` | Print the catalogue and exit |

## What you can install

| Tier | Tool | In plain words | Needs |
|---|---|---|---|
| core | Caveman | Short, clipped replies; code and errors stay exact | — |
| core | i-have-adhd | Next action first, then short numbered steps | — |
| core | Ponytail | Smallest change that fully fixes the problem | — |
| core | context-mode | Big command output is handled off to the side; only the answer comes back | Node.js |
| core | RTK | Shortens every terminal command's output, keeps the facts | Homebrew / winget |
| core | CodeGraph | A map of your code: where things are, what calls what | Node.js |
| core | Graphify | A plain-language overview of a project and its docs | uv |
| core | Safe delete | Blocks `rm`; files go to `~/_trash/` instead | — |
| core | Auto index hooks | Keeps the CodeGraph/Graphify maps fresh in the background (git repos, and folders that already have an index). Also "index first": in an indexed repo a code search with Grep is held until CodeGraph has been asked once that session (released after 2 reminders, so it never traps), Read and Glob get a one-time hint, and architecture questions get pointed at the Graphify report. Decisions log to `~/.claude/cache/index-first.jsonl` | — |
| core | Token measuring | A record of every turn's tokens, a 30-day baseline, and a weekly, fortnightly or monthly report | — |
| core | Rules file + guides | Tells Claude when to use each tool you installed | 4 placeholders |
| guard | Deny rules | Claude can never read `.env`, `~/.ssh`, `~/.aws`, or run `git reset --hard`, `git clean` or a force push, in any permission mode | — |
| guard | Bash sandbox (macOS, Linux) | Claude Code's own sandbox: shell commands write only inside the project. Off unless ticked | macOS, Linux, WSL2 |
| guard | Done checks | After each edit runs the project's `.claude/lint`; before finishing runs `.claude/verify` (your tests). A failure sends Claude back to fix it | A `.claude/verify` per project |
| memory | Supermemory | Remembers decisions across chats | Supermemory account |
| memory | Cognee (local) | Private knowledge map of your chats, on your computer; Claude and Codex can share it | Your Claude plan (no key) or an LLM API key (paid per use); Python 3.10+ |
| memory | remember | Session diary with a summary at start | — |
| routing | Routing card + lean agents | Cheapest model that can do each task; small helper agents | — |
| routing | Model pilot (macOS only) | Before each prompt, picks the cheapest model and effort that will do the job; shows what really ran | Recent Claude Code; Jev optional |
| routing | Model badge (macOS only) | A label with the model name beside each helper agent's row | Recent Claude Code |
| judge | Jev | Fast yes/no triage over long lists | TypeSafe key (paid) |
| judge | mjudge | Yes/no/score over images, video, audio, PDFs | Gemini key (free tier) |
| deliberation | Deliberation | Other AI models (GPT, Gemini, Grok, OpenRouter) judge a plan: a second opinion or a debate | One provider account |
| deliberation | Grill Me | `/grill-me`: Claude questions you about your own plan, one hard question at a time; `/grill-with-docs` also records decisions | Node.js |

Each tool has one job, and the rules file gives each one a trigger, so they do not compete:

- **RTK and context-mode** both trim command output. RTK shortens every command automatically; context-mode takes the big outputs and analysis off to the side.
- **CodeGraph and Graphify** both map a project. CodeGraph answers "where is this function, what calls it"; Graphify answers "how does this project fit together".
- **Grill Me and Deliberation** both test a plan. Grill Me questions you about your project; Deliberation asks other models to judge the plan. Use Grill Me first, then Deliberation for one-way, high-stakes calls.
- **Routing card and Model pilot** both deal with models. With Model pilot on, it alone picks the chat's model and offers the fresh chat; the routing card keeps only the rules for helper agents. Without Model pilot, the card's own rules apply (fresh chat around 250k tokens).
- **Supermemory, Cognee and remember** are memory with different jobs: Supermemory for decisions and preferences across chats and devices; Cognee for a local knowledge map that Codex can share; remember for picking up where the last session left off. agentmemory was dropped: Supermemory already does its job.

The token report lists any installed tool with no sign of use in its period, so you can drop what you do not use.

Every key, where it goes, and what still works without it: [.env.example](.env.example).

## Safety rules and done checks

The rule behind this group: **can it be taken back?** Code edits can (git), so Claude does them freely. Leaked secrets, wiped work and force-pushed history can't, so they become deny rules. Claude Code applies deny rules in every permission mode, auto and bypass included.

- **Deny rules** are added to `permissions.deny` in `~/.claude/settings.json`; your own rules are kept. Add more there yourself (for example `"Read(./secrets/**)"`). Only the Bash and file tools are covered: on Windows the PowerShell tool is not.
- **Outgoing data** (messages, uploads) is better left to auto mode, which checks each action, than to a fixed rule list.
- **Bash sandbox:** off unless you tick it. Some installers and tools that write outside the project will ask or fail inside it; `/sandbox` changes it any time.
- **Done checks** do nothing until a project opts in. Add an executable `.claude/verify` to a project, for example:

  ```sh
  #!/bin/sh
  npm test --silent
  ```

  Keep its output quiet: the last 40 lines of a failure go back to Claude, which tries up to three times before stopping. `.claude/lint` (optional) gets the edited file's path after each edit. On Windows use `verify.cmd` or `verify.ps1`.
- **Bigger jobs** are safer in a cloud session (Claude Code on the web): a fresh copy of the repo, nothing on your computer at risk.

### For teams: managed settings

An admin can set defaults for everyone in `managed-settings.json` (see Claude Code's [settings docs](https://code.claude.com/docs/en/settings)): `model` (the default), `availableModels` (which models people may pick), `effortLevel` and `maxEffortLevel`, and `permissions.deny`. Anthropic's "Maximizing Value from Claude Code" webinar calls changing a team default away from the biggest model the highest-leverage cost fix.

## Model pilot

Anthropic's own guidance on picking a model and effort, digested from 14 sources and two videos: [docs/model-choice-guide.md](docs/model-choice-guide.md).

A mod for Claude Code on macOS, written for this kit (MIT, in [`mods/model-pilot`](mods/model-pilot/README.md)). Before each prompt a small, fast judge decides which model tier (Haiku, Sonnet, Opus, Fable) and effort the task needs, and Claude Code runs the turn on that. A row above the prompt shows the pick and the model that actually ran, read from the session transcript. Your own choice always wins: name a model in the prompt, or pick one in the menu, and the pilot leaves it alone.

- **Judges, in order:** Jev if you have it (about half a second), then Haiku (about two seconds), then built-in rules. Without Jev you lose nothing but speed. Privacy mode uses the rules only.
- **Measured on 124 labelled prompts:** it picked a model that was too weak in 1.6% of cases with Jev and 2.4% with Haiku. Full tables are in the mod's README.
- **Where a job is cheapest to run.** Doing it in the chat you are in has no start-up cost, but every step re-reads the whole chat. A helper agent loads its own context once: about 14k tokens for the kit's lean agents (`haiku-lean`, `sonnet-lean`), about 72k for an all-tools agent. A new session loads about 120k. So a few lookups are cheaper in place, and a big, tool-heavy job is cheaper in a lean helper. The pilot says so when it matters, and `/pilot cost` shows the figures for the chat you are in. These sizes were measured on the author's setup; yours will differ.
- **Fresh chat offer.** At a chat size you choose (the installer asks: auto, 250k, 500k, 750k or never) it offers to write a summary so you can continue in a new chat. It only offers.
- **Only one model selector at a time.** If another one is on, the installer asks before switching it off.

## What it changes on your computer

- **Third-party tools** come from their own sources: Claude Code plugin marketplaces, npm, PyPI (via uv), Homebrew or winget. Nothing third-party is bundled in this repo.
- **The kit's own scripts** go to `~/.local/bin` and `~/.claude/hooks`. A differing file is backed up to `*.bak-kit-<time>` first.
- **Your own docs are never overwritten.** If `CLAUDE.md`, a guide or an agent already exists and differs, the kit's version lands next to it as `*.kit-new`.
- **`~/.claude/settings.json` is merged, never replaced.** Backed up to `settings.json.bak-kit-<time>` first. Only missing hooks and env keys are added.
- **Token report**: a launchd agent (`~/Library/LaunchAgents/com.claude-setup-kit.token-report.plist`) or a Windows scheduled task (`claude-setup-kit token-report`) that checks daily at 09:00 and writes a report when your chosen period ends; nothing is scheduled if you chose off. A Stop hook (`token-ledger.py`) adds one line per finished turn to `~/.claude/cache/token-compare/ledger.jsonl`.
- **A record** of what was installed in `~/.claude/kit/installed`; the doctor checks exactly that list.

To undo a change: restore the `*.bak-kit-<time>` copy next to the file, remove the plugin with `claude plugin uninstall <name>`, and delete the launchd agent or scheduled task.

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

**Token report.** Three parts work together, all local, none of them using Claude tokens:

1. **Baseline, at install.** The installer reads your Claude Code history for the 30 days before the install, freezes it, and shows it (sessions, requests, tokens, tokens a day). Every report compares against it.
2. **A record of every turn.** A Stop hook (`token-ledger.py`, runs in the background, never blocks) writes one line per finished turn: requests, tokens read as context, output tokens, the model family, and what was saved in that turn: RTK's own count for that turn's shell commands (measured), the bytes context-mode kept out of context in that session (measured, turned into tokens at 4 bytes per token), and Model pilot's saving against the menu model (an estimate). A tool that is not installed shows as missing, never as 0.
3. **The report**, weekly (Monday to Sunday), fortnightly or monthly, as you chose at install; change it any time with `python3 ~/.claude/hooks/token-report.py --set week|fortnight|month|off`. To see the last prompts one by one (used and saved per turn): `python3 ~/.claude/hooks/token-report.py --turns 20`. A job checks daily at 09:00 and writes `~/.claude/cache/token-compare/reports/<period>-<first day>.md` once a period has finished, so a Mac that was asleep catches up; on macOS a notification says it is ready. It shows tokens used, tokens saved and what you would have used without the kit. Saved has two parts, kept apart: **measured** (RTK's own count of shell output it cut; a floor) and **estimated** (how much smaller sessions start than in your 30-day baseline, per session type, times the period's requests). Then the per-turn record: turns, tokens used, tokens a turn, and the savings in those turns. Five more tools get one line each, from `token-tools.py`, with measured and estimated kept in separate columns and none of it added to the totals (RTK and context-mode both trim shell output, so adding them would count some of it twice). **Caveman**: output tokens its own log attributes to a Caveman mode; no saving is claimed, because the log has no without-Caveman comparison. **context-mode**: bytes it kept out of context, from its own records (measured), with a token estimate beside it at 4 bytes per token. **CodeGraph** and **Graphify**: calls found in your transcripts and the size of what they returned; no saving is estimated, because nothing records what the searches and file reads they replaced would have cost. **model-pilot**: the number of model decisions in its own log and its estimated saving against the menu model, an estimate (the turn's real tokens repriced, minus the judge calls). A last line lists installed on-demand tools (context-mode, CodeGraph, Graphify, RTK, Model pilot, Model badge, Jev, mjudge, Deliberation, Grill Me) with no tool call, command or log line that month. Tools that run by hook every session are not judged. Run it by hand: `python3 ~/.claude/hooks/token-report.py --period week 2026-11-09`, or `--period month 2026-11`.

## What it costs to run

| Tier | Cost |
|---|---|
| core | Free. Needs a Claude Code plan as usual |
| memory | Supermemory: account required (pricing not checked by this kit). Cognee: with no key it runs through the `claude` command on your Claude plan and counts towards its usage limits; with an `LLM_API_KEY` in `~/.cognee/.env` every saved turn is billed per use on that account (set a monthly spend limit in the provider console). remember: free |
| routing | Routing card and agents: free. Model pilot: one small judge call per judged prompt, on your Claude plan with Haiku (a fraction of a cent) or on your TypeSafe account with Jev |
| judge | TypeSafe: paid account (pricing not checked). Gemini: free tier available; free-tier inputs may be used for training |
| deliberation | Each second opinion uses that provider's tokens or plan (ChatGPT/Codex, Gemini, xAI, OpenRouter) |

Every hook also adds a little latency. The Jev shadow hooks are async and fail open. `jev-gate` is the exception: it runs before every Skill call, synchronously, with a 20 s timeout, and adds one verdict line to context.

## Known limits

- **Tested on macOS only.** The Windows installer (`install.ps1`) has not been run on Windows yet. Linux is not supported: `install.sh` stops unless `KIT_ALLOW_NON_MAC=1` is set (untested).
- **The model router saved nothing on a small job** (see Measured numbers). Routing pays off only when large, tool-heavy work goes to lean helpers.
- **Trim savings are unmeasured until 23 Nov 2026.**
- **Model pilot is macOS only and adds a short wait.** A judged prompt waits for the judge before its first token: about half a second with Jev, about two seconds with Haiku. Follow-ups and prompts where you chose the model are not judged. Its savings are estimates, and only one model selector can be on at a time. Accuracy, method and limits: [`mods/model-pilot/README.md`](mods/model-pilot/README.md).
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
| remember | `anthropics/claude-plugins-official` | Community licence |
| Deliberation | `antonbabenko/agent-plugins` | MIT |
| Grill Me (`grill-me`, `grilling`, `grill-with-docs`) | `mattpocock/skills`, fetched with `npx skills` | MIT |
| Model pilot, Model badge | this repo, `mods/` | MIT |

## Files

```
install.sh        macOS installer (guided; idempotent)
install.ps1       Windows installer (same flow and options)
doctor.sh         macOS check of what was installed; --quick skips the MCP check
doctor.ps1        Windows check; -Quick skips the MCP check
scan.sh           secret / personal-data scan over what git would publish
mods/             Model pilot and Model badge: Claude Code mods, with their tests (and the pilot's evaluation sets)
pack-private.sh   no longer used by the installers
.env.example      every key, where it goes, what works without it
lib/              tool catalogue, hook fragments, settings merger
files/            the kit's own scripts, hooks, agents, guides and CLAUDE.md template
```

## Contributing

Run `./scan.sh` before every commit. Before publishing a fork, also run `./scan.sh --also "<your name>" --also "<your email>"`. Test installs only in a throw-away home folder: `env -i HOME=$(mktemp -d) PATH=/usr/bin:/bin:/opt/homebrew/bin KIT_RTK_METHOD=script ./install.sh --yes`.
