// model-pilot's evaluation: runs a labelled prompt set through the production
// judge and policy and scores it. `/pilot eval <file.jsonl>`; a development aid.
import type { EngineInterface } from 'claude-code'

import { judge } from './engine'
import type { Judged } from './engine'
import { rulesVerdict } from './judge'
import { decide, TIERS } from './policy'
import type { JudgeInput, Tier, Verdict } from './policy'

const HARD_STOP_MS = 8000

export type Case = { id: string; prompt: string; recent?: string; context_tokens?: number; kind?: 'prompt' | 'agent'; tier: Tier; effort: string }
export type Outcome = { id: string; by: string; label: Tier; picked: Tier; effort: string; labelEffort: string; source: string; ms: number; confidence: number; reason: string; gap?: string; checkable?: boolean }

const requiredOf = (verdict: Verdict, source: 'judge' | 'rules', contextTokens: number): Tier =>
  // A neutral session: menu on haiku, nothing cached, so the required tier is what runs.
  decide({ verdict, source, explicit: {}, menuTier: 'haiku', isModelPinned: false, isEffortPinned: false, contextTokens, warm: {}, now: 0, cacheTtlMs: 1, lowerStreak: 0, canUpgrade: true }).required

export function score(rows: readonly Outcome[]): Record<string, number> {
  const n = rows.length || 1
  const r = (t: Tier) => TIERS.indexOf(t)
  const ms = rows.filter(x => x.source === 'judge').map(x => x.ms).sort((a, b) => a - b)
  const at = (q: number) => ms[Math.min(ms.length - 1, Math.floor(q * ms.length))] ?? 0
  const pct = (k: number) => Math.round((1000 * k) / n) / 10
  return {
    cases: rows.length,
    exact_pct: pct(rows.filter(x => x.picked === x.label).length),
    under_pct: pct(rows.filter(x => r(x.picked) < r(x.label)).length),
    over_pct: pct(rows.filter(x => r(x.picked) > r(x.label)).length),
    over_by_2_pct: pct(rows.filter(x => r(x.picked) > r(x.label) + 1).length),
    effort_exact_pct: pct(rows.filter(x => x.effort === x.labelEffort).length),
    judged: ms.length,
    by_jev: rows.filter(x => x.by === 'jev').length,
    by_haiku: rows.filter(x => x.by === 'haiku').length,
    fell_back_to_rules: rows.filter(x => x.source === 'rules').length,
    judge_p50_ms: at(0.5),
    judge_p95_ms: at(0.95),
    judge_within_1500ms_pct: pct(ms.filter(m => m <= 1500).length * (n / (ms.length || 1))),
    judge_within_3000ms_pct: pct(ms.filter(m => m <= 3000).length * (n / (ms.length || 1))),
  }
}

export async function runEval($: EngineInterface, path: string, model: string): Promise<string> {
  if (!path) return 'Usage: /pilot eval <file.jsonl> [--jev | --haiku | --rules]'
  const flag = / --(jev|haiku|rules)$/.exec(path)?.[1] ?? 'chain'
  const isRulesOnly = flag === 'rules'
  const chain: readonly ('jev' | 'haiku')[] = flag === 'jev' ? ['jev'] : flag === 'haiku' ? ['haiku'] : ['jev', 'haiku']
  const file = path.replace(/ --(jev|haiku|rules)$/, '').trim()
  const cases = (await $.fs.read(file))
    .split('\n')
    .filter(l => l.trim() && !l.trim().startsWith('//'))
    .map(l => JSON.parse(l) as Case)
  const rows: Outcome[] = []
  const queue = [...cases]
  const worker = async (): Promise<void> => {
    for (let c = queue.shift(); c; c = queue.shift()) {
      const input: JudgeInput = { prompt: c.prompt, recent: c.recent ?? '', contextTokens: c.context_tokens ?? 30_000, currentTier: 'sonnet', kind: c.kind ?? 'prompt' }
      const j: Judged = isRulesOnly ? { verdict: rulesVerdict(input), source: 'rules', by: 'rules', ms: 0 } : await judge($, input, { isPrivate: false, budgetMs: HARD_STOP_MS, model, chain })
      rows.push({ id: c.id, by: j.by, label: c.tier, picked: requiredOf(j.verdict, j.source, input.contextTokens), effort: j.verdict.effort, labelEffort: c.effort, source: j.source, ms: j.ms, confidence: j.verdict.confidence, gap: j.verdict.gap, checkable: j.verdict.checkable, reason: j.fail ? `${j.verdict.reason} [${j.fail}]` : j.verdict.reason })
    }
  }
  // Two at a time: close to how prompts arrive, without queueing behind each other.
  await Promise.all([worker(), worker()])
  rows.sort((a, b) => a.id.localeCompare(b.id))
  const summary = score(rows)
  const out = `${file.replace(/\.jsonl$/, '')}.${flag}.results.json`
  await $.fs.write(out, `${JSON.stringify({ summary, rows }, null, 1)}\n`)
  return `${JSON.stringify(summary)}\nresults: ${out}`
}
