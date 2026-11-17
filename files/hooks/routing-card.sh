#!/bin/sh
# SessionStart: puts the model/effort routing card in every session's context (~250 tokens, cached after turn 1).
# Full rules: ~/.claude/guides/agents-and-models.md. Edit the card here; keep it short.
# With Model pilot on (not in shadow mode) the pilot owns this chat's model and the fresh-chat offer, so the card
# drops its own lines for those two and keeps only the helper-agent rules: one source for each decision.
PILOT=$(python3 -c 'import json,os,sys
try: d=json.load(open(os.path.expanduser("~/.claude/settings.json")))
except Exception: sys.exit()
k="model-pilot@claude-setup-kit"
on=d.get("enabledPlugins",{}).get(k) is True
shadow=((d.get("pluginConfigs",{}).get(k) or {}).get("options") or {}).get("shadow") is True
print("1" if on and not shadow else "")' 2>/dev/null)

cat <<'CARD'
MODEL ROUTING ACTIVE. Before each task, pick the cheapest model + effort that does it reliably; whatever model this chat runs on.
Tiers: haiku/medium = lookups, news, facts, summaries, tagging, run-and-report (never real coding, never >100k context) · sonnet/medium = scoped job, done fits one sentence · opus/medium (high if hard; never low for search/debug/verify) = daily driver: unknown-cause debug, design, security, strategy · fable/medium-high = huge open-ended multi-hour job, only when opus at xhigh would still fall short. Never max.
Effort before model: didn't try hard enough → raise effort (same model keeps the cache); didn't know enough → one model up. One hard turn → `ultrathink` in the prompt. Checkable work → low, re-run failures at high.
Down (task below this chat's tier): short answer / a few tool calls → answer here (measured: delegating a 3-lookup job saved nothing; this chat's own context costs more than the lookups). Big tool-heavy work (bulk reads, many searches/commands, large output) → helper agent, lean first: haiku-lean / sonnet-lean (~14k start-up; general-purpose and *-runner/*-worker ~72k, only when lean lacks a tool). Long independent job → start_session, cheaper model + effort, permission_mode "auto" (each new session loads ~120k tokens of fixed context: prefer helpers).
Up (task above this chat's tier): bounded → Agent with explicit model (opus/fable) + effort. Long autonomous → new chat on the higher model with a written handoff (sessions can't start above parent).
Split (big job, many scoped parts): this chat leads and judges; each scoped part → a Sonnet helper at medium ("use Sonnet subagents to upgrade each package and fix its tests"). Define "done" as a check (tests pass, output shown) before starting.
Every Agent call: pass model + effort; print label `▶ <agent> · <model> · <effort> — <task>`. Brief helpers with the memory facts they need (helpers don't search memory).
CARD
if [ -n "$PILOT" ]; then cat <<'CARD'
Model pilot is on: it sets this chat's model + effort per prompt and offers a fresh chat at the size the user chose. Leave both to it; never `/model` yourself. Bad result → /rewind and retry. Token stack stays on in helpers: context-mode, CodeGraph, RTK, Caveman.
CARD
else cat <<'CARD'
Never switch this chat's model mid-chat (the new model re-reads the whole chat at the cache-write price); bad result → /rewind, raise effort one level, then one model up at lower effort. Token stack stays on in helpers: context-mode, CodeGraph, RTK, Caveman.
Hand off by tokens, not turns: move when turns left × (context − 130k) × 0.1 > 162k (≈14 turns at 250k, ≈5 at 430k; under ~150k stay), always before ~900k, or task finished → hand off to a fresh chat (written summary, or `/handoff` if that mod is installed) instead of continuing; never `/model` mid-chat (it discards the cache); hand off before leaving a chat idle over an hour. If the user insists on switching here: suggest `/compact` first (cache still warm), then switch, so the new model reads a summary, not the whole chat.
CARD
fi
cat <<'CARD'
Context hygiene: long artefacts (spec, plan, report, draft >~40 lines) → write to a file; chat shows a ≤10-line summary + path; amend in the file, never re-paste; re-read only the changed section. Helpers hand back conclusions + paths, not dumps.
Screens: text first, pixels last. Web → read_page / get_page_text / find (Playwright: browser_snapshot); apps → app_ax_find; screenshot only to judge looks, at scale 0.5 or zoom on a region; many images to judge → mjudge, if installed (no Claude tokens). Text the user wants to show → ask them to paste it or give the path.
Code questions in a repo with .codegraph/ → codegraph_explore before Read/Grep ("where is / who calls / what breaks"); Read only files you will edit.
CARD
echo "Details: read ~/.claude/guides/agents-and-models.md when delegating."
