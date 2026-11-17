import { expect, test } from 'claude-code/testing'

import { bandText, modelName } from './band'
import type { PilotFlags, PilotView } from '../types'

const on: PilotFlags = { isOn: true, isModelPinned: false, isEffortPinned: false }
const view = (o: Partial<PilotView> = {}): PilotView => ({
  pickedTier: 'haiku', requestedEffort: 'low', ranModel: 'claude-fable-5-2', ranFrom: 'transcript', isMismatch: false,
  isShadow: true, source: 'judge', judge: 'jev', reason: '', tip: null, handoffTokens: null, ...o,
})

test('model ids read as names', async () => {
  expect(modelName('claude-opus-5-5')).toBe('Opus 5.5')
  expect(modelName('claude-haiku-4-5-20251001')).toBe('Haiku 4.5')
  expect(modelName('claude-fable-5')).toBe('Fable 5')
  expect(modelName('some-proxy-model')).toBe('some-proxy-model')
  expect(modelName(null)).toBe('unknown')
})

test('shadow: would pick, then what ran, on one line', async () => {
  const t = bandText(on, view(), true)
  expect(t.mode).toBe('shadow')
  expect(t.line).toBe('Would pick Haiku · low effort  →  ran Fable 5.2 · judge Jev')
})

test('a model set in the menu reads as yours, with no empty arrow', async () => {
  const t = bandText({ ...on, isModelPinned: true }, view({ pickedTier: null, ranModel: 'claude-opus-5-5' }), true)
  expect(t.line).toBe('Your model: Opus 5.5 · low effort')
})

test('live, off, first turn and mismatch', async () => {
  expect(bandText(on, view({ isShadow: false, ranModel: 'claude-haiku-5-5' }), false).line).toBe('Haiku · low effort  →  ran Haiku 5.5 · judge Jev')
  expect(bandText(on, view(), false).mode).toBe(null)
  expect(bandText({ ...on, isOn: false }, view(), true)).toEqual({ mode: 'off', line: "The menu's model runs.", isWarning: false, tip: null })
  expect(bandText(on, null, true).line).toBe('Watching: each prompt is judged, nothing is changed.')
  const m = bandText(on, view({ isMismatch: true, isShadow: false }), false)
  expect(m.isWarning).toBe(true)
  expect(m.line).toBe('Picked Haiku, but Fable 5.2 ran.')
})
