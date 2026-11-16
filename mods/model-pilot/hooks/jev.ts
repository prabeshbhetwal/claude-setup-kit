// model-pilot's Jev judge (TypeSafe): the request body and the reading of its answer. Pure.
// Jev answers a choice with a probability per option, so "how sure the tier is high
// enough" is measured, not self-reported: 1 minus the weight on the tiers above the pick.
import { RULES_FOR_JUDGES, TIER_GUIDE, defaultEffort } from './judge'
import { EFFORTS, TIERS } from './policy'
import type { JudgeInput, Verdict } from './policy'

const clip = (s: string, head: number, tail: number): string =>
  s.length <= head + tail ? s : `${s.slice(0, head)}\n[... ${s.length - head - tail} characters cut ...]\n${s.slice(-tail)}`

/** The body `jev raw` posts: the request as state, two choice questions over it. */
export function jevBody(i: JudgeInput): Record<string, unknown> {
  return {
    model: 'jev-latest',
    state: {
      kind: i.kind,
      request: clip(i.prompt, 1800, 1200),
      request_chars: i.prompt.length,
      recent: i.recent || '(none: this is the first request)',
      context_tokens: i.contextTokens,
    },
    questions: {
      tier: {
        type: 'choice',
        instructions: `Which is the cheapest Claude model tier that will do \`request\` reliably? You route it; you do not answer it.\n${RULES_FOR_JUDGES}`,
        criteria: TIER_GUIDE,
      },
      effort: {
        type: 'choice',
        instructions: 'How much reasoning effort does `request` need? Haiku-tier tasks are low; sonnet-tier tasks are medium unless truly trivial; opus-tier medium or high.',
        criteria: { low: 'no real reasoning needed', medium: 'ordinary work', high: 'hard or risky', xhigh: 'hardest problems only' },
      },
    },
  }
}

/** Reads `jev raw`'s output; undefined when it holds no usable verdict. */
export function parseJevReply(stdout: string): Verdict | undefined {
  let raw: unknown
  try {
    raw = JSON.parse(stdout)
  } catch {
    return undefined
  }
  const answers = (raw as { answers?: Record<string, { choice?: unknown; confidence?: unknown; probabilities?: Record<string, unknown> }> } | null)?.answers
  const tier = TIERS.find(t => t === answers?.tier?.choice)
  if (!tier) return undefined
  const probs = answers?.tier?.probabilities ?? {}
  const above = TIERS.slice(TIERS.indexOf(tier) + 1).reduce((sum, t) => sum + (typeof probs[t] === 'number' ? (probs[t] as number) : 0), 0)
  const self = typeof answers?.tier?.confidence === 'number' ? answers.tier.confidence : 0.5
  const confidence = Object.keys(probs).length ? Math.min(1, Math.max(0, 1 - above)) : self
  const effort = EFFORTS.find(e => e === answers?.effort?.choice) ?? defaultEffort(tier)
  const runnerUp = TIERS.filter(t => t !== tier && typeof probs[t] === 'number' && (probs[t] as number) >= 0.05)
    .map(t => `${t} ${(probs[t] as number).toFixed(2)}`)
    .join(', ')
  return { tier, effort, confidence, reason: `Jev: ${tier} ${self.toFixed(2)}${runnerUp ? ` (also ${runnerUp})` : ''}` }
}
