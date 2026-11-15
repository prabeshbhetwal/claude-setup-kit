# Agents & Model Routing Guide
Read for: spawning sub-agent, delegated task, nested session, parallel worktree; choosing model or effort level.

## Goal
Every task runs on cheapest model + effort that does it reliably — whatever main model is running (Haiku → Fable). Route down and up. Never dynamic workflows / mass fan-out (burns 5-hour limit).

## Tiers (pick first fit)
| Tier | Use when | Effort |
|---|---|---|
| Haiku 5.5 | Simple, repetitive, easy to check: lookups, news/weather/facts, summaries, tagging, conversions, file search, run-and-report | low |
| Sonnet 5.5 | Scoped: "done" fits in one sentence — feature, fix, tests, draft, focused review | medium (low if back-and-forth) |
| Opus 5.5 | Hard reasoning/judgment: unknown-cause debugging, design, security, strategy, migrations | medium; high when hard; xhigh only long + hard + critical |
| Fable 5.2 | Huge open-ended job, judgment + accuracy both critical, hours of autonomous work (2× Opus price) | high (xhigh rare) |
- Never Max (cost, overthinking). Default effort = model default (Medium).

## Route each request (main session, before working)
1. Classify request tier T. Same tier as current → do it here.
2. **T below current (route down):**
   - Short answer, no/one tool call → answer here (delegation start-up cost > saving).
   - Tool-heavy or multi-step (searches, bulk reads, web lookups, many commands) → helper agent on T, lean agent first (`haiku-lean`, `sonnet-lean`).
   - Long independent job → nested session (`start_session`, cheaper `model` + `effort`, `permission_mode: "auto"`).
3. **T above current (route up):**
   - Bounded task → helper agent with explicit `model` (`opus`/`fable`) + `effort`. Router keeps named models.
   - Long autonomous Fable/Opus job → `/pick-model handoff` (new chat one model up). Sessions can't start above parent model.
4. Bad result ladder: fix prompt (`/rewind`) → raise effort one level → move up one model at lower effort (Opus high fails → Fable medium).
5. Never switch main model mid-chat (cache loss, lost thinking) → handoff instead.
6. **Handoff rule:** context above ~250k, or task finished → hand off to a fresh chat (`/handoff`) instead of continuing; never `/model` mid-chat (it discards the cache); hand off before leaving a chat idle over an hour.

## Start-up cost (measured on the author's setup, 2026-11-15; yours depends on installed plugins and MCP servers)
| Helper | Tokens before work |
|---|---|
| `general-purpose` / all-tools agents (`haiku-runner`, `sonnet-worker`) | ~72k |
| `haiku-lean` (6 tools) | ~14k |
| 1-tool agent (`web-fetch`) | ~3k |
| New nested session (`start_session`) | ~120k fixed context to load (75–120k cache write) |
→ Prefer lean agents; all-tools agent only when task needs tools lean lacks. Nested session only for long independent jobs.
- Phase 3 (2026-11-15): routing decisions Opus main 19/20 model, 16/20 effort (20/20 within one level); Haiku main 16/20, 14/20. Delegating a small 3-lookup job cost ≈ same as doing it (deduped: baseline 923k cache-read + 82k cache-write on Opus; routed 784k + 92k on Opus plus 92k + 27k on Haiku): main chat's own context dominates. Savings come from big tool-heavy helpers and from starting chats on a cheaper model (selector, prompt 1).
- Measuring from transcripts: dedupe usage by `message.id` (each content-block line repeats it; raw sums overstate about 2×).

## Roster
| Role | Agent | Model · effort | Use for |
|---|---|---|---|
| Lean runner | `haiku-lean` | Haiku · low | Lookups, web facts, read/search/summarise, run command and report. No edits. |
| Lean worker | `sonnet-lean` | Sonnet · medium | Scoped edits/fixes/tests in few files. |
| Runner | `haiku-runner` | Haiku · high | Mechanical edits needing broad tools. |
| Worker | `sonnet-worker` | Sonnet · high (xhigh hard) | Bounded multi-file work needing broad tools. |
| Main driver | main session | as picked (you, or model-selector if installed) | Integration, design, final verification. |
| Deep helper | `general-purpose` + `model: opus`/`fable` | Opus/Fable · per tier | Hard bounded sub-problems from a cheaper main session. |
| Director | `fable-director` | Fable 5.2 · high | Decompose large/multi-part work into dispatch plan. |
| Fable executor | Agent `model: fable` or handoff to Fable chat | Fable 5.2 · high | Fable-tier jobs (see Tiers). |

## Optional mods (only if installed from a Model Selector pack you obtained yourself)
- `model-selector`: judges prompts 1–3 of a chat → model + effort; then effort only. `/pick-model auto|ask|off`, `/pick-model handoff`.
- `model-router`: routes unnamed helpers at spawn; keeps the model named by the caller or agent file. Measured on the author's setup: no saving on a small 3-lookup job (see Start-up cost).
- `handoff`, `cache-clock`: handoff to a new chat; cache-cold timer.
- Not installed → ignore `/pick-model` and `/handoff`; hand off by writing a summary into a new chat.

## Dispatch rules
- Pass `effort` on every Agent call; this rule = standing authorisation.
- Independent subtasks in parallel; no mass fan-out.
- Labelling: before every Agent call print `▶ <agent> · <model> · <effort> — <task ≤8 words>`. Keep label when relaying results.
- Nested sessions: `permission_mode: "auto"`, explicit `model` + `effort`.
