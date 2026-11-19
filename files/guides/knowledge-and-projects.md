# Knowledge, Projects & Bootstrap Guide

Read for: starting substantial work in repo or project; "remember this" / "save this principle" / "store this preference"; maintaining `CLAUDE.md`, `claude.md`, `memory.md` or project instruction files; scheduled tasks.

## Context Bootstrap
Classify each substantial task without asking:
| Context | Instruction layers |
|---|---|
| Ordinary conversation | Global only |
| Coding / repository | Global + repo `CLAUDE.md` |
| Cowork / non-code project | Global + project instructions/knowledge |
| Mixed | All relevant local layers |

- Repo without `CLAUDE.md`: before substantial work, ask me whether to create one (not every repo is mine to add files to). If yes, inspect repo (CodeGraph/Graphify where installed), create it with only durable, evidence-based, project-specific facts, where applicable: architecture and system design; build, test, lint, package-manager and deploy commands; dev workflows; conventions; key dependencies; architectural boundaries; repo-specific file-safety rules; constraints; durable setup/environment requirements; relevant `graphify-out/` paths and navigation rules.
- Never fabricate architecture, commands, dependencies or conventions. Never copy global rules into it.
- Existing `CLAUDE.md`: read first, keep valid content, extend only with new durable knowledge, no duplicates, no wholesale replacement unless asked.
- Substantial non-code projects: establish/maintain project instructions (objective, scope, workflow, sources of truth, output requirements, file conventions, recurring procedures, scheduled-task behaviour, decisions, working principles, terminology).
- Create supporting files only when they genuinely improve project. No empty boilerplate. No write access → follow structure internally, never claim files created.

## Memory Files
- `claude.md` = reusable principles and workflows. `memory.md` = facts, decisions, preferences, examples, project context.
- On "remember this" / "save this principle" / "store this preference":
  1. Extract rule or fact.
  2. Append to or update correct file.
  3. Confirm in chat what written and where.
- On diff with my edited version: infer general lesson; style/workflow → `claude.md`, preferences/examples → `memory.md`.
- Never store temporary debugging notes, transient facts or one-off observations as durable memory unless asked.

## Projects, Cowork & Scheduled Tasks
- Project knowledge files plus root `claude.md` / `memory.md` = local source of truth for that project.
- Scheduled tasks: load latest rules each run; generalise repeated corrections into reusable principles.
- Keep project-specific knowledge in project, not global instructions.

## Automatic Maintenance
- As work progresses, note durable decisions, commands, conventions, constraints, workflows and repeated corrections that belong in an instruction file. Propose the change (file + exact lines); write it only after I say yes. An explicit "remember this" counts as yes.
- Never store debugging notes, one-off observations, transient task state or speculative assumptions as permanent instructions.
- Keep valid existing knowledge; avoid duplication; keep files concise. Update existing file over creating overlapping one.
- Remove or revise obsolete guidance only when confidently superseded and file-safety rules allow.