import { describe, it, expect, vi, afterEach } from 'vitest'
import { adminRequest } from '../../electron/main/admin-policy'
import { nodeState, spansOf, ordered } from '../../src/admin/replay'
import { adminApi, AdminError } from '../../src/admin/api'
import type { Observation } from '../../src/admin/types'
const event = (id: number, phase: string, extra: Partial<Observation> = {}): Observation =>
  ({
    id,
    event_id: `e-${id}`,
    schema_version: 1,
    execution_id: 'run',
    booking_id: 'booking',
    span_id: 's',
    parent_span_id: null,
    kind: 'graph.node',
    phase,
    node: 'planning',
    agent: null,
    graph_version: 'v1',
    occurred_at: new Date(1000 + id * 100).toISOString(),
    data: { recording_retained: false, transcript_retained: false },
    ...extra,
  }) as Observation
afterEach(() => vi.unstubAllGlobals())
describe('Puente administrativo limitado', () => {
  it('solo proyecta operaciones declaradas y valida argumentos', () => {
    expect(
      adminRequest({ operation: 'calls', params: { q: 'Restaurante & café', limit: 20 } }).path,
    ).toContain('q=Restaurante+%26+caf%C3%A9')
    expect(
      adminRequest({ operation: 'simulate', input: { scenario_id: 'all-full', adults: 4 } }).method,
    ).toBe('POST')
    for (const input of [
      { operation: 'fetch', url: 'https://example.test' },
      { operation: 'call', id: '../bookings' },
      { operation: 'events', params: { execution_id: 'a', limit: 201 } },
      { operation: 'simulate', input: { scenario_id: 'all-full', mode: 'real_telephony' } },
      { operation: 'settings', token: 'secret' },
      { operation: 'calls', params: { url: 'http://evil.test' } },
    ])
      expect(() => adminRequest(input)).toThrow()
    expect(adminRequest({ operation: 'settings' }).path).toBe('/api/admin/observability/settings')
  })
})
describe('Replay puro con timestamps persistidos', () => {
  it('reconstruye estados sin anticipar cierres ni inventar estados de nodos ausentes', () => {
    const events = [
      event(1, 'started'),
      event(2, 'completed'),
      event(3, 'started', { span_id: 'retry' }),
      event(4, 'interrupted', { span_id: 'retry' }),
    ]
    expect(nodeState(events, 'planning', 1050, 'v1')).toBe('not-run')
    expect(nodeState(events, 'planning', 1150, 'v1')).toBe('running')
    expect(nodeState(events, 'planning', 1250, 'v1')).toBe('completed')
    expect(nodeState(events, 'planning', 1350, 'v1')).toBe('running')
    expect(nodeState(events, 'planning', 1450, 'v1')).toBe('interrupted')
    expect(nodeState(events, 'verification', 1500, 'v1')).toBe('not-run')
    expect(nodeState(events, 'planning', 1500, 'another-graph')).toBe('not-run')
  })
  it('preserva spans incompletos, parentesco y estados concurrentes', () => {
    const events = [
      event(1, 'started'),
      event(2, 'started', { span_id: 'child', parent_span_id: 's', kind: 'tool', tool: 'read' }),
      event(3, 'completed', { span_id: 'child', parent_span_id: 's', kind: 'tool' }),
      event(4, 'started', { span_id: 'parallel' }),
      event(5, 'completed', { span_id: 'parallel' }),
    ]
    const spans = spansOf(events)
    expect(spans.find((s) => s.id === 'child')?.depth).toBe(1)
    expect(spans.find((s) => s.id === 's')?.end).toBeUndefined()
    expect(nodeState(events, 'planning', 2000)).toBe('running')
    expect(ordered([...events].reverse()).map((e) => e.id)).toEqual([1, 2, 3, 4, 5])
  })
  it('fija el high watermark para recorrer todas las páginas de read-only', async () => {
    const request = vi
      .fn()
      .mockResolvedValueOnce({
        status: 200,
        data: {
          items: [event(1, 'started')],
          high_watermark: 20,
          next_after_event_id: 1,
          has_more: true,
        },
      })
      .mockResolvedValueOnce({
        status: 200,
        data: {
          items: [event(2, 'completed')],
          high_watermark: 20,
          next_after_event_id: 20,
          has_more: false,
        },
      })
    vi.stubGlobal('window', { admin: { request } })
    const result = await adminApi.events('run')
    expect(result.events).toHaveLength(2)
    expect(request.mock.calls[1][0]).toEqual({
      operation: 'events',
      params: { execution_id: 'run', after_event_id: 1, until_event_id: 20, limit: 200 },
    })
    expect(request.mock.calls.every(([spec]) => spec.operation === 'events')).toBe(true)
  })
  it('un evento de proveedor no cierra el span de voz cuyo contexto comparte', () => {
    const start = event(1, 'started', { kind: 'voice.session' })
    const failure = event(2, 'failed', { kind: 'voice.provider' })
    expect(spansOf([start, failure])[0].end).toBeUndefined()
    const end = event(3, 'failed', { kind: 'voice.session' })
    expect(spansOf([start, failure, end])[0].end?.id).toBe(3)
  })
  it('distingue spans que cierran dentro del mismo milisegundo', () => {
    const start = event(1, 'started', { occurred_at: '2026-11-01T12:00:00.123100Z' })
    const end = event(2, 'completed', { occurred_at: '2026-11-01T12:00:00.123900Z' })
    const instant = new Date('2026-11-01T12:00:00.123Z').getTime() + 0.5
    expect(nodeState([start, end], 'planning', instant, 'v1')).toBe('running')
  })
  it('presenta los fallos de acceso sin filtrar detalles o tokens', async () => {
    vi.stubGlobal('window', {
      admin: {
        request: vi
          .fn()
          .mockResolvedValue({ status: 401, data: { error: { message: 'provider secret' } } }),
      },
    })
    await expect(adminApi.settings()).rejects.toThrow('Administrative access denied')
    vi.stubGlobal('window', {})
    await expect(adminApi.calls({})).rejects.toBeInstanceOf(AdminError)
  })
})
