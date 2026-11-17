// The question model-pilot asks before a turn it would run on Fable. Pure.
import type { Decision, Effort } from './policy'

export const RUN_FABLE = 'Run on Fable'
export const FABLE_CHAT = 'Fable for this chat'
export const USE_OPUS = 'Use Opus instead'

const WHY_EFFORT: Record<Effort | 'max', string> = {
  low: 'a short job, so little thinking is needed',
  medium: 'a normal job: some planning, no long search for the answer',
  high: 'several steps to reason through, where extra thinking pays for itself',
  xhigh: 'a long, hard problem where thinking more now prevents costly mistakes',
  max: 'the hardest kind of problem; every bit of thinking counts',
}

/** Whether this decision needs the person's yes: the pilot chose Fable, the menu did not. */
export function needsFableYes(d: Decision, menuTier: string, isShadow: boolean, isAsked: boolean): boolean {
  return isAsked && !isShadow && d.tier === 'fable' && menuTier !== 'fable' && d.source !== 'explicit' && d.source !== 'pinned'
}

const usd = (n: number): string => `$${n < 0.1 ? n.toFixed(3) : n.toFixed(2)}`

/** The question: why Fable, the effort and why that effort is enough, and the cost against Opus. */
export function fableQuestion(d: Decision, fableUsd: number, opusUsd: number): string {
  const effort = d.effort ?? 'medium'
  return [
    `Model pilot would run this prompt on Fable: ${d.reason}.`,
    `Effort ${effort}: ${WHY_EFFORT[effort]}.`,
    `Estimated cost of this turn: about ${usd(fableUsd)} on Fable, ${usd(opusUsd)} on Opus (on some plans Fable draws on usage credits).`,
    'Run it on Fable?',
  ].join(' ')
}

/** The decision after the answer; anything but a yes (no answer, a dismissed dialog, free text) runs on Opus. */
export function afterAnswer(d: Decision, answer: string | undefined): Decision {
  if (answer === RUN_FABLE || answer === FABLE_CHAT) return d
  return { ...d, tier: 'opus', reason: `${d.reason} (${answer === USE_OPUS ? 'you chose Opus' : 'no answer to the Fable question'}: Opus instead)` }
}
