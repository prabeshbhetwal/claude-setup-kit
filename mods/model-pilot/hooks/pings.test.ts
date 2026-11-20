import { expect, test } from 'claude-code/testing'

import type { EngineInterface } from 'claude-code'

import { mergePings, pingsPath, readPings } from './pings'
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

// A $ whose fs is a map of path -> text, with the failures a real disk can give.
const fake = (files: Record<string, string>, boom = false) =>
  ({
    fs: {
      exists: async (p: string) => {
        if (boom) throw new Error('disk gone')
        return p in files
      },
      read: async (p: string) => {
        if (boom) throw new Error('disk gone')
        return files[p]
      },
    },
  }) as unknown as EngineInterface

const PATH = pingsPath('/home/u', 's1')

test('readPings reads the file Cache Keeper writes, at the path it writes it', async () => {
  expect(PATH, 'same path as Cache Keeper').toBe('/home/u/.claude/cache/cache-warm/s1.json')
  const $ = fake({ [PATH]: JSON.stringify({ 'claude-opus-5-5': 1_255_000, 'claude-haiku-5-5': 9 }) })
  expect(await readPings($, '/home/u', 's1')).toEqual({ 'claude-opus-5-5': 1_255_000, 'claude-haiku-5-5': 9 })
})

test('readPings gives {} for every bad file instead of throwing', async () => {
  const bad = ['', 'not json', 'null', '[1,2]', '"x"', '42', '{"a":']
  for (const text of bad) expect(await readPings(fake({ [PATH]: text }), '/home/u', 's1'), text).toEqual({})
  expect(await readPings(fake({}), '/home/u', 's1'), 'missing file').toEqual({})
  expect(await readPings(fake({}, true), '/home/u', 's1'), 'fs throws').toEqual({})
  expect(await readPings(fake({ [PATH]: '{}' }), '', 's1'), 'no HOME: nothing found').toEqual({})
})

test('readPings drops values that are not finite numbers and keeps the rest', async () => {
  const text = '{"a":1,"b":"2","c":null,"d":true,"e":{"x":1},"f":2.5,"big":1e999,"neg":-1e999}'
  expect(await readPings(fake({ [PATH]: text }), '/home/u', 's1'), '1e999 parses to Infinity: dropped').toEqual({ a: 1, f: 2.5 })
})

test('another session’s pings never leak in', async () => {
  const $ = fake({ [pingsPath('/home/u', 's2')]: '{"claude-opus-5-5":5}' })
  expect(await readPings($, '/home/u', 's1')).toEqual({})
})

test('file to warm: a stored ping extends the tier the pilot knows, end to end', async () => {
  const $ = fake({ [PATH]: JSON.stringify({ 'claude-opus-5-5': 9_000, 'claude-sonnet-5-5': 9_000 }) })
  const warm = { opus: { at: 1_000, tokens: 90_000 } }
  const out = mergePings(warm, await readPings($, '/home/u', 's1'))
  expect(out.opus).toEqual({ at: 9_000, tokens: 90_000 })
  expect(out.sonnet, 'unknown tier stays unknown').toBeUndefined()
})

test('mergePings is idempotent, never moves a time back, and leaves its input alone', async () => {
  const warm = { opus: { at: 5_000, tokens: 1 }, haiku: { at: 7_000, tokens: 2 } }
  const frozen = JSON.stringify(warm)
  for (const at of [0, 4_999, 5_000, 5_001, 1e12]) {
    const once = mergePings(warm, { 'claude-opus-5-5': at })
    expect(once.opus!.at, `ping ${at}`).toBeGreaterThanOrEqual(5_000)
    expect(mergePings(once, { 'claude-opus-5-5': at }), 'twice = once').toEqual(once)
    expect(once.haiku, 'other tier untouched').toEqual(warm.haiku)
  }
  expect(JSON.stringify(warm), 'input not mutated').toBe(frozen)
})
