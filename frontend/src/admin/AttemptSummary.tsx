import { en } from '../i18n/en'
import { evidenceLabel, factMessage, reviewCopy } from '../i18n/attempt'
import { useState } from 'react'
import { FileCheck2, Link2, ShieldAlert } from 'lucide-react'
import type { Call, Observation } from './types'
import { Button } from './ui'

type Evidence = NonNullable<Call['explanation']>['facts'][number]['evidence'][number]
export function AttemptSummary({
  call,
  events,
  selectEvent,
}: {
  call: Call
  events: Observation[]
  selectEvent: (e: Observation) => void
}) {
  const [reference, setReference] = useState<Evidence | null>(null)
  const explanation = call.explanation
  if (!explanation)
    return (
      <div className="ac-attempt-summary">{en.theBackendHasNoStructuredExplanationForThis}</div>
    )
  const review = explanation.review
  const reviewText = reviewCopy(explanation)
  const offer = explanation.offers.find((o) => o.id === reference?.id)
  const evidence = (ref: Evidence) => {
    setReference(ref)
    if (ref.kind === 'event') {
      const event = events.find((e) => e.id === ref.event_cursor)
      if (event) selectEvent(event)
    }
  }
  return (
    <div className="ac-attempt-summary" data-testid="attempt-summary">
      <div className="ac-summary-intro">
        <FileCheck2 size={16} />
        <div>
          <strong>{en.attemptExplanation}</strong>
          <small>{en.currentStoredFactsNotATranscriptIndependentOf}</small>
        </div>
      </div>
      {explanation.simulated && (
        <p className="ac-summary-simulation">{en.simulatedContactThisDoesNotEstablishAReal}</p>
      )}
      {review.category !== 'none' && (
        <div className={`ac-review-guidance ${review.category}`} data-testid="attempt-review">
          <ShieldAlert size={17} />
          <div>
            <strong>{reviewText.title}</strong>
            <p>{reviewText.message}</p>
            {!!review.steps?.length && (
              <details>
                <summary>{en.reviewProcedure}</summary>
                <ol>
                  {reviewText.steps.map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ol>
                <p>{en.thisPanelIsReadOnlyItCannotMake}</p>
                {review.reconciliation_available && (
                  <p>
                    {en.existingOperatorEndpoint}{' '}
                    <code>POST /api/voice/calls/{call.call_session_id}/reconcile</code>
                    {en.requiresLocalAccessTheCurrentVersionAndA}
                  </p>
                )}
                <Button onClick={() => window.admin?.openBooker()}>{en.openBookingApp}</Button>
              </details>
            )}
          </div>
        </div>
      )}
      <div className="ac-summary-facts">
        {explanation.facts.map((fact, index) => (
          <article key={`${fact.code}-${index}`}>
            <p>{factMessage(fact, explanation, call.result)}</p>
            <div>
              {fact.evidence.map((ref) => (
                <button
                  key={`${ref.kind}-${ref.id}`}
                  onClick={() => evidence(ref)}
                  aria-label={en.viewEvidence(evidenceLabel(ref))}
                >
                  <Link2 size={11} />
                  {evidenceLabel(ref)}
                </button>
              ))}
            </div>
          </article>
        ))}
      </div>
      {reference && (
        <section className="ac-evidence-card" data-testid="attempt-evidence">
          <strong>{evidenceLabel(reference)}</strong>
          <code>{reference.id}</code>
          {reference.kind === 'request' && (
            <pre>{JSON.stringify(explanation.requested, null, 2)}</pre>
          )}
          {reference.kind === 'offer' && <pre>{JSON.stringify(offer?.terms ?? null, null, 2)}</pre>}
          {reference.kind === 'evaluation' && (
            <p>
              {offer?.evaluation ?? en.unavailable} ·{' '}
              {offer?.approval_pending ? en.approvalPending : en.noPendingApproval}
            </p>
          )}
          {reference.kind === 'confirmation' && (
            <p>
              {en.confirmation} {explanation.simulated ? en.simulated2 : en.recorded}:{' '}
              {call.confirmation_id ?? en.unavailable}
            </p>
          )}
          {reference.kind === 'call' && (
            <p>
              {en.attempt} {call.status} · {call.result ?? en.noResult} {en.booking}{' '}
              {explanation.booking_status}
            </p>
          )}
          {reference.kind === 'event' && (
            <p>
              {events.some((e) => e.id === reference.event_cursor)
                ? en.eventSelectedInTheReplay(reference.event_cursor ?? en.nA)
                : en.thisEventIsOutsideTheRetainedCaptureIt}
            </p>
          )}
        </section>
      )}
    </div>
  )
}
