// model-pilot prices and usage maths. Pure; every dollar figure is an estimate.
import type { Tier } from './policy'

type Rate = { in: number; out: number; cacheRead: number; cacheWrite: number }

// US dollars per million tokens, Anthropic first-party list prices as of 2026-11-16.
// Claude Code asks for the 1-hour prompt cache, so a cache write costs 2x input.
// Haiku 5.5 has two rate cards: prompts over 100K tokens pay 5x. Sonnet 5.5 reads cache at 0.05x. Checked against the
// engine's own cost figure (total_cost_usd) on live runs: see eval/live/README.md.
// shortcut: a static table, update when list prices change; every figure built on it is an estimate.
const BASE: Record<Tier, { in: number; out: number; cacheRead: number }> = {
  haiku: { in: 0.1, out: 0.5, cacheRead: 0.01 },
  sonnet: { in: 2, out: 10, cacheRead: 0.1 },
  opus: { in: 4, out: 20, cacheRead: 0.2 },
  fable: { in: 8, out: 40, cacheRead: 0.2 },
}
const HAIKU_LONG = { in: 0.5, out: 2.5, cacheRead: 0.05 }
export const HAIKU_LONG_PROMPT = 100_000
const TIER_LIST = Object.keys(BASE) as Tier[]

/** The rate card for one request on `tier` whose prompt holds `promptTokens`. */
export function rateOf(tier: Tier, promptTokens: number): Rate {
  const b = tier === 'haiku' && promptTokens > HAIKU_LONG_PROMPT ? HAIKU_LONG : BASE[tier]
  return { ...b, cacheWrite: b.in * 2 }
}

export type Usage = {
  input_tokens?: number
  output_tokens?: number
  cache_read_input_tokens?: number
  cache_creation_input_tokens?: number
}

export const promptOf = (u: Usage): number =>
  (u.input_tokens ?? 0) + (u.cache_read_input_tokens ?? 0) + (u.cache_creation_input_tokens ?? 0)

/** What ONE request's token counts cost on a tier, in US dollars. Sum per request, never price a sum. */
export function priceOf(u: Usage, tier: Tier): number {
  const p = rateOf(tier, promptOf(u))
  return (
    ((u.input_tokens ?? 0) * p.in +
      (u.output_tokens ?? 0) * p.out +
      (u.cache_read_input_tokens ?? 0) * p.cacheRead +
      (u.cache_creation_input_tokens ?? 0) * p.cacheWrite) /
    1e6
  )
}

export type Costs = Record<Tier, number>
export const noCosts = (): Costs => ({ haiku: 0, sonnet: 0, opus: 0, fable: 0 })

/**
 * The first request of a turn as another tier would have sent it: the cached part of
 * the prompt is a cheap read if that tier's cache is warm, else written afresh.
 * shortcut: assumes a warm cache holds the whole prompt; fine while turns grow the chat a little at a time.
 */
export function asIfOn(u: Usage, isWarm: boolean): Usage {
  const cached = (u.cache_read_input_tokens ?? 0) + (u.cache_creation_input_tokens ?? 0)
  return { ...u, cache_read_input_tokens: isWarm ? cached : 0, cache_creation_input_tokens: isWarm ? 0 : cached }
}

/** Adds one request's cost, priced on every tier, to a turn's running totals. */
export function addCosts(c: Costs, u: Usage): Costs {
  const out = { ...c }
  for (const t of TIER_LIST) out[t] += priceOf(u, t)
  return out
}

export function addUsage(a: Usage, b: Usage | null | undefined): Usage {
  if (!b) return a
  return {
    input_tokens: (a.input_tokens ?? 0) + (b.input_tokens ?? 0),
    output_tokens: (a.output_tokens ?? 0) + (b.output_tokens ?? 0),
    cache_read_input_tokens: (a.cache_read_input_tokens ?? 0) + (b.cache_read_input_tokens ?? 0),
    cache_creation_input_tokens:
      (a.cache_creation_input_tokens ?? 0) + (b.cache_creation_input_tokens ?? 0),
  }
}

/**
 * Estimated saving against the menu model: the turn's requests priced on the menu
 * tier minus on the tier that ran, minus the Haiku judge call. An estimate: a different
 * model would have had different cache hits and written different output.
 */
export function estSavingUsd(c: Costs, menu: Tier, ran: Tier, judge: Usage | undefined): number {
  const saving = c[menu] - c[ran] - (judge ? priceOf(judge, 'haiku') : 0)
  return Math.round(saving * 1e6) / 1e6
}
