// model-pilot: per prompt, the cheapest Claude model and effort that will do the
// job reliably; a row above the prompt shows the pick and what actually ran.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import { appendLog, isRoutableAgent, judge } from './engine'
import { runEval } from './evalrun'
import { afterAnswer, FABLE_CHAT, fableQuestion, needsFableYes, RUN_FABLE, USE_OPUS } from './fable'
import { agentTier, estTurnCost, HANDOFF_PROMPT, spawnNote, tierOf } from './policy'
import type { Decision } from './policy'
import { begin, CACHE_TTL_MS, chainOf, finish, isPrivateHere, noteSwitch, prestart, record, settle, turnOf, warmNow } from './route'
import { bandText } from './band'
import { costText, HELP, statusText } from './status'
import type { Options } from './route'
import type { PilotFlags, PilotView } from '../types'

const view = atom({ plugin: 'model-pilot', key: 'view' } as const, null as PilotView | null)
const flags = atom({ plugin: 'model-pilot', key: 'flags' } as const, {
  isOn: true,
  isModelPinned: false,
  isEffortPinned: false,
} as PilotFlags)

/** The flags when the pilot is on, else undefined. */
async function activeFlags($: EngineInterface, isEnabled: boolean): Promise<PilotFlags | undefined> {
  if (!isEnabled) return undefined
  const f = await read($, flags)
  return f.isOn ? f : undefined
}

let isFableOkHere = false

/** When the pilot, not the person, chose Fable: ask first (unless switched off). Anything but a yes runs on Opus. */
async function withFableYes($: EngineInterface, o: Options, d: Decision, menuModel: string): Promise<Decision> {
  if (!needsFableYes(d, tierOf(menuModel) ?? 'sonnet', o.isShadow, o.confirmFable && !isFableOkHere)) return d
  const i = { contextTokens: (await $.session.usage()).context.tokens ?? 0, warm: warmNow(), now: await $.clock.now(), cacheTtlMs: CACHE_TTL_MS }
  const q = fableQuestion(d, estTurnCost('fable', d.required, i, 1, d.effort), estTurnCost('opus', d.required, i, 1, d.effort))
  const answer = await $.ui.ask(q, { options: [RUN_FABLE, FABLE_CHAT, USE_OPUS], header: 'Fable?' }).catch(() => undefined)
  if (answer === FABLE_CHAT) isFableOkHere = true
  return afterAnswer(d, answer)
}

export const register: Register = (on, options) => {
  const o: Options = {
    privacy: options.privacy === true,
    privateFolders: typeof options.privateFolders === 'string' ? options.privateFolders : '',
    allowUpgrade: options.allowUpgrade !== false,
    handoff: typeof options.handoff === 'string' ? options.handoff : 'auto',
    useJev: options.jev !== false,
    judgeBudgetMs: typeof options.judgeBudgetMs === 'number' && options.judgeBudgetMs > 0 ? options.judgeBudgetMs : 2500,
    judgeModel: typeof options.judgeModel === 'string' && options.judgeModel.trim() ? options.judgeModel.trim() : 'haiku',
    isShadow: options.shadow === true,
    confirmFable: options.confirmFable !== false,
  }
  const isEnabled = options.enabled !== false
  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'pilot', description: 'Model pilot: on, off, auto, status, cost', argumentHint: 'on|off|auto|status|cost' })
    if ((await $.store.get('isOn')) === false) await update($, flags, f => ({ ...f, isOn: false }))
    return next(e)
  })

  on('prompt.submit', async ($, e, next) => {
    // Only a prompt that starts a turn of its own; the judge then runs while the turn is set up.
    if (!e.command && !e.isMeta && e.turnId === undefined) {
      try {
        const f = await activeFlags($, isEnabled)
        if (f) await prestart($, o, f, e.text)
      } catch {
        // judged at turn.start instead
      }
    }
    return next(e)
  })

  on('turn.start', async ($, e, next) => {
    if (e.agentId === undefined) {
      try {
        const f = await activeFlags($, isEnabled)
        if (f) await begin($, o, f, e.turnId, e.text)
      } catch {
        // the turn runs on the menu's model
      }
    }
    return next(e)
  })

  on('turn.step', async function* ($, e, next) {
    const rec = e.agentId === undefined ? turnOf(e.turnId) : undefined
    if (!rec || rec.isFailed) return yield* next(e)
    if (!rec.decision) {
      try {
        const f = await read($, flags)
        const settled = await settle($, o, f, rec, e)
        rec.decision = await withFableYes($, o, settled.decision, e.model)
        if (settled.flags) {
          const pinned = settled.flags
          await update($, flags, () => pinned)
          $.ui.toast('model-pilot: you changed the menu, so that choice is yours now. /pilot auto hands it back.')
        }
      } catch {
        rec.isFailed = true
        return yield* next(e)
      }
    }
    // The same pick for every request of the turn: the model never changes mid-turn.
    const d = rec.decision
    if (o.isShadow) {
      const out = yield* next(e)
      record(rec, out.usage)
      return out
    }
    const model = d.tier && tierOf(e.model) !== d.tier ? d.tier : e.model
    const effort = d.effort && d.effort !== e.effort ? d.effort : e.effort
    if (model === e.model && effort === e.effort) {
      const out = yield* next(e)
      record(rec, out.usage)
      return out
    }
    const stream = next({ ...e, model, effort })
    let hasYielded = false
    try {
      for (;;) {
        const piece = await stream.next()
        if (piece.done) {
          record(rec, piece.value.usage)
          return piece.value
        }
        hasYielded = true
        yield piece.value
      }
    } catch (err) {
      if (hasYielded) throw err
      // The pick could not be sent (a model this account lacks, say): once, as the menu has it.
      rec.isFailed = true
      const out = yield* next(e)
      record(rec, out.usage)
      return out
    }
  })

  on('turn.complete', async ($, e, next) => {
    const out = await next(e)
    const rec = e.agentId === undefined ? turnOf(e.turnId) : undefined
    if (rec) {
      try {
        const shown = await finish($, o, e.turnId, rec)
        if (shown) {
          await update($, view, () => shown)
          if (shown.handoffTokens !== null) {
            $.ui.toast(`model-pilot: context is at ${Math.round(shown.handoffTokens / 1000)}k tokens. The row above the prompt offers a handoff to a fresh chat.`)
          }
        }
      } catch {
        // the row keeps what it showed
      }
    }
    return out
  })

  on('agent.spawn', async ($, e, next) => {
    let tier: string | undefined
    let line: Record<string, unknown> | undefined
    try {
      const f = options.subagents === false || o.isShadow ? undefined : await activeFlags($, isEnabled)
      if (f && !f.isModelPinned && e.model === undefined && e.subagentType !== 'fork' && (await isRoutableAgent($, e.subagentType))) {
        const j = await judge(
          $,
          { prompt: e.prompt, recent: '', contextTokens: 0, currentTier: tierOf(e.parentModel) ?? 'sonnet', kind: 'agent' },
          { isPrivate: await isPrivateHere($, o), budgetMs: o.judgeBudgetMs * 2, model: o.judgeModel, chain: chainOf(o) },
        )
        const parent = tierOf(e.parentModel) ?? 'sonnet'
        const picked = agentTier(j.verdict, j.source, parent)
        tier = picked
        const note = spawnNote(e.subagentType, picked, parent, { contextTokens: (await $.session.usage()).context.tokens ?? 0, warm: warmNow(), now: await $.clock.now(), cacheTtlMs: CACHE_TTL_MS })
        if (note) await update($, view, v => (v ? { ...v, tip: note } : v))
        line = { place_tip: note, judge: j.by, kind: 'agent', agent: e.subagentType, picked: tier, picked_effort: null, required: tier, menu: e.parentModel, source: j.source, reason: j.verdict.reason, confidence: j.verdict.confidence, judge_ms: j.ms, judge_fail: j.fail ?? null, prompt_chars: e.prompt.length }
      }
    } catch {
      tier = undefined
    }
    if (!tier || !line) return next(e)
    const out = await next({ ...e, model: tier })
    const actual = out.model ?? null
    void appendLog($, { ts: new Date(await $.clock.now()).toISOString(), session: await $.session.id(), ...line, actual, actual_from: 'api', mismatch: tierOf(actual ?? undefined) !== tier, est_saving_usd: 0 }).catch(() => undefined)
    return out
  })

  on('classic.PostModelSwitch', async ($, e, next) => {
    noteSwitch()
    if (isEnabled && (e.source === 'command' || e.source === 'picker' || e.source === 'sdk')) {
      await update($, flags, f => ({ ...f, isModelPinned: true }))
    }
    return next(e)
  })

  on('command.run', { command: 'pilot' }, async ($, e) => {
    const [word = 'status', ...rest] = e.args.trim().split(/\s+/)
    if (word === 'on' || word === 'off') {
      await update($, flags, f => ({ ...f, isOn: word === 'on' }))
      await $.store.set('isOn', word === 'on')
      return { text: `Model pilot is ${word}.${isEnabled ? '' : ' It is also switched off in the plugin settings, which wins.'}` }
    }
    if (word === 'auto') {
      await update($, flags, f => ({ ...f, isModelPinned: false, isEffortPinned: false }))
      return { text: 'Model and effort are the pilot\'s to pick again.' }
    }
    if (word === 'eval') return { text: await runEval($, rest.join(' '), o.judgeModel) }
    const f = await read($, flags)
    if (word === 'cost') {
      const usage = await $.session.usage()
      return { text: costText(usage.context.tokens ?? 0, tierOf(await $.session.model()) ?? 'sonnet', warmNow(), await $.clock.now(), CACHE_TTL_MS) }
    }
    if (word !== 'status' && word !== '') return { text: HELP }
    return { text: statusText({ isEnabled, isPrivacy: await isPrivateHere($, o), isShadow: o.isShadow, chain: chainOf(o), handoff: o.handoff, f, v: await read($, view) }) }
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (options.band === false || !isEnabled || e.props.hasSurvey) return next(e)
    const f = await read($, flags)
    const v = await read($, view)
    const { Box, Button, Text } = $.ui.resolve(e)
    const t = bandText(f, v, o.isShadow)
    const isPinned = f.isOn && (f.isModelPinned || f.isEffortPinned)
    const handoff = f.isOn && v !== null ? v.handoffTokens : null
    return (
      <Box flexDirection="column">
        <Box flexDirection="row" justifyContent="space-between" alignItems="center" gap={1}>
          <Box flexDirection="row" gap={1} flexShrink={1}>
            <Text weight="semibold">Model pilot</Text>
            {t.mode !== null && <Text dimColor>· {t.mode}</Text>}
          </Box>
          <Box flexDirection="row" gap={1}>
            {handoff !== null && (
              <Button key="handoff" label={`Write handoff (${Math.round(handoff / 1000)}k)`} onPress={async () => {
                await update($, view, x => (x ? { ...x, handoffTokens: null } : x))
                await $.prompt.submit({ text: HANDOFF_PROMPT, asUser: true })
              }} />
            )}
            {isPinned && <Button key="auto" plain label="Hand back" onPress={() => update($, flags, x => ({ ...x, isModelPinned: false, isEffortPinned: false }))} />}
            <Button key="power" plain label={f.isOn ? 'Turn off' : 'Turn on'} onPress={async () => {
              await update($, flags, x => ({ ...x, isOn: !x.isOn }))
              await $.store.set('isOn', !f.isOn)
            }} />
          </Box>
        </Box>
        <Text dimColor={!t.isWarning} color={t.isWarning ? 'warning' : undefined} wrap="truncate-end">{t.line}</Text>
        {t.tip !== null && <Text dimColor italic wrap="truncate-end">Tip: {t.tip}</Text>}
      </Box>
    )
  })
}
