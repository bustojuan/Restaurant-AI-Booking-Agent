import { en, UI_LOCALE, UI_TIME_ZONE } from '../i18n/en'
import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs))
export const cleanName = (name: string) => name.replace(/\s*\[SIMULADO\]/g, '')
export const dateLabel = (date: string | null | undefined) =>
  date
    ? new Intl.DateTimeFormat(UI_LOCALE, {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        timeZone: UI_TIME_ZONE,
      }).format(new Date(`${date}T12:00:00+01:00`))
    : en.datePending
export const timestamp = (value: string) =>
  new Intl.DateTimeFormat(UI_LOCALE, {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
    timeZone: UI_TIME_ZONE,
  }).format(new Date(value))
export const todayMadrid = () =>
  new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/Madrid',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date())
export function isFutureMadrid(date: string | null | undefined, time: string | null | undefined) {
  if (!date || !time) return false
  const parts = new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Europe/Madrid',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(new Date())
  const part = (type: string) => parts.find((p) => p.type === type)?.value ?? ''
  const now = `${part('year')}-${part('month')}-${part('day')}T${part('hour')}:${part('minute')}:${part('second')}`
  return `${date}T${time.length === 5 ? `${time}:00` : time}` > now
}
export const statusLabel: Record<string, string> = {
  DRAFT: en.draft,
  READY: en.ready,
  RUNNING: en.findingATable,
  WAITING_FOR_USER: en.awaitingYourApproval,
  CONFIRMED: en.bookingConfirmed,
  EXHAUSTED: en.noAvailability,
  CANCELLED: en.cancelled,
  FAILED: en.executionFailed,
}
export const resultLabel: Record<string, string> = {
  NO_AVAILABILITY: en.noAvailability,
  INCOMPATIBLE_OFFER: en.incompatibleProposal,
  OFFER_ACCEPTABLE: en.acceptableAlternative,
  USER_APPROVAL_REQUIRED: en.approvalRequired,
  INSUFFICIENT_INFORMATION: en.insufficientInformation,
  DECLINED: en.proposalDeclined,
  CONFIRMED: en.confirmed,
  NOT_CONFIRMED: en.unconfirmed,
  TIMEOUT: en.timedOut,
  ERROR: 'Error',
  CANCELLED: en.cancelled,
  INTERRUPTED: en.interrupted,
  DECLINED_AI: en.doesNotAcceptAiAgents,
  DISCONNECTED: en.disconnected,
  AMBIGUOUS: en.ambiguousOutcome,
  UNCERTAIN: en.uncertainOutcome,
}
