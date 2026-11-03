import { describe, it, expect } from 'vitest'
import type { Observation } from '../../src/admin/types'
import {
  activeInvocations,
  invocationEntry,
  pathActive,
  contactActivities,
} from '../../src/admin/graph-replay'
import { eventLabel } from '../../src/admin/replay'
const e = (id: number, extra: Partial<Observation>) =>
  ({
    id,
    event_id: `event-${id}`,
    schema_version: 1,
    booking_id: 'b',
    execution_id: 'r',
    graph_version: 'g',
    graph_thread_id: 'thread',
    kind: 'graph.node',
    phase: 'started',
    occurred_at: new Date(id * 100).toISOString(),
    span_id: `s${id}`,
    parent_span_id: null,
    data: {},
    ...extra,
  }) as Observation
const transition = (id: number, source: string, target: string, span: string) =>
  e(id, {
    kind: 'graph.transition',
    phase: 'selected',
    span_id: span,
    data: { from_node: source, to_node: target },
  } as Partial<Observation>)
describe('Entradas de cada invocación del grafo', () => {
  const events = [
    e(1, { node: 'planning' }),
    transition(2, 'planning', 'supervisor', 's1'),
    e(3, { node: 'supervisor' }),
    e(4, { node: 'supervisor', phase: 'completed', span_id: 's3' }),
    e(5, { node: 'verification' }),
    transition(6, 'verification', 'supervisor', 's5'),
    e(7, { node: 'verification', phase: 'completed', span_id: 's5' }),
    e(8, { node: 'supervisor' }),
    e(9, { node: 'supervisor', phase: 'completed', span_id: 's8' }),
    e(10, { node: 'planning', phase: 'completed', span_id: 's1' }),
  ]
  it('en la segunda ejecución solo anima Verification, también al retroceder', () => {
    const links = (source: string) => [{ source, target: 'supervisor' }]
    expect(pathActive(events, 850, 'g', links('planning'))).toBe(false)
    expect(pathActive(events, 850, 'g', links('verification'))).toBe(true)
    expect(pathActive(events, 350, 'g', links('planning'))).toBe(true)
    expect(pathActive(events, 350, 'g', links('verification'))).toBe(false)
    expect(pathActive(events, 950, 'g', links('verification'))).toBe(false)
    const supervisor = activeInvocations(events, 850, 'g').find(
      (x) => x.span.start.node === 'supervisor',
    )!
    expect(supervisor.ordinal).toBe(2)
    expect(supervisor.entry?.id).toBe(6)
    expect(
      activeInvocations(
        events.filter((e) => e.id !== 3),
        850,
        'g',
        events,
      ).find((x) => x.span.start.node === 'supervisor')?.ordinal,
    ).toBe(2)
  })
  it('no reutiliza una entrada vieja si faltan eventos ni mezcla threads', () => {
    const degraded = events.filter((x) => ![3, 6].includes(x.id))
    degraded.push(transition(6, 'negotiation', 'verification', 'other-source'))
    expect(invocationEntry(degraded, events[7])).toBeUndefined()
    expect(
      invocationEntry(
        events.filter((x) => x.id !== 6),
        events[7],
      ),
    ).toBeUndefined()
    expect(
      invocationEntry(
        [...events, transition(75, 'planning', 'supervisor', 'foreign')].map((x) =>
          x.id === 75
            ? { ...x, occurred_at: new Date(750).toISOString(), graph_thread_id: 'other' }
            : x,
        ),
        events[7],
      )?.id,
    ).toBe(6)
  })
  it('contrae solo una cadena de transiciones observadas de la misma invocación', () => {
    const chain = [
      e(1, { node: 'research' }),
      transition(2, 'research', 'prepare_call', 's1'),
      e(3, { node: 'prepare_call' }),
      transition(4, 'prepare_call', 'voice_session', 's3'),
      e(5, { node: 'voice_session' }),
    ]
    const path = [
      { source: 'research', target: 'prepare_call' },
      { source: 'prepare_call', target: 'voice_session' },
    ]
    expect(pathActive(chain, 550, 'g', path)).toBe(true)
    expect(
      pathActive(
        chain.filter((x) => x.id !== 2),
        550,
        'g',
        path,
      ),
    ).toBe(false)
  })
  it('distingue especialistas dentro del contacto y revisiones posteriores sin anticiparlos', () => {
    const events = [
      e(1, { node: 'voice_session' }),
      e(2, { kind: 'agent', node: 'voice_session', agent: 'negotiation', parent_span_id: 's1' }),
      e(3, { kind: 'agent', node: 'negotiation', agent: 'negotiation' }),
    ]
    expect(contactActivities(events, 150, 'g')).toHaveLength(0)
    expect(contactActivities(events, 350, 'g').map((s) => s.start.id)).toEqual([2])
    expect(eventLabel(events[1])).toContain('during contact')
    expect(eventLabel(events[2])).toBe('Offer Review')
  })
})
