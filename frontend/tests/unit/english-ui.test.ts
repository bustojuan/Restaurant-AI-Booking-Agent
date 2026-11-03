import { expect, it } from 'vitest'
import { cleanName, dateLabel, timestamp } from '../../src/lib/utils'
import { categoryLabel, scenarioLabel, stateLabel } from '../../src/i18n/presentation'
import { evidenceLabel, factMessage, reviewCopy } from '../../src/i18n/attempt'
import { UI_LOCALE } from '../../src/i18n/en'
import type { Call } from '../../src/admin/types'

it('preserves source names, accents, addresses and user text while mapping only application IDs', () => {
  for (const value of [
    'Ático Restaurante & Terraza',
    'Calle de Alcalá',
    'Plaza Mayor',
    'El Pimiento Verde',
    'Madrid',
    'Navarra',
    'Celiaquía: zona tranquila',
  ]) {
    expect(cleanName(value)).toBe(value)
  }
  expect(categoryLabel('cuisine', 'navarrese')).toBe('Navarrese')
  expect(categoryLabel('establishment', 'fast_food')).toBe('Fast Food')
  expect(categoryLabel('cuisine', 'unknown-provider-id')).toBe('unknown-provider-id')
  expect(scenarioLabel('ai-correction')).toBe('Correction after an incompatible time')
  expect(stateLabel('WAITING_FOR_USER')).toBe('Awaiting your approval')
})

it('uses English presentation with day/month/year, Madrid time and a 24-hour clock', () => {
  expect(UI_LOCALE).toBe('en-GB')
  expect(dateLabel('2026-11-01')).toBe('01/11/2026')
  expect(timestamp('2026-11-01T20:30:00Z')).toBe('01/11/2026, 21:30')
  expect(timestamp('2026-07-01T19:30:00Z')).toBe('01/07/2026, 21:30')
})

it('projects English explanations without mutating stored Spanish evidence or inventing confirmation', () => {
  const explanation = {
    requested: {
      requested_date: '2026-11-01',
      time: '21:00:00',
      party_size: 4,
      flexibility_minutes: 30,
    },
    offers: [
      {
        id: 'offer-1',
        terms: { requested_date: '2026-11-01', time: '22:30:00', party_size: 4 },
        evaluation: 'UNACCEPTABLE',
      },
    ],
    facts: [],
    simulated: true,
    booking_status: 'FAILED',
    booking_version: 4,
    review: {
      category: 'review_required',
      title: 'Podría existir una reserva',
      message: 'Mensaje histórico',
      steps: ['Instrucción original'],
      automatic_continuation: false,
    },
  } as unknown as NonNullable<Call['explanation']>
  const fact = {
    code: 'time_outside_window',
    message: 'La oferta es incompatible',
    evidence: [{ kind: 'offer', id: 'offer-1', label: 'Oferta guardada' }],
  } as NonNullable<Call['explanation']>['facts'][number]
  const original = JSON.stringify({ explanation, fact })
  expect(factMessage(fact, explanation, 'INCOMPATIBLE_OFFER')).toContain('90 minutes')
  expect(factMessage(fact, explanation, 'INCOMPATIBLE_OFFER')).toContain('30 minutes')
  expect(evidenceLabel(fact.evidence[0])).toBe('Stored offer offer-1')
  expect(reviewCopy(explanation).title).toBe('A booking may exist: review required')
  expect(reviewCopy(explanation).steps[0]).toContain('Do not contact the restaurant')
  expect(JSON.stringify({ explanation, fact })).toBe(original)
})
