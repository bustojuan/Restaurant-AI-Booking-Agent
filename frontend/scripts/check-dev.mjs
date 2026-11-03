// Run after `npm run dev -- --remoteDebuggingPort 9223`; local QA only.
import { chromium } from '@playwright/test'
const browser = await chromium.connectOverCDP('http://127.0.0.1:9223')
try {
  const page = browser.contexts()[0].pages()[0]
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.reload()
  await page.getByRole('heading', { name: 'Configuración de la reserva' }).waitFor()
  const bridge = await page.evaluate(() => typeof window.desktop?.request === 'function')
  const nonce = await page.locator('meta[property="csp-nonce"]').getAttribute('nonce')
  if (!bridge || !nonce || errors.length)
    throw new Error('Development renderer verification failed')
  console.log(
    JSON.stringify({ renderer: 'ok', bridge, cspNonce: Boolean(nonce), pageErrors: errors.length }),
  )
  await page.evaluate(() => window.desktop.window('close'))
} finally {
  await browser.close()
}
