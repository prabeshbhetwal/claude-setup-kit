// model-pilot's privacy check: privacy mode, or a session inside a folder listed for rules-only judging.
import type { EngineInterface } from 'claude-code'

import type { Options } from './options'

/** The listed folders, `~` expanded, trailing slashes cut. */
const folderList = (list: string, home: string): string[] =>
  list
    .split(/[,\n]/)
    .map(s => s.trim())
    .filter(Boolean)
    .map(s => (s === '~' || s.startsWith('~/') ? home + s.slice(1) : s).replace(/\/+$/, ''))

/** Whether `cwd` is under one of the folders listed for rules-only judging. */
export function isPrivateFolder(cwd: string, list: string, home: string): boolean {
  const here = cwd.replace(/\/+$/, '')
  return folderList(list, home).some(f => here === f || here.startsWith(`${f}/`))
}

// Each argument as the file system resolves it (symlinks, /var and /private/var); one that does not resolve stays as written.
const REAL = 'for p; do (cd "$p" 2>/dev/null && pwd -P) || printf "%s\\n" "$p"; done'

/** Privacy mode, or the session's folder under a listed one, compared as written and as resolved on both sides. */
export async function isPrivateHere($: EngineInterface, o: Pick<Options, 'privacy' | 'privateFolders'>): Promise<boolean> {
  if (o.privacy) return true
  if (!o.privateFolders.trim()) return false
  const home = (await $.env.get('HOME')) ?? ''
  const cwd = await $.session.cwd()
  if (isPrivateFolder(cwd, o.privateFolders, home)) return true
  const list = folderList(o.privateFolders, home)
  const r = await $.process.run(['/bin/sh', '-c', REAL, 'sh', cwd, ...list], { timeoutMs: 3000 }).catch(() => undefined)
  const real = (r?.stdout ?? '').split('\n').filter(Boolean)
  return real.length === list.length + 1 && isPrivateFolder(real[0] ?? '', real.slice(1).join('\n'), home)
}
