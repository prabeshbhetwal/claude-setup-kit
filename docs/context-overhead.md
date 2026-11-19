# Why a new chat starts with tens of thousands of tokens already used

A fresh Claude Code chat is never empty. Everything below is loaded before your first word, and Claude re-reads it at every step. Open `/context` in a new chat to see your own split; this page explains what the rows mean and what moves them.

## What is in the starting load

| Row in `/context` | What it is | What changes it |
|---|---|---|
| System prompt, system tools | Fixed by Claude Code and the app | Nothing you can edit |
| MCP tools | Tool definitions from connected servers | Disconnect servers you do not use |
| MCP server instructions | A text block each connected server adds | Same: one block per server |
| Custom agents | One description line per agent | Uninstall plugins you do not use |
| Skills | One description per skill, about 20 to 50 tokens each | Uninstall plugins and skills you do not use |
| Memory files | `CLAUDE.md` and the rules it loads | Edit them; usually the smallest row |
| Messages | The start-up text: the list of deferred tool names, the skill and agent lists, session-start hook output | Trim hook output; fewer connectors and plugins |

## What deferring does and does not do

Deferring a tool (Claude loads it only when needed) removes its **definition** from the starting load. Its **name** still sits in a list, and the server's instructions, skill descriptions and agent descriptions stay. In one measured setup (a single machine, so read it as an example, not a benchmark) about 500 tool names took roughly 17k tokens, the skill list about 12k, and session-start hook output about 6k, all in the "Messages" row.

So the biggest levers, in order, are:

1. Disconnect connectors you do not use.
2. Uninstall plugins you do not use. Each brings skills, agents and sometimes a server.
3. Remove duplicates: the same server connected twice, or a skill installed both on its own and inside a plugin.
4. Make session-start hooks print one-line pointers, not whole manuals.
5. Turn off app tools you do not need (built-in browser, simulators), where the app allows it.

Editing `CLAUDE.md` or routing files only touches the "Memory files" row, so it cannot fix a large starting load by itself.

## What to expect

- A plain install with no extras starts at roughly 15 to 20k tokens (an estimate, not measured here). The system prompt and the built-in tools are most of it, and they are fixed.
- With a full stack of tools and plugins, 25 to 35k is a realistic floor. Below about 15k is not possible in the desktop app.
- A large starting load costs money mostly through re-reading: it is part of every step of every chat. Trimming it helps most for chats that run many steps.

The kit does not change any of this for you. It never disconnects or uninstalls anything of yours.
