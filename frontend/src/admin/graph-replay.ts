import type { Observation } from './types'
import { ordered, spansOf, time, type Span } from './replay'

const before = (a: Observation, b: Observation) =>
  time(a) < time(b) || (time(a) === time(b) && a.id < b.id)
const sameRun = (a: Observation, b: Observation) =>
  a.execution_id === b.execution_id &&
  a.graph_version === b.graph_version &&
  a.graph_thread_id === b.graph_thread_id

/** Associate the incoming transition with one invocation, not with the node's whole history. */
export function invocationEntry(events: Observation[], start: Observation) {
  const previous = ordered(events)
    .filter(
      (e) =>
        e.kind === 'graph.node' &&
        e.phase === 'started' &&
        e.node === start.node &&
        sameRun(e, start) &&
        before(e, start),
    )
    .at(-1)
  const latest = ordered(events)
    .filter(
      (e) =>
        e.kind === 'graph.transition' &&
        sameRun(e, start) &&
        before(e, start) &&
        (!previous || before(previous, e)),
    )
    .at(-1)
  return latest?.data.to_node === start.node ? latest : undefined
}

export function activeInvocations(
  events: Observation[],
  at: number,
  graph: string,
  history = events,
) {
  return spansOf(events)
    .filter(
      (s) =>
        s.start.kind === 'graph.node' &&
        s.start.graph_version === graph &&
        time(s.start) <= at &&
        (!s.end || time(s.end) > at),
    )
    .map((span) => ({
      span,
      ordinal: ordered(history).filter(
        (e) =>
          e.kind === 'graph.node' &&
          e.phase === 'started' &&
          e.node === span.start.node &&
          sameRun(e, span.start) &&
          (before(e, span.start) || e.id === span.start.id),
      ).length,
      entry: invocationEntry(events, span.start),
    }))
}

export type GraphLink = { source: string; target: string }
export function pathActive(events: Observation[], at: number, graph: string, via: GraphLink[]) {
  if (!via.length) return false
  return activeInvocations(events, at, graph).some(({ span, entry }) => {
    if (span.start.node !== via.at(-1)!.target || !entry) return false
    let selected: Observation | undefined = entry
    // Walk the actual recorded chain backwards through any collapsed technical nodes.
    for (let i = via.length - 1; i >= 0; i--) {
      const link = via[i]
      if (
        !selected ||
        selected.data.from_node !== link.source ||
        selected.data.to_node !== link.target
      )
        return false
      if (i) {
        const sourceStart = ordered(events)
          .filter(
            (e) =>
              e.kind === 'graph.node' &&
              e.phase === 'started' &&
              e.node === link.source &&
              sameRun(e, selected!) &&
              (selected!.span_id ? e.span_id === selected!.span_id : before(e, selected!)),
          )
          .at(-1)
        selected = sourceStart ? invocationEntry(events, sourceStart) : undefined
      }
    }
    return true
  })
}

export function contactActivities(events: Observation[], at: number, graph: string) {
  const spans = spansOf(events)
  const contacts = spans.filter(
    (s) =>
      s.start.kind === 'graph.node' &&
      s.start.node === 'voice_session' &&
      s.start.graph_version === graph &&
      time(s.start) <= at,
  )
  const byId = new Map(spans.map((s) => [s.id, s]))
  const insideContact = (s: Span) => {
    const seen = new Set<string>()
    let parent = s.start.parent_span_id
    while (parent && !seen.has(parent)) {
      seen.add(parent)
      if (contacts.some((c) => c.id === parent)) return true
      parent = byId.get(parent)?.start.parent_span_id ?? null
    }
    // Independent voice delegation graphs use the persisted call correlation, not a fabricated parent.
    return (
      !!s.start.call_attempt_id &&
      contacts.some((c) => {
        const callIds = new Set(
          events
            .filter(
              (e) =>
                e.kind === 'backend.call.started' &&
                time(e) >= time(c.start) &&
                (!c.end || time(e) <= time(c.end)),
            )
            .map((e) => e.call_attempt_id),
        )
        return (
          s.start.graph_version !== graph &&
          callIds.has(s.start.call_attempt_id) &&
          time(s.start) >= time(c.start) &&
          (!c.end || time(s.start) <= time(c.end))
        )
      })
    )
  }
  return spans.filter(
    (s) =>
      s.start.kind === 'agent' &&
      ['negotiation', 'verification'].includes(s.start.agent ?? '') &&
      time(s.start) <= at &&
      insideContact(s),
  )
}
