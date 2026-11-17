// Output tokens per model request, by model tier and effort. Pure.
import type { Effort, Tier } from './policy'

/**
 * Mean output tokens (thinking included) per main-thread request, from 440 Claude Code
 * transcripts on the author's machine, October to November 2026 (engine 2.1.325).
 * Observational: harder tasks get higher effort, so the step from one effort to the next
 * is an upper bound on what effort alone adds. Cells marked `est` had under 20 requests
 * and are filled from the neighbouring cells.
 */
export const OUT_PER_STEP: Record<Tier, Record<Effort, number>> = {
  haiku: { low: 160, medium: 330, high: 500 /* est */, xhigh: 700 /* est */ },
  sonnet: { low: 200, medium: 890, high: 1050 /* est */, xhigh: 1250 /* est */ },
  opus: { low: 650, medium: 680, high: 810, xhigh: 900 },
  fable: { low: 520, medium: 940, high: 1220, xhigh: 2350 },
}

const ORDER: readonly Effort[] = ['low', 'medium', 'high', 'xhigh']

/** Output tokens per request at an effort; 'max' counts as xhigh, none as medium. */
export const outPerStep = (tier: Tier, effort: Effort | 'max' | undefined): number =>
  OUT_PER_STEP[tier][effort === 'max' ? 'xhigh' : effort ?? 'medium']

/** One effort level lower, never under low: what a stronger model needs for the same job. */
export const effortBelow = (e: Effort): Effort => ORDER[Math.max(0, ORDER.indexOf(e) - 1)] ?? 'low'
