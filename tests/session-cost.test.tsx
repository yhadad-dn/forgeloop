import { describe, expect, test } from 'claude-code/testing'

const USAGE = {
  startedAt: 0,
  context: { tokens: 82000, window: 200000, percent: 41 },
  rateLimits: [],
  cost: { usd: 1.8421 },
}

describe('session-cost band', () => {
  test('draws nothing before the first usage read', async ($, on) => {
    on('ui.render', ($, e) => {
      const { Box } = $.ui.resolve(e)
      return <Box />
    })
    for (const surface of ['terminal', 'desktop', 'vscode'] as const) {
      const ui = await $.ui.mount({
        plugin: 'forgeloop',
        surface,
        component: 'AbovePrompt',
        props: { hasSurvey: false },
      })
      expect(await ui.find({ type: 'Text', text: /Session \$/ })).toBeUndefined()
      await ui.unmount()
    }
  })

  test('shows cost and context after a session starts, on every surface', async ($, on) => {
    on('ui.render', ($, e) => {
      const { Box } = $.ui.resolve(e)
      return <Box />
    })
    on('session.usage', () => ({ value: USAGE }))
    let status: string | undefined
    on('ui.status', ($, e, next) => {
      status = e.text
      return next(e)
    })
    on('session.start', () => ({ cwd: '/' }))
    await $.session.start({ cwd: '/', surface: 'vscode', isInteractive: true })
    expect(status).toBe('$1.84 · ctx 41%')
    for (const surface of ['terminal', 'desktop', 'vscode'] as const) {
      const ui = await $.ui.mount({
        plugin: 'forgeloop',
        surface,
        component: 'AbovePrompt',
        props: { hasSurvey: false },
      })
      expect(await ui.find({ type: 'Text', text: /Session \$1\.84 · ctx 41%/ })).toBeDefined()
      await ui.unmount()
    }
  })
})
