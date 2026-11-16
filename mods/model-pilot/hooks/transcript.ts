// Reads what actually ran from a Claude Code session transcript (JSONL). Pure.

export type RanRow = { model: string; at: number }

/**
 * The model of the newest main-thread assistant row in `tail` (the last lines
 * of `<session>.jsonl`), with its timestamp. Rows look like
 * {"type":"assistant","isSidechain":false,"timestamp":"2026-01-02T03:04:05.678Z","message":{"model":"claude-x"}}.
 * Sub-agent rows (isSidechain) and the engine's synthetic rows are skipped.
 */
export function lastAssistantModel(tail: string): RanRow | undefined {
  const lines = tail.split('\n')
  for (let n = lines.length - 1; n >= 0; n--) {
    const line = lines[n]?.trim()
    if (!line || !line.includes('"assistant"')) continue
    let row: unknown
    try {
      row = JSON.parse(line)
    } catch {
      continue // a line cut in half by `tail`, or still being written
    }
    const r = row as { type?: unknown; isSidechain?: unknown; timestamp?: unknown; message?: { model?: unknown } }
    const model = r.message?.model
    if (r.type !== 'assistant' || r.isSidechain === true) continue
    if (typeof model !== 'string' || model === '' || model.startsWith('<')) continue
    const at = typeof r.timestamp === 'string' ? Date.parse(r.timestamp) : NaN
    return { model, at: Number.isNaN(at) ? 0 : at }
  }
  return undefined
}
