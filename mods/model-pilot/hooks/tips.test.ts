import { expect, test } from 'claude-code/testing'

import { placeCosts, placeTip, spawnNote } from './policy'
import type { Tier } from './policy'

const HOUR = 3_600_000
/** A chat with `tokens` of context, warm on `tier` (or cold). */
const chat = (tokens: number, tier?: Tier) => ({
  contextTokens: tokens,
  now: HOUR,
  cacheTtlMs: HOUR,
  warm: tier ? { [tier]: { at: HOUR - 1000, tokens } } : {},
})
const ratio = (a: number, b: number): number => a / b

test('the tip stays quiet when the lean sub-agent saves only 10 to 30 percent', async () => {
  const c = chat(120_000, 'sonnet')
  const p = placeCosts('sonnet', 'sonnet', c)
  const r = ratio(p['lean sub-agent'], p['in place'])
  expect(r > 0.7 && r < 0.9).toBe(true) // the fixture sits between the real threshold and a looser one
  expect(p['in place'] - p['lean sub-agent'] >= 0.02).toBe(true) // so only the ratio holds it back
  expect(placeTip('sonnet', 'sonnet', c)).toBe(null)
  expect(placeTip('sonnet', 'opus', chat(120_000, 'opus'))?.startsWith('lean sub-agent')).toBe(true) // a bigger saving still speaks
})

test('a sub-agent note stays quiet when in place is only 10 to 30 percent cheaper', async () => {
  const lean = placeCosts('sonnet', 'sonnet', chat(40_000, 'sonnet'))
  const rl = ratio(lean['in place'], lean['lean sub-agent'])
  expect(rl > 0.7 && rl < 0.9 && lean['lean sub-agent'] - lean['in place'] >= 0.02).toBe(true)
  expect(spawnNote('sonnet-lean', 'sonnet', 'sonnet', chat(40_000, 'sonnet'))).toBe(null)
  const all = placeCosts('sonnet', 'sonnet', chat(90_000))
  const ra = ratio(all['in place'], all['all-tools sub-agent'])
  expect(ra > 0.7 && ra < 0.9 && all['all-tools sub-agent'] - all['in place'] >= 0.02).toBe(true)
  expect(spawnNote('general-purpose', 'sonnet', 'sonnet', chat(90_000))).toBe(null)
})

test('a sub-agent note stays quiet when the whole difference is under two cents', async () => {
  // A haiku job: in place is far cheaper by ratio, but the gap is a fraction of a cent.
  const lean = placeCosts('haiku', 'haiku', chat(0))
  expect(lean['in place'] < lean['lean sub-agent'] * 0.7 && lean['lean sub-agent'] - lean['in place'] < 0.02).toBe(true)
  expect(spawnNote('sonnet-lean', 'haiku', 'haiku', chat(0))).toBe(null)
  const all = placeCosts('haiku', 'haiku', chat(40_000))
  expect(all['in place'] < all['all-tools sub-agent'] * 0.7 && all['all-tools sub-agent'] - all['in place'] < 0.02).toBe(true)
  expect(spawnNote('general-purpose', 'haiku', 'haiku', chat(40_000))).toBe(null)
})

test('a sub-agent name of 18 characters is kept whole, a longer one is cut to 17 and an ellipsis', async () => {
  const c = chat(40_000, 'sonnet')
  const eighteen = 'abcdefghijklmnopqr'
  expect(spawnNote(eighteen, 'sonnet', 'sonnet', c)?.startsWith(`${eighteen} cost ~$`)).toBe(true)
  const long = 'abcdefghijklmnopqrs' // 19
  const note = spawnNote(long, 'sonnet', 'sonnet', c)
  expect(note?.startsWith('abcdefghijklmnopq… cost ~$')).toBe(true)
  expect(note?.includes('abcdefghijklmnopqr')).toBe(false)
})
