// model-pilot's per-turn routing: the judge starts when the prompt is submitted,
// the decision is made at the turn's first model request, and what ran is read
// back at the turn's end. Module state is this session's.
import type { EngineInterface } from 'claude-code'

import { appendLog, judge, readRan, recentDigest } from './engine'
import type { Judged } from './engine'
import { explicitChoice, isFollowUp, rulesVerdict } from './judge'
import { decide, handoffBand, handoffThreshold, isPrivateFolder, placeTip, rulesFloor, tierOf, TIERS } from './policy'
import type { Decision, Effort, JudgeInput, Tier, Verdict, Warm } from './policy'
import { addUsage, estSavingUsd } from './prices'
import type { Usage } from './prices'
import type { PilotFlags, PilotView } from '../types'

export type Options = {
  privacy: boolean
  privateFolders: string
  allowUpgrade: boolean
  /** 'auto', '250k', '500k', '750k' or 'never'. */
  handoff: string
  /** Try Jev before Haiku when its CLI and key are there. */
  useJev: boolean
  /** The longest the first model request waits for the judge. */
  judgeBudgetMs: number
  /** The model that judges: an alias or an id. */
  judgeModel: string
  /** Judge and log, but leave every request as the menu has it. */
  isShadow: boolean
}

type Pending = { at: number; input?: JudgeInput; judged: Promise<Judged | undefined> }

export type Rec = {
  text: string
  t0: number
  explicit: ReturnType<typeof explicitChoice>
  isSticky: boolean
  isFirst: boolean
  pending?: Pending
  judgedOut?: Judged
  /** How long the first request waited for the judge. */
  waitedMs: number
  /** How long the judge had already run when the first request was ready. */
  leadMs: number
  decision?: Decision
  /** A cost tip for this turn's job, when one is worth giving. */
  tip: string | null
  verdictEffort?: Effort
  menuModel?: string
  usage: Usage
  contextTokens: number
  ran?: string
  isFailed?: boolean
}

type StepEvent = { model: string; effort?: unknown }

export const CACHE_TTL_MS = 60 * 60 * 1000 // Claude Code asks for the 1-hour prompt cache
const JUDGE_HARD_STOP_MS = 8000

const turns = new Map<string, Rec>()
const submitted = new Map<string, Pending>()
let last: { required: Tier; effort: Effort } | undefined
let warm: Warm = {}
let lowerStreak = 0
let seen: StepEvent | undefined
let isSwitchNoted = false
let turnCount = 0
let offeredBand = -1

/** The prompt cache as last seen, per tier. */
export const warmNow = (): Warm => warm
export const turnOf = (turnId: string): Rec | undefined => turns.get(turnId)
/** A model switch the engine reported; the step-0 comparison then stays quiet. */
export const noteSwitch = (): void => {
  isSwitchNoted = true
}

/** The judges this setup tries, in order. */
export const chainOf = (o: Options): readonly ('jev' | 'haiku')[] => (o.useJev ? ['jev', 'haiku'] : ['haiku'])

export async function isPrivateHere($: EngineInterface, o: Options): Promise<boolean> {
  if (o.privacy) return true
  if (!o.privateFolders.trim()) return false
  return isPrivateFolder(await $.session.cwd(), o.privateFolders, (await $.env.get('HOME')) ?? '')
}

/** Whether this prompt needs a verdict at all: not a follow-up, not fully chosen by the person. */
function needsJudge(f: PilotFlags, text: string): boolean {
  if (isFollowUp(text) && last !== undefined) return false
  const x = explicitChoice(text)
  return !((f.isModelPinned || x.tier !== undefined) && (f.isEffortPinned || x.effort !== undefined))
}

function startJudge($: EngineInterface, o: Options, text: string, at: number): Pending {
  const pending: Pending = { at, judged: Promise.resolve(undefined) }
  pending.judged = (async () => {
    const isPrivate = await isPrivateHere($, o)
    const [usage, model, recent] = await Promise.all([
      $.session.usage(),
      $.session.model(),
      isPrivate ? '' : recentDigest($, text),
    ])
    pending.input = { prompt: text, recent, contextTokens: usage.context.tokens ?? 0, currentTier: tierOf(model) ?? 'sonnet', kind: 'prompt' }
    return judge($, pending.input, { isPrivate, budgetMs: JUDGE_HARD_STOP_MS, model: o.judgeModel, chain: chainOf(o) })
  })().catch(() => undefined)
  return pending
}

/** At `prompt.submit`: start the judge at once, so it runs while the turn is set up. */
export async function prestart($: EngineInterface, o: Options, f: PilotFlags, text: string): Promise<void> {
  if (!needsJudge(f, text)) return
  const at = await $.clock.now()
  for (const [key, p] of submitted) if (at - p.at > 120_000) submitted.delete(key)
  submitted.set(text, startJudge($, o, text, at))
}

/** At `turn.start`: bind the prompt to its turn; start the judge if nothing did. */
export async function begin($: EngineInterface, o: Options, f: PilotFlags, turnId: string, text: string): Promise<void> {
  const t0 = await $.clock.now()
  const early = submitted.get(text)
  submitted.delete(text)
  const rec: Rec = {
    text,
    t0,
    explicit: explicitChoice(text),
    isSticky: isFollowUp(text) && last !== undefined,
    isFirst: turnCount === 0,
    pending: early ?? (needsJudge(f, text) ? startJudge($, o, text, t0) : undefined),
    waitedMs: 0,
    leadMs: 0,
    tip: null,
    usage: {},
    contextTokens: 0,
  }
  turnCount += 1
  turns.set(turnId, rec)
  if (turns.size > 16) turns.delete(turns.keys().next().value as string)
}

/** The verdict for the turn: the judge's if it is back in time, else the rules, kept at or above the menu's tier. */
async function verdictFor($: EngineInterface, o: Options, rec: Rec, menuTier: Tier): Promise<{ verdict: Verdict; source: 'judge' | 'rules' | 'sticky' }> {
  if (rec.isSticky && last) {
    return { verdict: { tier: last.required, effort: last.effort, confidence: 1, reason: 'follow-up: same as the work before' }, source: 'sticky' }
  }
  const input: JudgeInput = rec.pending?.input ?? { prompt: rec.text, recent: '', contextTokens: 0, currentTier: menuTier, kind: 'prompt' }
  let fail = 'not asked'
  if (rec.pending) {
    const from = await $.clock.now()
    rec.leadMs = from - rec.pending.at
    const waitMs = rec.isFirst ? Math.min(o.judgeBudgetMs * 2, o.judgeBudgetMs + 1500) : o.judgeBudgetMs // a session's first call is cold
    const got = await Promise.race([rec.pending.judged, $.clock.sleep(waitMs).then(() => 'late' as const)])
    rec.waitedMs = (await $.clock.now()) - from
    if (got !== 'late' && got !== undefined) {
      rec.judgedOut = got
      if (got.source === 'judge') return { verdict: got.verdict, source: 'judge' }
      fail = got.fail ?? 'failed'
    } else {
      fail = got === 'late' ? 'timeout' : 'failed'
      rec.judgedOut = { verdict: rulesVerdict(input), source: 'rules', by: 'rules', ms: rec.waitedMs, fail }
    }
  }
  const rules = rulesVerdict(rec.pending?.input ?? input)
  const tier = rulesFloor(rules.tier, menuTier)
  const why = fail === 'privacy' ? 'privacy mode' : `judge ${fail}`
  const reason = tier === rules.tier ? `${rules.reason} (${why})` : `${why}: menu model kept`
  return { verdict: { ...rules, tier, reason }, source: 'rules' }
}

/**
 * At the turn's first model request: what the menu changed since the last turn
 * (a pin), then the decision. Returns the flags to store when they changed.
 */
export async function settle($: EngineInterface, o: Options, f: PilotFlags, rec: Rec, e: StepEvent): Promise<{ decision: Decision; flags?: PilotFlags }> {
  let flags: PilotFlags | undefined
  if (seen) {
    const hasModelMoved = seen.model !== e.model
    if (hasModelMoved && !isSwitchNoted && !f.isModelPinned) flags = { ...f, isModelPinned: true }
    const hasEffortMoved = !hasModelMoved && seen.effort !== undefined && e.effort !== undefined && seen.effort !== e.effort
    if (hasEffortMoved && !f.isEffortPinned) flags = { ...(flags ?? f), isEffortPinned: true }
  }
  seen = { model: e.model, effort: e.effort }
  isSwitchNoted = false
  const now = flags ?? f

  rec.menuModel = e.model
  const menuTier = tierOf(e.model) ?? 'sonnet'
  const { verdict, source } = await verdictFor($, o, rec, menuTier)
  rec.verdictEffort = verdict.effort
  const cache = { contextTokens: (await $.session.usage()).context.tokens ?? 0, warm, now: await $.clock.now(), cacheTtlMs: CACHE_TTL_MS }
  const decision = decide({
    verdict,
    source,
    explicit: rec.explicit,
    menuTier,
    isModelPinned: now.isModelPinned,
    isEffortPinned: now.isEffortPinned,
    ...cache,
    lowerStreak,
    canUpgrade: o.allowUpgrade,
  })
  rec.tip = source === 'sticky' ? null : placeTip(decision.required, decision.tier ?? menuTier, cache)
  return { decision, flags }
}

/** After each model request of the turn: what it cost and which model answered. */
export function record(rec: Rec, usage: (Usage & { model?: string }) | null | undefined): void {
  if (!usage) return
  rec.usage = addUsage(rec.usage, usage)
  if (usage.model) rec.ran = usage.model
  rec.contextTokens = (usage.input_tokens ?? 0) + (usage.cache_read_input_tokens ?? 0) + (usage.cache_creation_input_tokens ?? 0)
}

/** At `turn.complete`: read what ran from the transcript, log it, build the row. */
export async function finish($: EngineInterface, o: Options, turnId: string, rec: Rec): Promise<PilotView | undefined> {
  turns.delete(turnId)
  const d = rec.decision
  if (!d) return undefined
  const now = await $.clock.now()
  const session = await $.session.id()
  const row = await readRan($, session, rec.t0 - 2000).catch(() => undefined)
  const ranModel = row?.model ?? rec.ran ?? null
  const menuTier = tierOf(rec.menuModel) ?? 'sonnet'
  const ranTier = tierOf(ranModel ?? undefined) ?? menuTier
  const isMismatch = !o.isShadow && (rec.isFailed === true || (ranModel !== null && d.tier !== undefined && tierOf(ranModel) !== d.tier))

  if (ranModel !== null) {
    warm = { ...warm, [ranTier]: { at: now, tokens: rec.contextTokens } }
    lowerStreak = TIERS.indexOf(d.required) < TIERS.indexOf(ranTier) ? lowerStreak + 1 : 0
  }
  if (rec.verdictEffort) last = { required: d.required, effort: rec.verdictEffort }

  let handoffTokens: number | null = null
  const threshold = handoffThreshold(o.handoff, (await $.session.usage()).context.window)
  if (threshold > 0) {
    const band = handoffBand(rec.contextTokens, threshold)
    if (band > offeredBand) handoffTokens = rec.contextTokens
    offeredBand = Math.max(offeredBand, band)
  }

  const j = rec.judgedOut
  const ranFrom = row ? 'transcript' : ranModel ? 'api' : null
  await appendLog($, {
    ts: new Date(now).toISOString(),
    session,
    kind: 'turn',
    picked: d.tier ?? null,
    picked_effort: d.effort ?? null,
    required: d.required,
    menu: rec.menuModel ?? null,
    actual: ranModel,
    actual_from: ranFrom,
    mismatch: isMismatch,
    source: d.source,
    shadow: o.isShadow,
    reason: d.reason,
    confidence: d.confidence,
    judge: j?.by ?? null,
    judge_ms: j?.ms ?? 0,
    judge_wait_ms: rec.waitedMs,
    judge_lead_ms: rec.leadMs,
    judge_fail: j?.fail ?? null,
    est_saving_usd: ranModel === null ? 0 : estSavingUsd(rec.usage, menuTier, ranTier, j?.usage),
    // In shadow mode nothing was applied: what the pick would have saved on the same tokens.
    est_saving_if_applied_usd: o.isShadow && d.tier ? estSavingUsd(rec.usage, menuTier, d.tier, undefined) : null,
    usage: rec.usage,
    place_tip: rec.tip,
    prompt_chars: rec.text.length,
  }).catch(() => undefined)

  return { pickedTier: d.tier ?? null, requestedEffort: d.effort ?? null, ranModel, ranFrom, isMismatch, isShadow: o.isShadow, source: d.source, judge: j?.by ?? null, reason: d.reason, tip: rec.tip, handoffTokens }
}
