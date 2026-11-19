# claude-setup-kit

A guided, one-command setup that makes Claude Code cheaper to run and easier to work with, on macOS.

It installs a set of free, open-source tools that cut the tokens Claude spends, give it memory across chats, send work to cheaper models when that is safe, and stop it from permanently deleting your files. The installer explains every tool in plain words, lets you tick the ones you want, asks before each change, and installs anything your computer is missing first (with your OK).

- **Free core.** The core tier needs no accounts and no API keys.
- **Nothing hidden.** Every change is listed and asked for first. Your own files are backed up or kept, never overwritten.
- **Safe to re-run.** A second run changes nothing that is already in place.
- **Checks itself.** `doctor.sh` tests every installed piece and tells you what is left for you to do.

## Quick start

```bash
git clone https://github.com/prabeshbhetwal/claude-setup-kit.git
cd claude-setup-kit
./install.sh
```


You need the Claude app (or a Claude Code plan) and an internet connection. Everything else the installer can install for you.

## What happens when you run it, step by step

1. **It asks first about the tools that need an API key or an account** (Supermemory, Jev, mjudge, Deliberation), in one checkbox list, so no key comes as a surprise later. Each says which key it needs and what it costs. Supermemory starts ticked; the others start unticked.
2. **Then it explains the other groups** ("tiers"): core, safety rules and checks (guard), memory, model routing, plan checks, extras. (The judge tools need keys, so they are in the first group.) For every tool you see what it does, how it helps you, what it needs, and its licence.
3. **You tick what you want.** Each group shows a checkbox list:
   ```
     [x] 1. Caveman
     [x] 2. i-have-adhd
     [ ] 3. Ponytail
     Type numbers to tick/untick (e.g. 1 3), a = all, n = none, Enter = done:
   ```
   Core starts ticked (recommended for everyone), plus remember in memory and the two safety tools in the guard group (deny rules and done checks); the rest start unticked.
4. **It asks about anything that depends on something else.** Example: "Auto index hooks only works together with CodeGraph. Add CodeGraph as well?" Saying no leaves out the tool that needed it.
5. **It asks before each kind of change, and says why:**
   - writing the rules file `~/.claude/CLAUDE.md` (it tells Claude when to use each tool). If you already have one, yours is kept and the kit's version is saved next to it as `CLAUDE.md.kit-new`;
   - adding the kit's hooks to `~/.claude/settings.json` (it first shows you the exact lines that would change, with secret-looking values hidden; backed up first; nothing of yours in it is removed; missing hooks, env keys and deny rules are added, and an older, shorter time limit on a kit hook is raised);
   - how often you want the token report: weekly, fortnightly, monthly or off.
6. **It shows the full list and asks "Go ahead?"** Nothing has changed up to this point. Saying no stops cleanly.
7. **It checks your computer for what the tools need** and offers to install anything missing, one at a time, with a plain explanation:

   | Missing | Why it is needed | How it is installed |
   |---|---|---|
   | Apple Command Line Tools (Python 3 + Git) | every kit script uses python3 and git | `xcode-select --install` |
   | Homebrew | the standard Mac installer, used for Node.js and uv | brew.sh's official script (asks for your Mac password) |
   | Claude Code command-line tool | lets the installer add plugins | `claude.ai/install.sh` |
   | Node.js | runs context-mode and CodeGraph, fetches Grill Me | `brew install node` |
   | uv | installs Graphify in its own space | `brew install uv` |

   Say no to any of them and the installer stops, prints the exact command, and changes nothing of the kit.
8. **It installs.** Third-party tools come from their own official sources (Claude Code plugin marketplaces, npm, PyPI, Homebrew); this repo bundles none of them. The kit's own small scripts go to `~/.local/bin` and `~/.claude/hooks`.
9. **It prints a short numbered to-do list** of the things only you can do: restart Claude, run the doctor, sign in or add keys for the tools you picked, fill four placeholders in `CLAUDE.md`.

## After the install

1. Quit and reopen the Claude app (or start a new `claude` session), so the new plugins and hooks load.
2. Run `./doctor.sh` . Aim for `0 fail`. A `WARN` is a step still waiting on you, usually a key.
3. Work through the to-do list. Keys are never typed into Claude's chat: each one says exactly where it goes (see [.env.example](.env.example)).
4. Open `~/.claude/CLAUDE.md` and fill in the four `{{...}}` placeholders: your name, city and time zone, how Claude should address you, and your English variant.

What you will notice in your next chat:
- replies are shorter and start with the next action (Caveman, i-have-adhd);
- long command output is condensed (RTK, context-mode);
- in any git project with 10+ source files, a code map builds in the background (CodeGraph, Graphify);
- `rm` is blocked; deleted files go to `~/_trash/<project>/<date>/` instead;
- a token report appears on the schedule you chose (monthly on the 1st by default, at 09:00), and a setup scorecard every Monday (see below).

## Let Claude install it for you

Inside Claude the installer has no keyboard to answer questions, so it picks the tiers from the command line. Open this folder in Claude Code and paste:

```
Install the claude-setup-kit in this folder.
1. Read README.md and .env.example.
2. Run ./install.sh --tiers core,memory,routing --skip supermemory,cognee.
   Anything that needs my password or a window click (Apple tools, Homebrew): tell me the exact command and wait for me.
3. Run the doctor script and fix every FAIL, re-running it until there are none.
4. Walk me through the to-do list one item at a time. Never ask me to paste an API key into this chat.
5. Remind me to restart the Claude app at the end.
Never delete files, never print a secret.
```

Pick the tiers you want; `--list` prints every tool.

## Options

| Option | What it does |
|---|---|
| `--yes` | No questions: core tier only |
| `--tiers core,memory` | No questions: every tool in these tiers (`core guard memory routing judge deliberation extras`). `memory` includes Supermemory (needs an account) and Cognee (uses your plan's limits or an API key): add `--skip supermemory,cognee` to leave them out |
| `--only rtk,caveman` | Just these tools |
| `--skip graphify` | Leave tools out (and anything that needs them) |
| `--install-missing` | Install missing prerequisites without asking |
| `--title-recheck 5`, `--title-spelling au` | Session titles: prompts between title checks (default 5), spelling `au` (default), `us` or `none` |
| `--caveman-mode lite` | Caveman strength: lite, full (default), ultra (fragments only) |
| `--uninstall session-title` | Take Dynamic session titles out again: its hook entries, script and settings file |
| `--jev-share pilot,recall,mine,code` | Which parts may send text to TypeSafe through Jev (default: none): `pilot` Model pilot, `recall` and `mine` house rules, `code` the CodeGraph gate. See [What leaves your Mac](#what-leaves-your-mac) |
| `--jev-hooks yes` | Add Jev's background hooks, `jev-gate` included (default no; `no` on a later run takes them out) |
| `--confirm-fable no` | Model pilot: `yes` (default) asks before the pilot runs a prompt on Fable and shows the cost against Opus; `no` lets it run without asking |
| `--handoff 500k` | Model pilot: when to offer a fresh chat (`auto`, `250k`, `500k`, `750k`, `never`) |
| `--report week` | Token report: `week`, `fortnight`, `month` (default) or `off` |
| `--list` | Print the catalogue and exit |

## What you can install

| Tier | Tool | In plain words | Needs |
|---|---|---|---|
| core | Caveman | Short, clipped replies; code and errors stay exact | Nothing |
| core | i-have-adhd | Next action first, then short numbered steps | Nothing |
| core | Ponytail | Smallest change that fully fixes the problem | Nothing |
| core | context-mode | Big command output is handled off to the side; only the answer comes back | Node.js |
| core | RTK | Shortens every terminal command's output, keeps the facts | Homebrew, or its own install script |
| core | CodeGraph | A map of your code: where things are, what calls what | Node.js |
| core | Graphify | A plain-language overview of a project and its docs | uv |
| core | Safe delete | Blocks `rm` and `rmdir` (also behind `sudo`, `time`, `nice`, `bash -c`); files go to `~/_trash/` instead. `find -delete`, `unlink` and `rsync --delete` are not caught. Also raises every plugin's hook time limit to 15 s (backs up each file it changes) | Nothing |
| core | Auto index hooks | Keeps the CodeGraph/Graphify maps fresh in the background, and makes Claude ask CodeGraph first: a code search with Grep is turned back until CodeGraph has been asked once (twice at most per session). Adds the index folders to each repo's `.git/info/exclude` | Nothing |
| core | Token measuring | A record of every turn's tokens, a 30-day baseline, and a weekly, fortnightly or monthly report. Also the Monday scorecard and house rules: a hook on every prompt, and Monday mining of your chats (on your Mac unless you let Jev help) | Nothing |
| core | Rules file + guides | Tells Claude when to use each tool you installed | 4 placeholders |
| guard | Deny rules | Claude's file tools may not read `.env` files, `*.pem` keys, `~/.ssh`, `~/.aws`, `~/.gnupg`, `~/.netrc`; `git reset --hard`, `git clean`, force pushes, `git checkout -- .`, `git restore .`, `git stash clear` and reading Keychain passwords are refused, in any permission mode. `.env.example` stays readable (an allow rule is added for it). Best effort: the rules match how a command is written, so a differently written one can get past them, and a shell command like `cat .env` is only stopped with the Bash sandbox on too | Nothing |
| guard | Bash sandbox | Claude Code's own sandbox: shell commands write only inside the project. Off unless ticked | macOS |
| guard | Done checks | After each edit runs the project's `.claude/lint`; before finishing runs `.claude/verify` (your tests). A failure sends Claude back to fix it. Runs only in projects you allow: `python3 ~/.claude/hooks/verify-done.py allow` in the project folder | A `.claude/verify` per project |
| memory | Supermemory | Remembers decisions across chats | Supermemory account |
| memory | Cognee (local) | Private knowledge map of your chats, on your computer; Claude and Codex can share it | Your Claude plan (no key) or an LLM API key (paid per use); Python 3.10+ |
| memory | remember | Session diary with a summary at start | Nothing |
| routing | Routing card + lean agents | Cheapest model that can do each task; small helper agents | Nothing |
| routing | Model pilot (macOS only) | Before each prompt, picks the cheapest model and effort that will do the job; shows what really ran | Recent Claude Code; Jev optional |
| routing | Model badge (macOS only) | A label with the model name beside each helper agent's row | Recent Claude Code |
| judge | Jev | Fast yes/no triage over long lists. What it may send is asked separately: see [What leaves your Mac](#what-leaves-your-mac) | TypeSafe key (paid) |
| judge | mjudge | Yes/no/score over images, video, audio, PDFs | Gemini key (free tier) and Jev (paid) |
| extras | Dynamic session titles | Keeps each chat's title a short label of what you are doing now (1 to 4 words) and renames it as the work moves on. Spelling: Australian (default), American or none. Never changes a title you typed without asking you | The Claude desktop app |
| deliberation | Deliberation | Other AI models (GPT, Gemini, Grok, OpenRouter) judge a plan: a second opinion or a debate | One provider account |
| deliberation | Grill Me | `/grill-me`: Claude questions you about your own plan, one hard question at a time; `/grill-with-docs` also records decisions | Node.js |

Each tool has one job, and the rules file gives each one a trigger, so they do not compete:

- **RTK and context-mode** both trim command output. RTK shortens every command automatically; context-mode takes the big outputs and analysis off to the side.
- **CodeGraph and Graphify** both map a project. CodeGraph answers "where is this function, what calls it"; Graphify answers "how does this project fit together".
- **Grill Me and Deliberation** both test a plan. Grill Me questions you about your project; Deliberation asks other models to judge the plan. Use Grill Me first, then Deliberation for one-way, high-stakes calls.
- **Routing card and Model pilot** both deal with models. With Model pilot on, it alone picks the chat's model and offers the fresh chat; the routing card keeps only the rules for helper agents. Without Model pilot, the card's own rule applies: move to a fresh chat when the turns still to come would cost more in a big chat than a summary costs (under about 150k tokens stay; at 250k if more than about 14 turns remain, at 430k if more than about 5; always before about 900k).
- **Supermemory, Cognee and remember** are memory with different jobs: Supermemory for decisions and preferences across chats and devices; Cognee for a local knowledge map that Codex can share; remember for picking up where the last session left off.

The token report lists any installed tool with no sign of use in its period, so you can drop what you do not use.

Every key, where it goes, and what still works without it: [.env.example](.env.example).

## Safety rules and done checks

The rule behind this group: **can it be taken back?** Code edits can (git), so Claude does them freely. Leaked secrets, wiped work and force-pushed history can't, so they become deny rules. Claude Code applies deny rules in every permission mode, auto and bypass included.

- **Deny rules** are added to `permissions.deny` in `~/.claude/settings.json`; your own rules are kept. Add more there yourself (for example `"Read(./secrets/**)"`). The rules name the real env files (`.env`, `.env.local`, `.env.production` and the like), so `.env.example` stays readable. If you added a broader `Read(.env.*)` rule yourself, it also blocks `.env.example`: remove it if you want that file readable. The command rules are best effort: they match the shape of a command (`git clean`, `git push --force`), so the same act written another way (other flags, a script, another tool) is not caught. Treat them as a seat belt, and use the Bash sandbox and backups for real protection.
- **Hook time limits:** each session start raises every plugin hook to at least 15 s, so busy machines don't skip them ("A hook didn't answer in time").
- **Bash sandbox:** off unless you tick it. Some installers and tools that write outside the project will ask or fail inside it; `/sandbox` changes it any time.
- **Done checks** do nothing until a project opts in. Add an executable `.claude/verify` to a project, for example:

  ```sh
  #!/bin/sh
  npm test --silent
  ```

  Keep its output quiet: the last 40 lines of a failure go back to Claude, which tries up to three times before stopping. `.claude/lint` (optional) gets the edited file's path after each edit.
- **Bigger jobs** are safer in a cloud session (Claude Code on the web): a fresh copy of the repo, nothing on your computer at risk.

### For teams: managed settings

An admin can set defaults for everyone in `managed-settings.json` (see Claude Code's [settings docs](https://code.claude.com/docs/en/settings)): `model` (the default), `availableModels` (which models people may pick), `effortLevel` and `maxEffortLevel`, and `permissions.deny`.

## Model pilot

A mod for Claude Code on macOS, in [`mods/model-pilot`](mods/model-pilot/README.md). Before each prompt a small, fast judge decides which model (Haiku, Sonnet, Opus, Fable) and effort the task needs, and Claude Code runs the turn on that. A row above the prompt shows the pick and the model that actually ran. Your own choice always wins: name a model in the prompt, or pick one in the menu, and the pilot leaves it alone.

- **Judges, in order:** Jev if you have it and allowed it (off by default; the plugin option `jev`), then Haiku, then built-in rules. Privacy mode uses the rules only.
- **Fresh chat offer.** At a chat size you choose (the installer asks: auto, 250k, 500k, 750k or never) it offers to write a summary so you can continue in a new chat. It only offers.
- **Only one model selector at a time.** If another one is on, the installer asks before switching it off. With no one to ask (`--yes`, `--tiers`), it leaves Model pilot out instead.
- **Accuracy, cost and limits:** [`mods/model-pilot/README.md`](mods/model-pilot/README.md).

## What it changes on your computer

- **Third-party tools** come from their own sources: Claude Code plugin marketplaces, npm, PyPI (via uv), or Homebrew. Nothing third-party is bundled in this repo.
- **The kit's own scripts** go to `~/.local/bin` and `~/.claude/hooks`. A differing file is backed up to `*.bak-kit-<time>` first.
- **Your own docs are never overwritten.** If `CLAUDE.md`, a guide or an agent already exists and differs, the kit's version lands next to it as `*.kit-new`.
- **`~/.claude/settings.json` is merged, never replaced.** Backed up to `settings.json.bak-kit-<time>` first; nothing of yours in it is removed; missing hooks, env keys and deny rules are added, and an older, shorter time limit on a kit hook is raised. Model pilot's choices go under `pluginConfigs`, written so that a symlinked `settings.json` stays a symlink and keeps its permissions.
- **Token report**: a launchd agent (`~/Library/LaunchAgents/com.claude-setup-kit.token-report.plist`) that checks daily at 09:00 and writes a report when your chosen period ends. With off it still runs daily and does nothing, so `token-report.py --set month` turns it back on. A Stop hook (`token-ledger.py`) adds one line per finished turn to `~/.claude/cache/token-compare/ledger.jsonl`.
- **Weekly scorecard**: a second launchd agent (`~/Library/LaunchAgents/com.claude-setup-kit.setup-monitor.plist`) that runs Mondays at 08:15, whatever you chose for the token report, and writes to `~/.claude/monitor/`.
- **Session titles** (only if ticked): `~/.claude/hooks/session-title.py`, its settings in `~/.claude/kit/session-title.json`, and two hook entries in `settings.json`; per-chat notes go in `~/.claude/cache/session-title/`.
- **A record** of what was installed in `~/.claude/kit/installed`; the doctor checks exactly that list.

### Undoing it

There is no one-step uninstall yet (only `--uninstall session-title`). Take out what you want, piece by piece:

- **Settings and files:** restore the `*.bak-kit-<time>` copy next to the file. A `settings.json` backup is a snapshot: restoring it also drops anything you or other tools changed since, so compare the two first and remove only the kit's lines if in doubt.
- **Plugins:** `claude plugin uninstall <name>`. For Model pilot and Model badge, then `claude plugin marketplace remove claude-setup-kit` and move `~/.claude/local-marketplaces/claude-setup-kit` to the bin.
- **Plugin hook time limits:** the rm blocker's start-up hook raised them and kept each plugin's original file once, as `<file>.bak-kit` beside it. Take that hook out of `settings.json` first (or it raises them again), then copy each `.bak-kit` back. A plugin update also replaces them.
- **Scheduled jobs:** `launchctl bootout gui/$(id -u)/com.claude-setup-kit.token-report`, the same with `.setup-monitor`, then remove the two plists in `~/Library/LaunchAgents`.
- **CodeGraph:** `claude mcp remove codegraph -s user`, then `npm uninstall -g --prefix ~/.local @colbymchenry/codegraph`.
- **Graphify:** `uv tool uninstall graphifyy`, or `pipx uninstall graphifyy` if the installer used pipx (it says which), and the skill folder `~/.claude/skills/graphify`.
- **RTK:** `brew uninstall rtk`, or remove `~/.local/bin/rtk` if its own install script put it there.
- **Kit scripts:** `trashmv`, `jev`, `jev-gate` and `mjudge` in `~/.local/bin`; the kit's hooks in `~/.claude/hooks`; agents, guides and rules in `~/.claude/agents`, `~/.claude/guides` and `~/.claude/rules`; the weekly scorecard and house rules in `~/.claude/monitor` and `~/.claude/house-rules`; Jev's policy and log in `~/.claude/jev`; the TypeSafe key with `security delete-generic-password -s typesafe-api-key`.
- **Small settings:** Caveman's mode in `~/.config/caveman/config.json`; the i-have-adhd always-on flag `~/.claude/.i-have-adhd-always`; Grill Me's skills in `~/.claude/skills/` (`grill-me`, `grilling`, `grill-with-docs`).
- **The record:** delete the line for each removed tool from `~/.claude/kit/installed` so the doctor stops checking it.

Everything Claude "deleted" sits in `~/_trash/<project>/<date>/`; it is never emptied for you, so look there now and then and remove old date folders yourself.

## Token report

The installer records your last 30 days of Claude Code use as a baseline, then a hook writes one line per finished turn: tokens used and tokens saved. A report arrives weekly, fortnightly or monthly (your choice at install; off is allowed), and a macOS notification says when it is ready. Everything runs locally and uses no Claude tokens.

- Change the period: `python3 ~/.claude/hooks/token-report.py --set week|fortnight|month|off`
- See the last prompts one by one: `python3 ~/.claude/hooks/token-report.py --turns 20`
- Your own numbers over 30 days: `python3 ~/.claude/hooks/token-scorecard.py 30`

How it counts, and what is measured versus estimated: [docs/token-report.md](docs/token-report.md). The author's own numbers: [docs/measurements.md](docs/measurements.md).

## Checking the kit

`python3 lib/audit.py` checks that what this README promises is what the scripts do (flags, tiers, hooks, links, what runs first, an install into an empty home folder, a second run that must change nothing). It touches nothing of yours. The checks, and how to review a change by hand, are in [docs/checking-changes.md](docs/checking-changes.md).

## Why a new chat starts with tokens already used

See [docs/context-overhead.md](docs/context-overhead.md): what each row of `/context` is, and which changes actually shrink it.

## Weekly setup scorecard and house rules

Every Monday at 08:15 a job scores the last week of your setup (cost per turn, start-up load, corrections, tool errors, hook health) against your own 4-week median and writes a short report to `~/.claude/monitor/reports/`. It runs whatever you chose for the token report, including off. It also proposes **house rules** from your own words in past chats, for example "never make UI look AI-generated". Nothing becomes a rule until you approve it:

```
python3 ~/.claude/monitor/bin/house-rules.py review
python3 ~/.claude/monitor/bin/house-rules.py approve <id>
```

Approved rules come back only when they fit the prompt, and are silent otherwise: a small hook (`house-rules-recall.py`) checks every prompt for that. The Monday mining reads your local chat logs on your Mac; it and the recall hook send text to TypeSafe only if you said yes to them under Jev (see [What leaves your Mac](#what-leaves-your-mac)).

## What it costs to run

| Tier | Cost |
|---|---|
| core | Free. Needs a Claude Code plan as usual |
| memory | Supermemory: account required (pricing not checked by this kit). Cognee: with no key it runs through the `claude` command on your Claude plan and counts towards its usage limits; with an `LLM_API_KEY` in `~/.cognee/.env` every saved turn is billed per use on that account (set a monthly spend limit in the provider console). remember: free |
| routing | Routing card and agents: free. Model pilot: one small judge call per judged prompt, on your Claude plan with Haiku (a fraction of a cent) or on your TypeSafe account with Jev |
| judge | TypeSafe: paid account (pricing not checked). Gemini: free tier available; free-tier inputs may be used for training |
| extras | Session titles: free; about 150 tokens every fifth prompt (set by `--title-recheck`) |
| deliberation | Each second opinion uses that provider's tokens or plan (ChatGPT/Codex, Gemini, xAI, OpenRouter) |

## What leaves your Mac

Claude Code itself sends your chats to Anthropic, as it always does. On top of that, the tools below send text off your Mac, and only if you ticked them. Apart from Model pilot, mjudge and the Jev rows, the kit's own scripts work on your Mac only. Plugins by other authors are listed as far as this kit knows; their own docs are the final word.

| Tool | Sends | To |
|---|---|---|
| Supermemory | Memories it saves from your chats, and your prompts as search queries for its recall. This is the plugin's own behaviour; see its docs | Supermemory |
| Cognee | The chat text it captures (your prompts and Claude's answers), so a model can build the knowledge map. The map itself stays on your Mac | Anthropic through the `claude` command on your Claude plan, or the provider of the `LLM_API_KEY` in `~/.cognee/.env` |
| Deliberation | The question or plan you ask about | The AI providers you set up (OpenAI, Google, xAI, OpenRouter) |
| mjudge | The media files you ask about; PNG and JPG files also go to TypeSafe through Jev | Google Gemini, and TypeSafe |
| Model pilot | Each prompt and a digest of recent turns, to pick a model: to Haiku on your Claude plan; to TypeSafe only if you answered yes to "Model pilot" under Jev (`--jev-share pilot`) | Anthropic, or TypeSafe |
| Jev, Claude's own triage | Whatever Claude pipes into `jev` under the rules file: log lines, search results, diffs, file lists or file text | TypeSafe |
| Jev, CodeGraph gate | The first 3,000 characters of a prompt that looks like a code question, to confirm it is one. Only if you said yes (`--jev-share code`) | TypeSafe |
| Jev, house rules recall | The first 200 characters of a prompt (emails, links, paths removed) when a saved rule might fit. Only if you said yes (`--jev-share recall`) | TypeSafe |
| Jev, house rules mining | On Mondays, last week's sentences where you corrected Claude (redacted). Only if you said yes (`--jev-share mine`) | TypeSafe |
| Jev background hooks | Shell commands, up to 300 lines of large tool output with your last prompt, email sender, subject and snippet, helper agents' reports, and (through `jev-gate`, when a skill with "review" in its name runs) up to 60,000 characters of the current diff plus the last commit message. Only if you said yes (`--jev-hooks yes`) | TypeSafe |

Every Jev use other than Claude's own triage is off until you say yes. Saying no on a later run takes the background hooks out again, and they also check your answer each time they run. Jev never sends text that looks like a password or key. To keep a folder out, add it to `skip_paths` in `~/.claude/jev/policy.json`: `jev` itself checks it against the folder it is run in (the session folder for hooks and plugins; the image's real folder for mjudge), so it covers Claude's triage, mjudge's Jev step and every hook. Text piped in from another folder is not checked, so run triage from inside the project it concerns. If `policy.json` is missing or damaged, every optional Jev use stays off; `enabled: false` there turns Jev off everywhere. Model pilot has its own privacy switch and private-folders list in its settings. Jev's local log (`~/.claude/jev/decisions.jsonl`) keeps short previews of what it judged and is capped at about 5 MB.

The TypeSafe key lives in the macOS Keychain. For a stricter setup, create the item with no trusted apps, so macOS asks you before anything reads it: `security add-generic-password -s typesafe-api-key -a "$USER" -T '' -w` (it prompts for the key). macOS then asks when Jev reads it: Allow asks again next time, Always Allow lets that reader in silently from then on.

## Known limits

- **Hooks run on every prompt and command.** Depending on what you tick, the kit starts up to four small hooks on each prompt (the CodeGraph gate, the index check, house rules recall, session titles) and up to three before each shell command (RTK, the rm blocker, the index check). With Jev's background hooks on, add one more before each shell command and one after it and other tool calls. Plugins (Supermemory, Caveman, Cognee and others) run hooks of their own on top. Each takes a fraction of a second; the total has not been measured on other machines.
- **No keyboard, no choice.** Run without a terminal (for example by Claude) and with no options, the installer stops and asks for `--yes`, `--tiers` or `--only` instead of guessing.

- **Tested on macOS only.** Windows and Linux are not supported: `install.sh` stops unless `KIT_ALLOW_NON_MAC=1` is set (untested).
- **Model pilot is macOS only and adds a short wait.** A judged prompt waits for the judge before its first token. Follow-ups and prompts where you chose the model are not judged. Its savings are estimates.
- **Session titles need the Claude desktop app.** They call the app's session-title tool, so the hook runs only when Claude Code reports the desktop app (`CLAUDE_CODE_ENTRYPOINT=claude-desktop`) and stays silent in the command line, headless runs and the SDK. If you decline a rename of a title you typed, your title is kept and the hook stops asking about it. The spelling check catches common patterns only (`-ize`, `color`, `behavior` and similar), and whether a title fits the work is only prompted, not checked. Settings live in `~/.claude/kit/session-title.json`; to remove the tool run `./install.sh --uninstall session-title` (it shows the change to `settings.json` first, backs it up, takes out only the kit's two hook entries and moves the script and its settings file aside; running it again changes nothing).
- **Index hooks skip small repos.** They only build indexes for git repos with 10 or more source files, and never for your home folder.
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

## Contributing

Run `./scan.sh` before every commit. Before publishing a fork, also run `./scan.sh --also "<your name>" --also "<your email>"`. Test installs only in a throw-away home folder, for example `env -i HOME=$(mktemp -d) PATH=/usr/bin:/bin:/opt/homebrew/bin ./install.sh --only safety`. Tools that install plugins (most of the core tier, so `--yes` too) also need the `claude` command on that `PATH`: add the folder it lives in (`dirname "$(command -v claude)"`), or the installer stops and lists it as missing.
