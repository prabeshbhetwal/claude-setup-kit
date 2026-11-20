import { expect, test } from 'claude-code/testing'

import { mergePings } from './pings'
import { record } from './route'
import type { Rec } from './route'

test('a later ping moves only its own tier forward, and never invents a tier', async () => {
  const warm = { opus: { at: 1_000, tokens: 90_000 }, haiku: { at: 5_000, tokens: 40_000 } }
  const out = mergePings(warm, { 'claude-opus-5-5': 9_000, 'claude-haiku-5-5': 2_000, 'claude-sonnet-5-5': 9_000 })
  expect(out.opus, 'opus ping is later: moved').toEqual({ at: 9_000, tokens: 90_000 })
  expect(out.haiku, 'haiku ping is older: kept').toEqual({ at: 5_000, tokens: 40_000 })
  expect(out.sonnet, 'no sonnet entry to move').toBeUndefined()
  expect(mergePings(warm, {}), 'no pings: unchanged').toBe(warm)
})

test('record keeps when the answered request went out', async () => {
  const rec = { usage: {}, contextTokens: 0 } as unknown as Rec
  record(rec, null, 7_000)
  expect(rec.sentAt, 'no response: not a cache read').toBeUndefined()
  record(rec, { input_tokens: 1, model: 'claude-opus-5-5' }, 7_000)
  expect(rec.sentAt, 'answered: the send time').toBe(7_000)
})
