import { expect, test } from 'claude-code/testing'
import type { EngineInterface } from 'claude-code'

import { firstOf, judge } from './engine'
import type { JevState } from './engine'

/** An engine stand-in for the Jev call: its runner returns `reply` and records the argv. */
function jevEngine(reply: { stdout?: string; stderr?: string; exitCode?: number }) {
  const argvs: string[][] = []
  const $ = {
    clock: { now: async () => 0, sleep: async () => undefined },
    session: { cwd: async () => '/work/app' },
    env: { get: async () => '/home/u' },
    fs: { exists: async () => true },
    process: { run: async (argv: string[]) => (argvs.push(argv), { stdout: '', stderr: '', exitCode: 0, ...reply }) },
  }
  return { $: $ as unknown as EngineInterface, argvs }
}
const ask = (e: ReturnType<typeof jevEngine>, jev: JevState) =>
  judge(e.$, { prompt: 'explain this', recent: '', contextTokens: 0, currentTier: 'sonnet', kind: 'prompt' }, { isPrivate: false, budgetMs: 100, model: 'haiku', chain: ['jev'], jev })

test('Jev is asked with its policy site and the session folder, so policy.json applies', async () => {
  const e = jevEngine({ stdout: JSON.stringify({ answers: { tier: { choice: 'sonnet', confidence: 0.9 } } }) })
  const j = await ask(e, { isOff: false, failures: 0 })
  expect(j.by).toBe('jev')
  expect(e.argvs[0]?.slice(1)).toEqual(['raw', '--site', 'model-pilot', '--cwd', '/work/app'])
})

test('a refusal by the policy, or a jev too old for the flags, is no answer and Jev is not asked again', async () => {
  for (const stderr of ['jev: refused by ~/.claude/jev/policy.json (disabled)', 'jev: error: unrecognized arguments: --site']) {
    const st = { isOff: false, failures: 0 }
    const j = await ask(jevEngine({ exitCode: 2, stderr }), st)
    expect(j.source).toBe('rules')
    expect(st.isOff).toBe(true)
  }
})

// Settles after `ticks` turns of the microtask queue: an order without timers.
const after = async <T>(ticks: number, v: T): Promise<T> => {
  for (let i = 0; i < ticks; i++) await Promise.resolve()
  return v
}

test('the hedge takes the first judge that answers, not the first that settles', async () => {
  expect(await firstOf([after(30, 'jev'), after(5, 'haiku')])).toBe('haiku')
  expect(await firstOf([after(5, undefined), after(20, 'haiku')])).toBe('haiku')
  expect(await firstOf([Promise.reject(new Error('down')), after(10, 'jev')])).toBe('jev')
})

test('no judge answers: undefined, never a hang', async () => {
  expect(await firstOf<string>([after(5, undefined), Promise.reject(new Error('x'))])).toBe(undefined)
  expect(await firstOf<string>([])).toBe(undefined)
})
