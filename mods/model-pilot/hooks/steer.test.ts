import { expect, test } from 'claude-code/testing'

import { decide } from './policy'
import type { DecideInput, Verdict } from './policy'
import { effortAbove, FAILED_CHECK, steer } from './steer'

const v = (o: Partial<Verdict> = {}): Verdict => ({ tier: 'opus', effort: 'medium', confidence: 0.9, reason: 'r', ...o })
const base = (over: Partial<DecideInput>): DecideInput => ({
  verdict: v(), source: 'judge', explicit: {}, menuTier: 'sonnet', isModelPinned: false, isEffortPinned: false,
  contextTokens: 50_000, warm: {}, now: 0, cacheTtlMs: 3_600_000, lowerStreak: 0, canUpgrade: true, ...over,
})

test('care, not knowledge, one tier above the menu: stay on the menu model, one effort up', async () => {
  const d = decide(base({ verdict: v({ gap: 'care' }) }))
  expect(d.tier).toBe('sonnet')
  expect(d.effort).toBe('high')
  // Knowledge goes up a model as before.
  expect(decide(base({ verdict: v({ gap: 'knowledge' }) })).tier).toBe('opus')
  // Two tiers up, or on haiku, effort alone is not enough.
  expect(decide(base({ verdict: v({ gap: 'care', tier: 'fable' }) })).tier).toBe('fable')
  expect(decide(base({ verdict: v({ gap: 'care', tier: 'sonnet' }), menuTier: 'haiku' })).tier).toBe('sonnet')
  expect(effortAbove('xhigh')).toBe('xhigh')
})

test('checkable work tries low first; a reported failure re-runs at high', async () => {
  expect(decide(base({ verdict: v({ tier: 'sonnet', checkable: true }) })).effort).toBe('low')
  expect(decide(base({ verdict: v({ tier: 'sonnet', checkable: true, gap: 'knowledge' }) })).effort).toBe('medium')
  expect(decide(base({ verdict: v({ tier: 'haiku', checkable: true }) })).effort).toBe('medium')
  expect(decide(base({ verdict: v({ tier: 'sonnet' }), isRetry: true })).effort).toBe('high')
  expect(steer(v({ effort: 'xhigh' }), 'opus', 'opus', true, true).effort).toBe('xhigh')
  expect(FAILED_CHECK.test('the tests still fail')).toBe(true)
  expect(FAILED_CHECK.test('great, thanks')).toBe(false)
})

test('rules and sticky verdicts are not steered, and the person\'s choices win', async () => {
  expect(decide(base({ verdict: v({ gap: 'care' }), source: 'rules' })).tier).toBe('opus')
  expect(decide(base({ verdict: v({ tier: 'sonnet', checkable: true }), explicit: { effort: 'high' } })).effort).toBe('high')
})
