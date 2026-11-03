import { contextBridge, ipcRenderer } from 'electron'
import type { DesktopBridge, BookingEvent, Connection } from '../../src/types/bridge'
import type { AdminBridge, Observation, AdminConnection } from '../../src/admin/types'
const bridge: DesktopBridge = {
  request: (spec) => ipcRenderer.invoke('api:request', spec),
  settings: () => ipcRenderer.invoke('app:settings'),
  setBackend: (url) => ipcRenderer.invoke('app:backend', url),
  openExternal: (url) => ipcRenderer.invoke('app:external', url),
  window: (action) => ipcRenderer.send('app:window', action),
  connectEvents: () => ipcRenderer.send('booking:connect'),
  openAdmin: () => ipcRenderer.send('admin:open'),
  onEvent: (listener) => {
    const handler = (_event: Electron.IpcRendererEvent, data: BookingEvent) => listener(data)
    ipcRenderer.on('booking:event', handler)
    return () => ipcRenderer.removeListener('booking:event', handler)
  },
  onConnection: (listener) => {
    const handler = (_event: Electron.IpcRendererEvent, data: Connection) => listener(data)
    ipcRenderer.on('booking:connection', handler)
    return () => ipcRenderer.removeListener('booking:connection', handler)
  },
}
if (process.argv.includes('--baria-admin')) {
  const admin: AdminBridge = {
    request: (spec) => ipcRenderer.invoke('admin:request', spec),
    connection: () => ipcRenderer.invoke('admin:settings'),
    connect: () => ipcRenderer.send('admin:connect'),
    openBooker: () => ipcRenderer.send('admin:open-booker'),
    window: (action) => ipcRenderer.send('app:window', action),
    onEvent: (listener) => {
      const h = (_e: Electron.IpcRendererEvent, data: Observation) => listener(data)
      ipcRenderer.on('admin:event', h)
      return () => ipcRenderer.removeListener('admin:event', h)
    },
    onConnection: (listener) => {
      const h = (_e: Electron.IpcRendererEvent, data: AdminConnection) => listener(data)
      ipcRenderer.on('admin:connection', h)
      return () => ipcRenderer.removeListener('admin:connection', h)
    },
  }
  contextBridge.exposeInMainWorld('admin', admin)
} else contextBridge.exposeInMainWorld('desktop', bridge)
