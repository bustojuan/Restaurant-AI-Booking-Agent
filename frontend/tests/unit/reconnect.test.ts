import { it, expect } from 'vitest'
import { WebSocketServer } from 'ws'
import { BookingEventStream } from '../../electron/main/events'
import type { BookingEvent } from '../../src/types/bridge'
it('autentica en el primer frame, recupera con cursor y elimina duplicados tras desconexión', async () => {
  const server = new WebSocketServer({ host: '127.0.0.1', port: 0 })
  await new Promise<void>((r) => server.once('listening', r))
  const address = server.address()
  if (typeof address === 'string' || !address) throw new Error('No local WS port')
  const origins: string[] = [],
    tokens: string[] = [],
    received: number[] = []
  let count = 0
  const frame = (id: number) =>
    ({
      schema_version: 1,
      event_id: id,
      payload: { summary: { id: 'booking', version: id } },
      booking_id: 'booking',
    }) as BookingEvent
  server.on('connection', (socket, req) => {
    origins.push(req.url ?? '')
    socket.once('message', (data) => {
      tokens.push(JSON.parse(data.toString()).token)
      if (++count === 1) {
        socket.send(JSON.stringify(frame(1)))
        setTimeout(() => socket.close(), 30)
      } else {
        socket.send(JSON.stringify(frame(1)))
        socket.send('{bad-json')
        socket.send(JSON.stringify(frame(2)))
      }
    })
  })
  const client = new BookingEventStream(
    () => `http://127.0.0.1:${address.port}`,
    () => 'test-only-token',
    (e) => received.push(e.event_id),
    () => {},
  )
  try {
    client.start()
    await expect.poll(() => received, { timeout: 4000 }).toEqual([1, 2])
    expect(origins).toEqual(['/api/events/ws?after_event_id=0', '/api/events/ws?after_event_id=1'])
    expect(tokens).toEqual(['test-only-token', 'test-only-token'])
    expect(origins.join()).not.toContain('token')
  } finally {
    client.close()
    await new Promise<void>((r) => server.close(() => r()))
  }
})
it('permite reinicio mientras conecta sin errores de socket no gestionados', async () => {
  const client = new BookingEventStream(
    () => 'http://127.0.0.1:1',
    () => 'test-only-token',
    () => {},
    () => {},
  )
  client.start()
  client.start()
  client.close()
  await new Promise((r) => setTimeout(r, 30))
  expect(true).toBe(true)
})
