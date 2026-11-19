// model-pilot's calls on the engine: the judge request, the transcript read, the log.
import type { EngineInterface } from 'claude-code'

import { jevBody, parseJevReply } from './jev'
import { RUBRIC, judgePrompt, parseJudgeReply, rulesVerdict, floorCoding } from './judge'
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
  /** Jev's off switch and failure count; /pilot eval passes its own so test runs never turn Jev off live. */
  jev?: JevState
}

export type JevState = { isOff: boolean; failures: number }

// Jev is optional. Without its CLI or a key it is left alone for the session, silently.
const live: JevState = { isOff: false, failures: 0 }

/** Asks Jev through the kit's `jev` CLI, which holds the key; undefined when it cannot answer. */
async function askJev($: EngineInterface, input: JudgeInput, timeoutMs: number, st: JevState): Promise<Verdict | undefined> {
  if (st.isOff) return undefined
  try {
    const bin = `${(await $.env.get('HOME')) ?? ''}/.local/bin/jev`
    if (!(await $.fs.exists(bin))) {
      st.isOff = true
      return undefined
    }
    const r = await $.process.run([bin, 'raw'], { stdin: JSON.stringify(jevBody(input)), timeoutMs })
    const verdict = r.exitCode === 0 ? parseJevReply(r.stdout) : undefined
    if (verdict) {
      st.failures = 0
      return verdict
    }
    if (/no TypeSafe key/.test(r.stderr)) st.isOff = true
    if (/credential/.test(r.stderr)) return undefined // its own guard refused the text: not a failure of Jev
  } catch {
    // timed out or could not start
  }
  st.failures += 1
  if (st.failures >= 3) st.isOff = true
  return undefined
}

type HaikuOut = { verdict?: Verdict; usage?: Usage; fail: string }

/** Asks the small model through the engine; never throws. */
async function askHaiku($: EngineInterface, input: JudgeInput, model: string, timeoutMs: number): Promise<HaikuOut> {
  try {
    const r = await $.model.complete({ model, system: RUBRIC, prompt: judgePrompt(input), effort: 'low', maxTokens: 400, timeoutMs })
    if (!r.isAnswered) return { usage: r.usage, fail: r.reason === 'aborted' ? 'timeout' : r.reason }
    const verdict = parseJudgeReply(r.text)
    return verdict ? { verdict, usage: r.usage, fail: '' } : { usage: r.usage, fail: 'unparseable' }
  } catch {
    return { fail: 'rejected' } // a request the engine refused to send
  }
}

/** The first promise to settle with a value; undefined when every one settles without. */
export function firstOf<T>(ps: Promise<T | undefined>[]): Promise<T | undefined> {
  return new Promise(resolve => {
    let left = ps.length
    const done = (v: T | undefined) => {
      if (v !== undefined) resolve(v)
      else if (--left === 0) resolve(undefined)
    }
    for (const p of ps) p.then(done, () => done(undefined))
    if (left === 0) resolve(undefined)
  })
}

// Jev usually answers in about half a second. Past this, Haiku is asked as well and the
// first answer wins, so a slow Jev never leaves the turn to the rules.
export const HEDGE_MS = 1200

/** Asks the judges: Jev first, Haiku too if Jev is slow or fails; the rules when neither answers. */
/** The verdict, with Haiku never left on real coding (Anthropic: Haiku is not for writing code). */
export async function judge($: EngineInterface, input: JudgeInput, o: JudgeOptions): Promise<Judged> {
  const j = await judgeOnce($, input, o)
  j.verdict = floorCoding(j.verdict, input.prompt) // mutate, not copy: a late Haiku usage must still reach the caller's object
  return j
}

async function judgeOnce($: EngineInterface, input: JudgeInput, o: JudgeOptions): Promise<Judged> {
  if (o.isPrivate) return { verdict: rulesVerdict(input), source: 'rules', by: 'rules', ms: 0, fail: 'privacy' }
  const t0 = await $.clock.now()
  const ms = async () => (await $.clock.now()) - t0
  const st = o.jev ?? live
  const hasJev = o.chain.includes('jev') && !st.isOff
  const jev = hasJev ? askJev($, input, Math.max(o.budgetMs, 3000), st) : Promise.resolve(undefined)
  if (hasJev) {
    const early = await Promise.race([jev, $.clock.sleep(HEDGE_MS).then(() => undefined)])
    if (early) return { verdict: early, source: 'judge', by: 'jev', ms: await ms() }
  }
  if (!o.chain.includes('haiku')) {
    const late = await jev
    return late
      ? { verdict: late, source: 'judge', by: 'jev', ms: await ms() }
      : { verdict: rulesVerdict(input), source: 'rules', by: 'rules', ms: await ms(), fail: hasJev ? 'jev unavailable' : 'no judge' }
  }
  const haiku = askHaiku($, input, o.model, Math.max(200, Math.round(o.budgetMs)))
  const tagged = firstOf<{ by: 'jev' | 'haiku'; verdict: Verdict }>([
    jev.then(v => (v ? { by: 'jev' as const, verdict: v } : undefined)),
    haiku.then(h => (h.verdict ? { by: 'haiku' as const, verdict: h.verdict } : undefined)),
  ])
  const won = await tagged
  // The Haiku call is paid for whether or not it won; count it once it is back.
  if (won?.by === 'haiku') return { verdict: won.verdict, source: 'judge', by: 'haiku', ms: await ms(), usage: (await haiku).usage }
  if (won) {
    // Jev won while Haiku was still out: its usage lands on this object when it returns, before the turn is costed.
    const j: Judged = { verdict: won.verdict, source: 'judge', by: won.by, ms: await ms() }
    void haiku.then(h => { j.usage = h.usage })
    return j
  }
  const out = await haiku
  return { verdict: rulesVerdict(input), source: 'rules', by: 'rules', ms: await ms(), usage: out.usage, fail: out.fail || 'no answer' }
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
