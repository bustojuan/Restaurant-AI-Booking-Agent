import {
  test,
  expect,
  _electron as electron,
  type ElectronApplication,
  type Page,
} from '@playwright/test'
import { mkdtempSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
const origin = 'http://127.0.0.1:18001',
  token = 'frontend-test-only-token-no-real-access'
async function api(path: string, method = 'GET', body?: unknown, version?: number) {
  const r = await fetch(origin + '/api' + path, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      ...(version === undefined ? {} : { 'If-Match': `"${version}"` }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!r.ok) throw new Error(`Test API ${r.status}: ${await r.text()}`)
  return r.status === 204 ? null : r.json()
}
let app: ElectronApplication, page: Page, draftId: string
test.beforeEach(async () => {
  const draft = await api('/bookings', 'POST', {})
  draftId = draft.id
  const w = await api('/workspace')
  await api('/workspace', 'PUT', { active_draft_id: draft.id }, w.version)
  const launchEnv: Record<string, string> = {
    ...Object.fromEntries(
      Object.entries(process.env).filter((e): e is [string, string] => e[1] !== undefined),
    ),
    BARIA_BACKEND_URL: origin,
    LOCAL_API_TOKEN: token,
    BARIA_USER_DATA: mkdtempSync(join(tmpdir(), 'baria-electron-')),
  }
  delete launchEnv.ELECTRON_RUN_AS_NODE
  app = await electron.launch({ args: ['.'], cwd: process.cwd(), env: launchEnv })
  page = await app.firstWindow()
  await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setSize(1600, 900))
  await expect(page.getByText('Saved as draft', { exact: false })).toBeVisible()
  expect(await page.locator('html').getAttribute('lang')).toBe('en-GB')
})
test.afterEach(async ({}, info) => {
  if (page && info.status !== info.expectedStatus)
    await page.screenshot({ path: info.outputPath('failure.png') }).catch(() => {})
  await app?.close()
})
async function list() {
  await page.getByRole('button', { name: 'List', exact: true }).click()
  await expect(page.getByTestId('restaurant-madrid-1')).toBeVisible()
}
async function add(id: string) {
  await page
    .getByTestId(`restaurant-${id}`)
    .getByRole('button', { name: 'Add', exact: true })
    .click()
  await expect(page.getByTestId(`queue-${id}`)).toBeVisible()
}

test('English interface: booking dialogs, filters, favorites and drafts at desktop sizes', async () => {
  test.setTimeout(180000)
  await list()
  await add('madrid-1')
  await page
    .getByTestId('restaurant-madrid-1')
    .getByRole('button', { name: 'Save favorite Mesa del Sol' })
    .click()
  const directory = 'docs/screenshots/english-ui'
  mkdirSync(directory, { recursive: true })
  for (const [width, height] of [
    [1440, 900],
    [1920, 1080],
  ]) {
    await app.evaluate(
      ({ BrowserWindow }, size) =>
        BrowserWindow.getAllWindows()[0].setContentSize(size[0], size[1]),
      [width, height],
    )
    async function shot(name: string) {
      await page.waitForTimeout(200)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      )
      await page.screenshot({ path: `${directory}/${name}-${width}.png` })
    }
    await shot('restaurant-list')
    await page.getByRole('button', { name: 'Advanced filters', exact: true }).click()
    await expect(
      page.getByRole('heading', { name: 'Refine your search', exact: true }),
    ).toBeVisible()
    await expect(page.getByRole('button', { name: 'Fast Food', exact: true })).toBeVisible()
    await shot('filters')
    await page.keyboard.press('Escape')
    await page.locator('.diet-chips').getByRole('button', { name: 'Add', exact: true }).click()
    await expect(
      page.getByRole('heading', { name: 'Add dietary requirement', exact: true }),
    ).toBeVisible()
    await expect(page.getByRole('combobox', { name: 'Requirement type', exact: true })).toHaveValue(
      'allergy',
    )
    await shot('dietary-requirement')
    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: 'Favorites', exact: true }).first().click()
    await expect(page.getByRole('heading', { name: 'Your favorites' })).toBeVisible()
    await expect(page.locator('.favorite-item').filter({ hasText: 'Mesa del Sol' })).toBeVisible()
    await expect(page.locator('.favorite-item small').first()).toContainText(
      'Mediterranean · Spanish',
    )
    await shot('favorites')
    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: /^Bookings/ }).click()
    await page.getByRole('tab', { name: /Drafts/ }).click()
    await expect(page.getByRole('button', { name: 'Continue', exact: true }).first()).toBeVisible()
    await shot('drafts')
    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: 'Settings', exact: true }).click()
    await expect(page.getByText('FastAPI available', { exact: true })).toBeVisible()
    await shot('settings')
    await page.keyboard.press('Escape')
  }
})
async function dragTo(source: ReturnType<Page['locator']>, target: ReturnType<Page['locator']>) {
  await target.scrollIntoViewIfNeeded()
  await source.scrollIntoViewIfNeeded()
  const a = await source.boundingBox()
  if (!a) throw new Error('No drag source')
  await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2)
  await page.mouse.down()
  await page.mouse.move(a.x + a.width / 2 + 12, a.y + a.height / 2, { steps: 6 })
  await expect(page.locator('.desktop-app')).toHaveClass(/drag-active/)
  await target.scrollIntoViewIfNeeded()
  const b = await target.boundingBox()
  if (!b) throw new Error('No drop target')
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 18 })
  if ((await target.getAttribute('data-testid'))?.startsWith('drop-slot-')) {
    // Auto-scroll can move the intended gap while the pointer crosses the sidebar.
    await expect
      .poll(async () => {
        const current = await target.boundingBox()
        if (!current) return ''
        await page.mouse.move(current.x + current.width / 2, current.y + current.height / 2)
        return target.getAttribute('class')
      })
      .toMatch(/\bover\b/)
  }
  await page.mouse.up()
}

test('Catálogo OSM: mapa, búsqueda, selección y persistencia independientes', async () => {
  test.setTimeout(150000)
  test.skip(
    !process.env.E2E_CATALOG_SNAPSHOTS,
    'Requiere snapshots locales OSM; nunca descarga en tests',
  )
  await expect(page.getByTestId('map')).toHaveAttribute('data-loaded', 'true')
  await expect.poll(async () => page.locator('.map-pin').count()).toBeGreaterThan(5)
  let visiblePin: string | null = null
  await expect
    .poll(async () => {
      visiblePin = await page.locator('.map-pin').evaluateAll((pins) => {
        const pin = pins.find((p) => {
          const r = p.getBoundingClientRect()
          return r.x > 80 && r.x < 800 && r.y > 280 && r.y < 650
        })
        return pin?.getAttribute('data-testid') ?? null
      })
      return visiblePin
    })
    .toBeTruthy()
  await page.getByTestId(visiblePin!).click()
  const card = page.locator('.floating-card')
  await expect(card.getByText('OpenStreetMap record · ODbL')).toBeVisible()
  const id = (await card.getAttribute('data-testid'))!.replace('restaurant-', '')
  const source = await api(`/restaurants/${id}`)
  await expect(card.getByRole('heading', { level: 3 })).toHaveText(source.name)
  if (source.address) await expect(card.locator('.address')).toContainText(source.address)
  await dragTo(card.locator('.restaurant-card-body'), page.locator('.queue-empty'))
  await expect(page.getByTestId(`queue-${id}`)).toBeVisible()
  await card.getByRole('button', { name: /Save favorite/ }).click()
  await page.screenshot({ path: 'docs/screenshots/real-catalog-map.png' })
  await page.getByRole('button', { name: 'List', exact: true }).click()
  await expect(page.locator('.restaurant-card')).toHaveCount(40)
  await page.getByRole('button', { name: 'Navarra', exact: true }).click()
  await page.getByRole('textbox', { name: 'Search restaurants, areas' }).fill('Pamplona')
  const matches = await api('/restaurants?region=Navarra&catalog=real&q=Pamplona')
  await expect(page.locator('.list-heading .muted')).toHaveText(`${matches.total} results`)
  await expect(page.locator('.restaurant-card')).toHaveCount(Math.min(40, matches.total))
  await expect(page.getByTestId(`queue-${id}`)).toBeVisible()
  const persisted = await api(`/bookings/${draftId}`)
  expect(persisted.restaurants.map((e: { restaurant: { id: string } }) => e.restaurant.id)).toEqual(
    [id],
  )
  await page.reload()
  await expect(page.getByTestId(`queue-${id}`).locator('.priority')).toHaveText('1')
  expect((await api(`/restaurants/${id}`)).is_favorite).toBe(true)
  await expect
    .poll(async () => Number(await page.getByTestId('map').getAttribute('data-buildings')), {
      timeout: 45000,
    })
    .toBeGreaterThan(0)
  await page.screenshot({ path: 'docs/screenshots/real-catalog.png' })
})

for (const source of ['pin', 'card', 'handle'] as const) {
  test(`Arrastre desde mapa: ${source}, inserción y persistencia`, async () => {
    if (source === 'card') {
      let b = await api(`/bookings/${draftId}`)
      for (const restaurant_id of ['madrid-2', 'navarra-1'])
        b = await api(`/bookings/${draftId}/restaurants`, 'POST', { restaurant_id }, b.version)
      await page.reload()
      await expect(page.getByTestId('queue-navarra-1')).toBeVisible()
    }
    await expect(page.getByTestId('map')).toHaveAttribute('data-loaded', 'true')
    const pin = page.getByRole('button', { name: 'View Mesa del Sol', exact: true })
    await expect(pin).toBeVisible()
    if (source !== 'pin') {
      await pin.click()
      await expect(page.locator('.floating-card')).toBeVisible()
    }
    const draggable =
      source === 'pin'
        ? pin
        : source === 'card'
          ? page.locator('.floating-card .restaurant-card-body')
          : page
              .locator('.floating-card')
              .getByRole('button', { name: 'Drag Mesa del Sol into booking', exact: true })
    await dragTo(
      draggable,
      source === 'card' ? page.getByTestId('drop-slot-1') : page.locator('.queue-empty'),
    )
    await expect(page.getByTestId('queue-madrid-1')).toBeVisible()
    expect(
      (await api(`/bookings/${draftId}`)).restaurants.map(
        (e: { restaurant: { id: string } }) => e.restaurant.id,
      ),
    ).toEqual(source === 'card' ? ['madrid-2', 'madrid-1', 'navarra-1'] : ['madrid-1'])
    await expect(page.getByTestId('map')).toBeVisible()
    await page.reload()
    await expect(page.getByTestId('queue-madrid-1').locator('.priority')).toHaveText(
      source === 'card' ? '2' : '1',
    )
  })
}
test('Electron seguro, mapa 3D real y composición en cuatro resoluciones', async () => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  const prefs = await app.evaluate(({ app }) =>
    app
      .getAppMetrics()
      .filter((m) => m.type === 'Tab')
      .map((m) => m.sandboxed),
  )
  expect(prefs).toContain(true)
  expect(
    await page.evaluate(() => ({
      node: typeof (window as unknown as { require?: unknown }).require,
      token: JSON.stringify(window.desktop).includes('LOCAL_API_TOKEN'),
    })),
  ).toEqual({ node: 'undefined', token: false })
  await expect(page.getByTestId('map')).toHaveAttribute('data-loaded', 'true', { timeout: 40000 })
  await expect
    .poll(async () => Number(await page.getByTestId('map').getAttribute('data-buildings')), {
      timeout: 40000,
    })
    .toBeGreaterThan(0)
  await expect(page.locator('.maplibregl-canvas')).toBeVisible()
  await expect(page.getByRole('button', { name: 'View Mesa del Sol', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'View Mesa del Sol', exact: true }).click()
  await expect(page.locator('.floating-card')).toBeVisible()
  mkdirSync('docs/screenshots', { recursive: true })
  for (const [width, height] of [
    [1920, 1080],
    [1600, 900],
    [1440, 900],
    [1280, 800],
  ]) {
    await app.evaluate(
      ({ BrowserWindow }, size) => {
        BrowserWindow.getAllWindows()[0].setSize(size[0], size[1])
      },
      [width, height],
    )
    await page.waitForTimeout(800)
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true)
    const sidebar = await page.locator('.booking-sidebar').boundingBox()
    expect(sidebar?.width).toBeGreaterThanOrEqual(369)
    await expect(
      page.getByRole('button', { name: 'Start AI Booking', exact: true }),
    ).toBeInViewport()
    await page.screenshot({ path: `docs/screenshots/desktop-${width}x${height}.png` })
  }
  await page.getByRole('button', { name: '2D', exact: true }).click()
  await page.getByRole('button', { name: '3D', exact: true }).click()
  await page.getByRole('button', { name: 'Navarra', exact: true }).click()
  await expect(page.getByText('Navarra', { exact: true }).first()).toBeVisible()
  await page.getByRole('button', { name: 'Settings', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible()
  await expect(page.getByText('FastAPI available')).toBeVisible()
  await page.keyboard.press('Escape')
  expect(errors).toEqual([])
})
test('Búsqueda, favoritos, selección independiente, autosave y persistencia', async () => {
  await list()
  await add('madrid-1')
  await add('madrid-2')
  await page
    .getByTestId('restaurant-madrid-1')
    .getByRole('button', { name: 'Save favorite Mesa del Sol' })
    .click()
  await page.getByRole('button', { name: 'Italian', exact: true }).click()
  await expect(page.getByTestId('restaurant-madrid-1')).toHaveCount(0)
  await expect(page.getByTestId('queue-madrid-1')).toBeVisible()
  await page.getByRole('button', { name: 'All', exact: true }).click()
  await page.getByRole('textbox', { name: 'Search restaurants, areas' }).fill('Sakura')
  await expect(page.getByTestId('restaurant-madrid-4')).toBeVisible()
  await expect(page.getByTestId('restaurant-madrid-2')).toHaveCount(0)
  await page.getByRole('button', { name: 'Clear search' }).click()
  await page.getByRole('button', { name: 'Navarra', exact: true }).click()
  await expect(page.getByTestId('restaurant-navarra-1')).toBeVisible()
  await add('navarra-1')
  await expect(page.getByTestId('queue-madrid-1')).toBeVisible()
  await page.getByRole('textbox', { name: 'Contact name' }).fill('Persona simulada')
  await page.getByRole('textbox', { name: 'Contact phone' }).fill('+34000000000')
  await page.getByLabel('Booking date').fill('2030-06-14')
  await page.getByLabel('Booking time').fill('21:00')
  await page
    .getByLabel('Special Requests', { exact: true })
    .fill('Celiaquía: zona tranquila, ocasión especial')
  await expect
    .poll(async () => {
      const b = await api(`/bookings/${draftId}`)
      return b.configuration.notes
    })
    .toBe('Celiaquía: zona tranquila, ocasión especial')
  await page.reload()
  await expect(page.getByTestId('queue-navarra-1')).toBeVisible()
  await expect(page.getByRole('textbox', { name: 'Contact name' })).toHaveValue('Persona simulada')
  await expect(page.getByLabel('Special Requests', { exact: true })).toHaveValue(
    'Celiaquía: zona tranquila, ocasión especial',
  )
  await page.getByRole('button', { name: 'Favorites', exact: true }).first().click()
  await expect(page.getByRole('heading', { name: 'Your favorites' })).toBeVisible()
  await expect(page.locator('.favorite-item').filter({ hasText: 'Mesa del Sol' })).toBeVisible()
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: /^Bookings/ }).click()
  await page.getByRole('tab', { name: /Drafts/ }).click()
  await expect(page.getByRole('button', { name: 'Continue', exact: true }).first()).toBeVisible()
})
test('Arrastrar desde explorador, insertar entre fichas, reordenar y limpiar', async () => {
  await list()
  await add('madrid-1')
  await add('madrid-2')
  await dragTo(
    page
      .getByTestId('restaurant-madrid-3')
      .getByRole('button', { name: 'Drag Asador de Prueba into booking' }),
    page.getByTestId('drop-slot-1'),
  )
  await expect(page.getByTestId('queue-madrid-3')).toBeVisible()
  await expect
    .poll(async () =>
      (await api(`/bookings/${draftId}`)).restaurants.map(
        (e: { restaurant: { id: string } }) => e.restaurant.id,
      ),
    )
    .toEqual(['madrid-1', 'madrid-3', 'madrid-2'])
  await dragTo(
    page.getByTestId('queue-madrid-2').getByRole('button', { name: 'Reorder Pasta de Prueba' }),
    page.getByTestId('queue-madrid-1'),
  )
  await expect
    .poll(async () =>
      (await api(`/bookings/${draftId}`)).restaurants.map(
        (e: { restaurant: { id: string } }) => e.restaurant.id,
      ),
    )
    .toEqual(['madrid-2', 'madrid-1', 'madrid-3'])
  await page
    .getByTestId('queue-madrid-3')
    .getByRole('button', { name: 'Move Asador de Prueba up' })
    .click()
  await expect
    .poll(async () => (await api(`/bookings/${draftId}`)).restaurants[1].restaurant.id)
    .toBe('madrid-3')
  await expect(
    page.getByTestId('restaurant-madrid-1').getByRole('button', { name: 'Added', exact: true }),
  ).toBeDisabled()
  await page.reload()
  await expect(page.getByTestId('queue-madrid-3').locator('.priority')).toHaveText('2')
  await page.getByRole('button', { name: 'Clear list' }).click()
  await page.getByRole('button', { name: 'Clear list', exact: true }).click()
  await expect(page.locator('.queue-item')).toHaveCount(0)
})
test('LangGraph simulado, aprobación real del backend y confirmación con eventos', async () => {
  const b = await api(`/bookings/${draftId}`)
  await api(
    `/bookings/${draftId}`,
    'PATCH',
    {
      configuration: {
        customer_name: 'Prueba de interfaz',
        contact_phone: '+34000000000',
        requested_date: '2030-06-14',
        preferred_time: '21:00',
        adults: 4,
      },
    },
    b.version,
  )
  let current = await api(`/bookings/${draftId}`)
  for (const id of ['madrid-1', 'madrid-2', 'madrid-3'])
    current = await api(
      `/bookings/${draftId}/restaurants`,
      'POST',
      { restaurant_id: id },
      current.version,
    )
  await page.reload()
  await page.getByRole('button', { name: 'Start AI Booking', exact: true }).click()
  await expect(page.getByText('This execution is a simulation')).toBeVisible()
  await page.getByRole('combobox', { name: 'Scenario', exact: true }).selectOption('approval')
  await page.getByRole('button', { name: 'Start simulation', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Your decision is needed' })).toBeVisible({
    timeout: 30000,
  })
  await expect(page.getByText('Deposit: 20 €')).toBeVisible()
  await page.keyboard.press('Escape')
  await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setSize(1920, 1080))
  await page.getByRole('button', { name: 'View Mesa del Sol', exact: true }).click()
  await page.getByRole('button', { name: /^Bookings/ }).click()
  await expect(page.locator('.execution-preview')).toBeVisible()
  await page.screenshot({ path: 'docs/screenshots/reservations-popover.png' })
  await page.getByRole('button', { name: 'View details', exact: true }).click()
  await page.getByRole('button', { name: 'Approve alternative', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'Simulated confirmation', exact: true }),
  ).toBeVisible({ timeout: 30000 })
  await expect(page.getByText('Booking Confirmed', { exact: true }).first()).toBeVisible()
  expect((await api(`/bookings/${draftId}`)).status).toBe('CONFIRMED')
  await page.screenshot({ path: 'docs/screenshots/execution-confirmed.png' })
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: /^Bookings/ }).click()
  await page.getByRole('tab', { name: /History/ }).click()
  await expect(
    page.locator('.history-preview').filter({ hasText: 'Booking Confirmed' }).first(),
  ).toBeVisible()
})
test('Concurrencia: conserva la edición pendiente y respeta cambios ajenos', async () => {
  const b = await api(`/bookings/${draftId}`)
  await page.getByRole('textbox', { name: 'Contact name' }).fill('Cambio local pendiente')
  await api(
    `/bookings/${draftId}`,
    'PATCH',
    { configuration: { notes: 'Cambio externo conservado' } },
    b.version,
  )
  await expect(page.locator('.save-status.error')).toBeVisible()
  await expect(page.getByRole('textbox', { name: 'Contact name' })).toHaveValue(
    'Cambio local pendiente',
  )
  await page.getByRole('button', { name: 'Review current version', exact: true }).click()
  await expect(page.getByLabel('Special Requests', { exact: true })).toHaveValue(
    'Cambio externo conservado',
  )
  await page.getByRole('textbox', { name: 'Contact name' }).fill('Cambio local revisado')
  await expect
    .poll(async () => (await api(`/bookings/${draftId}`)).configuration.customer_name)
    .toBe('Cambio local revisado')
  expect((await api(`/bookings/${draftId}`)).configuration.notes).toBe('Cambio externo conservado')
})
test('Cancelación de ejecución y reutilización como borrador sin llamar', async () => {
  let b = await api(`/bookings/${draftId}`)
  b = await api(
    `/bookings/${draftId}`,
    'PATCH',
    {
      configuration: {
        customer_name: 'Prueba cancelación',
        contact_phone: '+34000000000',
        requested_date: '2030-06-14',
        preferred_time: '21:00',
      },
    },
    b.version,
  )
  for (const id of ['madrid-1', 'madrid-2', 'madrid-3'])
    b = await api(`/bookings/${draftId}/restaurants`, 'POST', { restaurant_id: id }, b.version)
  await page.reload()
  await page.getByRole('button', { name: 'Start AI Booking', exact: true }).click()
  await page.getByRole('combobox', { name: 'Scenario', exact: true }).selectOption('all-full')
  await page.getByRole('button', { name: 'Start simulation', exact: true }).click()
  await page.getByRole('button', { name: 'Cancel execution', exact: true }).click()
  await page.getByRole('button', { name: 'Confirm cancellation', exact: true }).click()
  await expect.poll(async () => (await api(`/bookings/${draftId}`)).status).toBe('CANCELLED')
  await page.getByRole('button', { name: /Reuse as a new draft/ }).click()
  await expect(page.getByRole('textbox', { name: 'Contact name' })).toHaveValue(
    'Prueba cancelación',
  )
  await expect(page.locator('.queue-item')).toHaveCount(3)
  const workspace = await api('/workspace')
  expect(workspace.active_draft_id).not.toBe(draftId)
  expect((await api(`/bookings/${workspace.active_draft_id}`)).status).toBe('DRAFT')
})
test('Varios borradores: restaurar configuración y orden, eliminar el inactivo', async () => {
  let b = await api(`/bookings/${draftId}`)
  b = await api(
    `/bookings/${draftId}`,
    'PATCH',
    { configuration: { notes: 'Borrador que conservar', adults: 5 } },
    b.version,
  )
  for (const id of ['madrid-2', 'navarra-1'])
    b = await api(`/bookings/${draftId}/restaurants`, 'POST', { restaurant_id: id }, b.version)
  await page.reload()
  await expect(page.locator('.queue-item')).toHaveCount(2)
  await page.getByRole('button', { name: 'New draft', exact: true }).click()
  await expect(page.locator('.queue-item')).toHaveCount(0)
  const other = (await api('/workspace')).active_draft_id
  await page.getByRole('button', { name: /^Bookings/ }).click()
  await page.getByRole('tab', { name: /Drafts/ }).click()
  await page
    .getByTestId(`draft-${draftId}`)
    .getByRole('button', { name: 'Continue', exact: true })
    .click()
  await expect(page.getByLabel('Special Requests', { exact: true })).toHaveValue(
    'Borrador que conservar',
  )
  await expect(page.getByTestId('queue-navarra-1').locator('.priority')).toHaveText('2')
  await page.getByRole('button', { name: /^Bookings/ }).click()
  await page.getByRole('tab', { name: /Drafts/ }).click()
  await page
    .getByTestId(`draft-${other}`)
    .getByRole('button', { name: 'Delete draft', exact: true })
    .click()
  await page.getByRole('dialog').getByRole('button', { name: 'Delete draft', exact: true }).click()
  await expect
    .poll(
      async () =>
        (
          await fetch(`${origin}/api/bookings/${other}`, {
            headers: { Authorization: `Bearer ${token}` },
          })
        ).status,
    )
    .toBe(404)
  expect(
    (await api(`/bookings/${draftId}`)).restaurants.map(
      (e: { restaurant: { id: string } }) => e.restaurant.id,
    ),
  ).toEqual(['madrid-2', 'navarra-1'])
})
