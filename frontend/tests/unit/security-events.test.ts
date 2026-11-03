import { describe, it, expect } from 'vitest'
import { allowedRequest, backendOrigin, externalUrl } from '../../electron/main/policy'
import { EventCursor } from '../../src/services/events'
import type { BookingEvent } from '../../src/types/bridge'
describe('Puente Electron', () => {
  it.each([
    'https://evil.test',
    'http://localhost:8001/path',
    'http://user:password@127.0.0.1:8001',
    'file:///etc/passwd',
    'http://127.0.0.1.evil.test',
  ])('rechaza origen backend %s', (url) => expect(() => backendOrigin(url)).toThrow())
  it('solo permite rutas del contrato y métodos explícitos', () => {
    expect(
      allowedRequest({
        method: 'PUT',
        path: '/api/bookings/id/restaurants/order',
        body: { restaurant_ids: [] },
        version: 1,
      }).version,
    ).toBe(1)
    for (const path of [
      '//evil.test/api/bookings',
      '/api/../admin',
      '/api/bookings#fragment',
      '/api/voice/sandbox/ws',
      '/api/health\\evil',
    ])
      expect(() => allowedRequest({ method: 'GET', path })).toThrow()
    expect(() => allowedRequest({ method: 'POST', path: '/api/health' })).toThrow()
  })
  it.each([
    'javascript:alert(1)',
    'file:///C:/secret',
    'data:text/html,hello',
    'https://user:password@example.com',
  ])('no abre enlaces inseguros %s', (url) => expect(() => externalUrl(url)).toThrow())
  it('acepta webs reales HTTP(S) sin credenciales', () =>
    expect(externalUrl('https://example.com/menu')).toBe('https://example.com/menu'))
})
describe('Cursor de eventos', () => {
  const event = (id: number, version: number) =>
    ({
      event_id: id,
      schema_version: 1,
      booking_id: 'a',
      payload: { summary: { id: 'a', version } },
    }) as BookingEvent
  it('elimina duplicados y eventos fuera de orden sin descartar actividad con igual versión', () => {
    const c = new EventCursor()
    expect(c.accept(event(3, 8))).toBe(true)
    expect(c.accept(event(3, 8))).toBe(false)
    expect(c.accept(event(2, 9))).toBe(false)
    expect(c.accept(event(4, 7))).toBe(false)
    expect(c.accept(event(5, 8))).toBe(true)
    expect(c.accept(event(6, 9))).toBe(true)
  })
})
