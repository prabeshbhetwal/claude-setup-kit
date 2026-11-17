import { expect, test } from 'claude-code/testing'
import type { TestBody } from 'claude-code/testing'

import { label } from './register'

const row = (tool: string, input: unknown, tool_use_id = 'call-1') =>
  ({
    plugin: 'model-badge',
    component: 'ToolUse',
    requestId: tool_use_id,
    props: { tool_use_id, tool, input, isRunning: true, isErrored: false, isInterrupted: false },
  }) as const

const engineRow = (on: Parameters<TestBody>[1]) =>
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>agent row</Text>
  })

test('model ids read as names', async () => {
  expect(label('claude-haiku-5-5')).toBe('Haiku 5.5')
  expect(label('claude-opus-5-5[1m]')).toBe('Opus 5.5')
  expect(label('claude-sonnet-4-5-20250929')).toBe('Sonnet 4.5')
  expect(label('claude-opus-4-20250514')).toBe('Opus 4')
  expect(label('haiku')).toBe('Haiku')
  expect(label('gpt-x')).toBe('gpt-x')
})

test('an Agent row passing a model shows it beside the row, on every surface', async ($, on) => {
  engineRow(on)
  for (const surface of ['terminal', 'desktop', 'vscode', 'mobile'] as const) {
    const ui = await $.ui.mount({ ...row('Agent', { description: 'Proofread', model: 'haiku' }), surface })
    expect((await ui.find({ type: 'Text', text: /agent row/ }))?.text).toBe('agent row')
    expect((await ui.find({ type: 'Text', text: /Haiku/ }))?.text).toBe(' [Haiku]')
    await ui.unmount()
  }
})

test('the resolved model from the spawn wins over the input', async ($, on) => {
  engineRow(on)
  on('state.get', () => ({ value: { value: { 'call-1': 'claude-sonnet-5-5' }, version: 1 } }))
  const ui = await $.ui.mount({ ...row('Agent', { description: 'x' }), surface: 'desktop' })
  expect((await ui.find({ type: 'Text', text: /Sonnet/ }))?.text).toBe(' [Sonnet 5.5]')
  await ui.unmount()
})

test('other tools, and Agent rows with no known model, are left alone', async ($, on) => {
  engineRow(on)
  for (const r of [row('Bash', { command: 'ls', model: 'haiku' }), row('Agent', { description: 'x' }, 'call-2')]) {
    const ui = await $.ui.mount({ ...r, surface: 'desktop' })
    expect(await ui.find({ type: 'Text', text: /\[/ })).toBeUndefined()
    await ui.unmount()
  }
})
