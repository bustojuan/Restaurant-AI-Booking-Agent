import WebSocket from 'ws'
import type { BookingEvent, Connection } from '../../src/types/bridge'
export class BookingEventStream {
  private socket: WebSocket | undefined
  private timer: ReturnType<typeof setTimeout> | undefined
  private stopped = true
  private retry = 0
  private cursor = 0
  constructor(
    private origin: () => string,
    private token: () => string,
    private emit: (event: BookingEvent) => void,
    private status: (state: Connection) => void,
  ) {}
  private disconnect() {
    clearTimeout(this.timer)
    if (this.socket) {
      this.socket.removeAllListeners()
      this.socket.on('error', () => {})
      this.socket.terminate()
      this.socket = undefined
    }
  }
  start() {
    this.stopped = false
    this.disconnect()
    if (!this.token()) {
      this.status('disconnected')
      return
    }
    this.status('connecting')
    const socket = (this.socket = new WebSocket(
      `${this.origin().replace('http:', 'ws:')}/api/events/ws?after_event_id=${this.cursor}`,
      { handshakeTimeout: 5000, maxPayload: 2_000_000 },
    ))
    socket.on('open', () => {
      this.retry = 0
      socket.send(JSON.stringify({ token: this.token() }))
      this.status('connected')
    })
    socket.on('message', (raw) => {
      try {
        const e = JSON.parse(raw.toString()) as BookingEvent
        if (
          !Number.isSafeInteger(e.event_id) ||
          e.event_id <= this.cursor ||
          e.schema_version !== 1 ||
          !e.payload?.summary
        )
          return
        this.cursor = e.event_id
        this.emit(e)
      } catch {
        /* Ignore malformed frames; no sensitive logs. */
      }
    })
    socket.on('error', () => {})
    socket.on('close', () => {
      this.status('disconnected')
      if (!this.stopped)
        this.timer = setTimeout(
          () => this.start(),
          Math.min(15000, 500 * 2 ** Math.min(this.retry++, 5)),
        )
    })
  }
  reset() {
    this.cursor = 0
    this.retry = 0
    this.start()
  }
  close() {
    this.stopped = true
    this.disconnect()
  }
}
