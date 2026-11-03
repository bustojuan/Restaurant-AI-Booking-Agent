import { en } from '../i18n/en'
import type { Booking, Configuration } from '../types/bridge'
import { api, errorText } from './api'
export type EditorState = {
  booking: Booking | null
  dirty: Partial<Configuration>
  saving: boolean
  error: string | null
  ready: boolean
}
export class BookingEditor {
  private state: EditorState = {
    booking: null,
    dirty: {},
    saving: false,
    error: null,
    ready: false,
  }
  private listeners = new Set<() => void>()
  private pending: Promise<unknown> = Promise.resolve()
  private timer: ReturnType<typeof setTimeout> | undefined
  private initializing: Promise<void> | undefined
  subscribe = (fn: () => void) => {
    this.listeners.add(fn)
    return () => {
      this.listeners.delete(fn)
    }
  }
  snapshot = () => this.state
  private update(patch: Partial<EditorState>) {
    this.state = { ...this.state, ...patch }
    this.listeners.forEach((fn) => fn())
  }
  private enqueue<T>(fn: () => Promise<T>): Promise<T> {
    const p = this.pending.then(fn)
    this.pending = p.catch(() => {})
    return p
  }
  init() {
    return (this.initializing ??= this.enqueue(async () => {
      try {
        const w = await api.workspace()
        let b = w.active_draft_id ? await api.booking(w.active_draft_id) : null
        if (!b || b.status !== 'DRAFT') {
          b = await api.create()
          await api.setDraft(b.id)
        }
        this.update({ booking: b, ready: true, error: null })
      } catch (e) {
        this.initializing = undefined
        this.update({ error: errorText(e), ready: true })
        throw e
      }
    }))
  }
  edit(patch: Partial<Configuration>) {
    if (this.state.booking?.status !== 'DRAFT') return
    this.update({ dirty: { ...this.state.dirty, ...patch }, error: null })
    clearTimeout(this.timer)
    this.timer = setTimeout(() => {
      void this.flush().catch(() => {})
    }, 600)
  }
  configuration() {
    return { ...this.state.booking?.configuration, ...this.state.dirty } as Configuration
  }
  private async save() {
    const b = this.state.booking,
      dirty = this.state.dirty
    if (!b || !Object.keys(dirty).length) return
    this.update({ saving: true, error: null })
    try {
      const updated = await api.patch(b, dirty)
      const remaining = { ...this.state.dirty }
      for (const key of Object.keys(dirty) as (keyof Configuration)[])
        if (JSON.stringify(remaining[key]) === JSON.stringify(dirty[key])) delete remaining[key]
      this.update({ booking: updated, dirty: remaining })
    } catch (e) {
      this.update({ error: errorText(e) })
      throw e
    } finally {
      this.update({ saving: false })
    }
  }
  flush = () => {
    clearTimeout(this.timer)
    return this.enqueue(() => this.save())
  }
  mutate(fn: (booking: Booking) => Promise<Booking>) {
    clearTimeout(this.timer)
    return this.enqueue(async () => {
      await this.save()
      if (!this.state.booking) throw new Error(en.noActiveDraft)
      this.update({ saving: true, error: null })
      try {
        const b = await fn(this.state.booking)
        this.update({ booking: b })
        return b
      } catch (e) {
        this.update({ error: errorText(e) })
        throw e
      } finally {
        this.update({ saving: false })
      }
    })
  }
  async switchTo(id?: string, copy?: Booking) {
    await this.flush()
    return this.enqueue(async () => {
      const b = id
        ? await api.booking(id)
        : await api.create(
            copy?.configuration,
            copy?.restaurants.map((e) => e.restaurant.id),
          )
      if (b.status !== 'DRAFT') throw new Error(en.thisRequestCanNoLongerBeEdited)
      await api.setDraft(b.id)
      this.update({ booking: b, dirty: {}, error: null })
      return b
    })
  }
  async reload() {
    if (!this.state.booking) return
    const b = await api.booking(this.state.booking.id)
    this.update({ booking: b, error: null })
  }
  receive(b: Booking) {
    if (b.id === this.state.booking?.id && b.version > this.state.booking.version) {
      if (this.state.saving) return
      if (Object.keys(this.state.dirty).length)
        this.update({
          error: en.theDraftChangedOutsideThisWindowReviewThe,
        })
      else this.update({ booking: b })
    }
  }
}
export const editor = new BookingEditor()
