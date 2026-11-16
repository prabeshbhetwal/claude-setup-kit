// model-pilot's calls on the engine: the judge request, the transcript read, the log.
import type { EngineInterface } from 'claude-code'

import { jevBody, parseJevReply } from './jev'
import { RUBRIC, judgePrompt, parseJudgeReply, rulesVerdict } from './judge'
import { agentFileNamesModel } from './policy'
import type { JudgeInput, Verdict } from './policy'
import type { Usage } from './prices'
import { lastAssistantModel } from './transcript'
import type { RanRow } from './transcript'

export type Judged = {
  verdict: Verdict
  source: 'judge' | 'rules'
  /** Which judge decided. */
  by: 'jev' | 'haiku' | 'rules'
  /** How long the judge calls took; 0 when none was made. */
  ms: number
  usage?: Usage
  /** Why the rules decided instead of the judge, when they did. */
  fail?: string
}

export type JudgeOptions = {
  isPrivate: boolean
  budgetMs: number
  /** The Haiku-step model: an alias or an id. */
  model: string
  /** The judges to try, in order; the rules always stand behind them. */
  chain: readonly ('jev' | 'haiku')[]
}

// Jev is optional. Without its CLI or a key it is left alone for the session, silently.
let isJevOff = false
let jevFailures = 0

/** Asks Jev through the kit's `jev` CLI, which holds the key; undefined when it cannot answer. */
async function askJev($: EngineInterface, input: JudgeInput, timeoutMs: number): Promise<Verdict | undefined> {
  if (isJevOff) return undefined
  try {
    const bin = `${(await $.env.get('HOME')) ?? ''}/.local/bin/jev`
    if (!(await $.fs.exists(bin))) {
      isJevOff = true
      return undefined
    }
    const r = await $.process.run([bin, 'raw'], { stdin: JSON.stringify(jevBody(input)), timeoutMs })
    const verdict = r.exitCode === 0 ? parseJevReply(r.stdout) : undefined
    if (verdict) {
      jevFailures = 0
      return verdict
    }
    if (/no TypeSafe key/.test(r.stderr)) isJevOff = true
    if (/credential/.test(r.stderr)) return undefined // its own guard refused the text: not a failure of Jev
  } catch {
    // timed out or could not start
  }
  jevFailures += 1
  if (jevFailures >= 3) isJevOff = true
  return undefined
}

/** Asks the judges in order; the rules answer when none can, or none may, be asked. */
export async function judge($: EngineInterface, input: JudgeInput, o: JudgeOptions): Promise<Judged> {
  if (o.isPrivate) return { verdict: rulesVerdict(input), source: 'rules', by: 'rules', ms: 0, fail: 'privacy' }
  const t0 = await $.clock.now()
  let fail = 'no judge'
  let usage: Usage | undefined
  if (o.chain.includes('jev')) {
    const verdict = await askJev($, input, Math.min(o.budgetMs, 3000))
    if (verdict) return { verdict, source: 'judge', by: 'jev', ms: (await $.clock.now()) - t0 }
    fail = 'jev unavailable'
  }
  if (o.chain.includes('haiku')) try {
    fail = 'rejected'
    const r = await $.model.complete({
      model: o.model,
      system: RUBRIC,
      prompt: judgePrompt(input),
      effort: 'low',
      maxTokens: 400,
      timeoutMs: Math.max(200, Math.round(o.budgetMs)),
    })
    usage = r.usage
    if (r.isAnswered) {
      const verdict = parseJudgeReply(r.text)
      if (verdict) return { verdict, source: 'judge', by: 'haiku', ms: (await $.clock.now()) - t0, usage }
      fail = 'unparseable'
    } else {
      fail = r.reason === 'aborted' ? 'timeout' : r.reason
    }
  } catch {
    // a request the engine refused to send: the rules decide
  }
  return { verdict: rulesVerdict(input), source: 'rules', by: 'rules', ms: (await $.clock.now()) - t0, usage, fail }
}

/** A few lines on the turns before `prompt`, so a follow-up is judged in context. */
export async function recentDigest($: EngineInterface, prompt: string): Promise<string> {
  const rows = await Promise.race([
    $.session.messages(),
    $.clock.sleep(400).then(() => undefined),
  ]).catch(() => undefined)
  if (!Array.isArray(rows)) return ''
  const list = rows.slice(-7)
  const tail = list.at(-1)
  if (tail?.role === 'user' && tail.text.trim() === prompt.trim()) list.pop()
  return list
    .slice(-6)
    .map(m => {
      const tools = [...new Set(m.toolUses.map(u => String((u as { tool?: unknown; name?: unknown }).tool ?? (u as { name?: unknown }).name ?? '')))]
        .filter(Boolean)
        .slice(0, 8)
      const text = m.text.replace(/\s+/g, ' ').trim().slice(0, 300)
      return `${m.role}: ${text || '(no text)'}${tools.length ? ` [tools: ${tools.join(', ')}]` : ''}`
    })
    .join('\n')
}

const TAIL =
  'tail -c 600000 "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/projects/*/"$1".jsonl 2>/dev/null'

/** The model of the newest reply in this session's transcript, if written since `sinceMs`. */
export async function readRan($: EngineInterface, sessionId: string, sinceMs: number): Promise<RanRow | undefined> {
  if (!/^[\w-]+$/.test(sessionId)) return undefined
  for (const waitMs of [0, 300]) {
    if (waitMs) await $.clock.sleep(waitMs)
    const r = await $.process.run(['/bin/sh', '-c', TAIL, 'sh', sessionId], { timeoutMs: 5000 })
    const row = lastAssistantModel(r.stdout)
    if (row && row.at >= sinceMs) return row
  }
  return undefined
}

const APPEND =
  'f="${MODEL_PILOT_LOG:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}/mods-logs/model-pilot.jsonl}"; mkdir -p "$(dirname "$f")" && cat >> "$f"'

/** Appends one decision to the log; O_APPEND keeps concurrent sessions' lines whole. */
export async function appendLog($: EngineInterface, entry: Record<string, unknown>): Promise<void> {
  await $.process.run(['/bin/sh', '-c', APPEND], { stdin: `${JSON.stringify(entry)}\n`, timeoutMs: 5000 })
}

/**
 * Whether a sub-agent type may be given a model: only `general-purpose`, or an
 * agent file of the person's or the project's that names no model. A plugin's
 * agent or a built-in special one may carry a model the hook cannot see.
 */
export async function isRoutableAgent($: EngineInterface, type: string): Promise<boolean> {
  if (type === 'general-purpose') return true
  if (!/^[\w-]+$/.test(type)) return false
  const home = (await $.env.get('HOME')) ?? ''
  const cwd = await $.session.cwd()
  for (const path of [`${cwd}/.claude/agents/${type}.md`, `${home}/.claude/agents/${type}.md`]) {
    if (await $.fs.exists(path).catch(() => false)) {
      return !agentFileNamesModel(await $.fs.read(path))
    }
  }
  return false
}
