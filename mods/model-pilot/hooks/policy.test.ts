import { expect, test } from 'claude-code/testing'

import { agentFileNamesModel, agentTier, decide, estTurnCost, handoffBand, handoffThreshold, isPrivateFolder, placeCosts, placeTip, rulesFloor, spawnNote, tierOf, tierUp } from './policy'
import type { DecideInput, Verdict } from './policy'
import { addCosts, asIfOn, estSavingUsd, noCosts, priceOf } from './prices'

const near = (a: number, b: number): boolean => Math.abs(a - b) < 1e-7

const verdict = (tier: Verdict['tier'], confidence = 0.9, effort: Verdict['effort'] = 'medium'): Verdict => ({ tier, effort, confidence, reason: 'r' })
const HOUR = 3_600_000
const base = (over: Partial<DecideInput>): DecideInput => ({
  verdict: verdict('sonnet'),
  source: 'judge',
  explicit: {},
  menuTier: 'opus',
  isModelPinned: false,
  isEffortPinned: false,
  contextTokens: 20_000,
  warm: {},
  now: 10 * HOUR,
  cacheTtlMs: HOUR,
  lowerStreak: 0,
  canUpgrade: true,
  ...over,
})

test('model ids and aliases map to tiers', async () => {
  expect(tierOf('claude-opus-5-5[1m]')).toBe('opus')
  expect(tierOf('haiku')).toBe('haiku')
  expect(tierOf('claude-mythos-5-2')).toBe('fable')
  expect(tierOf('gpt-9')).toBe(undefined)
  expect(tierOf(undefined)).toBe(undefined)
  expect(tierUp('haiku')).toBe('sonnet')
  expect(tierUp('opus', 'opus')).toBe('opus')
  expect(tierUp('fable', 'opus')).toBe('fable')
})

test('a cold conversation runs on the required tier', async () => {
  const d = decide(base({ verdict: verdict('haiku', 0.9, 'low') }))
  expect(d.tier).toBe('haiku')
  expect(d.effort).toBe('medium') // Haiku never runs at low
  expect(d.required).toBe('haiku')
})

test('an unsure judge goes one tier up, but not into fable', async () => {
  expect(decide(base({ verdict: verdict('haiku', 0.4) })).required).toBe('sonnet')
  expect(decide(base({ verdict: verdict('sonnet', 0.5) })).required).toBe('opus')
  expect(decide(base({ verdict: verdict('opus', 0.3) })).required).toBe('opus')
  expect(decide(base({ verdict: verdict('fable', 0.3) })).required).toBe('fable')
})

test('rules and sticky verdicts are not raised for confidence', async () => {
  expect(decide(base({ verdict: verdict('haiku', 0.5), source: 'rules' })).required).toBe('haiku')
  expect(decide(base({ verdict: verdict('sonnet', 0.1), source: 'sticky' })).required).toBe('sonnet')
})

test('never below the required tier, whatever the cache says', async () => {
  const d = decide(base({ verdict: verdict('opus'), menuTier: 'haiku', contextTokens: 200_000, warm: { haiku: { at: 10 * HOUR - 1000, tokens: 200_000 } } }))
  expect(d.tier).toBe('opus')
})

test('haiku over a very long context is raised to sonnet', async () => {
  expect(decide(base({ verdict: verdict('haiku'), contextTokens: 250_000 })).required).toBe('sonnet')
})

test('a big warm conversation stays put when the lower tier would cost more to load', async () => {
  // 150k tokens cached on opus: one sonnet turn would rewrite the whole cache.
  const d = decide(base({ verdict: verdict('sonnet'), contextTokens: 150_000, warm: { opus: { at: 10 * HOUR - 60_000, tokens: 150_000 } } }))
  expect(d.tier).toBe('opus')
  expect(d.required).toBe('sonnet')
  expect(d.reason.includes('cheaper')).toBe(true)
})

test('a short lookup in a long chat warm on opus stays on opus: re-writing 150k tokens on haiku costs more', async () => {
  const d = decide(base({ verdict: verdict('haiku'), contextTokens: 150_000, warm: { opus: { at: 10 * HOUR - 60_000, tokens: 150_000 } } }))
  expect(d.tier).toBe('opus')
})

test('in a small chat haiku is cheap enough to switch to even from a warm opus cache', async () => {
  const d = decide(base({ verdict: verdict('haiku'), contextTokens: 20_000, warm: { opus: { at: 10 * HOUR - 60_000, tokens: 20_000 } } }))
  expect(d.tier).toBe('haiku')
})

test('a lower need that persists is eventually worth the switch', async () => {
  const stay = base({ verdict: verdict('sonnet'), contextTokens: 30_000, warm: { opus: { at: 10 * HOUR - 60_000, tokens: 30_000 } } })
  expect(decide({ ...stay, lowerStreak: 0 }).tier).toBe('opus')
  expect(decide({ ...stay, lowerStreak: 3 }).tier).toBe('sonnet')
})

test('a saving counts the cache re-write a switch causes', async () => {
  const first = { input_tokens: 5, output_tokens: 300, cache_read_input_tokens: 150_000 }
  // Ran on opus, warm. Haiku would have written the 150k afresh on its long-prompt card.
  expect(priceOf(asIfOn(first, false), 'haiku') > priceOf(first, 'opus')).toBe(true)
  expect(near(priceOf(asIfOn(first, true), 'opus'), priceOf(first, 'opus'))).toBe(true)
})

test('an expired cache holds nobody', async () => {
  const d = decide(base({ verdict: verdict('sonnet'), contextTokens: 150_000, warm: { opus: { at: 10 * HOUR - 2 * HOUR, tokens: 150_000 } } }))
  expect(d.tier).toBe('sonnet')
})

test('a small cold conversation ignores the menu tier and takes the cheaper required one', async () => {
  expect(decide(base({ verdict: verdict('sonnet'), menuTier: 'fable', contextTokens: 5_000 })).tier).toBe('sonnet')
})

test('upgrades above the menu can be switched off', async () => {
  const up = base({ verdict: verdict('opus'), menuTier: 'sonnet' })
  expect(decide(up).tier).toBe('opus')
  const held = decide({ ...up, canUpgrade: false })
  expect(held.tier).toBe('sonnet')
  expect(held.required).toBe('opus')
  expect(held.reason.includes('upgrades are off')).toBe(true)
})

test('a model named in the prompt wins over everything', async () => {
  const d = decide(base({ verdict: verdict('opus'), explicit: { tier: 'haiku', effort: 'max' }, isModelPinned: true, isEffortPinned: true }))
  expect(d.tier).toBe('haiku')
  expect(d.effort).toBe('max')
  expect(d.source).toBe('explicit')
})

test('a menu pick is left alone: model pinned keeps the model, effort pinned keeps the effort', async () => {
  const model = decide(base({ verdict: verdict('haiku', 0.9, 'low'), isModelPinned: true }))
  expect(model.tier).toBe(undefined)
  expect(model.effort).toBe('medium') // haiku-level job: medium at least
  expect(model.source).toBe('pinned')
  const effort = decide(base({ verdict: verdict('haiku', 0.9, 'low'), isEffortPinned: true }))
  expect(effort.tier).toBe('haiku')
  expect(effort.effort).toBe(undefined)
})

test('the pilot never asks for max effort on its own', async () => {
  for (const t of ['haiku', 'sonnet', 'opus', 'fable'] as const) {
    expect(decide(base({ verdict: verdict(t, 0.9, 'xhigh') })).effort).toBe('xhigh')
  }
})

test('turn cost: a warm cache is a cheap read, a cold one a full write', async () => {
  const i = { contextTokens: 100_000, now: HOUR, cacheTtlMs: HOUR, warm: { opus: { at: HOUR - 1000, tokens: 100_000 } } }
  expect(estTurnCost('opus', 'haiku', i, 1) < estTurnCost('opus', 'haiku', { ...i, warm: {} }, 1)).toBe(true)
  expect(estTurnCost('haiku', 'haiku', i, 1) < estTurnCost('opus', 'haiku', i, 1)).toBe(true)
})

test('prices and the saving estimate', async () => {
  const short = { input_tokens: 50_000, output_tokens: 10_000 }
  expect(near(priceOf(short, 'opus'), 0.4)).toBe(true)
  expect(near(priceOf(short, 'haiku'), 0.01)).toBe(true)
  const c = addCosts(noCosts(), short)
  expect(estSavingUsd(c, 'opus', 'haiku', undefined)).toBe(0.39)
  expect(estSavingUsd(c, 'opus', 'opus', { input_tokens: 1000, output_tokens: 100 }) < 0).toBe(true)
  expect(estSavingUsd(c, 'sonnet', 'opus', undefined) < 0).toBe(true)
})

test('prices match what the engine billed on a live run (1-hour cache writes, Haiku long-prompt card)', async () => {
  // Two Haiku 5.5 requests from a live Claude Code run; the engine's total_cost_usd was 0.1241726.
  const r1 = { input_tokens: 2, output_tokens: 51, cache_read_input_tokens: 0, cache_creation_input_tokens: 117_772 }
  const r2 = { input_tokens: 2, output_tokens: 7, cache_read_input_tokens: 117_772, cache_creation_input_tokens: 365 }
  const c = addCosts(addCosts(noCosts(), r1), r2)
  expect(near(c.haiku, 0.1241726)).toBe(true)
  // Each request is priced on its own prompt: one long prompt must not push short ones onto the long card.
  expect(near(priceOf({ input_tokens: 90_000 }, 'haiku'), 0.009)).toBe(true)
  expect(near(priceOf({ input_tokens: 110_000 }, 'haiku'), 0.055)).toBe(true)
})

test('sub-agents: unsure goes up; an agent file that names a model is detected', async () => {
  expect(agentTier(verdict('haiku', 0.9), 'judge', 'opus')).toBe('haiku')
  expect(agentTier(verdict('haiku', 0.4), 'judge', 'opus')).toBe('sonnet')
  expect(agentTier(verdict('haiku', 0.4), 'rules', 'opus')).toBe('haiku')
  expect(agentTier(verdict('sonnet'), 'rules', 'opus')).toBe('opus')
  expect(agentFileNamesModel('---\nname: x\nmodel: opus\n---\nbody')).toBe(true)
  expect(agentFileNamesModel('---\nname: x\nmodel: "claude-haiku-5-5"\n---\n')).toBe(true)
  expect(agentFileNamesModel('---\nname: x\nmodel: inherit\n---\n')).toBe(false)
  expect(agentFileNamesModel('---\nname: x\ntools: Read\n---\nmodel: opus in the body')).toBe(false)
  expect(agentFileNamesModel('no frontmatter')).toBe(false)
})

test('without the judge, rules may drop to haiku for a lookup but never otherwise below the menu', async () => {
  expect(rulesFloor('haiku', 'opus')).toBe('haiku')
  expect(rulesFloor('sonnet', 'opus')).toBe('opus')
  expect(rulesFloor('opus', 'sonnet')).toBe('opus')
  expect(rulesFloor('sonnet', 'haiku')).toBe('sonnet')
})

test('private folders match the folder and what is under it, not its neighbours', async () => {
  expect(isPrivateFolder('/home/u/work/client-a/src', '~/work/client-a, /srv/secret', '/home/u')).toBe(true)
  expect(isPrivateFolder('/home/u/work/client-a', '~/work/client-a/', '/home/u')).toBe(true)
  expect(isPrivateFolder('/home/u/work/client-ab', '~/work/client-a', '/home/u')).toBe(false)
  expect(isPrivateFolder('/srv/secret/x', '~/work/client-a, /srv/secret', '/home/u')).toBe(true)
  expect(isPrivateFolder('/home/u', '', '/home/u')).toBe(false)
})

test('the handoff is offered once per 50k band above the threshold', async () => {
  expect(handoffBand(249_999, 250_000)).toBe(-1)
  expect(handoffBand(250_000, 250_000)).toBe(0)
  expect(handoffBand(299_999, 250_000)).toBe(0)
  expect(handoffBand(300_000, 250_000)).toBe(1)
})

test('the handoff threshold follows the setting, and auto follows the window', async () => {
  expect(handoffThreshold('250k', 1_000_000)).toBe(250_000)
  expect(handoffThreshold('750k', 200_000)).toBe(750_000)
  expect(handoffThreshold('never', 1_000_000)).toBe(0)
  expect(handoffThreshold('auto', 1_000_000)).toBe(500_000)
  expect(handoffThreshold('auto', 200_000)).toBe(250_000)
  expect(handoffThreshold('nonsense', 1_000_000)).toBe(500_000)
})

test('where a job is cheapest: small jobs in place, big tool-heavy jobs in a lean sub-agent', async () => {
  const chat = { contextTokens: 120_000, now: HOUR, cacheTtlMs: HOUR, warm: { opus: { at: HOUR - 1000, tokens: 120_000 } } }
  const small = placeCosts('haiku', 'opus', chat)
  expect(small['in place'] < small['lean sub-agent']).toBe(true)
  expect(small['in place'] < small['all-tools sub-agent']).toBe(true)
  const big = placeCosts('sonnet', 'opus', chat)
  expect(big['lean sub-agent'] < big['in place']).toBe(true)
  expect(big['lean sub-agent'] < big['all-tools sub-agent']).toBe(true)
  expect(big['lean sub-agent'] < big['new session']).toBe(true)
})

test('the tip speaks only when a lean sub-agent is clearly cheaper', async () => {
  const chat = { contextTokens: 120_000, now: HOUR, cacheTtlMs: HOUR, warm: { opus: { at: HOUR - 1000, tokens: 120_000 } } }
  expect(placeTip('haiku', 'opus', chat)).toBe(null)
  const tip = placeTip('sonnet', 'opus', chat)
  expect(tip?.startsWith('lean sub-agent ~$')).toBe(true)
  expect(`Tip: ${tip}`.length < 60).toBe(true)
  expect(placeTip('sonnet', 'sonnet', { ...chat, contextTokens: 3_000, warm: {} })).toBe(null)
})

test('a sub-agent spawned for a small job is noted, a fitting one is not', async () => {
  const chat = { contextTokens: 40_000, now: HOUR, cacheTtlMs: HOUR, warm: { sonnet: { at: HOUR - 1000, tokens: 40_000 } } }
  const note = spawnNote('general-purpose', 'sonnet', 'sonnet', chat)
  expect(note?.startsWith('general-purpose cost ~$')).toBe(true)
  expect(`Tip: ${note}`.length < 60).toBe(true) // the app clips long lines instead of wrapping them
  expect(spawnNote('sonnet-lean', 'sonnet', 'opus', { ...chat, contextTokens: 200_000, warm: { opus: { at: HOUR - 1000, tokens: 200_000 } } })).toBe(null)
})

test('staying on a warmer, stronger model lowers the effort one level instead of switching down', async () => {
  const warm = { opus: { at: 10 * HOUR - 60_000, tokens: 150_000 } }
  const d = decide(base({ verdict: verdict('sonnet', 0.9, 'high'), contextTokens: 150_000, warm }))
  expect(d.tier).toBe('opus')
  expect(d.effort).toBe('medium')
  // The person's own effort is never lowered.
  expect(decide(base({ verdict: verdict('sonnet', 0.9, 'high'), contextTokens: 150_000, warm, explicit: { effort: 'high' } })).effort).toBe('high')
  // On the required tier itself, the judged effort stands.
  expect(decide(base({ verdict: verdict('sonnet', 0.9, 'high'), menuTier: 'sonnet' })).effort).toBe('high')
})

test('turn cost follows effort: more thinking is dearer on the same tier', async () => {
  const i = { contextTokens: 100_000, warm: {}, now: 0, cacheTtlMs: HOUR }
  expect(estTurnCost('fable', 'opus', i, 1, 'low') < estTurnCost('fable', 'opus', i, 1, 'xhigh')).toBe(true)
  expect(estTurnCost('sonnet', 'sonnet', i, 1, 'xhigh') < estTurnCost('opus', 'sonnet', i, 1, 'low')).toBe(true)
})

test('Anthropic guidance: haiku never at low or past 100k tokens; the warm-tier rule never drops into low', async () => {
  expect(decide(base({ verdict: verdict('haiku', 0.9, 'low'), contextTokens: 120_000 })).required).toBe('sonnet')
  const warm = { opus: { at: 10 * HOUR - 60_000, tokens: 150_000 } }
  const d = decide(base({ verdict: verdict('sonnet', 0.9, 'medium'), contextTokens: 150_000, warm }))
  expect(d.tier).toBe('opus')
  expect(d.effort).toBe('medium')
})
