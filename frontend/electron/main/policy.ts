import { en } from '../../src/i18n/en'
import { z } from 'zod'
export const requestSchema = z
  .object({
    method: z.enum(['GET', 'POST', 'PUT', 'PATCH', 'DELETE']),
    path: z.string().max(4000),
    body: z.unknown().optional(),
    version: z.number().int().nonnegative().optional(),
  })
  .strict()
const routes: Record<string, RegExp[]> = {
  GET: [
    /^\/api\/(health|workspace|restaurants|restaurants\/categories|restaurants\/[\w-]+|favorites|bookings|bookings\/[\w-]+|bookings\/[\w-]+\/(events|offers|ai|ai\/state|ai\/traces)|ai\/capabilities|simulations\/scenarios|voice\/bookings\/[\w-]+\/calls)$/,
  ],
  POST: [
    /^\/api\/(favorites|bookings|bookings\/[\w-]+\/(restaurants|start|cancel|decisions|ai\/pause|ai\/resume))$/,
  ],
  PUT: [/^\/api\/(workspace|bookings\/[\w-]+\/restaurants\/order)$/],
  PATCH: [/^\/api\/bookings\/[\w-]+$/],
  DELETE: [/^\/api\/(favorites\/[\w-]+|bookings\/[\w-]+|bookings\/[\w-]+\/restaurants\/[\w-]+)$/],
}
export function allowedRequest(input: unknown) {
  const spec = requestSchema.parse(input)
  if (!spec.path.startsWith('/api/') || /[\\#\r\n]/.test(spec.path))
    throw new Error(en.pathNotAllowed)
  const url = new URL(spec.path, 'http://127.0.0.1')
  if (url.origin !== 'http://127.0.0.1' || !routes[spec.method].some((r) => r.test(url.pathname)))
    throw new Error(en.pathNotAllowed)
  if (JSON.stringify(spec.body ?? null).length > 100_000) throw new Error(en.requestTooLarge)
  return spec
}
export function backendOrigin(input: string) {
  const url = new URL(input)
  if (
    url.protocol !== 'http:' ||
    !['127.0.0.1', 'localhost'].includes(url.hostname) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    url.pathname !== '/'
  )
    throw new Error(en.useALocalHttpUrlWithoutAPath)
  return url.origin
}
export function externalUrl(input: string) {
  const url = new URL(input)
  if (
    !['https:', 'http:'].includes(url.protocol) ||
    url.username ||
    url.password ||
    input.length > 4000
  )
    throw new Error(en.linkNotAllowed)
  return url.href
}
