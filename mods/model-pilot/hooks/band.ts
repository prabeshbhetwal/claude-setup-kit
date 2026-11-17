// The words on model-pilot's row above the prompt. Pure, so the layout in register.tsx stays small.
import type { PilotFlags, PilotView } from '../types'

export type BandText = {
  /** Second word of the title line: shadow, off, or nothing. */
  mode: string | null
  /** The one line under the title. */
  line: string
  isWarning: boolean
  tip: string | null
}

const cap = (s: string): string => s.charAt(0).toUpperCase() + s.slice(1)

/** "claude-opus-5-5" → "Opus 5.5"; ids it cannot read are shown as they are. */
export function modelName(id: string | null): string {
  if (!id) return 'unknown'
  const m = /^claude-([a-z]+)-(\d+)(?:-(\d{1,2}))?(?:-\d{8})?$/.exec(id)
  return m ? `${cap(m[1] ?? '')} ${m[2] ?? ''}${m[3] ? `.${m[3]}` : ''}` : id
}

const judgeName = (j: string): string => (j === 'jev' ? 'Jev' : j === 'haiku' ? 'Haiku' : j)

export function bandText(f: PilotFlags, v: PilotView | null, isShadow: boolean): BandText {
  const mode = !f.isOn ? 'off' : isShadow ? 'shadow' : null
  const none = { isWarning: false, tip: null }
  if (!f.isOn) return { mode, line: "The menu's model runs.", ...none }
  if (v === null) return { mode, line: isShadow ? 'Watching: each prompt is judged, nothing is changed.' : 'Picks a model for each prompt.', ...none }
  const ran = modelName(v.ranModel)
  if (v.isMismatch) return { mode, line: `Picked ${cap(v.pickedTier ?? 'menu model')}, but ${ran} ran.`, isWarning: true, tip: v.tip }
  const effort = v.requestedEffort ? ` · ${v.requestedEffort} effort` : ''
  const judge = v.judge ? ` · judge ${judgeName(v.judge)}` : ''
  let line: string
  if (f.isModelPinned || v.pickedTier === null) line = `Your model: ${ran}${effort}`
  else if (v.isShadow) line = `Would pick ${cap(v.pickedTier)}${effort}  →  ran ${ran}${judge}`
  else line = `${cap(v.pickedTier)}${effort}  →  ran ${ran}${judge}`
  return { mode, line, isWarning: false, tip: v.tip }
}
