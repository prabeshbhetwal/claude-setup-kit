import { expect, test } from 'claude-code/testing'

import { afterAnswer, FABLE_CHAT, fableQuestion, needsFableYes, RUN_FABLE, USE_OPUS } from './fable'
import type { Decision } from './policy'

const d: Decision = { tier: 'fable', effort: 'high', required: 'fable', source: 'judge', reason: 'a large redesign across many files', confidence: 0.9 }

test('asks only when the pilot, not the person, chose Fable', async () => {
  expect(needsFableYes(d, 'opus', false, true)).toBe(true)
  expect(needsFableYes(d, 'fable', false, true)).toBe(false) // Fable is the menu's model
  expect(needsFableYes({ ...d, source: 'explicit' }, 'opus', false, true)).toBe(false) // "use fable" in the prompt
  expect(needsFableYes({ ...d, source: 'pinned' }, 'opus', false, true)).toBe(false) // the person pinned the model in the menu
  expect(needsFableYes(d, 'opus', true, true)).toBe(false) // shadow changes nothing
  expect(needsFableYes(d, 'opus', false, false)).toBe(false) // switched off, or yes for this chat
  expect(needsFableYes({ ...d, tier: 'opus' }, 'sonnet', false, true)).toBe(false)
})

test('the question gives the reason, the effort and why, and both costs', async () => {
  const q = fableQuestion(d, 1.234, 0.61)
  expect(q.includes('a large redesign across many files')).toBe(true)
  expect(q.includes('Effort high: several steps')).toBe(true)
  expect(q.includes('$1.23 on Fable, $0.61 on Opus')).toBe(true)
  expect(q.endsWith('?')).toBe(true)
})

test('yes keeps Fable; anything else runs on Opus', async () => {
  expect(afterAnswer(d, RUN_FABLE).tier).toBe('fable')
  expect(afterAnswer(d, FABLE_CHAT).tier).toBe('fable')
  expect(afterAnswer(d, USE_OPUS).tier).toBe('opus')
  expect(afterAnswer(d, undefined).reason.includes('no answer')).toBe(true)
  expect(afterAnswer(d, 'something typed').tier).toBe('opus')
})
