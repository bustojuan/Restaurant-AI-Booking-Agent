import {
  test,
  expect,
  _electron as electron,
  type ElectronApplication,
  type Page,
} from '@playwright/test'
import { mkdtempSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
const origin = 'http://127.0.0.1:18001',
  token = 'frontend-admin-test-only-token-no-real-access',
  root = '/api/admin/observability'
async function admin(path: string, method = 'GET', body?: unknown) {
  const response = await fetch(origin + root + path, {
    method,
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  expect(response.ok, await response.clone().text()).toBeTruthy()
  return response.json()
}
let app: ElectronApplication, page: Page
async function launch(options: { token?: string; admin?: boolean } = {}) {
  const env: Record<string, string> = {
    ...Object.fromEntries(
      Object.entries(process.env).filter((e): e is [string, string] => e[1] !== undefined),
    ),
    BARIA_BACKEND_URL: origin,
    LOCAL_API_TOKEN: 'frontend-test-only-token-no-real-access',
    ADMIN_API_TOKEN: options.token ?? token,
    BARIA_ADMIN_ONLY: options.admin === false ? '0' : '1',
    BARIA_USER_DATA: mkdtempSync(join(tmpdir(), 'baria-admin-e2e-')),
  }
  delete env.ELECTRON_RUN_AS_NODE
  app = await electron.launch({ args: ['.'], cwd: process.cwd(), env })
  page = await app.firstWindow()
  await page.waitForLoadState('domcontentloaded')
}
async function resize(width: number, height: number) {
  await app.evaluate(
    ({ BrowserWindow }, { width, height }) => {
      const win =
        BrowserWindow.getAllWindows().find((w) => w.getTitle() === 'AI Control Center') ??
        BrowserWindow.getAllWindows()[0]
      win.setContentSize(width, height)
    },
    { width, height },
  )
}
test.afterEach(async ({}, info) => {
  if (page && info.status !== info.expectedStatus)
    await page.screenshot({ path: info.outputPath('failure.png') }).catch(() => {})
  await app?.close()
})
test('AI Control Center: histórico, filtros, agrupación y replay persistido en Electron', async () => {
  test.setTimeout(180000)
  const run = await admin('/playground/runs', 'POST', {
    scenario_id: 'priority-success',
    adults: 4,
    flexibility_minutes: 30,
  })
  await expect
    .poll(async () => (await admin(`/playground/runs/${run.booking_id}`)).passed, {
      timeout: 30000,
    })
    .toBe(true)
  await launch()
  await resize(1440, 900)
  await expect(page.getByTestId('admin-calls')).toBeVisible()
  expect(
    await page.evaluate(() => ({
      desktop: typeof window.desktop,
      admin: !!window.admin,
      bridgeKeys: Object.keys(window.admin ?? {}).sort(),
    })),
  ).toEqual({
    desktop: 'undefined',
    admin: true,
    bridgeKeys: [
      'request',
      'connection',
      'connect',
      'openBooker',
      'onEvent',
      'onConnection',
      'window',
    ].sort(),
  })
  await page.getByRole('textbox', { name: 'Search calls' }).fill(run.booking_id)
  await expect(page.locator('[data-testid^="call-row-"]')).toHaveCount(3)
  await page.getByRole('combobox', { name: 'Filter result' }).selectOption('CONFIRMED')
  await expect(page.locator('[data-testid^="call-row-"]')).toHaveCount(1)
  await page.getByRole('combobox', { name: 'Filter result' }).selectOption('')
  await page.getByRole('tab', { name: 'Booking view' }).click()
  await page.getByRole('button', { name: /Booking #/ }).click()
  await expect(page.locator('.ac-booking-children button')).toHaveCount(3)
  await page.getByRole('tab', { name: 'Call view' }).click()
  const id = (await admin(`/calls?q=${run.booking_id}&direction=asc`)).items[2].id
  const countBefore = (await admin('/calls')).total
  await page.getByTestId(`call-row-${id}`).click()
  await expect(page.getByTestId('call-detail')).toBeVisible()
  await expect(page.getByTestId('agent-graph')).toBeVisible()
  await page.getByRole('button', { name: /All events/ }).click()
  await expect(
    page.getByText('Transcript unavailable for this call', { exact: true }),
  ).toBeVisible()
  await expect(page.locator('.react-flow__node')).not.toHaveCount(0)
  await expect(page.locator('.ac-waterfall-row')).not.toHaveCount(0)
  await page.getByRole('button', { name: 'Previous event', exact: true }).click()
  await page.getByRole('button', { name: 'Next event', exact: true }).click()
  await page.getByRole('button', { name: 'Close inspector', exact: true }).click()
  await page.getByRole('slider', { name: 'Replay position' }).focus()
  await page.getByRole('slider', { name: 'Replay position' }).press('Home')
  await page.getByRole('button', { name: 'Play history', exact: true }).click()
  await page.getByRole('button', { name: 'Pause replay', exact: true }).click()
  expect((await admin('/calls')).total).toBe(countBefore)
  await page.reload()
  await expect(page.getByTestId('admin-calls')).toBeVisible()
  await page.getByRole('textbox', { name: 'Search calls' }).fill(run.booking_id)
  await expect(page.locator('[data-testid^="call-row-"]')).toHaveCount(3)
  await app.close()
  await launch()
  await page.getByRole('textbox', { name: 'Search calls' }).fill(run.booking_id)
  await expect(page.locator('[data-testid^="call-row-"]')).toHaveCount(3)
})
test('Revisión visual de las seis vistas a 1440 y 1920, datos de simulación identificados', async () => {
  test.setTimeout(240000)
  const run = await admin('/playground/runs', 'POST', {
    scenario_id: 'priority-success',
    adults: 4,
    flexibility_minutes: 30,
  })
  await expect
    .poll(async () => (await admin(`/playground/runs/${run.booking_id}`)).passed, {
      timeout: 30000,
    })
    .toBe(true)
  const calls = await admin(`/calls?q=${run.booking_id}`),
    call = calls.items.find((c: { result: string }) => c.result === 'CONFIRMED')
  await launch()
  const directory = 'docs/screenshots/control-center'
  mkdirSync(directory, { recursive: true })
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  async function shot(name: string, width: number) {
    await page.waitForTimeout(250) // Allow discrete navigation/fit animations to settle before visual review.
    await page.screenshot({ path: `${directory}/${name}-${width}.png` })
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth),
    ).toBe(false)
  }
  for (const [width, height] of [
    [1440, 900],
    [1920, 1080],
  ]) {
    await resize(width, height)
    await page.getByRole('button', { name: 'Calls', exact: false }).first().click()
    await expect(page.getByTestId('admin-calls')).toBeVisible()
    await expect(page.locator('[data-testid^="call-row-"]')).not.toHaveCount(0)
    await shot('calls', width)
    await page.getByTestId(`call-row-${call.id}`).click()
    await expect(page.getByTestId('agent-graph')).toBeVisible()
    await expect(page.locator('.react-flow__node')).not.toHaveCount(0)
    await shot('call-detail', width)
    await page.getByRole('button', { name: 'Expand graph' }).click()
    await shot('agent-graph', width)
    await page.getByRole('button', { name: 'Restore graph' }).click()
    const node = page
      .locator('.react-flow__node')
      .filter({ has: page.getByText('Supervisor', { exact: true }) })
    await node.click()
    await expect(page.getByTestId('agent-inspector')).toBeVisible()
    const graphWidth = async () => (await page.getByTestId('agent-graph').boundingBox())!.width
    const before = await graphWidth()
    const resizeHandle = page.getByRole('separator', { name: 'Resize panels' })
    await resizeHandle.focus()
    await resizeHandle.press('ArrowLeft')
    await expect.poll(graphWidth).toBeLessThan(before)
    await resizeHandle.press('ArrowRight')
    await page.getByRole('tab', { name: 'I/O', exact: true }).click()
    await shot('inspector', width)
    await page.getByRole('button', { name: 'Analytics', exact: true }).click()
    await expect(page.getByText('Confirmed bookings', { exact: true })).toBeVisible()
    await shot('analytics', width)
    await page.getByRole('button', { name: 'Playground', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Run simulation', exact: true })).toBeEnabled()
    await shot('playground', width)
    await page.getByRole('button', { name: 'Settings', exact: true }).click()
    await expect(page.getByText('Backend connected', { exact: true })).toBeVisible()
    await shot('settings', width)
  }
  expect(errors).toEqual([])
})
test('Playground ejecuta escenarios existentes y abre sus trazas; estados vacíos y acceso denegado', async () => {
  test.setTimeout(120000)
  await launch()
  await resize(1440, 900)
  await page.getByRole('textbox', { name: 'Search calls' }).fill('inexistente-xyz')
  await expect(page.getByText('No calls to display')).toBeVisible()
  await page.getByRole('button', { name: 'Playground', exact: true }).click()
  await page.getByRole('button', { name: /First restaurant confirms/ }).click()
  await page.getByRole('button', { name: 'Run simulation', exact: true }).click()
  await expect(page.getByText('Evaluation passed', { exact: true })).toBeVisible({
    timeout: 30000,
  })
  await page.locator('.ac-simulation-calls button').first().click()
  await expect(page.getByTestId('call-detail')).toBeVisible()
  await app.close()
  await launch({ token: 'wrong-admin-token-but-long-enough-1234' })
  await expect(page.getByRole('alert')).toContainText('Administrative access denied')
})
test('Abrir, cerrar y reabrir administrador desde la aplicación principal', async () => {
  await launch({ admin: false })
  const opened = app.waitForEvent('window')
  await page.getByRole('button', { name: 'AI Control Center', exact: true }).click()
  const adminPage = await opened
  await expect(adminPage.getByTestId('admin-calls')).toBeVisible()
  await adminPage.getByRole('button', { name: 'Close administrator' }).click()
  await expect.poll(async () => app.windows().length).toBe(1)
  await page.getByRole('button', { name: 'AI Control Center', exact: true }).click()
  await expect.poll(async () => app.windows().length).toBe(2)
})

test('Replay por invocación, especialistas durante contacto y explicaciones con evidencias', async () => {
  test.setTimeout(240000)
  const run = await admin('/playground/runs', 'POST', { scenario_id: 'confirm-first' })
  await expect
    .poll(async () => (await admin(`/playground/runs/${run.booking_id}`)).passed, {
      timeout: 30000,
    })
    .toBe(true)
  const c = (await admin(`/calls?q=${run.booking_id}`)).items[0]
  const events = (await admin(`/events?execution_id=${c.execution_id}&limit=200`)).items
  const supervisors = events.filter(
    (e: any) => e.kind === 'graph.node' && e.node === 'supervisor' && e.phase === 'started',
  )
  await launch()
  await page.getByRole('textbox', { name: 'Search calls' }).fill(run.booking_id)
  await page.getByTestId(`call-row-${c.id}`).click()
  await expect(page.getByTestId('attempt-summary')).toBeVisible()
  await expect(page.getByTestId('attempt-summary')).toContainText(
    'A simulated confirmation has been stored',
  )
  await page.getByRole('button', { name: 'View evidence: Saved request', exact: true }).click()
  await expect(page.getByTestId('attempt-evidence')).toContainText('flexibility_minutes')
  await expect(page.locator('[data-contact-agent="negotiation"]')).toBeVisible()
  await expect(page.locator('[data-contact-agent="verification"]')).toBeVisible()
  await expect(page.locator('.react-flow__node').filter({ hasText: 'Offer Review' })).toBeVisible()
  await page.getByRole('button', { name: /All events/ }).click()
  await page
    .getByRole('button', { name: `Event ${supervisors[1].id} graph.node`, exact: true })
    .click()
  await expect(page.getByTestId('invocation-context')).toContainText('Supervisor · invocation 2')
  await expect(page.getByTestId('invocation-context')).toContainText('Verification')
  const intersectsOtherNodes = await page
    .locator(
      '[data-path-source="verification"][data-path-target="supervisor"] .react-flow__edge-path',
    )
    .evaluate((element) => {
      const path = element as SVGPathElement,
        matrix = path.getScreenCTM()!
      const nodes = [...document.querySelectorAll('.react-flow__node')]
        .filter((n) => !['supervisor', 'verification'].includes(n.getAttribute('data-id') ?? ''))
        .map((n) => n.getBoundingClientRect())
      for (let at = 8; at < path.getTotalLength() - 8; at += 4) {
        const point = path.getPointAtLength(at)
        const screen = new DOMPoint(point.x, point.y).matrixTransform(matrix)
        if (
          nodes.some(
            (r) =>
              screen.x > r.left + 2 &&
              screen.x < r.right - 2 &&
              screen.y > r.top + 2 &&
              screen.y < r.bottom - 2,
          )
        )
          return true
      }
      return false
    })
  expect(intersectsOtherNodes).toBe(false)
  await expect(
    page.locator('[data-active-path="true"][data-path-target="supervisor"]'),
  ).toHaveCount(1)
  await expect(page.locator('[data-active-path="true"][data-path-source="planning"]')).toHaveCount(
    0,
  )
  await page.getByRole('button', { name: 'Close inspector', exact: true }).click()
  for (const [width, height] of [
    [1440, 900],
    [1920, 1080],
  ]) {
    await resize(width, height)
    await page.waitForTimeout(250) // Let React Flow refit after inspector/viewport changes.
    await page.screenshot({
      path: `docs/screenshots/control-center/replay-invocation-${width}.png`,
    })
    await page.getByRole('button', { name: 'Expand graph' }).click()
    await page.waitForTimeout(250)
    await page.screenshot({ path: `docs/screenshots/control-center/contact-graph-${width}.png` })
    await page.getByRole('button', { name: 'Restore graph' }).click()
  }
  await page
    .getByRole('button', { name: `Event ${supervisors[0].id} graph.node`, exact: true })
    .click()
  await expect(page.getByTestId('invocation-context')).toContainText('Supervisor · invocation 1')
  await expect(
    page.locator('[data-active-path="true"][data-path-source="verification"]'),
  ).toHaveCount(0)
  await page.getByRole('button', { name: 'Close inspector', exact: true }).click()
  await page.getByRole('slider', { name: 'Replay position' }).focus()
  await page.getByRole('slider', { name: 'Replay position' }).press('End')
  await expect(page.locator('[data-active-path="true"]')).toHaveCount(0)
  await page.getByRole('button', { name: /Attempt summary/ }).click()
  const callCount = (await admin('/calls')).total
  const detail = await admin(`/calls/${c.id}`)
  const cursor = detail.explanation.facts.find((f: any) => f.code === 'business_event').evidence[0]
    .event_cursor
  await page.getByRole('button', { name: `View evidence: Event #${cursor}`, exact: true }).click()
  await expect(page.getByTestId('attempt-evidence')).toContainText(`Event #${cursor} selected`)
  expect((await admin('/calls')).total).toBe(callCount)
})

test('Ambigüedad: continuación sin aceptación frente a revisión de posible reserva', async () => {
  test.setTimeout(240000)
  await launch()
  for (const [scenario, title] of [
    ['ai-ambiguous', 'No accepted proposal: the queue could continue'],
    ['ai-incomplete-confirmation', 'A booking may exist: review required'],
  ]) {
    const run = await admin('/playground/runs', 'POST', { scenario_id: scenario })
    await expect
      .poll(async () => (await admin(`/playground/runs/${run.booking_id}`)).passed != null, {
        timeout: 60000,
      })
      .toBe(true)
    const c = (await admin(`/calls?q=${run.booking_id}&direction=asc`)).items[0]
    await page.getByRole('textbox', { name: 'Search calls' }).fill(run.booking_id)
    await page.getByTestId(`call-row-${c.id}`).click()
    await expect(page.getByTestId('attempt-review')).toContainText(title)
    if (scenario === 'ai-incomplete-confirmation') {
      await page.getByText('Review procedure', { exact: true }).click()
      await expect(page.getByTestId('attempt-review')).toContainText(
        'Do not contact the restaurant',
      )
      await expect(page.getByTestId('attempt-review')).toContainText('read-only')
      for (const [width, height] of [
        [1440, 900],
        [1920, 1080],
      ]) {
        await resize(width, height)
        await page.screenshot({
          path: `docs/screenshots/control-center/ambiguity-review-${width}.png`,
        })
      }
    }
    await page.locator('.ac-breadcrumb').getByRole('button', { name: 'Calls', exact: true }).click()
  }
})

test('Abrir reservas desde el administrador, reutilizar y reabrir la ventana con su borrador', async () => {
  await launch()
  await expect(page.getByTestId('admin-calls')).toBeVisible()
  for (const width of [1440, 1920]) {
    await resize(width, width === 1440 ? 900 : 1080)
    await expect(page.getByRole('button', { name: 'Booking app', exact: true })).toBeInViewport()
    await page.screenshot({ path: `docs/screenshots/control-center/navigation-${width}.png` })
  }
  const opened = app.waitForEvent('window')
  await page.getByRole('button', { name: 'Booking app', exact: true }).click()
  const booker = await opened
  await expect(booker.getByText('Saved as draft', { exact: false })).toBeVisible()
  expect(
    await booker.evaluate(() => ({ admin: typeof window.admin, desktop: !!window.desktop })),
  ).toEqual({ admin: 'undefined', desktop: true })
  expect(await page.evaluate(() => typeof window.desktop)).toBe('undefined')
  const currentDraft = () =>
    booker.evaluate(async () => {
      const workspace = await window.desktop!.request({ method: 'GET', path: '/api/workspace' })
      if (workspace.status !== 200)
        throw new Error(`Workspace HTTP ${workspace.status}: ${JSON.stringify(workspace.data)}`)
      return (workspace.data as { active_draft_id: string }).active_draft_id
    })
  await expect.poll(currentDraft).toBeTruthy() // Wait for the persisted workspace, not its initial UI label.
  const draftId = await currentDraft()
  expect(draftId).toBeTruthy()
  await booker.getByRole('button', { name: 'Minimize window', exact: true }).click()
  await page.getByRole('button', { name: 'Booking app', exact: true }).click()
  await expect
    .poll(() =>
      app.evaluate(({ BrowserWindow }) => {
        const win = BrowserWindow.getAllWindows().find((w) =>
          w.webContents.getURL().endsWith('index.html'),
        )
        return !!win && win.isVisible() && !win.isMinimized()
      }),
    )
    .toBe(true)
  expect(await currentDraft()).toBe(draftId)
  expect(app.windows()).toHaveLength(2)
  await booker.getByRole('button', { name: 'AI Control Center', exact: true }).click()
  expect(app.windows()).toHaveLength(2)
  await booker.getByRole('button', { name: 'Close application', exact: true }).click()
  await expect.poll(() => app.windows().length).toBe(1)
  const reopened = app.waitForEvent('window')
  await page.getByRole('button', { name: 'Booking app', exact: true }).click()
  const nextBooker = await reopened
  await expect(nextBooker.getByText('Saved as draft', { exact: false })).toBeVisible()
  expect(
    await nextBooker.evaluate(async () => {
      const workspace = await window.desktop!.request({ method: 'GET', path: '/api/workspace' })
      return (workspace.data as { active_draft_id: string }).active_draft_id
    }),
  ).toBe(draftId)
  await page.getByRole('button', { name: 'Close administrator', exact: true }).click()
  page = nextBooker
  await expect.poll(() => app.windows().length).toBe(1)
  const adminOpened = app.waitForEvent('window')
  await nextBooker.getByRole('button', { name: 'AI Control Center', exact: true }).click()
  await expect((await adminOpened).getByTestId('admin-calls')).toBeVisible()
})
test('Una llamada conservada sin telemetría no inventa el grafo y puede actualizarse', async () => {
  const run = await admin('/playground/runs', 'POST', { scenario_id: 'confirm-first' })
  await expect
    .poll(async () => (await admin(`/playground/runs/${run.booking_id}`)).passed, {
      timeout: 30000,
    })
    .toBe(true)
  const calls = await admin(`/calls?q=${run.booking_id}`),
    id = calls.items[0].id
  const headers = { Authorization: 'Bearer frontend-test-only-token-no-real-access' }
  const booking = await (
    await fetch(`${origin}/api/bookings/${run.booking_id}`, { headers })
  ).json()
  const erased = await fetch(`${origin}/api/bookings/${run.booking_id}/ai/data`, {
    method: 'DELETE',
    headers: { ...headers, 'If-Match': `"${booking.version}"` },
  })
  expect(erased.status).toBe(204)
  await launch()
  await resize(1440, 900)
  await page.getByRole('textbox', { name: 'Search calls' }).fill(run.booking_id)
  await page.getByTestId(`call-row-${id}`).click()
  await page.getByRole('button', { name: /All events/ }).click()
  await expect(page.getByRole('button', { name: 'Follow live', exact: true })).toBeDisabled()
  await expect(page.getByText('Historical graph unavailable', { exact: true })).toBeVisible()
  await expect(page.getByText('No retained timeline', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Refresh details', exact: true }).click()
  await expect(
    page.getByText('Transcript unavailable for this call', { exact: true }),
  ).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
})
