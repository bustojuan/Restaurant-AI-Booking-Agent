import { en } from './en'

// These maps accept application IDs, never restaurant names, addresses or free text.
const cuisines: Record<string, string> = {
  italian: 'Italian',
  spanish: 'Spanish',
  navarrese: 'Navarrese',
  basque: 'Basque',
  mediterranean: 'Mediterranean',
  japanese: 'Japanese',
  chinese: 'Chinese',
  korean: 'Korean',
  thai: 'Thai',
  indian: 'Indian',
  mexican: 'Mexican',
  american: 'American',
  french: 'French',
  peruvian: 'Peruvian',
  arab: 'Arab',
  fusion: 'Fusion',
  international: 'International',
  other: 'Other',
  asian: 'Asian',
  vietnamese: 'Vietnamese',
  indonesian: 'Indonesian',
  malaysian: 'Malaysian',
  turkish: 'Turkish',
  greek: 'Greek',
}
const establishments: Record<string, string> = {
  fast_food: 'Fast Food',
  burger: 'Burger Restaurant',
  pizzeria: 'Pizzeria',
  grill: 'Grill',
  seafood: 'Seafood',
  steakhouse: 'Steakhouse',
  traditional: 'Traditional Restaurant',
  gastrobar: 'Gastrobar',
  fine_dining: 'Fine Dining',
  cafe: 'Café with Food',
  buffet: 'Buffet',
  other: 'Other',
}
const dietary: Record<string, string> = {
  vegetarian: 'Vegetarian',
  vegan: 'Vegan',
  gluten_free: 'Gluten-free Options',
}
export function categoryLabel(group: 'cuisine' | 'establishment' | 'dietary', id: string) {
  return { cuisine: cuisines, establishment: establishments, dietary }[group][id] ?? id
}
const scenarios: Record<string, string> = {
  'priority-success': 'No availability, incompatible time, then confirmation',
  'all-full': 'All restaurants fully booked',
  approval: 'Simulated deposit requiring approval',
  'confirm-first': 'First restaurant confirms',
  'no-confirmation': 'Acceptable offer without confirmation',
  timeout: 'Simulated contact timeout',
  errors: 'Simulated contact error',
  'missing-evidence': 'Mandatory requirements not verified',
  'ai-incompatible': 'Alternative outside the authorized time window',
  'ai-valid-alternative': 'Valid alternative 15 minutes later',
  'ai-correction': 'Correction after an incompatible time',
  'ai-ambiguous': 'Ambiguous response with incomplete terms',
  'ai-refuses': 'Restaurant declines to speak to AI',
  'ai-injection': 'Attempt to change internal instructions',
  'ai-disconnect': 'Restaurant hangs up before making an offer',
  'ai-connection-error': 'Disconnection during confirmation',
  'ai-incomplete-confirmation': 'Apparent confirmation with missing details',
  'ai-interruption': 'Simulated turn interruption, without real audio',
}
export const scenarioLabel = (id: string) => scenarios[id] ?? id
const states: Record<string, string> = {
  DRAFT: en.draft,
  READY: en.ready,
  RUNNING: en.running,
  WAITING_FOR_USER: en.awaitingYourApproval,
  CONFIRMED: en.confirmed,
  EXHAUSTED: en.noAvailability,
  CANCELLED: en.cancelled,
  FAILED: en.executionFailed,
  COMPLETED: en.completed,
  ACTIVE: 'Active',
  DIALING: 'Dialing',
  UNCERTAIN: en.uncertainOutcome,
  PENDING: en.pending,
  STARTED: 'Started',
  INTERRUPTED: en.interrupted,
  ENDED: 'Ended',
  SIMULATED: en.simulated2,
  CREATED: 'Created',
  CONNECTED: 'Connected',
  DISCONNECTED: en.disconnected,
  NOT_STARTED: 'Not started',
  NOT_RUN: 'Not run',
  SELECTED: 'Selected',
}
export const stateLabel = (id: string | null | undefined) =>
  id ? (states[id.toUpperCase()] ?? id.replaceAll('_', ' ')) : en.nA
export const duringContact = (agent: string) => `${agent} · during contact`
export const activityLabel = (agent: string, phase: string) => `${agent} · ${stateLabel(phase)}`
export const bookingSummary = (status: string, completed: number, total: number) =>
  `${stateLabel(status)} · ${completed} of ${total} attempts completed.`
