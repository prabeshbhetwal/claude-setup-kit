# Coding Guide

Read for: write, edit, review, debug code; refactor; repo navigation.

## Architecture & Context Hygiene
- Source files ≤ 300 lines. Near 250, extract helpers, types, sub-components into sibling modules or domain folders.
- Domain models, data access, external integrations, orchestrators in separate files. Never duplicate logic; extract shared routines into common utilities.
- Prefer small, well-typed interfaces over large barrel exports (`index.ts`); imports explicit, local.
- After code changes: run lint, format, unit tests. Reject copy-paste fixes; use modular abstraction.

## Build Discipline (Ponytail)
- Auto-starts via ponytail plugin SessionStart hook (full mode). Toggle: `/ponytail lite|full|ultra`, off: "stop ponytail".
- Before writing code: need it at all? → already in repo? → stdlib? → native platform? → installed dep? → one line? → only then minimum code.
- Bug fix = root cause in shared function, not per-caller patch.
- Never simplify away: input validation, data-loss error handling, security, accessibility.

## Navigation
- Source code (Python/JS/TS/Go/etc.): CodeGraph first (`codegraph_explore`). No blind repo-wide grep/cat/recursive glob when `.codegraph/` exists.
- Specs, architecture, diagrams (`.png`), schema PDFs, feature docs: read `graphify-out/GRAPH_REPORT.md` (or `graphify-out/wiki/index.md`) first. Follow verified/inferred edges for cross-module links; no guessing. Never assume `graphify-out/` exists.
- Neither index present: fall back to Grep/Glob/Read.

## CodeGraph vs Graphify
- CodeGraph = concrete code facts (symbol source, callers/callees, blast radius). Graphify = big picture (why modules connect, communities, docs/diagrams/PDFs).
- Pure code question → CodeGraph only. Design/"why"/cross-module question → Graphify report first, then CodeGraph for exact symbols it names.
- Never run both for same lookup.
- Conflict: CodeGraph wins for code (live index). If `GRAPH_REPORT.md` older than last commit, say stale, offer `graphify update .`.
- CodeGraph prompt hook gated (`~/.claude/hooks/codegraph-gate.py`): injects context only for code-shaped prompts. If skipped prompt needs code context, call `codegraph_explore` directly.