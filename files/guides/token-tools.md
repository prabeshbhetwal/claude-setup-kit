# Token Tools Guide

Read for: choosing token tools, large command/tool output, recalling earlier sessions/past decisions, keeping long session lean.

## Lanes (no overlap)
- Caveman = how I talk (chat prose only). Ponytail = what I build (code/design choices only).
  - Caveman never touches code, commits, PRs, file content, security warnings, destructive-action confirmations.
  - Ponytail never shortens explanations user asked for (reports, walkthroughs).
  - Explicit user request for detail/full version beats both.
- Pick one tool that answers question; skip tools whose index absent.
- CodeGraph vs Graphify lanes: see `coding.md`. Diff/PR blast radius: `codegraph_explore`.
- Rows for tools that are not installed do not apply. Installed tools stay on; never switch one off to save tokens.

## Short-term: keep this session's context small
Use each when first relevant, combine where useful; never invoke just because session started.
| Tool | Use | Skip |
|---|---|---|
| Caveman | Every reply (chat prose) | Code, commits, file content, safety confirmations |
| i-have-adhd | Every reply: next action first, numbered steps, one closing action (always-on hook) | None |
| Ponytail | Every build/design choice: shortest working diff, stdlib first | Requested explanations |
| RTK | Auto on every Bash call. Treat condensed output as complete; rerun via `rtk proxy` only if unusable | None |
| context-mode (`ctx_batch_execute`, `ctx_execute`, `ctx_search`, `ctx_fetch_and_index`) | Output likely >20 lines (logs, tests, git log, API dumps, web pages, large files to analyse). Only summary enters context | Short commands, files about to be edited |
| CodeGraph (`codegraph_explore`) | Locate/understand/change code in repo with `.codegraph/`. One call instead of grep + many reads | Chat, Claude-setup questions, docs-only work |
| Graphify (skill + `graphify-out/`) | Architecture, "why does X connect to Y", docs/specs/diagrams/PDFs. Read `GRAPH_REPORT.md` / wiki first | Single-symbol lookups (CodeGraph), plain conversation |
| Context7 (optional, `context7@claude-plugins-official`) | Library/framework/API docs. Targeted snippets, not whole web pages | Non-library questions |
| Sub-agents (`haiku-lean`, `sonnet-lean`, Explore) | Wide searches or bulk reading. Only conclusion returns to context | Single known-file lookups |
| Deliberation | Second opinion from GPT/Gemini/Grok/OpenRouter; each call costs that provider's tokens | Routine work |

## Long-term: don't re-derive across sessions
| Tool | Use |
|---|---|
| Supermemory (plugin recall hook) | Auto-recall each prompt; search past decisions/"what did we decide"; save durable facts |
| remember plugin + auto-memory (`~/.claude/projects/*/memory/`) | Session history (`.remember/`) + one-fact-per-file memories with `MEMORY.md` index |
| CodeGraph / Graphify indexes | Built once per repo, reused every session instead of re-reading codebase |
- Graphify maps files (code, docs, PDFs, images), not chat history. Conversation context from Supermemory / Cognee / remember, not Graphify.
- Before searching codebase or web for something decided earlier, check memory first.

## Session hygiene
- Large outputs: Claude Code does not show Bash output past `BASH_MAX_OUTPUT_LENGTH` characters in full (an environment setting, default about 30,000; this kit does not set it). Quiet commands; read only the part needed.
- Unrelated new task in long session → suggest `/clear`; long single task → suggest `/compact` at milestone (both user-typed commands).
- Connectors, MCP servers, plugins not always on stay off until a task needs them; ask before enabling.