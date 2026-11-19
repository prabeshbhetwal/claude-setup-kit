// Anthropic's order for model and effort, as one pure step of the decision:
// more care (effort) before a bigger model, and checkable work at low effort first.
import type { Effort, Tier, Verdict } from './policy'

const ORDER: readonly Effort[] = ['low', 'medium', 'high', 'xhigh']
const TIER_ORDER: readonly Tier[] = ['haiku', 'sonnet', 'opus', 'fable']

/** One effort level higher, at most xhigh (the pilot never picks max). xhigh for one turn is what `ultrathink` does. */
export const effortAbove = (e: Effort): Effort => ORDER[Math.min(ORDER.length - 1, ORDER.indexOf(e) + 1)] ?? 'xhigh'

export type Steer = {
  /** Run on this tier instead of the judged one (the menu's, with more effort). */
  stayOn?: Tier
  effort: Effort
  note?: string
}

/** Words that report a failed check after a turn that tried at low effort. */
export const FAILED_CHECK = /\b(fail(?:s|ed|ing|ure)?|(?:an?|the|same|still an?) error|errors? (?:again|still)|broken|still (?:not|wrong|fails?)|(?:does|did)n'?t work|not working|(?:is|was|it's|still) wrong)\b/i

/**
 * - After a checkable turn at low effort, a report that the check failed re-runs at high.
 * - "Care, not knowledge" one tier above the menu's model: stay on the menu's model one
 *   effort level up (its cache stays warm; an effort change keeps the cache).
 * - Checkable work (tests, a build, a verifier) from sonnet up: low effort first.
 */
export function steer(v: Verdict, required: Tier, menuTier: Tier, isJudged: boolean, isRetry: boolean): Steer {
  if (isRetry) {
    const effort: Effort = ORDER.indexOf(v.effort) > ORDER.indexOf('high') ? v.effort : 'high'
    return { effort, note: 'the check failed after a low-effort try: re-run at high effort' }
  }
  if (!isJudged) return { effort: v.effort }
  const isOneAbove = TIER_ORDER.indexOf(required) === TIER_ORDER.indexOf(menuTier) + 1
  if (v.gap === 'care' && isOneAbove && menuTier !== 'haiku') {
    const effort = effortAbove(v.effort)
    return { stayOn: menuTier, effort, note: `needs care, not more knowledge: ${menuTier} at ${effort} effort instead of ${required}` }
  }
  if (v.checkable && required !== 'haiku' && v.gap !== 'knowledge') {
    return { effort: 'low', note: 'checkable: low effort first, high if the check fails' }
  }
  return { effort: v.effort }
}
