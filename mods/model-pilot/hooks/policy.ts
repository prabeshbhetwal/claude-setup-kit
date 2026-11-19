// model-pilot policy: pure functions, no engine calls. Everything here is unit-tested.
import { effortBelow, outPerStep } from './effort'
import { rateOf } from './prices'
import { steer } from './steer'

export type Tier = 'haiku' | 'sonnet' | 'opus' | 'fable'
export type Effort = 'low' | 'medium' | 'high' | 'xhigh'
export type Source = 'judge' | 'rules' | 'sticky' | 'explicit' | 'pinned' | 'off'

export const TIERS: readonly Tier[] = ['haiku', 'sonnet', 'opus', 'fable']
export const EFFORTS: readonly Effort[] = ['low', 'medium', 'high', 'xhigh']

export type Verdict = {
  tier: Tier
  effort: Effort
  confidence: number
  reason: string
  /** Why a stronger model would help: it needs more knowledge, or only more care. */
  gap?: 'knowledge' | 'care'
  /** An automatic check (tests, a build, a verifier) shows whether the result is right. */
  checkable?: boolean
}

export type JudgeInput = {
  prompt: string
  /** Short digest of the turns before this one; '' when there are none. */
  recent: string
  contextTokens: number
  currentTier: Tier
  /** 'agent' when the text is a sub-agent's task, not the person's prompt. */
  kind: 'prompt' | 'agent'
}

const rank = (t: Tier): number => TIERS.indexOf(t)
export const maxTier = (a: Tier, b: Tier): Tier => (rank(a) >= rank(b) ? a : b)
export const tierUp = (t: Tier, cap: Tier = 'fable'): Tier =>
  TIERS[Math.min(rank(t) + 1, Math.max(rank(cap), rank(t)))] ?? t

/** The tier a model id or alias belongs to: 'claude-opus-5-5[1m]' is 'opus'. */
export function tierOf(model: string | undefined): Tier | undefined {
  const m = (model ?? '').toLowerCase()
  if (m.includes('mythos')) return 'fable'
  return TIERS.find(t => m.includes(t))
}

// ------------------------------------------------------------- the decision

export type Warm = Partial<Record<Tier, { at: number; tokens: number }>>

export type DecideInput = {
  verdict: Verdict
  source: 'judge' | 'rules' | 'sticky'
  explicit: { tier?: Tier; effort?: Effort | 'max' }
  /** The tier the menu shows: what would run with the pilot off. */
  menuTier: Tier
  isModelPinned: boolean
  isEffortPinned: boolean
  contextTokens: number
  /** Per tier: when a request last ran on it and how many tokens it held. */
  warm: Warm
  now: number
  cacheTtlMs: number
  /** How many turns in a row needed less than the tier they ran on. */
  lowerStreak: number
  canUpgrade: boolean
  /** The person reports a failed check after a checkable turn ran at low effort. */
  isRetry?: boolean
}

export type Decision = {
  /** The tier to run on; undefined leaves the model to the menu. */
  tier?: Tier
  /** The effort to ask for; undefined leaves it to the menu. */
  effort?: Effort | 'max'
  /** The least capable tier judged enough for the task. */
  required: Tier
  source: Source
  reason: string
  confidence: number
}

// Rough shape of a turn by the tier its task needs: model requests and output tokens.
const SHAPE: Record<Tier, { steps: number; out: number }> = {
  haiku: { steps: 2, out: 400 },
  sonnet: { steps: 8, out: 4000 },
  opus: { steps: 12, out: 8000 },
  fable: { steps: 25, out: 20000 },
}

/**
 * Estimated cost of running the coming turn on `tier`, with the prompt cache as
 * it stands: tokens that tier read within the cache's lifetime are a cheap
 * read, the rest are written afresh. `horizon` counts the turns expected to
 * stay at this difficulty, so a switch that pays off over two turns is taken.
 */
export function estTurnCost(
  tier: Tier,
  required: Tier,
  i: Pick<DecideInput, 'contextTokens' | 'warm' | 'now' | 'cacheTtlMs'>,
  horizon: number,
  effort?: Effort | 'max',
): number {
  const p = rateOf(tier, i.contextTokens)
  const w = i.warm[tier]
  const cached = w && i.now - w.at < i.cacheTtlMs ? Math.min(w.tokens, i.contextTokens) : 0
  const { steps } = SHAPE[required]
  // With an effort, output follows what this tier writes per request at it (measured); without, the job's rough size.
  const out = effort === undefined ? SHAPE[required].out : steps * outPerStep(tier, effort)
  const first = cached * p.cacheRead + (i.contextTokens - cached) * p.cacheWrite
  const perTurn = (steps - 1) * i.contextTokens * p.cacheRead + out * p.out
  const later = steps * i.contextTokens * p.cacheRead + out * p.out
  return (first + perTurn + (horizon - 1) * later) / 1e6
}

export function decide(i: DecideInput): Decision {
  const v = i.verdict
  let required = v.tier
  let reason = v.reason
  // Unsure means one tier up, but an unsure opus is not worth fable's price.
  if (i.source === 'judge' && v.confidence < 0.6) {
    const up = tierUp(required, 'opus')
    if (up !== required) {
      reason = `${reason} (unsure: ${required} raised to ${up})`
      required = up
    }
  }
  // Haiku over 100k prompt tokens pays its long-prompt rate (5x) and slips on long context.
  if (required === 'haiku' && i.contextTokens > 100_000) {
    required = 'sonnet'
    reason = `${reason} (over 100k tokens: haiku raised to sonnet)`
  }

  // More care before a bigger model; checkable work at low effort first (steer.ts).
  const s = steer(v, required, i.menuTier, i.source === 'judge', i.isRetry === true)
  if (s.stayOn && !i.explicit.tier && !i.isModelPinned) required = s.stayOn
  if (s.note) reason = `${reason} (${s.note})`
  // Haiku at low skips searches on long prompts (Anthropic): the pilot asks it for medium at least.
  const judged: Effort = required === 'haiku' && s.effort === 'low' ? 'medium' : s.effort
  const effort: Effort | 'max' | undefined =
    i.explicit.effort ?? (i.isEffortPinned ? undefined : judged)

  if (i.explicit.tier) {
    return { tier: i.explicit.tier, effort, required, source: 'explicit', reason: `you named ${i.explicit.tier}`, confidence: 1 }
  }
  if (i.isModelPinned) {
    return { tier: undefined, effort, required, source: 'pinned', reason: 'model set in the menu', confidence: v.confidence }
  }
  if (!i.canUpgrade && rank(required) > rank(i.menuTier)) {
    return {
      tier: i.menuTier,
      effort,
      required,
      source: i.source,
      reason: `${reason} (wanted ${required}; upgrades are off)`,
      confidence: v.confidence,
    }
  }

  // Candidates: the required tier, and any higher tier that is the menu's or
  // still has this conversation in its cache. The cheapest for this turn wins.
  let ceiling = maxTier(required, i.menuTier)
  for (const t of TIERS) {
    const w = i.warm[t]
    if (w && i.now - w.at < i.cacheTtlMs) ceiling = maxTier(ceiling, t)
  }
  const horizon = 1 + Math.min(Math.max(i.lowerStreak, 0), 3)
  // A tier above the one required does the job with less thinking: one effort level
  // lower, unless the person set the effort. Each candidate is priced at its own effort.
  const isOwnEffort = i.explicit.effort !== undefined || i.isEffortPinned
  const effortOn = (t: Tier): Effort | 'max' | undefined =>
    !isOwnEffort && rank(t) > rank(required) ? effortBelow(v.effort) : effort
  let best: Tier = required
  let bestCost = Infinity
  for (const t of TIERS) {
    if (rank(t) < rank(required) || rank(t) > rank(ceiling)) continue
    const cost = estTurnCost(t, required, i, horizon, effortOn(t) ?? v.effort)
    if (cost < bestCost) {
      best = t
      bestCost = cost
    }
  }
  if (best !== required) {
    reason = `${reason} (${required} would do; ${best} at ${effortOn(best) ?? 'the menu'} effort is cheaper while its cache is warm)`
  }
  return { tier: best, effort: effortOn(best), required, source: i.source, reason, confidence: v.confidence }
}

// ------------------------------------------- where a job is cheapest to run

// Fixed context a fresh thread loads before its first step, in tokens. Measured on the
// author's setup (many plugins and tools); a lighter setup loads less.
export const STARTUP = { 'lean sub-agent': 14_000, 'all-tools sub-agent': 72_000, 'new session': 120_000 } as const
export type Place = 'in place' | keyof typeof STARTUP
type CacheState = Pick<DecideInput, 'contextTokens' | 'warm' | 'now' | 'cacheTtlMs'>

/**
 * Estimated cost of a job needing `required` in each place. In place, every step
 * re-reads this chat. A sub-agent pays its start-up once and re-reads only that,
 * while this chat pays two steps: the hand-off and reading the report.
 */
export function placeCosts(required: Tier, runTier: Tier, i: CacheState): Record<Place, number> {
  const { steps, out } = SHAPE[required]
  const fresh = (startup: number): number => {
    const p = rateOf(required, startup)
    // Sub-agents get the 5-minute cache everywhere: writes at 1.25x input, not the main chat's 1-hour 2x.
    return (startup * p.in * 1.25 + (steps - 1) * startup * p.cacheRead + out * p.out) / 1e6
  }
  const handOff = estTurnCost(runTier, 'haiku', i, 1)
  return {
    'in place': estTurnCost(runTier, required, i, 1),
    'lean sub-agent': fresh(STARTUP['lean sub-agent']) + handOff,
    'all-tools sub-agent': fresh(STARTUP['all-tools sub-agent']) + handOff,
    'new session': fresh(STARTUP['new session']),
  }
}

const usd = (n: number): string => `$${n < 0.1 ? n.toFixed(3) : n.toFixed(2)}`

/** A one-line tip when a lean sub-agent would be clearly cheaper than running the job in this chat; else null. */
export function placeTip(required: Tier, runTier: Tier, i: CacheState): string | null {
  const c = placeCosts(required, runTier, i)
  const here = c['in place']
  const lean = c['lean sub-agent']
  if (lean > here * 0.7 || here - lean < 0.02) return null
  // Short on purpose: the desktop app clips a long line instead of wrapping it (keep "Tip: " + this under 60 characters).
  return `lean sub-agent ~${usd(lean)} vs ~${usd(here)} here`
}

/** A one-line note when a sub-agent was spawned for a job that would have been cheaper in this chat; else null. */
export function spawnNote(agent: string, required: Tier, runTier: Tier, i: CacheState): string | null {
  const place: Place = /lean/i.test(agent) ? 'lean sub-agent' : 'all-tools sub-agent'
  const c = placeCosts(required, runTier, i)
  if (c['in place'] > c[place] * 0.7 || c[place] - c['in place'] < 0.02) return null
  const name = agent.length > 18 ? `${agent.slice(0, 17)}…` : agent
  return `${name} cost ~${usd(c[place])} vs ~${usd(c['in place'])} in place`
}

// --------------------------------------------------------------- sub-agents

/** Whether an agent definition's frontmatter names a model of its own. */
export function agentFileNamesModel(markdown: string): boolean {
  const m = /^---\r?\n([\s\S]*?)\r?\n---/.exec(markdown)
  if (!m?.[1]) return false
  const line = /^model:\s*(.+)$/m.exec(m[1])
  const value = line?.[1]?.trim().replace(/^["']|["']$/g, '').toLowerCase()
  return value !== undefined && value !== '' && value !== 'inherit'
}

/**
 * Where a rules verdict may run. The rules spot a plain lookup well and a hard
 * task badly, so without the judge they may drop to haiku for a lookup, and
 * otherwise never go below the tier the menu would have run.
 */
export const rulesFloor = (rules: Tier, menu: Tier): Tier => (rules === 'haiku' ? 'haiku' : maxTier(rules, menu))

/** Sub-agents are fresh threads: no cache to weigh, so the required tier runs. */
export function agentTier(v: Verdict, source: 'judge' | 'rules', parent: Tier): Tier {
  if (source === 'rules') return rulesFloor(v.tier, parent)
  return v.confidence < 0.6 ? tierUp(v.tier, 'opus') : v.tier
}

// ------------------------------------------------------------------ privacy

/** Whether `cwd` is under one of the folders listed for rules-only judging. */
export function isPrivateFolder(cwd: string, list: string, home: string): boolean {
  const norm = (s: string) => s.replace(/\/+$/, '')
  const here = norm(cwd)
  return list
    .split(/[,\n]/)
    .map(s => s.trim())
    .filter(Boolean)
    .map(s => norm(s === '~' || s.startsWith('~/') ? home + s.slice(1) : s))
    .some(f => here === f || here.startsWith(`${f}/`))
}

// ------------------------------------------------------------------ handoff

/**
 * The context size at which a fresh chat is offered. 'auto' is 500k on a 1M-token
 * window and 250k on a smaller one: far enough in that a summary pays, early enough
 * that the chat is not yet slow and expensive to re-read. 0 means never.
 */
export function handoffThreshold(setting: string, windowTokens: number): number {
  const fixed: Record<string, number> = { '250k': 250_000, '500k': 500_000, '750k': 750_000, never: 0 }
  return fixed[setting] ?? (windowTokens >= 1_000_000 ? 500_000 : 250_000)
}

/** Offer a handoff once per 50k-token band above the threshold; -1 below it. */
export function handoffBand(contextTokens: number, threshold: number): number {
  return contextTokens < threshold ? -1 : Math.floor((contextTokens - threshold) / 50_000)
}

export const HANDOFF_PROMPT = `Write a handoff so a fresh chat can continue this work without this conversation. Save it as ~/.claude/handoffs/<today's date>-<project folder name>-<first 8 characters of the output of: printf %s "$PWD" | shasum>-HANDOFF.md (the hash of the full path keeps same-named projects apart and the name short), outside the project so nothing lands in its repo (create the folder if needed; if the file exists, add a dated section at the top). Cover: the goal; what is done and verified; what is in progress; decisions made and why; files and commands that matter; open questions; the exact next step. Keep it under 150 lines. Then reply with the file's path and one line I can paste into a new chat to resume from it.`
