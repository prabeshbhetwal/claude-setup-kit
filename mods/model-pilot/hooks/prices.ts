// model-pilot prices and usage maths. Pure; every dollar figure is an estimate.
import type { Tier } from './policy'

// US dollars per million tokens, Anthropic first-party list prices as of 2026-11-03.
// Cache write is assumed at 1.25x input (5-minute rate); Haiku cache read at 0.1x input.
// shortcut: a static table, update when list prices change; every figure built on it is an estimate.
export const PRICES: Record<Tier, { in: number; out: number; cacheRead: number; cacheWrite: number }> = {
  haiku: { in: 0.1, out: 0.5, cacheRead: 0.01, cacheWrite: 0.125 },
  sonnet: { in: 2, out: 10, cacheRead: 0.1, cacheWrite: 2.5 },
  opus: { in: 4, out: 20, cacheRead: 0.2, cacheWrite: 5 },
  fable: { in: 8, out: 40, cacheRead: 0.2, cacheWrite: 10 },
}

export type Usage = {
  input_tokens?: number
  output_tokens?: number
  cache_read_input_tokens?: number
  cache_creation_input_tokens?: number
}

/** What the given token counts cost on a tier, in US dollars. */
export function priceOf(u: Usage, tier: Tier): number {
  const p = PRICES[tier]
  return (
    ((u.input_tokens ?? 0) * p.in +
      (u.output_tokens ?? 0) * p.out +
      (u.cache_read_input_tokens ?? 0) * p.cacheRead +
      (u.cache_creation_input_tokens ?? 0) * p.cacheWrite) /
    1e6
  )
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
 * Estimated saving against the menu model: the same tokens priced on the menu
 * tier minus what ran, minus the judge call. An estimate: a different model
 * would have had different cache hits and written different output.
 */
export function estSavingUsd(u: Usage, menu: Tier, ran: Tier, judge: Usage | undefined): number {
  const saving = priceOf(u, menu) - priceOf(u, ran) - (judge ? priceOf(judge, 'haiku') : 0)
  return Math.round(saving * 1e6) / 1e6
}
