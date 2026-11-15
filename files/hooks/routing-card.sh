#!/bin/sh
# SessionStart: puts the model/effort routing card in every session's context (~250 tokens, cached after turn 1).
# Full rules: ~/.claude/guides/agents-and-models.md. Edit the card here; keep it short.
cat <<'CARD'
MODEL ROUTING ACTIVE. Before each task, pick the cheapest model + effort that does it reliably; whatever model this chat runs on.
Tiers: haiku/low = lookups, news, facts, summaries, tagging, run-and-report · sonnet/medium = scoped job, done fits one sentence · opus/medium (high if hard) = unknown-cause debug, design, security, strategy · fable/high = huge open-ended multi-hour job, judgment + accuracy critical. Never max.
Down (task below this chat's tier): short answer / a few tool calls → answer here (measured: delegating a 3-lookup job saved nothing; this chat's own context costs more than the lookups). Big tool-heavy work (bulk reads, many searches/commands, large output) → helper agent, lean first: haiku-lean / sonnet-lean (~14k start-up; general-purpose and *-runner/*-worker ~72k, only when lean lacks a tool). Long independent job → start_session, cheaper model + effort, permission_mode "auto" (each new session loads ~120k tokens of fixed context: prefer helpers).
Up (task above this chat's tier): bounded → Agent with explicit model (opus/fable) + effort. Long autonomous → new chat on the higher model with a written handoff (sessions can't start above parent).
Every Agent call: pass model + effort; print label `▶ <agent> · <model> · <effort> — <task>`. Brief helpers with the memory facts they need (helpers don't search memory).
Never switch this chat's model mid-chat; bad result → /rewind, raise effort one level, then one model up at lower effort. Token stack stays on in helpers: context-mode, CodeGraph, RTK, Caveman.
Context above ~250k, or task finished → hand off to a fresh chat (written summary, or `/handoff` if that mod is installed) instead of continuing; never `/model` mid-chat (it discards the cache); hand off before leaving a chat idle over an hour.
Details: read ~/.claude/guides/agents-and-models.md when delegating.
CARD
