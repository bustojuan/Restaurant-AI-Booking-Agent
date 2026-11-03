import { en } from '../i18n/en'
import type { components } from '../types/api.generated'
import type {
  RequestSpec,
  Booking,
  Summary,
  Configuration,
  Capabilities,
  StartRequest,
} from '../types/bridge'
export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
  ) {
    super(message)
  }
}
export async function request<T>(spec: RequestSpec): Promise<T> {
  if (!window.desktop)
    throw new ApiError('desktop_required', en.openTheAppInElectronToConnectTo, 503)
  const reply = await window.desktop.request(spec)
  if (reply.status >= 400) {
    const data = reply.data as { error?: { code: string; message: string } }
    throw new ApiError(
      data.error?.code ?? 'request_failed',
      data.error?.message ?? en.theOperationCouldNotBeCompleted2,
      reply.status,
    )
  }
  return reply.data as T
}
export const get = <T>(path: string) => request<T>({ method: 'GET', path })
export const api = {
  booking: (id: string) => get<Booking>(`/api/bookings/${id}`),
  create: (configuration?: Partial<Configuration>, restaurant_ids: string[] = []) =>
    request<Booking>({
      method: 'POST',
      path: '/api/bookings',
      body: { ...(configuration ? { configuration } : {}), restaurant_ids },
    }),
  patch: (b: Booking, configuration: Partial<Configuration>) =>
    request<Booking>({
      method: 'PATCH',
      path: `/api/bookings/${b.id}`,
      version: b.version,
      body: { configuration },
    }),
  insert: (b: Booking, restaurant_id: string, position?: number) =>
    request<Booking>({
      method: 'POST',
      path: `/api/bookings/${b.id}/restaurants`,
      version: b.version,
      body: { restaurant_id, position },
    }),
  order: (b: Booking, restaurant_ids: string[]) =>
    request<Booking>({
      method: 'PUT',
      path: `/api/bookings/${b.id}/restaurants/order`,
      version: b.version,
      body: { restaurant_ids },
    }),
  remove: (b: Booking, id: string) =>
    request<Booking>({
      method: 'DELETE',
      path: `/api/bookings/${b.id}/restaurants/${id}`,
      version: b.version,
    }),
  delete: (b: Pick<Booking, 'id' | 'version'>) =>
    request<void>({ method: 'DELETE', path: `/api/bookings/${b.id}`, version: b.version }),
  start: (b: Booking, body: StartRequest) =>
    request<Summary>({
      method: 'POST',
      path: `/api/bookings/${b.id}/start`,
      version: b.version,
      body,
    }),
  workspace: () => get<components['schemas']['WorkspaceOut']>('/api/workspace'),
  setDraft: async (id: string | null) => {
    const w = await api.workspace()
    return request<components['schemas']['WorkspaceOut']>({
      method: 'PUT',
      path: '/api/workspace',
      body: { active_draft_id: id },
      version: w.version,
    })
  },
  capabilities: () => get<Capabilities>('/api/ai/capabilities'),
}
export function queryString(
  values: Record<string, string | number | boolean | string[] | undefined>,
) {
  const p = new URLSearchParams()
  Object.entries(values).forEach(([key, value]) => {
    if (value === undefined || value === '') return
    ;(Array.isArray(value) ? value : [value]).forEach((v) => p.append(key, String(v)))
  })
  return p.toString()
}
export function errorText(error: unknown) {
  if (error instanceof ApiError && error.status === 409)
    return en.theRequestChangedInAnotherWindowReloadTo
  return error instanceof Error ? error.message : en.theOperationCouldNotBeCompleted
}
