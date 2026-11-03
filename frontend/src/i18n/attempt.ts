import type { Call } from '../admin/types'
import { dateLabel } from '../lib/utils'

type Explanation = NonNullable<Call['explanation']>
type Fact = Explanation['facts'][number]
type Evidence = Fact['evidence'][number]

// Render structured, read-only projections in English. Stored messages stay untouched.
export function evidenceLabel(ref: Evidence) {
  const labels: Record<string, string> = {
    request: 'Saved request',
    call: 'Attempt result',
    offer: 'Stored offer',
    evaluation: 'Stored evaluation',
    confirmation: 'Confirmation',
    event: 'Event',
  }
  return `${labels[ref.kind] ?? ref.kind}${ref.kind === 'event' ? ` #${ref.event_cursor ?? ref.id}` : ['offer', 'confirmation'].includes(ref.kind) ? ` ${ref.id.slice(0, 8)}` : ''}`
}
export function factMessage(fact: Fact, explanation: Explanation, result: Call['result']) {
  const requested = explanation.requested
  const offerId = fact.evidence.find((r) => ['offer', 'evaluation'].includes(r.kind))?.id
  const offer = explanation.offers.find((o) => o.id === offerId)
  const terms = (v: NonNullable<Explanation['requested']>) =>
    `${v.party_size ?? 'N/A'} guests on ${dateLabel(v.requested_date)} at ${v.time?.slice(0, 5) ?? 'N/A'}`
  if (fact.code === 'requested' && requested)
    return `A table was requested for ${terms(requested)}, with ${requested.flexibility_minutes ?? 'N/A'} minutes of flexibility.`
  if (fact.code === 'offered' && offer) return `The stored offer is for ${terms(offer.terms)}.`
  if (fact.code === 'time_outside_window' && requested && offer) {
    const delta =
      Math.abs(
        Date.parse(`${offer.terms.requested_date}T${offer.terms.time}Z`) -
          Date.parse(`${requested.requested_date}T${requested.time}Z`),
      ) / 60000
    return `The offer was evaluated as incompatible. The time difference${Number.isFinite(delta) ? ` of ${delta} minutes` : ''} exceeds the authorized flexibility of ${requested.flexibility_minutes ?? 'N/A'} minutes.`
  }
  if (fact.code === 'evaluation')
    return (
      (
        {
          ACCEPTABLE:
            'The stored evaluation finds the offer acceptable. This alone does not confirm a booking.',
          UNACCEPTABLE: 'The stored evaluation classifies the offer as incompatible.',
          INSUFFICIENT_INFORMATION:
            'The stored evaluation indicates that information is missing before the offer can be accepted.',
          REQUIRES_USER_APPROVAL: 'The offer requires user approval before acceptance.',
        } as Record<string, string>
      )[offer?.evaluation ?? ''] ?? 'A stored evaluation is available in the evidence.'
    )
  if (fact.code === 'confirmed')
    return explanation.simulated
      ? 'A simulated confirmation has been stored.'
      : 'A backend confirmation has been stored.'
  if (fact.code === 'outcome')
    return (
      (
        {
          NO_AVAILABILITY: 'The stored result indicates no availability.',
          INCOMPATIBLE_OFFER: 'The attempt ended with an incompatible offer.',
          NOT_CONFIRMED: 'The attempt ended without a verified confirmation.',
          DECLINED_AI: 'The stored result indicates that the restaurant declined to speak to AI.',
          DECLINED: 'The user declined the proposal.',
          USER_APPROVAL_REQUIRED: 'The stored proposal requires user approval.',
          CANCELLED:
            'The execution was cancelled. This does not establish that an external booking was cancelled.',
        } as Record<string, string>
      )[result ?? ''] ?? 'See the recorded attempt result.'
    )
  if (fact.code === 'business_event')
    return 'A backend business decision was recorded. Open the linked event for its type and evidence.'
  if (fact.code === 'ambiguity') return reviewCopy(explanation).message
  return (
    (
      {
        offer_unavailable: 'The stored offer does not have a verifiable format.',
        date_mismatch: 'The offered date differs from the requested date.',
        party_mismatch: 'The offered guest count differs from the requested guest count.',
      } as Record<string, string>
    )[fact.code] ?? 'A stored detail is available in the linked evidence.'
  )
}
export function reviewCopy(explanation: Explanation) {
  const review = explanation.review
  const titles: Record<string, string> = {
    none: 'Recorded outcome',
    reconciled: 'Operator verified that no booking exists',
    review_required: 'A booking may exist: review required',
    continue: 'No accepted proposal: the queue could continue',
    unknown: 'Insufficient information to rule out a booking',
  }
  const messages: Record<string, string> = {
    none: 'Consult the offer, confirmation and events supporting this attempt.',
    reconciled:
      'The review is recorded. Execution remains stopped; no automatic redial or resumption occurs.',
    review_required:
      'There is no verified confirmation. A failed result does not prove that the restaurant made no booking. Check before continuing or repeating contact.',
    continue:
      'The attempt ended without a recorded accepted offer. The engine could continue through the queue; check the final booking status.',
    unknown:
      'The retained capture cannot establish what happened. Review the outcome before repeating contact.',
  }
  const simulatedReview =
    explanation.simulated && ['review_required', 'unknown'].includes(review.category)
  const steps = review.steps?.length
    ? review.category === 'review_required'
      ? [
          'Check with the restaurant whether a booking exists before creating another.',
          'Also verify that the call ended. Hanging up does not prove that no booking exists.',
          'If a booking exists, resolve it with the restaurant. This panel cannot infer confirmation or cancellation.',
          'If you verified that no booking exists, an operator can record the review through the existing reconciliation endpoint, which checks the provider and version. It does not resume execution.',
        ]
      : ['Verify with the restaurant whether a booking exists before repeating contact.']
    : []
  if (simulatedReview)
    steps.unshift(
      'For this simulation, review the scenario evidence. Do not contact the restaurant because of this result. The following steps apply to real attempts.',
    )
  return {
    title: titles[review.category] ?? 'Recorded review',
    message: simulatedReview
      ? 'This simulated attempt represents an unverifiable confirmation. It does not establish a real booking. A real call must stop until the outcome is reviewed.'
      : (messages[review.category] ?? 'Consult the stored review evidence.'),
    steps,
  }
}
