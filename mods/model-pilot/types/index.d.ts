// model-pilot's state contract: the values its row above the prompt draws from.
export type PilotView = {
  /** The tier picked, or null when the model was left to the menu. */
  pickedTier: string | null
  /** The effort asked for; the API never reports effort back, so it stays "requested". */
  requestedEffort: string | null
  /** message.model of the turn's last reply, as the session transcript records it. */
  ranModel: string | null
  /** Where ranModel was read from. */
  ranFrom: 'transcript' | 'api' | null
  isMismatch: boolean
  /** True when the pick was only observed, not applied. */
  isShadow: boolean
  source: string
  /** Which judge decided: 'jev', 'haiku', 'rules', or null when none was asked. */
  judge: string | null
  reason: string
  /** A cost tip (sub-agent against in place), when one is worth giving. */
  tip: string | null
  /** Context tokens when a handoff is on offer, else null. */
  handoffTokens: number | null
}
export type PilotFlags = {
  isOn: boolean
  isModelPinned: boolean
  isEffortPinned: boolean
}
declare module 'claude-code' {
  interface PluginState {
    'model-pilot': { view: PilotView | null; flags: PilotFlags }
  }
}
