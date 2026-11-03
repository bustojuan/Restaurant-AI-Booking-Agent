import { en } from '../i18n/en'
import type {
  AdminRequest,
  Call,
  CallPage,
  BookingPage,
  Execution,
  EventPage,
  Observation,
  GraphVersion,
  Analytics,
  AdminSettings,
  Scenario,
  PlaygroundInput,
  PlaygroundRun,
  Evaluation,
  Filters,
} from './types'
export class AdminError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}
export async function request<T>(spec: AdminRequest): Promise<T> {
  if (!window.admin) throw new AdminError(503, en.openAiControlCenterInElectronToConnect)
  const reply = await window.admin.request(spec)
  if (reply.status >= 400) {
    const message =
      reply.status === 401
        ? en.administrativeAccessDeniedCheckAdminApiTokenIn
        : reply.status === 503
          ? en.administrativeApiUnavailableCheckThatTheBackendIs
          : ((reply.data as { error?: { message?: string } })?.error?.message ??
            en.theOperationCouldNotBeCompleted)
    throw new AdminError(reply.status, message)
  }
  return reply.data as T
}
export const adminApi = {
  calls: (
    params: Filters & { offset?: number; limit?: number; sort?: string; direction?: string },
  ) => request<CallPage>({ operation: 'calls', params }),
  bookings: (params: Filters & { offset?: number; limit?: number }) =>
    request<BookingPage>({ operation: 'bookings', params }),
  call: (id: string) => request<Call>({ operation: 'call', id }),
  execution: (id: string) => request<Execution>({ operation: 'execution', id }),
  graph: (id: string) => request<GraphVersion>({ operation: 'graph', id }),
  analytics: (params: Filters) => request<Analytics>({ operation: 'analytics', params }),
  settings: () => request<AdminSettings>({ operation: 'settings' }),
  scenarios: () => request<Scenario[]>({ operation: 'scenarios' }),
  simulate: (input: PlaygroundInput) => request<PlaygroundRun>({ operation: 'simulate', input }),
  evaluation: (id: string) => request<Evaluation>({ operation: 'evaluation', id }),
  async events(id: string): Promise<{ events: Observation[]; high: number }> {
    // Freeze the high watermark on page one. Replay never invokes a runtime operation.
    let cursor = 0,
      high: number | undefined
    const events: Observation[] = []
    for (;;) {
      const page = await request<EventPage>({
        operation: 'events',
        params: { execution_id: id, after_event_id: cursor, until_event_id: high, limit: 200 },
      })
      high ??= page.high_watermark
      events.push(...page.items)
      if (!page.has_more) return { events, high }
      if (page.next_after_event_id <= cursor)
        throw new AdminError(500, en.inconsistentHistoryCursor)
      cursor = page.next_after_event_id
    }
  },
}
