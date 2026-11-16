# Live tests

Real Claude Code sessions, driven turn by turn, checked against what the engine itself recorded. They spend real money (the 16 November 2026 round cost about $25 in all).

| File | What it does |
|---|---|
| `drive.py` | Runs one session from a list of prompts (`{"text": ...}` per line) and saves, per turn, the engine's result and cost, every API request from the transcript, and the pilot's log lines |
| `check.py` | Passes a run when every main-thread request ran the picked model and effort, and every sub-agent ran the pick or the model its caller named |
| `ab.py` | Side by side: each task in `tasks.json` in a fresh copy of a small project, with the pilot off and on, judged by hidden tests or an expected answer |
| `results/` | The 16 November 2026 round, without prompts, replies or paths |

The engine path defaults to the desktop app's bundled engine; pass `--engine` for another (for example the `claude` CLI).

## Rerun

```bash
python3 -m venv /tmp/mp-venv && /tmp/mp-venv/bin/pip install pytest
```

```bash
python3 mods/model-pilot/eval/live/ab.py --out /tmp/mp-ab --venv /tmp/mp-venv
```

```bash
python3 mods/model-pilot/eval/live/drive.py --name t1 --turns turns.jsonl --out /tmp/mp-live --plugin mods/model-pilot --cwd /path/to/a/scratch/repo
```

```bash
python3 mods/model-pilot/eval/live/check.py /tmp/mp-live/t1.json
```

To test beside your own setup while another model selector is installed, switch that one off for the test process only, with `--settings '{"enabledPlugins":{"<its plugin>@<its marketplace>":false}}'`; the debug log then says it "will NOT register". Never run two selectors at once: both would rewrite the same requests.

## Round of 16 November 2026 (engine 2.1.325)

| Test | Setup | Result |
|---|---|---|
| A/B, 12 tasks | Settings left out (both arms alike), Fable in the menu | Off: 12/12, $2.79, 234 s. Pilot: 12/12, $0.53, 234 s (after fixes; $0.81 before) |
| Switching, 10 turns | The author's full setup, other selector off for the process | 10/10 turns and 2/2 sub-agents ran as decided |
| Judge failures | Bad Jev key; bad key plus a judge model that does not exist | Haiku decided; then the rules: lookup on Haiku, the coding task kept on Fable |
| Long session, 36 turns | Context grown past 250K tokens by reading files | 36/36, 0 errors |
| Fresh-chat offer | `handoff: 250k` | Offered at 279K, 328K, 377K, 427K, 475K, 524K (once per 50K band); none acted on |
| Cost | Logged `cost_usd` against the engine's `total_cost_usd` | 0.1% apart over 12 runs |

## What the round found and fixed

1. **Prices.** The engine billed Haiku 5.5 at its long-prompt rate (prompts over 100K tokens pay 5x; Claude Code prompts start around 118K) and charged 1-hour cache writes at 2x input. The table had the short-prompt rate and 1.25x. Fixed, with a unit test built from a live bill.
2. **Switching sums.** With true prices, cache reads cost about the same on Sonnet, Opus and Fable, so moving a long, warm chat down rarely pays. The decision now stays put there, and the logged saving counts the cache re-write a switch causes.
3. **Slow Jev.** Jev had up to 2.5 s before Haiku was asked, so a slow Jev left the turn to the rules. Haiku now joins after 1.2 s and the first answer wins.
4. **Log.** Each turn line now carries `cost_usd`, `context_tokens` and `handoff_offer_tokens`.

## Spec check

| Spec item | Evidence |
|---|---|
| Per-prompt pick by a small model, rules fallback, never under-pick, unsure goes up | Eval sets (`../results/`); unit tests; live failure runs |
| Your choice wins: menu, or a model named in the prompt; on/off switch | Live: "use opus", `/model`, `/pilot auto`; in the app, a menu change logged as "model set in the menu" |
| Indicator shows picked and what ran; effort marked "requested" | Seen in the app (shadow row); `actual` read from the transcript in every log line |
| Sub-agents routed; a named model never overridden | Live: unnamed agent ran the pick; named agent kept Opus |
| Fresh-chat offer only, threshold yours | Live offer test; installer question and `--handoff` tested in a temporary HOME |
| Privacy switch: rules only | Live (earlier round) and unit tests |
| Log and estimated cost; monthly report line | Log checked against the engine's bill; `token-tools.py` self-test |
| Never writes settings.json; never changes model mid-turn | One decision per turn, applied to every request of it (live: one model per turn throughout); the mod has no settings write |
| Jev, then Haiku, then rules; per-judge numbers | Live failure runs; eval tables in the mod README |

Not covered: Windows (the mod is macOS only); comparison with the selector it replaces (kept clean-room: its code was not read or run); very long real-world use (weeks), which shadow mode in daily work would show.
