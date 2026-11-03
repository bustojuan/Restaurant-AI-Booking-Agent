import { en, UI_LOCALE } from '../../src/i18n/en'
import { app, BrowserWindow, ipcMain, shell, session, Menu } from 'electron'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { readFileSync, writeFileSync } from 'node:fs'
import { parse } from 'dotenv'
import { BookingEventStream } from './events'
import { allowedRequest, backendOrigin, externalUrl } from './policy'
import { adminRequest } from './admin-policy'
import { AdminEventStream } from './admin-events'
import type { Connection, DesktopSettings } from '../../src/types/bridge'
const here = dirname(fileURLToPath(import.meta.url))
app.commandLine.appendSwitch('lang', UI_LOCALE)
let win: BrowserWindow | null = null
let adminWin: BrowserWindow | null = null
let backendUrl = backendOrigin(process.env.BARIA_BACKEND_URL ?? 'http://127.0.0.1:8001')
const envPath = process.env.BARIA_BACKEND_ENV ?? resolve(here, '../../../backend/.env')
let token = process.env.LOCAL_API_TOKEN ?? ''
let adminToken = process.env.ADMIN_API_TOKEN ?? ''
try {
  adminToken ||= parse(readFileSync(envPath)).ADMIN_API_TOKEN ?? ''
} catch {}
if (!token) {
  try {
    token = parse(readFileSync(envPath)).LOCAL_API_TOKEN ?? ''
  } catch {
    /* UI reports missing token */
  }
}
const settings = (): DesktopSettings => ({ backendUrl, tokenConfigured: token.length >= 24 })
function connection(state: Connection) {
  if (win && !win.isDestroyed()) win.webContents.send('booking:connection', state)
}
const stream = new BookingEventStream(
  () => backendUrl,
  () => token,
  (event) => {
    if (win && !win.isDestroyed()) win.webContents.send('booking:event', event)
  },
  connection,
)
const adminStream = new AdminEventStream(
  () => backendUrl,
  () => adminToken,
  (event) => {
    if (adminWin && !adminWin.isDestroyed()) adminWin.webContents.send('admin:event', event)
  },
  (state) => {
    if (adminWin && !adminWin.isDestroyed()) adminWin.webContents.send('admin:connection', state)
  },
)
if (process.env.BARIA_USER_DATA) app.setPath('userData', process.env.BARIA_USER_DATA)
app.whenReady().then(() => {
  const settingsPath = join(app.getPath('userData'), 'connection.json')
  if (!process.env.BARIA_BACKEND_URL) {
    try {
      backendUrl = backendOrigin(JSON.parse(readFileSync(settingsPath, 'utf8')).backendUrl)
    } catch {}
  }
  const adminOnly = process.env.BARIA_ADMIN_ONLY === '1' || process.argv.includes('--admin')
  const devUrl = process.env.ELECTRON_RENDERER_URL
  const rendererFile = join(here, '../renderer/index.html')
  const trusted = (url: string) =>
    devUrl
      ? new URL(url).origin === new URL(devUrl).origin
      : url.split('#')[0] === pathToFileURL(rendererFile).href
  const openBooker = () => {
    if (win && !win.isDestroyed()) {
      if (win.isMinimized()) win.restore()
      win.show()
      win.focus()
      return
    }
    win = new BrowserWindow({
      width: 1600,
      height: 1000,
      minWidth: 1100,
      minHeight: 720,
      frame: false,
      backgroundColor: '#f8fafc',
      show: false,
      title: 'AI Restaurant Booker',
      webPreferences: {
        preload: join(here, '../preload/index.cjs'),
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
        webSecurity: true,
      },
    })
    win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
    win.webContents.on('will-navigate', (event, url) => {
      if (!trusted(url)) event.preventDefault()
    })
    win.webContents.on('will-attach-webview', (event) => event.preventDefault())
    win.once('ready-to-show', () => {
      win?.show()
      win?.focus()
    })
    win.on('closed', () => {
      stream.close()
      win = null
    })
    if (devUrl) void win.loadURL(devUrl)
    else void win.loadFile(rendererFile)
  }
  const openAdmin = () => {
    if (adminWin && !adminWin.isDestroyed()) {
      if (adminWin.isMinimized()) adminWin.restore()
      adminWin.show()
      adminWin.focus()
      return
    }
    adminWin = new BrowserWindow({
      width: 1600,
      height: 1000,
      minWidth: 1200,
      minHeight: 780,
      frame: false,
      backgroundColor: '#0c1017',
      title: 'AI Control Center',
      show: false,
      webPreferences: {
        preload: join(here, '../preload/index.cjs'),
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
        webSecurity: true,
        additionalArguments: ['--baria-admin'],
      },
    })
    adminWin.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
    adminWin.webContents.on('will-navigate', (event, url) => {
      if (!trusted(url)) event.preventDefault()
    })
    adminWin.webContents.on('will-attach-webview', (event) => event.preventDefault())
    adminWin.once('ready-to-show', () => adminWin?.show())
    adminWin.on('closed', () => {
      adminStream.close()
      adminWin = null
    })
    if (devUrl) void adminWin.loadURL(devUrl + '#admin')
    else void adminWin.loadFile(rendererFile, { hash: 'admin' })
  }
  const guardAdmin = (event: Electron.IpcMainInvokeEvent | Electron.IpcMainEvent) => {
    if (
      !adminWin ||
      event.sender !== adminWin.webContents ||
      event.senderFrame !== event.sender.mainFrame ||
      !event.senderFrame ||
      !trusted(event.senderFrame.url)
    )
      throw new Error(en.administrativeOriginNotAllowed)
  }
  ipcMain.handle('admin:request', async (event, input: unknown) => {
    guardAdmin(event)
    try {
      const spec = adminRequest(input)
      const response = await fetch(backendUrl + spec.path, {
        method: spec.method,
        headers: { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' },
        body: 'body' in spec ? JSON.stringify(spec.body) : undefined,
        redirect: 'error',
        signal: AbortSignal.timeout(30000),
      })
      return { status: response.status, data: await response.json() }
    } catch {
      return {
        status: 503,
        data: {
          error: {
            code: 'admin_connection_failed',
            message: en.couldNotConnectToTheLocalAdministrativeApi,
          },
        },
      }
    }
  })
  ipcMain.handle('admin:settings', (event) => {
    guardAdmin(event)
    return { configured: adminToken.length >= 24 && adminToken !== token, backendUrl }
  })
  ipcMain.on('admin:connect', (event) => {
    guardAdmin(event)
    adminStream.start()
  })
  ipcMain.on('admin:open-booker', (event) => {
    guardAdmin(event)
    openBooker()
  })
  ipcMain.on('admin:open', (event) => {
    if (event.sender === win?.webContents && event.senderFrame === event.sender.mainFrame)
      openAdmin()
  })
  Menu.setApplicationMenu(
    Menu.buildFromTemplate([
      {
        label: en.development,
        submenu: [
          { label: en.bookingApp, accelerator: 'CmdOrCtrl+Shift+B', click: openBooker },
          { label: 'AI Control Center', accelerator: 'CmdOrCtrl+Shift+A', click: openAdmin },
          { role: 'toggleDevTools' },
          { role: 'reload' },
        ],
      },
    ]),
  )
  ipcMain.handle('api:request', async (event, input: unknown) => {
    if (
      event.sender !== win?.webContents ||
      event.senderFrame !== event.sender.mainFrame ||
      !event.senderFrame ||
      !trusted(event.senderFrame.url)
    )
      throw new Error(en.originNotAllowed)
    try {
      const spec = allowedRequest(input)
      const response = await fetch(backendUrl + spec.path, {
        method: spec.method,
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
          ...(spec.version !== undefined ? { 'If-Match': `"${spec.version}"` } : {}),
        },
        body: spec.body === undefined ? undefined : JSON.stringify(spec.body),
        redirect: 'error',
        signal: AbortSignal.timeout(15000),
      })
      return {
        status: response.status,
        data: response.status === 204 ? null : await response.json(),
      }
    } catch {
      return {
        status: 503,
        data: {
          error: {
            code: 'connection_failed',
            message: en.couldNotConnectToTheLocalBackendCheck,
          },
        },
      }
    }
  })
  const guard = (event: Electron.IpcMainInvokeEvent | Electron.IpcMainEvent) => {
    if (!event.senderFrame || !trusted(event.senderFrame.url)) throw new Error(en.originNotAllowed)
  }
  ipcMain.handle('app:settings', (event) => {
    guard(event)
    return settings()
  })
  ipcMain.handle('app:backend', (event, url: unknown) => {
    guard(event)
    if (typeof url !== 'string') throw new Error(en.invalidUrl)
    backendUrl = backendOrigin(url)
    writeFileSync(settingsPath, JSON.stringify({ backendUrl }))
    stream.reset()
    adminStream.reset()
    return settings()
  })
  ipcMain.handle('app:external', async (event, url: unknown) => {
    guard(event)
    if (typeof url !== 'string') throw new Error(en.invalidLink)
    await shell.openExternal(externalUrl(url))
  })
  ipcMain.on('app:window', (event, action: unknown) => {
    guard(event)
    const target = BrowserWindow.fromWebContents(event.sender)
    if (action === 'minimize') target?.minimize()
    if (action === 'maximize') {
      if (target?.isMaximized()) target.unmaximize()
      else target?.maximize()
    }
    if (action === 'close') target?.close()
  })
  ipcMain.on('booking:connect', (event) => {
    guard(event)
    stream.start()
  })
  session.defaultSession.setPermissionRequestHandler((_contents, _permission, callback) =>
    callback(false),
  )
  session.defaultSession.setPermissionCheckHandler(() => false)
  if (adminOnly) openAdmin()
  else openBooker()
})
app.on('before-quit', () => {
  stream.close()
  adminStream.close()
})
app.on('window-all-closed', () => app.quit())
