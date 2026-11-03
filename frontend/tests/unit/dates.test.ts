import { afterEach, it, expect, vi } from 'vitest'
import { isFutureMadrid, todayMadrid } from '../../src/lib/utils'
afterEach(() => vi.useRealTimers())
it('valida la hora futura en Madrid independientemente del huso del equipo', () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-11-01T20:00:00Z'))
  expect(todayMadrid()).toBe('2026-11-01')
  expect(isFutureMadrid('2026-11-01', '20:59')).toBe(false)
  expect(isFutureMadrid('2026-11-01', '21:00')).toBe(false)
  expect(isFutureMadrid('2026-11-01', '21:01')).toBe(true)
  expect(isFutureMadrid('2026-11-02', '00:01')).toBe(true)
  expect(isFutureMadrid(null, '21:00')).toBe(false)
})
