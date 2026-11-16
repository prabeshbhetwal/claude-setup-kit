import { expect, test } from 'claude-code/testing'

import { firstOf } from './engine'

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
