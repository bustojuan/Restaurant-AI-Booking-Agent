import WebSocket from 'ws'
import type { AdminConnection, Observation } from '../../src/admin/types'
export class AdminEventStream {
  private socket?: WebSocket
  private timer?: ReturnType<typeof setTimeout>
  private stopped = true
  private cursor = 0
  private retry = 0
  constructor(
    private origin: () => string,
    private token: () => string,
    private emit: (e: Observation) => void,
    private status: (s: AdminConnection) => void,
  ) {}
  start() {
    this.close()
    this.stopped = false
    if (!this.token()) {
      this.status('unauthorized')
      return
    }
    this.status('connecting')
    const socket = (this.socket = new WebSocket(
      `${this.origin().replace('http:', 'ws:')}/api/admin/observability/events/ws?after_event_id=${this.cursor}`,
      { handshakeTimeout: 5000, maxPayload: 2_000_000 },
    ))
    socket.on('open', () => {
      socket.send(JSON.stringify({ token: this.token() }))
      this.status('connected')
      this.retry = 0
    })
    socket.on('message', (raw) => {
      try {
        const event = JSON.parse(raw.toString()) as Observation
        if (
          event.schema_version !== 1 ||
          !Number.isSafeInteger(event.id) ||
          event.id <= this.cursor ||
          typeof event.kind !== 'string' ||
          typeof event.execution_id !== 'string'
        )
          return
        this.cursor = event.id
        this.emit(event)
      } catch {}
    })
    socket.on('error', () => {})
    socket.on('close', (code) => {
      this.status(code === 1008 ? 'unauthorized' : 'disconnected')
      if (!this.stopped && code !== 1008)
        this.timer = setTimeout(
          () => this.start(),
          Math.min(15000, 500 * 2 ** Math.min(this.retry++, 5)),
        )
    })
  }
  reset() {
    this.cursor = 0
    this.retry = 0
    if (!this.stopped) this.start()
  }
  close() {
    this.stopped = true
    clearTimeout(this.timer)
    this.socket?.removeAllListeners()
    this.socket?.on('error', () => {})
    this.socket?.terminate()
    this.socket = undefined
  }
}
