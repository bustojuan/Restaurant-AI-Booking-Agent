import { defineConfig } from '@playwright/test'
import { resolve } from 'node:path'
export default defineConfig({
  testDir: 'tests/e2e',
  timeout: 90000,
  expect: { timeout: 12000 },
  workers: 1,
  reporter: 'list',
  use: { trace: 'retain-on-failure' },
  // A separately managed server avoids Windows process-tree teardown failures.
  // It must be the isolated tests/start-backend.py server, never a personal API.
  webServer:
    process.env.BARIA_E2E_EXTERNAL_SERVER === '1'
      ? undefined
      : {
          command: `"${resolve('../.venv/Scripts/python.exe')}" tests/start-backend.py`,
          url: 'http://127.0.0.1:18001/api/health',
          reuseExistingServer: false,
          timeout: 120000,
        },
  outputDir: 'test-results',
})
