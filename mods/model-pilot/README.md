# model-pilot

A mod for Claude Code (the Claude desktop app's Code tab, and the CLI) on macOS. For each prompt it picks the cheapest Claude model and effort that will do the job reliably, shows what actually ran, and logs an estimated saving. MIT, written from scratch for this kit.

## What it does

1. **Judges each prompt.** When you submit a prompt, a judge reads it with a short digest of the last few turns and the context size, and answers with a tier (`haiku`, `sonnet`, `opus`, `fable`), an effort, a confidence and a one-line reason. Judges are tried in order: **Jev** (TypeSafe) when the kit's `jev` command and a TypeSafe key are on this Mac, then **Haiku** through Claude Code itself, then built-in rules. Without Jev nothing is missing and nothing nags: Haiku judges. The log records which judge decided.
2. **Decides.** Unsure (confidence under 0.6) means one tier up. A short "yes, do it" inherits the tier of the work it continues. The pick is then weighed against the prompt cache: moving a long conversation to another model rewrites its cache there, so the pilot stays on a warm, more capable model when that is cheaper, and never goes below the tier the task needs.
3. **Applies it for the whole turn.** Every model request of the turn carries the same model and effort. Nothing changes mid-turn, and your `settings.json` is never written.
4. **Shows the truth.** A row above the prompt reads `pilot: sonnet · effort medium (requested) → ran claude-sonnet-5-5`. "Ran" is `message.model` of the turn's last reply, read from the session transcript. If the pick and what ran differ, the row says so in the warning colour. Effort is labelled "requested" because the API does not report it back.
5. **Routes sub-agents** that name no model: `general-purpose`, and your own or the project's agent files with no `model:` line. An agent whose call or definition names a model is never touched; plugin agents and built-in special agents are left alone because their definitions cannot be read.
6. **Offers a fresh chat** at a context size you choose (`auto`, `250k`, `500k`, `750k`, `never`): a button that asks Claude to write `HANDOFF.md` so a new chat can continue. A long chat costs more at every step, because all of it is re-read, and early details are tracked less well; a summary is cheaper and sharper but loses what it leaves out. `auto` is 500k on a 1M-token window and 250k on a smaller one. An offer only.
7. **Says where a job is cheapest.** When a lean sub-agent would clearly cost less than running the job in the chat you are in, or when a sub-agent was spawned for a job too small to pay for its start-up, the row above the prompt says so with the estimate. `/pilot cost` prints the comparison for the current chat.
8. **Logs every decision** to `~/.claude/mods-logs/model-pilot.jsonl` (no prompt text: only its length) with the estimated cost difference against the menu model.

## Sub-agent, in place, or a new session

| Where | Fixed start-up | What each step re-reads |
|---|---|---|
| In place, in the chat you are in | none | the whole chat |
| Lean sub-agent (`haiku-lean`, `sonnet-lean`) | about 14k tokens | its own small context; your chat pays two steps, for the hand-off and the report |
| All-tools sub-agent (`general-purpose` and the like) | about 72k tokens | its own context; your chat pays the same two steps |
| New session | about 120k tokens | its own context |

Rule of thumb, as measured: a small job (a few lookups) is cheaper in place, and a big, tool-heavy job is cheaper in a lean sub-agent. The start-up sizes were measured on the author's setup, with many plugins and tools loaded; a lighter setup loads less. They are constants in `hooks/policy.ts`, and every cost figure built on them is an estimate.

## Your choice wins

- Name a model or effort in the prompt (`use opus for this`, `with haiku`, `effort high`) and that turn uses it.
- Pick a model or effort in the app's menu and the pilot leaves that choice alone until you run `/pilot auto` (or press `auto` on the row).
- `/pilot off` and `/pilot on` switch it for good; `/pilot status` shows where things stand.

## When the judge is slow or off

The judge starts as the prompt is submitted and the first model request waits for it for at most the judge budget (default 2.5 s; a session's first prompt gets up to 1.5 s more). If Jev cannot answer, or has not answered within 1.2 s, Haiku is asked as well and the first answer wins (Haiku is only paid for when Jev is slow or down). If no judge answers in time, built-in rules decide, and they are not trusted to go low: they may pick Haiku for a plain short lookup, and otherwise never go below the menu's model.

Privacy mode switches off both Jev and Haiku: rules only, with the same floor. With Jev on, the prompt text and the digest of recent turns go to TypeSafe; with Haiku they go to Anthropic, as the prompt itself does. The `jev` command holds the TypeSafe key; the mod never reads it.

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `enabled` | on | Master switch |
| `privacy` | off | Never send prompt text to the judge; rules only |
| `privateFolders` | empty | Comma-separated folders where privacy mode is always on |
| `allowUpgrade` | on | Let a hard task run above the menu's model |
| `subagents` | on | Route sub-agents that name no model |
| `confirmFable` | on | When the pilot (not you) picks Fable, ask first: why, the effort and why it is enough, and the cost against Opus. Buttons: run on Fable, Fable for this chat, use Opus. No answer runs on Opus |
| `handoff` | `auto` | When to offer a fresh chat: `auto`, `250k`, `500k`, `750k`, `never` |
| `jev` | on | Use Jev as the first judge when its command and key are present |
| `judgeBudgetMs` | 2500 | Longest wait for the judge at the first request of a turn |
| `judgeModel` | `haiku` | The model for the Haiku step |
| `shadow` | off | Judge and log but change nothing: a trial run |
| `band` | on | The row above the prompt |

## Model or effort

Effort changes how much a model thinks and writes per request; the model sets the price of every token, including the conversation it re-reads each step. Mean output tokens per main-thread request, from 440 transcripts on the author's machine (October to November 2026; thinking included):

| Tier | low | medium | high | xhigh |
|---|---|---|---|---|
| Haiku 5.5 | 160 | 330 | ~500 (estimate) | ~700 (estimate) |
| Sonnet 5.5 | 200 | 890 | ~1,050 (estimate) | ~1,250 (estimate) |
| Opus 5.5 | 650 | 680 | 810 | 900 |
| Fable 5.2 | 520 | 940 | 1,220 | 2,350 |

These are observed, not controlled: harder tasks get higher effort, so each step up is an upper bound on what effort alone adds. With Claude Code's prompts of 100k tokens and more, re-reading the chat costs more than the output: a Sonnet request at 120k tokens of cache reads is about $0.012 of input and $0.01 of output at xhigh, an Opus request about $0.024 of input before any output. So Sonnet at high effort still costs less per request than Opus at low; it costs more only when it needs more steps or a retry, which this table cannot show. Haiku's prompts over 100k tokens pay its long-prompt rate, so Haiku at high effort (about $0.007 a request) costs about half of Sonnet at low (about $0.014), not a tenth: Haiku saves money only when it needs no more steps than Sonnet would.

Effort changes keep the prompt cache: in 89 cases in the same transcripts where the effort changed between two requests on the same model, the second request still read the whole conversation from the cache (median ratio 1.0, against 1.0 when the effort stayed). So the pilot can change effort per turn freely; only a model change is weighed against the cache.

Following Anthropic's model and effort guidance, the pilot also: asks Haiku for medium at least (at low it skips searches on long prompts); never runs Haiku past 100k prompt tokens; never lowers a job into low effort when it stays on a stronger model (Opus at low lost 34 points to medium on defect search); never picks max; and leaves `opusplan` alone.

What the pilot does with this: it prices each candidate model at its own effort, and when it stays on a stronger model whose cache is warm (cheaper than switching down), it asks for one effort level less than the task was judged to need. An effort you set yourself is never lowered.

## Measured (November 2026, Claude Code 2.1.325)

Two labelled sets in `eval/`: `prompts.jsonl` (81 cases, used while writing the rubric) and `holdout.jsonl` (43 cases, written after the rubric was last changed). "Under" means a tier below the label, the error that matters. Run them yourself with `/pilot eval <file.jsonl>` and one of ` --jev`, ` --haiku`, ` --rules` (none: the chain); results are in `eval/results/`.

| Judge | Set | Exact | Under | Over | Latency p50 / p95 |
|---|---|---|---|---|---|
| Jev | prompts (81) | 98.8% | 0% | 1.2% | 0.4 s / 0.7 s |
| Jev | holdout (43) | 95.3% | 4.7% | 0% | 0.5 s / 1.1 s |
| Jev | both (124) | 97.6% | 1.6% (2 cases; 95% upper bound 5.0%) | 0.8% | |
| Haiku 5.5 | prompts (81) | 97.5% | 1.2% | 1.2% | 2.2 s / 3.4 s |
| Haiku 5.5 | holdout (43) | 95.3% | 4.7% | 0% | 2.0 s / 2.9 s |
| Haiku 5.5 | both (124) | 96.8% | 2.4% (3 cases; 95% upper bound 6.1%) | 0.8% | |
| Haiku 4.5 (`judgeModel: claude-haiku-4-5`) | both (124) | 91.9% | 7.3% | 0.8% | 1.1 s / 1.3 s |
| Rules alone, unfloored | both (124) | 68.5% | 14.5% | 16.9% | none |

Jev's two under-picks were hard tasks sent to Sonnet instead of Opus; Haiku's three were light edits or drafting sent to Haiku instead of Sonnet. Jev matched the labelled effort less often (81% against 98% for Haiku). The rules alone are weak at spotting hard work, which is why a rules verdict is floored at the menu's model in use. The sets are small: read the upper bounds, not just the rates.

## Measured live (November 2026)

Real Claude Code sessions driven by `eval/live/drive.py`, checked against the session transcript (which model and effort each API request used) and the engine's own cost figure. Scripts and how to rerun them: [eval/live/README.md](eval/live/README.md).

| Test | Result |
|---|---|
| Side by side: 12 coding and lookup tasks, hidden tests, Fable in the menu | Pilot 12/12 passed for $0.53; Fable alone 12/12 for $2.79 (81% less) |
| Switching under a full personal setup (many plugins and hooks): lookup, edit, follow-up, "use opus", design, sub-agents, `/model`, `/pilot auto` | 10/10 turns ran the picked model and effort; a sub-agent with no model ran the pick, one whose caller named a model kept it |
| Judge failures: bad Jev key; Jev and Haiku both down | Haiku took over; then the rules, never below the menu's model for real work |
| 36-turn session, context past 250K tokens | 36/36 turns correct, no errors |
| Fresh-chat offer at `250k` | Offered at 279K, then once per further 50K; never acted on its own |
| Logged cost against the engine's bill, 12 runs | Within 0.1% |
| Judge wait per turn | 0.25 to 1.5 s with Jev |

## Limits

- The judge adds a wait before the first token of a judged prompt: about half a second with Jev, about 2 seconds with Haiku, less whatever time your other prompt hooks take, since it runs beside them. Follow-ups, explicit choices and pinned sessions are not judged.
- Savings are estimates: each request of the turn repriced on the menu's model, with the first request's cache treated as that model's would have been (a cold cache is written afresh), minus the Haiku judge call (Jev is billed by TypeSafe and is not counted). A different model would have written different output. Prices are a table in `hooks/prices.ts`, list prices as of 16 November 2026: Claude Code's 1-hour cache writes cost 2x input, and Haiku 5.5 charges 5x on prompts over 100K tokens, which most Claude Code prompts are.
- Savings come mostly from where a chat starts and from short chats. Cache reads cost about the same on Sonnet, Opus and Fable, so once a long chat is warm on one model, moving it down means re-writing the whole cache, which rarely pays; the pilot weighs this and usually stays put. Lookups on Haiku can take a few seconds longer than on a larger model, because Haiku makes more tool calls.
- A model switch drops the earlier model's reasoning blocks from what the next model reads (the visible text and tool results stay). The cache weighing keeps switches rare in long conversations.
- macOS only: the transcript read and the log append use `/bin/sh` and `tail`.

## Develop

```bash
claude plugin validate mods/model-pilot
```

```bash
claude plugin test mods/model-pilot
```

```bash
claude --plugin-dir mods/model-pilot
```

Set `MODEL_PILOT_LOG=/some/file.jsonl` to send the log elsewhere while testing.
