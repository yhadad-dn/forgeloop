import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { CostLine } from '../types/session-cost'

const line = atom({ plugin: 'forgeloop', key: 'sessionCostLine' } as const, null)

const format = (l: CostLine): string => {
  const cost = `$${l.usd.toFixed(2)}`
  return l.contextPercent === null ? cost : `${cost} · ctx ${Math.round(l.contextPercent)}%`
}

async function refresh($: EngineInterface): Promise<void> {
  if ((await $.env.get('FORGELOOP_COST_BAND'))?.toLowerCase() === 'off') {
    return
  }
  const usage = await $.session.usage()
  const current: CostLine = {
    usd: usage.cost?.usd ?? 0,
    contextPercent: usage.context.percent ?? null,
  }
  await update($, line, () => current)
  $.ui.status(format(current))
  $.ui.invalidate('ui.render')
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await refresh($)
    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    await refresh($)
    return done
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if ((await $.env.get('FORGELOOP_COST_BAND'))?.toLowerCase() === 'off') {
      return next(e)
    }
    const current = await read($, line)
    if (e.props.hasSurvey || current === null) {
      return next(e)
    }
    const { Box, Text } = $.ui.resolve(e)
    return (
      <Box>
        <Text dimColor>{`Session ${format(current)}`}</Text>
      </Box>
    )
  })
}
