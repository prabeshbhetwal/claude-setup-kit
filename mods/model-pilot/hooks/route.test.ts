import { expect, test } from 'claude-code/testing'
import type { EngineInterface } from 'claude-code'

import type { Judged } from './engine'
import { rememberAgentEffort } from './effort'
import type { Decision, Effort } from './policy'
import { noCosts } from './prices'
import { isPrivateHere } from './privacy'
import { chainOf, optionsOf } from './options'
import type { Options } from './options'
import { finish, verdictFor } from './route'
import type { Rec } from './route'

type Run = { stdout?: string; stderr?: string; exitCode?: number }

/** An engine stand-in: a clock that never waits, a session, and a process runner that records each call. */
function fake(run: (argv: string[]) => Run = () => ({}), cwd = '/w') {
  const calls: { argv: string[]; stdin?: string }[] = []
  const $ = {
    clock: { now: async () => 1_000, sleep: async () => undefined },
    session: {
      cwd: async () => cwd,
      id: async () => 'not a session id', // readRan skips the transcript for an id like this
      usage: async () => ({ context: { tokens: 0, window: 200_000 } }),
      model: async () => 'claude-sonnet-5-5',
    },
    env: { get: async (k: string) => (k === 'HOME' ? '/home/u' : undefined) },
    process: {
      run: async (argv: string[], o?: { stdin?: string }) => {
        calls.push({ argv, stdin: o?.stdin })
        return { stdout: '', stderr: '', exitCode: 0, ...run(argv) }
      },
    },
  }
  return { $: $ as unknown as EngineInterface, calls }
}

const opts: Options = { ...optionsOf({}), handoff: 'never', judgeBudgetMs: 10 }
const decision: Decision = { tier: 'sonnet', effort: 'medium', required: 'sonnet', source: 'rules', reason: 'r', confidence: 0.5 }
const recOf = (over: Partial<Rec> = {}): Rec => ({
  text: 'explain the build',
  t0: 0,
  explicit: {},
  isSticky: false,
  isFirst: false,
  waitedMs: 0,
  leadMs: 0,
  tip: null,
  usage: {},
  costs: noCosts(),
  warmAtStart: [],
  contextTokens: 0,
  menuModel: 'claude-sonnet-5-5',
  ran: 'claude-sonnet-5-5',
  ...over,
})
const logged = (calls: { stdin?: string }[]): Record<string, unknown> => JSON.parse(calls.at(-1)?.stdin ?? '{}')

test('Jev is opt-in: the default settings judge with Haiku only', async () => {
  expect(chainOf(optionsOf({}))).toEqual(['haiku'])
  expect(chainOf(optionsOf({ jev: true }))).toEqual(['jev', 'haiku'])
  expect(chainOf(optionsOf({ jev: 'yes' }))).toEqual(['haiku'])
})

test('a judge that answers after the timeout still has its paid usage counted', async () => {
  const { $, calls } = fake()
  let answer: (j: Judged) => void = () => undefined
  const rec = recOf({ pending: { at: 0, judged: new Promise<Judged | undefined>(r => { answer = r }) } })
  const got = await verdictFor($, opts, rec, 'sonnet')
  expect(got.source).toBe('rules')
  expect(rec.judgedOut?.fail).toBe('timeout')
  answer({ verdict: got.verdict, source: 'judge', by: 'haiku', ms: 3000, usage: { input_tokens: 50_000 } })
  for (let i = 0; i < 3; i++) await Promise.resolve()
  await finish($, opts, 't1', { ...rec, decision })
  expect(logged(calls).est_saving_usd).toBe(-0.005) // 50k input tokens on Haiku
})

test('the judge call is costed on the configured judge model', async () => {
  const { $, calls } = fake()
  const judgedOut: Judged = { verdict: { tier: 'sonnet', effort: 'medium', confidence: 0.9, reason: 'r' }, source: 'judge', by: 'haiku', ms: 1, usage: { input_tokens: 1_000_000 } }
  await finish($, { ...opts, judgeModel: 'claude-sonnet-5-5' }, 't2', recOf({ decision, judgedOut }))
  expect(logged(calls).est_saving_usd).toBe(-2)
})

test('after /compact drops the context below the threshold, the next crossing offers a handoff again', async () => {
  const { $ } = fake()
  const o = { ...opts, handoff: '250k' }
  const at = async (id: string, tokens: number) => (await finish($, o, id, recOf({ decision, contextTokens: tokens })))?.handoffTokens ?? null
  expect(await at('h1', 260_000)).toBe(260_000)
  expect(await at('h2', 270_000)).toBe(null) // same band: offered once
  expect(await at('h3', 90_000)).toBe(null) // compacted
  expect(await at('h4', 260_000)).toBe(260_000)
})

test('private folders compare real paths on both sides, so a symlink cannot route around them', async () => {
  const resolve = () => ({ stdout: '/Volumes/data/client/app\n/Volumes/data/client\n' })
  const { $, calls } = fake(resolve, '/home/u/link-to-client/app')
  expect(await isPrivateHere($, { privacy: false, privateFolders: '~/client' })).toBe(true)
  expect(calls[0]?.argv.slice(-2)).toEqual(['/home/u/link-to-client/app', '/home/u/client'])
  const elsewhere = fake(() => ({ stdout: '/home/u/other\n/Volumes/data/client\n' }), '/home/u/other')
  expect(await isPrivateHere(elsewhere.$, { privacy: false, privateFolders: '~/client' })).toBe(false)
  const broken = fake(() => { throw new Error('no shell') }, '/home/u/client/x')
  expect(await isPrivateHere(broken.$, { privacy: false, privateFolders: '~/client' })).toBe(true) // as written still counts
  const alias = fake(() => { throw new Error('no shell') }, '/var/x')
  expect(await isPrivateHere(alias.$, { privacy: false, privateFolders: '/private/var' })).toBe(true) // cannot resolve: fail closed, rules only
})

test('the sub-agent effort map keeps only the newest entries', async () => {
  const m = new Map<string, Effort>()
  for (let i = 0; i < 100; i++) rememberAgentEffort(m, `a${i}`, 'high')
  expect(m.size).toBe(64)
  expect(m.has('a99')).toBe(true)
  expect(m.has('a0')).toBe(false)
})
