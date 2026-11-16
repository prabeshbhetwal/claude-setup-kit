import { expect, test } from 'claude-code/testing'

import { jevBody, parseJevReply } from './jev'

const reply = (tier: unknown, effort: unknown) => JSON.stringify({ model: 'jev-x', answers: { tier, effort }, usage: { input_tokens: 1, output_tokens: 1 } })

test('the body carries the request as state and two choice questions', async () => {
  const b = jevBody({ prompt: 'why is prod slow?', recent: '', contextTokens: 42, currentTier: 'sonnet', kind: 'prompt' }) as { state: Record<string, unknown>; questions: Record<string, { type: string; criteria: Record<string, string> }> }
  expect(b.state.request).toBe('why is prod slow?')
  expect(b.state.context_tokens).toBe(42)
  expect(Object.keys(b.questions.tier?.criteria ?? {})).toEqual(['haiku', 'sonnet', 'opus', 'fable'])
  expect(b.questions.effort?.type).toBe('choice')
})

test('confidence is the weight not on higher tiers', async () => {
  const v = parseJevReply(reply({ choice: 'sonnet', confidence: 0.6, probabilities: { haiku: 0.05, sonnet: 0.6, opus: 0.35, fable: 0 } }, { choice: 'medium' }))
  expect(v?.tier).toBe('sonnet')
  expect(v?.effort).toBe('medium')
  expect(Math.round((v?.confidence ?? 0) * 100)).toBe(65)
  expect(v?.reason.includes('opus 0.35')).toBe(true)
})

test('weight below the pick does not lower confidence', async () => {
  const v = parseJevReply(reply({ choice: 'opus', confidence: 0.55, probabilities: { haiku: 0, sonnet: 0.45, opus: 0.55, fable: 0 } }, { choice: 'high' }))
  expect(v?.confidence).toBe(1)
})

test('missing pieces fall back sanely, junk is refused', async () => {
  expect(parseJevReply(reply({ choice: 'haiku', confidence: 0.9 }, undefined))?.effort).toBe('low')
  expect(parseJevReply(reply({ choice: 'haiku', confidence: 0.9 }, undefined))?.confidence).toBe(0.9)
  expect(parseJevReply(reply({ choice: 'gpt' }, { choice: 'low' }))).toBe(undefined)
  expect(parseJevReply('jev unavailable: no key')).toBe(undefined)
  expect(parseJevReply('{}')).toBe(undefined)
})
