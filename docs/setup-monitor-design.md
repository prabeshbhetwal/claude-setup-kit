# Setup monitor and house rules: design

Status: v1, 2026-11-17. Review window: 2026-11-17 (baseline) to 2026-12-15 (month review).

## Goal

1. **Scorecard.** Tell, week by week, whether a change to the Claude Code setup lowers cost and keeps or raises quality. Local data only, no Claude tokens.
2. **House rules.** Learn the user's lasting preferences (UI/UX first), store them as reviewable rules, and bring the relevant ones back when a matching task starts. Nothing is applied without the user's approval.

## What already exists (reused, not rebuilt)

| Piece | Reused for |
|---|---|
| `files/hooks/token-scorecard.py`, `token-report.py`, `token-tools.py`, `token-ledger.py` | Usage dedupe by `message.id`, context definition, per-tool savings (RTK, context-mode, model-pilot) |
| `mods/model-pilot/hooks/prices.ts` | Price card (ported to Python, cache write 1.25x 5-min / 2x 1-hour) |
| `~/.claude/hooks/skill-router.py` | BM25 pre-filter + Jev confirm pattern for the recall hook |
| `~/.claude/hooks/jev_lib.py` | `scored()` with policy thresholds, decision log, fail-open log |
| `~/Library/LaunchAgents/com.prabesh.*.plist` | Pattern for the weekly job |

## Part 1: scorecard

### Units

- **Turn**: one real user prompt (not tool results, not task notifications, not `<command-*>` wrappers) and everything until the next one, subagents included.
- **Session**: one main transcript file. **Work session**: a session with at least one Edit/Write/MultiEdit/NotebookEdit.
- **Task** (for cost per task): a work session. Chat-only sessions are reported separately.
- **Cost**: API-equivalent USD from usage and the price card. Plan usage, not money; it is the comparable figure.

### Markers (27)

Each marker has a direction (lower or higher is better) and is computed per ISO week (Mon-Sun, local).

| # | Marker | Definition | Better |
|---|---|---|---|
| T1 | Start-up load, main | median context of first request in main sessions | lower |
| T2 | Start-up load, subagent | median context of first request in subagent runs | lower |
| T3 | Context per turn | median sum of request context per turn | lower |
| T4 | Requests per turn | median assistant requests per turn | lower |
| T5 | Cache re-read share | cache_read / total context | info |
| T6 | Cache misses | mid-session requests with ctx>100k and <10% cached, per 100 turns | lower |
| T7 | Long-context share | share of main requests above 250k context | lower |
| T8 | Compactions | compact boundaries per 100 turns | lower |
| T9 | Hook injection per prompt | median chars of UserPromptSubmit additional context per turn, /4 = tokens | lower |
| T10 | Output per turn | median output tokens per turn | info |
| C1 | Cost per turn | median API-equivalent USD per turn | lower |
| C2 | Cost per work session | median USD per work session (the "task") | lower |
| C3 | Cost per chat session | median USD per non-work session | lower |
| C4 | Weekly total | total USD, and per active day | info |
| C5 | Subagent share | subagent USD / total USD | info |
| C6 | Top-tier share | Opus + Fable USD / total USD | info |
| S1 | RTK saving | `rtk gain` weekly saved tokens and % | higher |
| S2 | context-mode kept out | bytes kept out in the week (its context.db), /4 tokens | higher |
| Q1 | Correction rate | turns whose prompt reads as a correction (no, wrong, redo, undo, revert, not what I asked, still broken...) per 100 turns | lower |
| Q2 | Interrupt rate | `[Request interrupted by user]` per 100 turns | lower |
| Q3 | Tool error rate | tool results with `is_error` per 100 tool calls | lower |
| Q4 | Block rate | tool results blocked by a hook, gate or permission per 100 tool calls | lower |
| Q5 | Test pass rate | Bash calls that run a test runner: share that succeed | higher |
| Q6 | Test retries | test commands failing then re-run in the same session, per work session | lower |
| Q7 | Review findings | findings reported by review tools (ReportFindings) per review | info |
| G1 | Rework rate | user's repos: commits that revert, or touch the same file within 24h of a commit by the same author with a fix/revert/redo message, as share of commits | lower |
| G2 | Reverts | `Revert`/`revert` commits in the week | lower |
| H1 | Hook health | hook timeouts + non-blocking hook errors per 100 sessions; Jev fail-opens in the week | lower |

The weekly report also lists the setup changes logged that week (`changes.jsonl`), so each marker move can be read against a change. A "change" is logged with `setup-monitor note "text"` (sessions and the kit installer call it).

### Judging a change

- Weekly numbers move with workload; the report shows the 4-week median beside the week and flags a marker only when it moves more than 15% past it, in the bad direction, two weeks running.
- Monthly trend: one row per marker, one column per week, Sparkline-free text table, plus change notes between columns. A change "helped" when its cost markers fell and Q1-Q5 did not get worse.
- Limits stated in the report: no randomisation, so this is before/after evidence, not proof; the live A/B harness in `mods/model-pilot/eval/live` remains the tool for causal tests.

### Collector

`files/monitor/setup-monitor.py` (installed to `~/.claude/monitor/`):

- `collect [--weeks N]`: streams transcripts modified in the window, skips weeks already frozen (a week freezes 2 days after it ends), writes `~/.claude/monitor/weeks/<YYYY-Www>.json`.
- `report [--week W]`: writes `~/.claude/monitor/reports/week-<W>.md`.
- `trend`: writes `~/.claude/monitor/reports/trend-<date>.md` over all stored weeks.
- `note "text"`: appends to `changes.jsonl`.
- `selftest`: fixture transcripts, asserts every marker.
- launchd `com.claude-setup-kit.setup-monitor.plist`: Mondays 08:15, runs `collect`, `report`, `trend`, house-rules `mine`, macOS notification with the 3 biggest moves.

## Part 2: house rules

### Store (`~/.claude/house-rules/`, a git repo so every change is versioned)

- `rules.json`: approved rules. Fields: `id`, `rule` (one sentence, at most 30 words), `tags` (ui, layout, colour, type, motion, copy, a11y, code, workflow), `keywords`, `evidence` [{date, session, quote<=200 chars}], `added`, `status` (active/retired).
- `candidates.json`: proposed rules waiting for review, same shape plus `count` (times seen) and `kind` (explicit/correction).
- `recall.jsonl`: one line per injection (time, rule ids, chars), for cost and "never used" markers.
- `RULES.md`: generated, human-readable view of `rules.json`.

### Capture (free, offline, weekly + on demand)

1. Pre-filter user prompts in transcripts: explicit preference phrases (I prefer, I like, I hate, always, never, don't use, stop using, I want it, too busy/too much, remember that) or correction phrases right after an assistant turn that edited UI files (`.tsx .jsx .vue .svelte .css .scss .html .swift`, design tokens) or used design skills.
2. Drop one-off instructions with a Jev check ("Does this message state a lasting preference about how work should look or be done, not a one-off instruction?"), redacted first (emails, URLs, numbers, paths shortened). Jev off → keep regex-only candidates with a lower score. Never sent: anything Jev's credential check refuses, files, code.
3. Cluster near-duplicates (word-set Jaccard >= 0.5) across sessions; `count` = distinct sessions. A candidate is shown when explicit, or when a correction recurs in 2+ sessions.
4. Seed: the existing UI/UX memories and skills the user wrote (`no-vibe-coded`, `blueprint-ui`, `impeccable` overlays) are not copied; rules only come from the user's own words.

### Review (the only way a rule becomes active)

`house-rules review` prints candidates with evidence; `house-rules approve <id> ["rewritten rule"]`, `house-rules reject <id>`, `house-rules retire <id>`. Inside a Claude session the user can say "review house-rule candidates" and Claude runs the same commands. Rejected candidates are kept (status rejected) so they are not proposed again. Approval also prints an `add_memory` line for Supermemory so the rule is findable from claude.ai too.

### Recall (UserPromptSubmit hook `house-rules-recall.py`)

- Only approved, active rules. BM25 over rule text + keywords + tags, plus a UI-intent gate (prompt mentions UI words or the cwd has UI files touched recently). Prompts under 4 words or slash commands: silent.
- If any rule passes BM25, Jev confirms ("Is this rule relevant to the request?", policy `house_rules_min`, default 0.7). Jev down → top 2 by BM25 above a stricter floor.
- Output: at most 4 rules, 600 chars (~150 tokens) hard cap, as `House rules (user-approved, apply if relevant): - rule`. Silent when nothing passes.
- Fails open, 2 s budget, logs to `recall.jsonl`.

### House-rule markers (added to the scorecard)

| # | Marker | Better |
|---|---|---|
| P1 | Recall rate: prompts with a house-rule injection, per 100 | info |
| P2 | House-rule tokens: median chars/4 per injection, and weekly total | lower |
| P3 | Rule use: active rules injected at least once in 4 weeks / active rules | higher |
| P4 | Candidates proposed / approved / rejected in the week | info |
| P5 | Repeat corrections: candidates whose evidence includes a date after the matching rule was approved (rule not working) | lower |

## Cost of the system itself

- Collector and miner: no Claude tokens; Jev calls only on pre-filtered prompts (tens per week).
- Recall hook: 0 tokens on most prompts; at most ~150 tokens when a rule matches; Jev latency only when >2 BM25 hits.
- Measured in the test report: share of real past prompts that trigger, median and max injected tokens, hook latency.

## Plan-reviewer pass (2026-11-17)

Panel: GPT, Gemini, DeepSeek, Grok via deliberation `plan-reviewer`. All four: approve with changes, confidence 75-85%.

| Finding | Action |
|---|---|
| Workload confounds weekly moves; ~15% rule is noise on small samples | Adopted: every cost/token marker also reported per stratum (main work / main chat / subagent); a new W1 workload-mix marker; a marker with fewer than 20 units in a week is shown as "n small" and never flagged |
| Turn parsing under-specified | Adopted: a turn starts at a `user` entry whose content is a typed string or text block, not `isMeta`, not a tool result, not `<task-notification>`, `<command-*>`, `<local-command-*>`, `<system-reminder>` or `[Request interrupted`; fixture in `selftest` |
| Q1 keyword matching noisy | Adopted: match only at the start of a short prompt (<=300 chars) or as a whole phrase; the weekly report prints 5 matched examples so precision can be eyeballed |
| Q5 test detection heuristic | Adopted: fixed list of runners (pytest, npm/pnpm/yarn/bun test, vitest, jest, go test, cargo test, swift test, xcodebuild test, make test, ./gradlew test) |
| Jev latency on the prompt path | Adopted: 1.5 s Jev timeout in the hook, p50/p95 measured in the test report |
| Jev privacy | Adopted: only the matched sentence (<=200 chars) is sent, with paths, URLs, emails and long numbers replaced |
| G2 redundant; Q2/Q4 are behaviour | Adopted: G2 folded into G1; Q2, Q4 marked info |
| Rule rot | Adopted: P3, and `house-rules review` lists rules not injected in 8 weeks as retire candidates |
| One change at a time | Advice for the user: the report names every change in a week; weeks with 2+ changes are marked "mixed" |

## Not built (named)

- Automatic rule writing by an LLM, embeddings, a UI dashboard, per-project rule files (tags + cwd keywords cover it for now), Cognee writes (Cognee stays conversation memory; taste lives in its own file).
