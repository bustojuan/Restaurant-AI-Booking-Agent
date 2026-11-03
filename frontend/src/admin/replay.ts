import { en, UI_LOCALE, UI_TIME_ZONE } from '../i18n/en'
import type { Observation } from './types'
export type Span = { id: string; start: Observation; end?: Observation; depth: number }
export type NodeState =
  'not-run' | 'pending' | 'running' | 'completed' | 'failed' | 'interrupted' | 'cancelled'
export const terminalPhases = new Set(['completed', 'failed', 'interrupted', 'cancelled'])
const spanKinds = new Set([
  'agent',
  'tool',
  'model',
  'graph.node',
  'graph.invocation',
  'voice.session',
  'delegation',
  'transport.dial',
])
export const time = (e: Observation) => {
  // Preserve available microseconds rather than merging adjacent zero-ms operations.
  const subMillisecond = e.occurred_at.match(/\.\d{3}(\d+)/)?.[1]
  return new Date(e.occurred_at).getTime() + (subMillisecond ? Number(`0.${subMillisecond}`) : 0)
}
export function ordered(events: Observation[]) {
  return [...events].sort((a, b) => time(a) - time(b) || a.id - b.id)
}
export function spansOf(events: Observation[]): Span[] {
  const spans = new Map<string, Span>()
  for (const e of ordered(events)) {
    if (!e.span_id || !spanKinds.has(e.kind)) continue
    if (e.phase === 'started') spans.set(e.span_id, { id: e.span_id, start: e, depth: 0 })
    else if (terminalPhases.has(e.phase)) {
      const span = spans.get(e.span_id)
      if (span && span.start.kind === e.kind) span.end = e
    }
  }
  for (const span of spans.values()) {
    const seen = new Set([span.id])
    let parent = span.start.parent_span_id
    while (parent && spans.has(parent) && !seen.has(parent)) {
      seen.add(parent)
      span.depth++
      parent = spans.get(parent)!.start.parent_span_id
    }
  }
  return [...spans.values()]
}
export function nodeState(
  events: Observation[],
  node: string,
  at: number,
  graph?: string,
): NodeState {
  const relevant = ordered(events).filter(
    (e) =>
      e.node === node &&
      e.kind === 'graph.node' &&
      (!graph || e.graph_version === graph) &&
      time(e) <= at,
  )
  const current = new Map<string, string>()
  for (const event of relevant) if (event.span_id) current.set(event.span_id, event.phase)
  // Concurrent invocations retain running status until each recorded span closes.
  if ([...current.values()].includes('started')) return 'running'
  const latest = relevant.at(-1)
  if (latest && terminalPhases.has(latest.phase)) return latest.phase as NodeState
  if (
    events.some(
      (e) =>
        e.kind === 'graph.transition' &&
        e.data.to_node === node &&
        (!graph || e.graph_version === graph) &&
        time(e) <= at,
    )
  )
    return 'pending'
  return 'not-run'
}
export const names: Record<string, string> = {
  supervisor: 'Supervisor',
  planning: 'Planning',
  research: 'Research',
  voice_session: 'Voice Session',
  voice: 'Voice',
  negotiation: 'Negotiation',
  verification: 'Verification',
  memory: 'Memory & Summary',
  memory_summary: 'Memory & Summary',
  evaluation: 'Evaluation',
  user_approval: 'User Approval',
  approval: 'User Approval',
  finalize: 'Finalize',
  __start__: 'Start',
  __end__: 'End',
}
export const display = (name: string) => names[name] ?? name.replaceAll('_', ' ')
export const eventLabel = (event: Observation) => {
  if (event.tool) return display(event.tool)
  if (event.node === 'negotiation') return en.offerReview
  if (event.node === 'verification') return en.confirmationReview
  if (
    ['negotiation', 'verification'].includes(event.agent ?? '') &&
    (event.node === 'voice_session' || ['negotiate', 'verify'].includes(event.node ?? ''))
  )
    return `${display(event.agent!)} · during contact`
  return display(event.agent ?? event.node ?? event.kind)
}
export const duration = (ms: number | null | undefined) =>
  ms == null
    ? en.nA
    : ms < 1000
      ? `${Math.round(ms)} ms`
      : `${(ms / 1000).toFixed(ms < 10000 ? 2 : 1)} s`
export const short = (id: string | null | undefined) => (id ? `${id.slice(0, 8)}` : en.nA)
export const dateTime = (value: string) =>
  new Intl.DateTimeFormat(UI_LOCALE, {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
    timeZone: UI_TIME_ZONE,
  }).format(new Date(value))
export const modeLabel = (mode: string) =>
  ({
    simulation: en.simulation,
    ai_simulation: en.aiSimulation,
    real_telephony: 'Real',
    voice_sandbox: en.voiceTest,
    unknown: en.nA,
  })[mode] ?? mode
export const resultLabel = (result: string | null) =>
  ({
    CONFIRMED: en.confirmed,
    NO_AVAILABILITY: en.noAvailability,
    INCOMPATIBLE_OFFER: en.incompatibleOffer,
    NOT_CONFIRMED: en.unconfirmed,
    OFFER_ACCEPTABLE: en.acceptableOffer,
    ERROR: en.technicalError,
    TIMEOUT: en.timedOut,
    CANCELLED: en.cancelled,
    AMBIGUOUS: en.ambiguous,
    UNCERTAIN: en.uncertainOutcome,
    INTERRUPTED: en.interrupted,
    DECLINED_AI: en.aiDeclined,
    DISCONNECTED: en.disconnected,
    USER_APPROVAL_REQUIRED: en.approvalRequired,
    INSUFFICIENT_INFORMATION: en.incompleteInformation,
  })[result ?? ''] ??
  result ??
  en.pending
