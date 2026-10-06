export type CostLine = { usd: number; contextPercent: number | null }

declare module 'claude-code' {
  interface PluginState {
    forgeloop: { sessionCostLine: CostLine | null }
  }
}
