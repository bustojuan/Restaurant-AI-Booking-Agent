import type { BookingEvent, Summary } from '../types/bridge'
export class EventCursor {
  last = 0
  versions = new Map<string, number>()
  accept(event: BookingEvent) {
    if (event.schema_version !== 1 || event.event_id <= this.last) return false
    this.last = event.event_id
    const previous = this.versions.get(event.booking_id) ?? -1
    if (event.payload.summary.version < previous) return false
    this.versions.set(event.booking_id, event.payload.summary.version)
    return true
  }
  fresh(summary: Summary) {
    return summary.version >= (this.versions.get(summary.id) ?? -1)
  }
}
