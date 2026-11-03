import { useQuery } from '@tanstack/react-query'
import { get } from '../../services/api'
import type { components } from '../../types/api.generated'
import type { Summary, BookingEvent } from '../../types/bridge'
export function useBookings() {
  return useQuery({
    queryKey: ['bookings'],
    queryFn: async () => {
      let all: Summary[] = [],
        offset = 0
      while (true) {
        const p = await get<components['schemas']['BookingPage']>(
          `/api/bookings?limit=100&offset=${offset}`,
        )
        all = all.concat(p.items)
        offset += p.items.length
        if (offset >= p.total || !p.items.length) return all
      }
    },
    refetchInterval: 15000,
  })
}
export async function loadEvents(id: string) {
  let events: BookingEvent[] = [],
    cursor = 0
  while (true) {
    const page = await get<components['schemas']['EventPage']>(
      `/api/bookings/${id}/events?after_event_id=${cursor}&limit=100`,
    )
    events = events.concat(page.items)
    if (!page.has_more) return events
    cursor = page.next_after_event_id
  }
}
export const activeStatuses = new Set(['RUNNING', 'WAITING_FOR_USER', 'READY'])
