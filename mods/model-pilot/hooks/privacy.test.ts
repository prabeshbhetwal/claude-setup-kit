import { expect, test } from 'claude-code/testing'
import type { EngineInterface } from 'claude-code'

import { optionsOf } from './options'
import { isPrivateHere } from './privacy'

// An engine that fails the test if privacy mode so much as looks at the session or runs a process.
const untouched = new Proxy({}, { get: () => { throw new Error('privacy mode must not call the engine') } }) as unknown as EngineInterface

test('privacy mode is private everywhere, whatever the folder list says, without asking the engine', async () => {
  expect(await isPrivateHere(untouched, { privacy: true, privateFolders: '' })).toBe(true)
  expect(await isPrivateHere(untouched, { privacy: false, privateFolders: '' })).toBe(false)
})

test('privacy is off by default and on only for a real true', async () => {
  expect(optionsOf({}).privacy).toBe(false)
  expect(optionsOf({ privacy: 'yes' }).privacy).toBe(false)
  expect(optionsOf({ privacy: true }).privacy).toBe(true)
})
