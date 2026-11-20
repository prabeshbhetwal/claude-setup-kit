// Cache Keeper's keep-warm pings, as the routing sees them. Each ping re-reads one
// model's cache and restarts its timer, so a cache the pilot last touched an hour
// ago may still be warm. Cache Keeper writes ~/.claude/cache/cache-warm/<session>.json:
// { "<model id>": <ms the ping went out> }.
import type { EngineInterface } from 'claude-code'

import { tierOf } from './policy'
import type { Warm } from './policy'

export const pingsPath = (home: string, sid: string) => `${home}/.claude/cache/cache-warm/${sid}.json`

/** The pings recorded for this session; {} when there are none or the file is unreadable. */
export async function readPings($: EngineInterface, home: string, sid: string): Promise<Record<string, number>> {
  try {
    const path = pingsPath(home, sid)
    if (!(await $.fs.exists(path))) return {}
    const json = JSON.parse(String(await $.fs.read(path))) as unknown
    if (!json || typeof json !== 'object' || Array.isArray(json)) return {}
    return Object.fromEntries(Object.entries(json).filter((kv): kv is [string, number] => typeof kv[1] === 'number' && Number.isFinite(kv[1])))
  } catch {
    return {}
  }
}

/**
 * Moves a tier's cache time forward to a later ping of that tier's model. A tier the
 * pilot has no entry for stays out: a ping says when, not how many tokens are cached.
 */
export function mergePings(warm: Warm, pings: Record<string, number>): Warm {
  let out = warm
  for (const [model, at] of Object.entries(pings)) {
    const t = tierOf(model)
    const w = t ? out[t] : undefined
    if (t && w && at > w.at) out = { ...out, [t]: { ...w, at } }
  }
  return out
}
