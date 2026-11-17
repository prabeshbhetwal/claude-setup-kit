/** Agent call id (`tool_use_id`) -> the model the spawn resolved to. */
export type Models = Record<string, string>

declare module 'claude-code' {
  interface PluginState {
    'model-badge': { models: Models }
  }
}
