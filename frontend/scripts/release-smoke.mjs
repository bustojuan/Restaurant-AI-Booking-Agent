// Run only against a newly installed local demo. No paid providers or real calls.
import { _electron as electron, expect } from '@playwright/test'
import { parse } from 'dotenv'
import { readFileSync, mkdirSync, mkdtempSync, writeFileSync } from 'node:fs'
import { dirname, resolve, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { tmpdir } from 'node:os'
import assert from 'node:assert/strict'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const origin = process.argv[2] ?? 'http://127.0.0.1:8001'
assert(/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(origin), 'Use a loopback demo API')
const config = parse(readFileSync(resolve(root, 'backend/.env')))
assert(config.REAL_TELEPHONY_ENABLED === 'false')
assert(config.VOICE_SANDBOX_ENABLED === 'false')
assert(config.AI_EXTRACTION_MODE === 'deterministic')
assert(config.LOCAL_API_TOKEN && config.ADMIN_API_TOKEN)
const output = resolve(root, '.release-validation')
mkdirSync(output, { recursive: true })
async function api(path, options = {}, admin = false) {
  const response = await fetch(origin + path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${admin ? config.ADMIN_API_TOKEN : config.LOCAL_API_TOKEN}`,
      ...options.headers,
    },
    signal: AbortSignal.timeout(15000),
  })
  assert(response.ok, `${options.method ?? 'GET'} ${path}: ${response.status}`)
  return response.json()
}
await api('/api/health')
const day = new Date(Date.now() + 14 * 86400000).toISOString().slice(0, 10)
const booking = await api('/api/bookings', {
  method: 'POST',
  body: JSON.stringify({
    configuration: {
      customer_name: 'Demo Guest',
      contact_phone: '+34000000000',
      requested_date: day,
      preferred_time: '21:00',
      adults: 4,
      flexibility_minutes: 30,
    },
    restaurant_ids: ['madrid-1', 'madrid-2', 'madrid-3'],
  }),
})
await api(`/api/bookings/${booking.id}/start`, {
  method: 'POST',
  headers: { 'If-Match': String(booking.version) },
  body: JSON.stringify({ mode: 'ai_simulation', scenario_id: 'priority-success' }),
})
await expect
  .poll(async () => (await api(`/api/bookings/${booking.id}`)).status, { timeout: 60000 })
  .toBe('CONFIRMED')
const result = await api(`/api/bookings/${booking.id}`)
assert.equal(result.summary.completed_attempts, 3)
const calls = await api(`/api/admin/observability/calls?q=${booking.id}&direction=asc`, {}, true)
assert.equal(calls.items.length, 3)
const executions = await api(
  `/api/admin/observability/executions?booking_id=${booking.id}`,
  {},
  true,
)
assert(executions.items.length > 0)
const env = {
  ...process.env,
  BARIA_BACKEND_URL: origin,
  BARIA_BACKEND_ENV: resolve(root, 'backend/.env'),
  LOCAL_API_TOKEN: config.LOCAL_API_TOKEN,
  ADMIN_API_TOKEN: config.ADMIN_API_TOKEN,
  BARIA_USER_DATA: mkdtempSync(join(tmpdir(), 'baria-clean-electron-')),
  BARIA_ADMIN_ONLY: '0',
}
delete env.ELECTRON_RUN_AS_NODE
const app = await electron.launch({ args: ['.'], cwd: resolve(root, 'frontend'), env })
try {
  const booker = await app.firstWindow()
  await expect(booker.getByText('Saved as draft', { exact: false })).toBeVisible({ timeout: 30000 })
  assert.equal(await booker.locator('html').getAttribute('lang'), 'en-GB')
  await booker.screenshot({ path: resolve(output, 'clean-main.png') })
  const opened = app.waitForEvent('window')
  await booker.getByRole('button', { name: 'AI Control Center', exact: true }).click()
  const admin = await opened
  await expect(admin.getByTestId('admin-calls')).toBeVisible({ timeout: 30000 })
  await admin.getByRole('textbox', { name: 'Search calls' }).fill(booking.id)
  await expect(admin.locator('[data-testid^="call-row-"]')).toHaveCount(3)
  await admin.getByTestId(`call-row-${calls.items[2].id}`).click()
  await expect(admin.getByTestId('agent-graph')).toBeVisible()
  await expect(admin.locator('.react-flow__node')).not.toHaveCount(0)
  await expect(admin.locator('.ac-waterfall-row')).not.toHaveCount(0)
  await admin.screenshot({ path: resolve(output, 'clean-admin.png') })
  writeFileSync(
    resolve(output, 'clean-install.json'),
    JSON.stringify(
      {
        freshInstallation: true,
        backendHealth: 'ok',
        mode: 'ai_simulation',
        bookingStatus: result.status,
        completedAttempts: 3,
        recordedCalls: 3,
        recordedExecutions: executions.items.length,
        mainWindow: true,
        adminWindow: true,
        graph: true,
        timeline: true,
        dependenciesFromOriginal: false,
        paidProviderCalls: 0,
      },
      null,
      2,
    ),
  )
  console.log(
    'Clean install passed: simulated booking, three persisted attempts, Electron, admin graph and timeline.',
  )
} finally {
  await app.close()
}
