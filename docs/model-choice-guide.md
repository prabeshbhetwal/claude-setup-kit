# Choosing a Claude model and effort in Claude Code

A digest of Anthropic's own guidance (read in full on 17 Nov 2026), used to tune Model pilot. Sources are listed at the end; numbers are Anthropic's and directional, not this kit's measurements. Where a source contradicts another, both are shown.

## The two dials

| Dial | What it changes | Rule of thumb |
|---|---|---|
| **Model** | Which fixed weights answer, and the price of every token | How capable. Fable = specialist, Opus = expert, Sonnet = very good generalist, Haiku = fast and cheap |
| **Effort** | How much work Claude does: files read, tests run, checks made, how far it goes before checking in. Thinking, tool calls and text all bill as output | How thorough |

**The one question when a result is wrong:** did Claude *not know enough* (switch to a larger model) or *not try hard enough* (raise effort)? Check the prompt, context, tools and CLAUDE.md first: a fix upstream often beats both.

## Prices (per million tokens, Anthropic API)

| Model | Input | Cache write 5 min / 1 h | Cache read | Output | Default effort (Claude Code) | Default effort (API) |
|---|---|---|---|---|---|---|
| Fable 5.2 | $8 | $10 / $16 | $0.20 | $40 | medium | high |
| Opus 5.5 | $4 | $5 / $8 | $0.20 | $20 | medium | medium |
| Sonnet 5.5 | $2 | $2.50 / $4 | $0.10 | $10 | medium | high |
| Haiku 5.5, prompt up to 100k | $0.10 | $0.125 / $0.20 | $0.01 | $0.50 | medium | medium |
| Haiku 5.5, prompt over 100k | $0.50 | $0.625 / $1 | $0.05 | $2.50 | | |

All four have a 1M-token window and 128k max output. Fast mode (Fable and Opus only) costs 2x. Batch is 50% off.

## Which model

| Model | Use it for | Avoid it for |
|---|---|---|
| **Opus 5.5** | Anthropic's recommended starting point and daily driver: complex coding, hard debugging, cross-cutting refactors, architecture. The Claude Code default on every plan | Long routine stretches (drop down) |
| **Sonnet 5.5** | Most well-scoped coding: features with clear scope, bug fixes, implementation sub-tasks, high-volume sub-agents | Ambiguous or unfamiliar problems where it is confidently wrong |
| **Haiku 5.5** | Lookups, renames, boilerplate, summarising, classifying, routing, scripted runs; work with checkable output | Real coding and anything needing judgment; prompts over 100k (price jumps 5x: compact first) |
| **Fable 5.2** | The hardest, longest, most ambiguous work: root-cause hunts, outage debugging, architecture, jobs bigger than one sitting. Finishes jobs Opus and Sonnet cannot at any effort | Anything Opus already clears: Opus is faster and half the price. Use it when Opus at xhigh or max still falls short |

**Cost per finished task, not per token.** On hard multi-step work a larger model often reaches the bar in fewer steps, so it can cost less in total. Anthropic's examples: on SWE-bench Pro, Opus 5.5 at low (87.4%, $0.12 per solve) matched Sonnet 5.5 at high (87.6%, $0.11). Opus 5.5 at its default matched Fable 5.1 at its default for about a fifth of the cost. On routine work a larger model only adds verification at a higher price.

## Which effort

| Level | Fits | Source note |
|---|---|---|
| low | Quick exchanges you review each step: brainstorming, a first sketch, a rename | Opus low vs medium on defect search: 34 points lower for a fifth of the cost. Risky for search and verification |
| medium | Default on Fable 5.2, Opus 5.5, Sonnet 5.5 and Haiku 5.5 in Claude Code. Day-to-day engineering with clear scope | Opus 5.5 at medium matches or beats Opus 5 at high |
| high | Verification matters, edge cases likely: fixing a bug in an existing codebase | Sonnet 5.5 medium vs high: about 7 points lower for 59% of the cost |
| xhigh | Deeper reasoning at higher spend | Fable: go above high only where you measured a gain |
| max | Hard unattended problems (for example a security audit) | Diminishing returns and overthinking; test before using broadly; session-only in Claude Code |

- **Use the default for most work.** Treat effort as a standing preference by type of work, not a dial per task.
- **Effort before model.** Raise effort before switching model: it is a smaller step and keeps the cache (measured above). Lower effort before dropping a model.
- **One hard turn:** the word `ultrathink` in a prompt runs that one turn at xhigh without changing the session's level. "think hard" is not a keyword.
- **Checkable work** (tests, a verifier): run at low, re-run only the failures at high. Anthropic's example: about 97% solved at $0.17 a task, against 95.3% at $0.29 with everything at high.
- **Haiku at low** can skip searches and checks on long agent prompts: use medium.

## Cache, switching and sessions

- **Cache reads cost 0.1x input; writes up to 2x.** A changed prefix forces a full re-read at the write price: a new model, a new effort level, fast mode on, `/compact`, or the cache expiring (1 hour on a subscription, 5 minutes on an API key).
- **Set the model at the start of a session or right after `/clear`.** Anthropic's Claude Code article says `/model`, `/effort` and fast mode all invalidate the cache mid-chat, and `opusplan` does so at every switch into and out of plan mode. The API docs say the 5.5 family supports per-message effort changes that keep the cache. **Measured in this kit:** in 89 past cases where effort changed between two requests on the same model, the second request still read the whole chat from the cache. So effort can change turn by turn; a model change is what costs a full re-read.
- **`/clear` between unrelated tasks; `/compact` when an earlier part of the same task is finished, ideally before a break** (the summary is cheap only while the old chat is cached). **`/rewind` instead of `/compact`** when the last turns went wrong: it costs nothing.
- **Built-in mixes:** `opusplan` plans on Opus and executes on Sonnet. A lead model with Sonnet sub-agents for scoped work is Anthropic's recommended split ("Use Sonnet subagents to upgrade each package and fix its tests"). Opus as orchestrator with Sonnet sub-agents cost about a third less on work larger than one context window; an advisor pairing paid off only narrowly.
- **Sub-agents inherit the main model** unless their definition sets `model:`; on another model they also need their own `effort`. Give noisy, repeated jobs a `haiku` or `sonnet` sub-agent. For small jobs a sub-agent is overhead.
- **Dynamic workflows** (`/config` "Dynamic workflows", key `enableWorkflows`) are not the same as sub-agents: a workflow is a script that runs dozens to hundreds of sub-agents and returns only the final answer. They use your plan's quota faster; `workflowSizeGuideline: small` bounds them.
- **Fable and usage credits:** depending on plan, Fable can bill to usage credits instead of plan limits. Claude Code asks once in a session; in `-p` and SDK runs it bills without asking.

## Context hygiene (from "Maximizing the value of your Claude Code sessions")

- Every turn re-sends everything in context: turn 40 re-reads the 39 before it.
- Keep CLAUDE.md short and specific (under about 200 lines); move workflow instructions into skills, which load only when used. Turn off unneeded MCP servers.
- Point at file paths or @-mention a file once; specific prompts avoid exploratory reads that stay in context.
- Quiet noisy commands; Bash output past `BASH_MAX_OUTPUT_LENGTH` characters (an environment setting, default about 30,000; this kit does not set it) is not shown to Claude in full.
- `/loop` belongs in its own fresh session.
- For known grunt work on models that allow it, thinking can be turned off (`MAX_THINKING_TOKENS=0`); thinking cannot be disabled on Opus 5.5, Sonnet 5.5 or Fable.

## From the "Maximizing Value from Claude Code" webinar (Lydia Hallie, Claude Code team, 27 min)

Recorded when Fable 5.1, Opus 5 and Haiku 4.5 were current, so its prices and one cache rule are older than the docs above.

- **Don't run the biggest model on a task that doesn't need it:** its price multiplies every token. Leaving the biggest model as a team's default is called the highest-leverage cost fix. Managed settings can set `model`, `availableModels`, `effortLevel` and `maxEffortLevel`.
- **Haiku** for precisely describable or mechanical edits, **Sonnet** the generalist, **Opus** the expert for subtle bugs and unfamiliar ground, **Fable** the specialist. Medium effort on Fable is "excellent"; newer models at lower effort often match older ones at high.
- **To switch model mid-task:** `/compact` first, then switch, so the new model reads a short summary instead of the whole chat. Compact or switch while the cache is warm, before a break.
- **Cache lifetime:** about 1 hour on a plan, 5 minutes on API billing or a cloud provider, and **5 minutes for sub-agents everywhere**. A 1-hour cache write costs 2x input against 1.25x for 5 minutes; the short window is cheaper if you work in steady bursts.
- **One long session used about twice the tokens** of the same work split with `/clear`.
- **Changing effort breaks the cache on most models** (Fable 5.1 the exception) per the webinar. The newer API docs say the 5.5 family keeps the cache across per-message effort changes, and this kit measured 89 of 89 same-model effort changes keeping it. Trust the measurement for the 5.5 models.
- Sub-agents can run a cheaper model and their own effort; send noisy work there and keep only the conclusion.

## Sources

1. [Choosing a Claude model and effort level in Claude Code](https://claude.com/blog/claude-model-and-effort-level-in-claude-code) (same text at [claude.com/resources](https://claude.com/resources/articles/claude-model-and-effort-level-in-claude-code))
2. [Model configuration, Claude Code docs](https://code.claude.com/docs/en/model-config); [settings reference](https://code.claude.com/docs/en/settings-reference); [workflows](https://code.claude.com/docs/en/workflows)
3. [Maximizing Value from Claude Code, webinar recording](https://anthropic.ondemand.goldcast.io/on-demand/5ca27c0b-2eab-45d5-bded-b18e6a2f0d7c) (transcribed in full); [Maximizing the value of your Claude Code sessions](https://claude.com/resources/articles/maximizing-the-value-of-your-claude-code-sessions); [webinar page](https://claude.com/resources/webinars/claude-code-maximizing-value) (recording behind a sign-up form, not watched)
4. [Models, usage, and limits in Claude Code](https://support.claude.com/en/articles/14552983-models-usage-and-limits-in-claude-code); [Claude Code model configuration](https://support.claude.com/en/articles/11940350-claude-code-model-configuration)
5. [Choosing the right model](https://platform.claude.com/docs/en/about-claude/models/choosing-a-model) (the docs.anthropic.com copy redirects to it); [Models overview](https://platform.claude.com/docs/en/models/overview); [Optimizing for cost and intelligence](https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence); effort, pricing, thinking and fast-mode pages linked from them
6. [Choosing a Claude model for knowledge workers](https://academy.claude.com/tutorials/choosing-the-right-claude-model) (interactive widgets not captured)
7. [Claude models explained](https://claude.com/blog/claude-models-explained-choosing-the-best-model-for-your-use-case)
8. [Building with the Claude 5.5 family (webinar)](https://www.anthropic.com/webinars/building-with-the-claude-5-5-family-choosing-the-right-model-and-getting-more-from-every-token): page only; recording behind a sign-up form
9. Video: "Choosing the right Claude model", Anthropic, https://youtu.be/C33hJGt-ySg
10. Video: "Rethinking Claude Code Best Practices", Lydia Hallie, https://youtu.be/vlfCjWuv4es (her claims are marked as hers where used)
