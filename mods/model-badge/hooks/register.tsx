import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { Models } from '../types'

const models = atom({ plugin: 'model-badge', key: 'models' } as const, {} as Models)
const KEEP = 300 // calls remembered; older rows fall back to the call's own `model` input

/** `claude-haiku-5-5` -> `Haiku 5.5`, `sonnet` -> `Sonnet`; anything else as given. */
export function label(model: string): string {
  const id = model.replace(/\[.*\]$/, '')
  const m = /^claude-([a-z]+)-(\d+)(?:-(\d{1,2}))?(?:-\d{8})?$/.exec(id)
  const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
  if (m) return `${cap(m[1] ?? '')} ${m[2]}${m[3] ? `.${m[3]}` : ''}`
  return /^[a-z]+$/.test(id) ? cap(id) : id
}

export const register: Register = on => {
  on('agent.spawn', async ($, e, next) => {
    const r = await next(e)
    if (r.model && e.tool_use_id) {
      const model = r.model
      await update($, models, prev => {
        const kept: Models = Object.fromEntries(Object.entries(prev).slice(-(KEEP - 1)))
        return { ...kept, [e.tool_use_id]: model }
      })
    }
    return r
  })

  on('ui.render', { component: 'ToolUse' }, async ($, e, next) => {
    const row = await next(e)
    if (e.props.tool !== 'Agent') return row
    const input = (e.props.input ?? {}) as { model?: unknown }
    const model = (await read($, models))[e.props.tool_use_id] ?? (typeof input.model === 'string' ? input.model : undefined)
    if (!model) return row
    const { Box, Text } = $.ui.resolve(e)
    return (
      <Box flexDirection="row" alignItems="flex-start">
        {row}
        <Text dimColor> [{label(model)}]</Text>
      </Box>
    )
  })
}
