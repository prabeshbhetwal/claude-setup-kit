import { expect, test } from 'claude-code/testing'

import { explicitChoice, isFollowUp, judgePrompt, parseJudgeReply, rulesFallback, rulesVerdict, floorCoding } from './judge'
import type { JudgeInput } from './policy'

const input = (prompt: string, kind: 'prompt' | 'agent' = 'prompt'): JudgeInput => ({ prompt, recent: '', contextTokens: 30_000, currentTier: 'sonnet', kind })

test('parses a clean verdict', async () => {
  const v = parseJudgeReply('{"tier":"sonnet","effort":"medium","confidence":0.8,"needs_tools":true,"reason":"scoped fix"}')
  expect(v).toEqual({ tier: 'sonnet', effort: 'medium', confidence: 0.8, reason: 'scoped fix' })
})

test('parses a verdict wrapped in prose or a code fence', async () => {
  const v = parseJudgeReply('Here you go:\n```json\n{"tier":"OPUS","effort":"high","confidence":0.9,"needs_tools":false,"reason":"x"}\n```')
  expect(v?.tier).toBe('opus')
  expect(v?.effort).toBe('high')
})

test('repairs what it safely can: max effort, missing effort, wild confidence', async () => {
  expect(parseJudgeReply('{"tier":"opus","effort":"max"}')?.effort).toBe('xhigh')
  expect(parseJudgeReply('{"tier":"haiku"}')?.effort).toBe('low')
  expect(parseJudgeReply('{"tier":"opus","effort":"banana"}')?.effort).toBe('medium')
  expect(parseJudgeReply('{"tier":"sonnet","confidence":7}')?.confidence).toBe(1)
  expect(parseJudgeReply('{"tier":"sonnet","confidence":"high"}')?.confidence).toBe(0.5)
})

test('rejects what is not a verdict', async () => {
  for (const bad of ['', 'sonnet', '{"tier":"gpt"}', '{"tier":', '[]', '{"effort":"low"}', 'null']) {
    expect(parseJudgeReply(bad)).toBe(undefined)
  }
})

test('the judge prompt carries the facts and cuts a long request in the middle', async () => {
  const long = `START ${'x'.repeat(5000)} END`
  const p = judgePrompt({ ...input(long), recent: 'user: hi', contextTokens: 123456 })
  expect(p.includes('context_tokens: 123456')).toBe(true)
  expect(p.includes('START')).toBe(true)
  expect(p.includes('END')).toBe(true)
  expect(p.includes('characters cut')).toBe(true)
  expect(p.length < 3600).toBe(true)
  expect(p.includes(`request_chars: ${long.length}`)).toBe(true)
})

test('rules: hard reasoning is opus', async () => {
  for (const p of [
    'why does the worker crash every few hours?',
    'find the root cause of the duplicate invoices',
    'design a data model for multi-tenant billing',
    'there is a race condition in the cache layer',
    'do a security review of the login flow',
    'the test is flaky on CI, no idea why',
    'plan the migration from Postgres 13 to 16',
  ]) expect(rulesVerdict(input(p)).tier).toBe('opus')
})

test('rules: scoped work is sonnet, never haiku', async () => {
  for (const p of [
    'add a --verbose flag to cli.py',
    'write unit tests for the parser',
    'fix the off-by-one in pagination',
    'what does this do?\n```js\nfoo()\n```',
    'rename getUser to fetchUser in api.ts',
    'refactor utils.ts into smaller modules',
  ]) expect(rulesVerdict(input(p)).tier).toBe('sonnet')
})

test('rules: short lookups are haiku', async () => {
  for (const p of ['what is the capital of Australia?', 'how do I undo the last git commit', 'translate "good morning" to Nepali', 'thanks', 'define idempotent']) {
    expect(rulesVerdict(input(p)).tier).toBe('haiku')
  }
})

test('a positive model choice beside a negated alternative still counts', async () => {
  expect(explicitChoice('Analyse this with Opus, not Fable.').tier).toBe('opus')
  expect(explicitChoice('Summarise the file with Haiku rather than Opus.').tier).toBe('haiku')
  expect(explicitChoice('Analyse this with Opus, not with Fable.').tier).toBe('opus')
  expect(explicitChoice('compare haiku with sonnet').tier).toBeUndefined()
  expect(explicitChoice('Compare requests not using Sonnet with those on Fable.').tier).toBeUndefined()
  expect(explicitChoice('Summarise those files with Opus, high effort.')).toEqual({ tier: 'opus', effort: 'high' })
  expect(explicitChoice('Sonnet got this wrong. Analyse this with Opus.').tier).toBe('opus')
  expect(explicitChoice('We compared the results yesterday. Summarise the notes with Opus.').tier).toBe('opus')
  expect(explicitChoice('Do not use fable; use sonnet instead.').tier).toBe('sonnet')
})

test('rules: an action asked as a question is work; ordinary words are not hard reasoning', async () => {
  for (const p of ['can you delete the old branches?', 'could you update the readme?', 'please fix the login bug']) expect(rulesVerdict(input(p)).tier).toBe('sonnet')
  for (const p of ['update my profile page', 'scale the image to 50%', 'design a logo']) expect(rulesVerdict(input(p)).tier).not.toBe('opus')
})

test('rules: the unknown defaults up to sonnet, whole-system jobs are fable', async () => {
  expect(rulesVerdict(input('the quarterly numbers for the board, with my comments on each division and the plan')).tier).toBe('sonnet')
  expect(rulesVerdict(input('audit the entire codebase and redesign it')).tier).toBe('fable')
})

test('rules: a mechanical sub-agent task may be haiku, the same prompt from a person is sonnet', async () => {
  expect(rulesVerdict(input('run the tests and report failures', 'agent')).tier).toBe('haiku')
  expect(rulesVerdict(input('run the tests and report failures')).tier).toBe('sonnet')
})

test('follow-ups are recognised, real requests are not', async () => {
  for (const t of ['yes', 'ok', 'go ahead', 'do it', 'continue', 'Yes please', 'lgtm', '', 'option 2', 'sounds good, thanks', '<task-notification>\n<task-id>a1</task-id>']) expect(isFollowUp(t)).toBe(true)
  for (const t of ['yes but use a queue instead', 'fix the login bug', 'ok now design the schema', 'why?']) expect(isFollowUp(t)).toBe(false)
})

test('only engine tags read as a delivery, not any prompt starting with "<"', async () => {
  for (const t of ['<cross-session-message from="x">hi', '<command-name>/pilot</command-name>', '<system-reminder>\nx', '<ci-monitor-event>', '<side-sessions-event>']) expect(isFollowUp(t)).toBe(true)
  for (const t of ['<div> is not centred, fix the css', '<script> tag breaks the build', '<T>(x: T) => T: explain this signature']) expect(isFollowUp(t)).toBe(false)
})

test('a negated model is never chosen; a bare "with" or "on" in a comparison or question is no choice', async () => {
  expect(explicitChoice('do not use fable; use sonnet').tier).toBe('sonnet')
  expect(explicitChoice("don't use fable for this, use opus").tier).toBe('opus')
  expect(explicitChoice('please never switch to fable').tier).toBe(undefined)
  expect(explicitChoice('use opus here, and do not use opus for the tests').tier).toBe(undefined)
  for (const t of ['is the context limit bigger on fable?', 'compare haiku with sonnet', 'how fast is it with opus?']) expect(explicitChoice(t).tier).toBe(undefined)
  expect(explicitChoice('Summarise the file with haiku.').tier).toBe('haiku')
  expect(explicitChoice('run this on opus').tier).toBe('opus')
})

test('a model named in the prompt is found', async () => {
  expect(explicitChoice('use opus for this: why is the build slow').tier).toBe('opus')
  expect(explicitChoice('Summarise the file with haiku.').tier).toBe('haiku')
  expect(explicitChoice('switch to sonnet and fix the test').tier).toBe('sonnet')
  expect(explicitChoice('fable: redesign the importer').tier).toBe('fable')
  expect(explicitChoice('run this on Claude Opus 5.5 please').tier).toBe('opus')
  expect(explicitChoice('answer with sonnet, high effort').effort).toBe('high')
  expect(explicitChoice('fix it, effort: xhigh').effort).toBe('xhigh')
})

test('words that only look like a model choice are left alone', async () => {
  for (const t of [
    'write a haiku about autumn',
    'use haiku structure for the poem',
    'the opus codec drops frames',
    'compare sonnet and opus pricing',
    'encode with opus codec at 64k',
    'my magnum opus is done',
    'a fable about a fox',
    'it took a lot of effort',
    'make a best effort guess',
  ]) expect(explicitChoice(t)).toEqual({})
})

test('the rules fallback keeps coding off haiku, as the judge path does', async () => {
  const prompt = 'how do I fix the login handler bug'
  expect(rulesVerdict(input(prompt)).tier).toBe('haiku') // a "how do" lookup to the rules alone
  const v = rulesFallback(input(prompt), 'haiku', 'timeout')
  expect(v.tier).toBe('sonnet')
  expect(v.reason.includes('judge timeout')).toBe(true)
  expect(rulesFallback(input('what is a monad?'), 'opus', 'privacy').tier).toBe('haiku')
  expect(rulesFallback(input('add a test for the parser'), 'opus', 'failed').reason).toBe('judge failed: menu model kept')
})

test('haiku is never left on real coding; a mechanical one-liner may stay', async () => {
  const v = { tier: 'haiku' as const, effort: 'low' as const, confidence: 0.9, reason: 'r' }
  expect(floorCoding(v, 'write a function that parses dates in utils.ts').tier).toBe('sonnet')
  expect(floorCoding(v, 'fix the bug in the login handler').effort).toBe('medium')
  expect(floorCoding(v, 'rename foo to bar').tier).toBe('haiku')
  expect(floorCoding(v, 'what does this function do?').tier).toBe('haiku')
})
