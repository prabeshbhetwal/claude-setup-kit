// model-pilot's `/pilot` texts: where things stand, and what a job costs in each place. Pure.
import { placeCosts, STARTUP, TIERS } from './policy'
import type { Place, Tier, Warm } from './policy'
import type { PilotFlags, PilotView } from '../types'
import { PRICES_AS_OF } from './prices'

export const HELP = 'Usage: /pilot on | off | auto | status | cost. "auto" hands a model or effort you picked in the menu back to the pilot.'

export type StatusInput = {
  isEnabled: boolean
  isPrivacy: boolean
  isShadow: boolean
  chain: readonly string[]
  handoff: string
  f: PilotFlags
  v: PilotView | null
}

export function statusText(a: StatusInput): string {
  const { f, v } = a
  const offer = a.handoff === 'never' ? 'never' : a.handoff === 'auto' ? 'auto (500k tokens on a 1M window, else 250k)' : `at ${a.handoff} tokens`
  return [
    `Model pilot: ${!a.isEnabled ? 'off in settings' : f.isOn ? 'on' : 'off'}${a.isShadow ? ', shadow mode (nothing is changed)' : ''}`,
    `Judges, in order: ${a.isPrivacy ? 'rules only (privacy mode)' : [...a.chain, 'rules'].join(', then ')}. Jev is used only when its command and key are present.`,
    `Model: ${f.isModelPinned ? 'yours (set in the menu)' : 'picked by the pilot'}. Effort: ${f.isEffortPinned ? 'yours (set in the menu)' : 'picked by the pilot'}.`,
    v
      ? `Last turn: picked ${v.pickedTier ?? 'nothing (menu model)'}, effort ${v.requestedEffort ?? 'menu'} (requested), ran ${v.ranModel ?? 'unknown'}${v.judge ? `, judged by ${v.judge}` : ''}. ${v.reason}`
      : 'No turn judged yet.',
    ...(v?.tip ? [`Tip: ${v.tip}.`] : []),
    `Fresh-chat offer: ${offer}.`,
    `Cost figures are estimates from list prices as of ${PRICES_AS_OF}.`,
    'Log: ~/.claude/mods-logs/model-pilot.jsonl',
    HELP,
  ].join('\n')
}

const usd = (n: number): string => `$${n < 0.1 ? n.toFixed(3) : n.toFixed(2)}`
const PLACES: readonly Place[] = ['in place', 'lean sub-agent', 'all-tools sub-agent', 'new session']
const JOB: Record<Tier, string> = { haiku: 'small (a few lookups)', sonnet: 'scoped build', opus: 'hard problem', fable: 'huge job' }

/** Estimated cost of a typical job of each size, in each place, for the chat as it stands. */
export function costText(contextTokens: number, runTier: Tier, warm: Warm, now: number, cacheTtlMs: number): string {
  const rows = TIERS.map(t => {
    const c = placeCosts(t, runTier, { contextTokens, warm, now, cacheTtlMs })
    const best = PLACES.reduce((a, b) => (c[b] < c[a] ? b : a))
    return `| ${JOB[t]} on ${t} | ${PLACES.map(p => (p === best ? `**${usd(c[p])}**` : usd(c[p]))).join(' | ')} |`
  })
  const lean = STARTUP['lean sub-agent'] / 1000
  const full = STARTUP['all-tools sub-agent'] / 1000
  const fresh = STARTUP['new session'] / 1000
  return [
    `Estimated cost of one job, by where it runs. This chat holds ${Math.round(contextTokens / 1000)}k tokens on ${runTier}.`,
    '',
    `| Job | ${PLACES.join(' | ')} |`,
    '|---|---|---|---|---|',
    ...rows,
    '',
    `In place: no start-up, but every step re-reads this chat. A sub-agent loads its own context once (about ${lean}k tokens for a lean agent such as haiku-lean or sonnet-lean, about ${full}k for an all-tools agent) and this chat pays two steps, for the hand-off and the report. A new session loads about ${fresh}k.`,
    "Rule of thumb: a few lookups are cheaper in place; a big, tool-heavy job is cheaper in a lean sub-agent. Start-up sizes were measured on the author's setup; every figure is an estimate.",
  ].join('\n')
}
