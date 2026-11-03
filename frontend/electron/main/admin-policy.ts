import { z } from 'zod'
const id = z.string().regex(/^[\w:.-]{1,250}$/)
const filters = {
  q: z.string().max(200).optional(),
  mode: z.enum(['simulation', 'ai_simulation', 'real_telephony', 'voice_sandbox']).optional(),
  status: z
    .string()
    .regex(/^[A-Z_]{1,60}$/)
    .optional(),
  result: z
    .string()
    .regex(/^[A-Z_]{1,60}$/)
    .optional(),
  date_from: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/)
    .optional(),
  date_to: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/)
    .optional(),
  model: z.string().max(250).optional(),
  prompt: z.string().max(250).optional(),
}
const page = z
  .object({
    ...filters,
    limit: z.number().int().min(1).max(100).optional(),
    offset: z.number().int().min(0).optional(),
    sort: z.enum(['started_at', 'duration_ms', 'restaurant', 'status']).optional(),
    direction: z.enum(['asc', 'desc']).optional(),
  })
  .strict()
const request = z.discriminatedUnion('operation', [
  z.object({ operation: z.literal('calls'), params: page }).strict(),
  z.object({ operation: z.literal('bookings'), params: page }).strict(),
  ...(['call', 'execution', 'graph', 'evaluation'] as const).map((operation) =>
    z.object({ operation: z.literal(operation), id }).strict(),
  ),
  z
    .object({
      operation: z.literal('events'),
      params: z
        .object({
          execution_id: id,
          after_event_id: z.number().int().min(0).optional(),
          until_event_id: z.number().int().min(0).optional(),
          limit: z.number().int().min(1).max(200).optional(),
        })
        .strict(),
    })
    .strict(),
  z.object({ operation: z.literal('analytics'), params: z.object(filters).strict() }).strict(),
  z.object({ operation: z.literal('settings') }).strict(),
  z.object({ operation: z.literal('scenarios') }).strict(),
  z
    .object({
      operation: z.literal('simulate'),
      input: z
        .object({
          scenario_id: id,
          adults: z.number().int().min(1).max(20).optional(),
          flexibility_minutes: z.number().int().min(0).max(120).optional(),
        })
        .strict(),
    })
    .strict(),
])
export function adminRequest(input: unknown) {
  const spec = request.parse(input)
  const root = '/api/admin/observability'
  const paths = {
    call: 'calls',
    execution: 'executions',
    graph: 'graphs',
    evaluation: 'playground/runs',
  }
  if ('id' in spec)
    return {
      method: 'GET',
      path: `${root}/${paths[spec.operation]}/${encodeURIComponent(spec.id)}`,
    }
  if (spec.operation === 'simulate')
    return { method: 'POST', path: `${root}/playground/runs`, body: spec.input }
  const path = spec.operation === 'scenarios' ? 'playground/scenarios' : spec.operation
  const query = new URLSearchParams()
  if ('params' in spec)
    Object.entries(spec.params).forEach(([key, value]) => {
      if (value !== undefined && value !== '') query.set(key, String(value))
    })
  return { method: 'GET', path: `${root}/${path}${query.size ? '?' + query : ''}` }
}
