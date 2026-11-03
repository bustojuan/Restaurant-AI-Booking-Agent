import { describe, it, expect, vi, beforeEach } from 'vitest'
import { BookingEditor } from '../../src/services/editor'
import type { Booking, Configuration } from '../../src/types/bridge'
import { api, ApiError } from '../../src/services/api'
vi.mock('../../src/services/api', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../src/services/api')>()
  return {
    ...original,
    api: {
      workspace: vi.fn(),
      booking: vi.fn(),
      create: vi.fn(),
      setDraft: vi.fn(),
      patch: vi.fn(),
    },
  }
})
const config: Configuration = {
  customer_name: null,
  contact_phone: null,
  requested_date: null,
  preferred_time: null,
  adults: 2,
  children: 0,
  high_chairs: 0,
  flexibility_minutes: 0,
  area: null,
  budget_per_person: null,
  strict_budget: false,
  table_type: 'indifferent',
  table_type_mandatory: false,
  accessibility_required: false,
  stroller_space: false,
  special_occasion: null,
  notes: null,
  dietary_requirements: [],
  requirements: [],
}
const booking = {
  id: 'draft',
  version: 1,
  status: 'DRAFT',
  configuration: config,
  restaurants: [],
  summary: {} as Booking['summary'],
} satisfies Booking
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.workspace).mockResolvedValue({ active_draft_id: 'draft', version: 1 })
  vi.mocked(api.booking).mockResolvedValue(structuredClone(booking))
})
describe('Autosave con concurrencia', () => {
  it('no crea borradores duplicados si se inicializa dos veces', async () => {
    const e = new BookingEditor()
    vi.mocked(api.workspace).mockResolvedValue({ active_draft_id: null, version: 1 })
    vi.mocked(api.create).mockResolvedValue(structuredClone(booking))
    await Promise.all([e.init(), e.init()])
    expect(api.create).toHaveBeenCalledTimes(1)
    expect(api.setDraft).toHaveBeenCalledTimes(1)
  })
  it('serializa los cambios y usa la versión persistida para la cola', async () => {
    const e = new BookingEditor()
    await e.init()
    vi.mocked(api.patch).mockImplementation(async (b, p) => ({
      ...b,
      version: b.version + 1,
      configuration: { ...b.configuration, ...p },
    }))
    e.edit({ adults: 4 })
    let version = 0
    await e.mutate(async (b) => {
      version = b.version
      return { ...b, version: b.version + 1 }
    })
    expect(version).toBe(2)
    expect(e.snapshot().booking?.version).toBe(3)
    expect(e.snapshot().dirty).toEqual({})
  })
  it('conserva la edición que llega mientras se guarda otra', async () => {
    const e = new BookingEditor()
    await e.init()
    let finish!: (b: Booking) => void
    vi.mocked(api.patch).mockImplementation(
      () =>
        new Promise((r) => {
          finish = r
        }),
    )
    e.edit({ notes: 'Primera' })
    const saving = e.flush()
    await new Promise((r) => setTimeout(r, 0))
    e.edit({ notes: 'Segunda' })
    finish({ ...booking, version: 2, configuration: { ...config, notes: 'Primera' } })
    await saving
    expect(e.snapshot().dirty).toEqual({ notes: 'Segunda' })
    vi.mocked(api.patch).mockResolvedValue({
      ...booking,
      version: 3,
      configuration: { ...config, notes: 'Segunda' },
    })
    await e.flush()
    expect(e.snapshot().dirty).toEqual({})
    expect(e.snapshot().booking?.configuration.notes).toBe('Segunda')
  })
  it('un conflicto no descarta el formulario ni ejecuta la cola', async () => {
    const e = new BookingEditor()
    await e.init()
    vi.mocked(api.patch).mockRejectedValue(new ApiError('version_conflict', 'Conflict', 409))
    e.edit({ adults: 5 })
    const operation = vi.fn()
    await expect(e.mutate(operation)).rejects.toThrow()
    expect(operation).not.toHaveBeenCalled()
    expect(e.snapshot().dirty).toEqual({ adults: 5 })
    expect(e.snapshot().error).toContain('another window')
    await e.flush().catch(() => {})
  })
  it('no cambia de borrador si no ha podido guardar el actual', async () => {
    const e = new BookingEditor()
    await e.init()
    vi.mocked(api.patch).mockRejectedValue(new ApiError('connection_failed', 'Offline', 503))
    e.edit({ notes: 'Keep draft' })
    await expect(e.switchTo('otro')).rejects.toThrow()
    expect(e.snapshot().booking?.id).toBe('draft')
    expect(api.setDraft).not.toHaveBeenCalled()
    await e.flush().catch(() => {})
  })
})
