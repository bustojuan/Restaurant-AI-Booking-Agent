import { defineConfig, externalizeDepsPlugin } from 'electron-vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { resolve } from 'node:path'
import { randomBytes } from 'node:crypto'
const devNonce = randomBytes(18).toString('base64')
export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
    build: { rollupOptions: { input: resolve('electron/main/index.ts') } },
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        input: resolve('electron/preload/index.ts'),
        output: { format: 'cjs', entryFileNames: 'index.cjs' },
      },
    },
  },
  renderer: {
    root: '.',
    plugins: [
      {
        name: 'desktop-development-csp',
        apply: 'serve',
        transformIndexHtml: {
          order: 'pre',
          handler: (html) =>
            html.replace("script-src 'self'", `script-src 'self' 'nonce-${devNonce}'`),
        },
      },
      react(),
      tailwindcss(),
    ],
    html: { cspNonce: devNonce },
    server: { host: '127.0.0.1', port: 5174, strictPort: true },
    build: { rollupOptions: { input: 'index.html' } },
  },
})
