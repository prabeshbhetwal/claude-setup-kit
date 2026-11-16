import { expect, test } from 'claude-code/testing'

import { lastAssistantModel } from './transcript'

const row = (o: Record<string, unknown>): string => JSON.stringify(o)
const reply = (model: string, timestamp: string, more: Record<string, unknown> = {}): string =>
  row({ type: 'assistant', isSidechain: false, timestamp, message: { role: 'assistant', model, content: [] }, ...more })

test('reads the newest main-thread reply', async () => {
  const tail = [
    row({ type: 'user', message: { role: 'user', content: 'hi' } }),
    reply('claude-opus-5-5', '2026-01-02T03:04:05.000Z'),
    row({ type: 'attachment' }),
    reply('claude-haiku-5-5', '2026-01-02T03:05:00.000Z'),
    row({ type: 'cost-state' }),
  ].join('\n')
  expect(lastAssistantModel(tail)).toEqual({ model: 'claude-haiku-5-5', at: Date.parse('2026-01-02T03:05:00.000Z') })
})

test('skips sub-agent rows, synthetic rows and rows with no model', async () => {
  const tail = [
    reply('claude-sonnet-5-5', '2026-01-02T03:04:05.000Z'),
    reply('claude-haiku-5-5', '2026-01-02T03:06:00.000Z', { isSidechain: true }),
    reply('<synthetic>', '2026-01-02T03:07:00.000Z'),
    row({ type: 'assistant', timestamp: '2026-01-02T03:08:00.000Z', message: { role: 'assistant' } }),
  ].join('\n')
  expect(lastAssistantModel(tail)?.model).toBe('claude-sonnet-5-5')
})

test('survives a first line cut in half, a half-written last line and blank lines', async () => {
  const tail = `-5-5","content":[]}}\n\n${reply('claude-opus-5-5', '2026-01-02T03:04:05.000Z')}\n{"type":"assistant","message":{"model":"claude-ha`
  expect(lastAssistantModel(tail)?.model).toBe('claude-opus-5-5')
})

test('a user message that merely mentions "assistant" is not a reply', async () => {
  const tail = row({ type: 'user', message: { role: 'user', model: 'x', content: 'the "assistant" said' } })
  expect(lastAssistantModel(tail)).toBe(undefined)
  expect(lastAssistantModel('')).toBe(undefined)
})

test('a bad timestamp reads as 0, so the caller treats the row as old', async () => {
  expect(lastAssistantModel(reply('claude-opus-5-5', 'yesterday'))?.at).toBe(0)
})
