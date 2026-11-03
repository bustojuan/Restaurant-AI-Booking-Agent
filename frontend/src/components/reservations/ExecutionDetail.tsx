import { activityLabel, bookingSummary } from '../../i18n/presentation'
import { en } from '../../i18n/en'
import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CheckCircle2,
  Clock3,
  FilePenLine,
  Phone,
  Pause,
  Play,
  Users,
  CalendarDays,
  ArrowRight,
  AlertCircle,
} from 'lucide-react'
import { api, get, request, errorText } from '../../services/api'
import { editor } from '../../services/editor'
import { useUI } from '../../app/context'
import { cleanName, dateLabel, timestamp, statusLabel, resultLabel } from '../../lib/utils'
import { loadEvents, activeStatuses } from './queries'
import { Modal } from '../ui/overlay'
import { Button } from '../ui/button'
import type { components } from '../../types/api.generated'
import type { Summary } from '../../types/bridge'
const eventLabels: Record<string, string> = {
  'booking.created': en.draftCreated,
  'booking.updated': en.requestUpdated,
  'restaurant.selected': en.selectionUpdated,
  'booking.started': en.executionStarted,
  'call.started': en.callAttemptStarted,
  'call.completed': en.attemptCompleted,
  'alternative.proposed': en.alternativeReceived,
  'user.approval_required': en.approvalRequested,
  'user.decision_received': en.decisionReceived,
  'booking.confirmed': en.bookingConfirmed,
  'booking.exhausted': en.queueExhausted,
  'booking.cancelled': en.executionCancelled,
  'booking.failed': en.executionFailed,
}
export function ExecutionDetail({ id, onClose }: { id: string | null; onClose: () => void }) {
  const { notice } = useUI()
  const q = useQueryClient()
  const [busy, setBusy] = useState(false),
    [cancel, setCancel] = useState(false)
  const detail = useQuery({
    queryKey: ['booking', id],
    queryFn: () => api.booking(id!),
    enabled: !!id,
    refetchInterval: 5000,
  })
  const events = useQuery({
    queryKey: ['events', id],
    queryFn: () => loadEvents(id!),
    enabled: !!id,
    refetchInterval: 5000,
  })
  const ai = useQuery({
    queryKey: ['ai', id],
    queryFn: async () => {
      try {
        return await get<components['schemas']['ExecutionView']>(`/api/bookings/${id}/ai`)
      } catch (e) {
        if (e instanceof Error && 'status' in e && e.status === 404) return null
        throw e
      }
    },
    enabled: !!id,
    refetchInterval: 5000,
    retry: false,
  })
  const b = detail.data,
    s = b?.summary
  const action = async (path: string, body?: unknown) => {
    if (!b) return
    setBusy(true)
    try {
      await request<Summary>({
        method: 'POST',
        path: `/api/bookings/${b.id}/${path}`,
        version: b.version,
        body,
      })
      await Promise.all([
        q.invalidateQueries({ queryKey: ['booking', id] }),
        q.invalidateQueries({ queryKey: ['bookings'] }),
        q.invalidateQueries({ queryKey: ['ai', id] }),
      ])
      await editor.reload()
    } catch (e) {
      notice(errorText(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal
      open={!!id}
      onOpenChange={(v) => !v && onClose()}
      title={en.bookingTracking}
      description={s ? en.request(s.id.slice(0, 8), statusLabel[s.status]) : en.loadingRequest}
      wide
    >
      {detail.isError ? (
        <div className="empty" role="alert">
          {en.couldNotLoadTheRequest}
          <Button onClick={() => void detail.refetch()}>{en.retry}</Button>
        </div>
      ) : s && b ? (
        <div className="execution-detail">
          <div className="detail-summary">
            <span className={`status-pill ${s.status.toLowerCase()}`}>
              {s.status === 'CONFIRMED' ? <CheckCircle2 size={16} /> : <Clock3 size={16} />}{' '}
              {statusLabel[s.status]}
            </span>
            <div>
              <Users size={16} />
              {s.party_size} {en.guests2}
              <CalendarDays size={16} />
              {dateLabel(s.requested_date)}
              <Clock3 size={16} />
              {s.preferred_time?.slice(0, 5) ?? '—'}
            </div>
          </div>
          <div className="progress-info">
            <span>
              {s.completed_attempts} {en.of2} {s.total_restaurants} {en.attemptsCompleted}
            </span>
            <span>
              {s.pending_restaurants.length} {en.pending2}
            </span>
          </div>
          <div className="progress-track">
            <div
              style={{
                width: `${s.total_restaurants ? (s.completed_attempts / s.total_restaurants) * 100 : 0}%`,
              }}
            />
          </div>
          <div className="detail-columns">
            <section>
              <h3>{en.restaurantsByPriority}</h3>
              <div className="detail-queue">
                {b.restaurants.map((e) => {
                  const attempts = s.contacted_restaurants.filter(
                    (a) => a.restaurant_id === e.restaurant.id,
                  )
                  const a = attempts.at(-1)
                  return (
                    <div
                      key={e.restaurant.id}
                      className={a?.status === 'RUNNING' ? 'active-attempt' : ''}
                    >
                      <span className="small-priority">{e.position + 1}</span>
                      <div>
                        <strong>{cleanName(e.restaurant.name)}</strong>
                        <p>
                          {a?.status === 'RUNNING'
                            ? en.callingNow
                            : a?.result
                              ? resultLabel[a.result]
                              : a
                                ? a.status
                                : en.pending}
                        </p>
                        {a?.duration_ms !== null && a?.duration_ms !== undefined && (
                          <small>{(a.duration_ms / 1000).toFixed(1)} s</small>
                        )}
                      </div>
                      {a?.status === 'RUNNING' && <Phone size={17} className="blue" />}
                      {a?.result === 'CONFIRMED' && <CheckCircle2 className="success" size={18} />}
                    </div>
                  )
                })}
              </div>
              {s.pending_approvals.map((o) => (
                <div className="approval-card" key={o.id}>
                  <h3>
                    <AlertCircle size={17} />

                    {en.yourDecisionIsNeeded}
                  </h3>
                  <p>
                    {dateLabel(o.details.requested_date)} · {o.details.time.slice(0, 5)} ·{' '}
                    {o.details.party_size} {en.guests3}{' '}
                    {
                      { inside: en.indoor, terrace: en.terrace, indifferent: en.noPreference }[
                        o.details.table_type
                      ]
                    }
                  </p>
                  {o.details.price_per_person !== null && (
                    <p>
                      {en.pricePerGuest} {o.details.price_per_person} €
                    </p>
                  )}
                  <p>
                    {en.deposit} {o.details.deposit} €
                  </p>
                  {(o.details.financial_conditions ?? []).map((v, i) => (
                    <p key={i}>{v}</p>
                  ))}
                  <ul>
                    {Object.entries(o.details.verified_requirements ?? {}).map(([key, value]) => (
                      <li key={key}>
                        {key}: {value ? en.verified : en.notVerified}
                      </li>
                    ))}
                  </ul>
                  <div className="modal-actions">
                    <Button
                      disabled={busy}
                      onClick={() => void action('decisions', { offer_id: o.id, approve: false })}
                    >
                      {en.decline}
                    </Button>
                    <Button
                      disabled={busy}
                      variant="primary"
                      onClick={() => void action('decisions', { offer_id: o.id, approve: true })}
                    >
                      {en.approveAlternative}
                    </Button>
                  </div>
                </div>
              ))}
              {s.confirmation && (
                <div className="confirmation-card">
                  <CheckCircle2 size={24} />
                  <h3>
                    {s.confirmation.simulated ? en.simulatedConfirmation : en.bookingConfirmed}
                  </h3>
                  <p>
                    {cleanName(
                      b.restaurants.find((e) => e.restaurant.id === s.confirmation?.restaurant_id)
                        ?.restaurant.name ?? s.confirmation.restaurant_id,
                    )}
                  </p>
                  <p>
                    {dateLabel(s.confirmation.details.requested_date)} ·{' '}
                    {s.confirmation.details.time.slice(0, 5)} · {s.confirmation.details.party_size}{' '}
                    {en.guests2}
                  </p>
                  <p>
                    {en.table}{' '}
                    {
                      { inside: en.indoor, terrace: en.terrace, indifferent: en.noPreference }[
                        s.confirmation.details.table_type
                      ]
                    }
                  </p>
                  {s.confirmation.details.price_per_person !== null && (
                    <p>
                      {s.confirmation.details.price_per_person} {en.guest}
                    </p>
                  )}
                  <p>
                    {en.deposit} {s.confirmation.details.deposit} €
                  </p>
                  {(s.confirmation.details.financial_conditions ?? []).map((v, i) => (
                    <p key={i}>{v}</p>
                  ))}
                  {s.confirmation.reference && (
                    <code>
                      {en.reference} {s.confirmation.reference}
                    </code>
                  )}
                </div>
              )}
            </section>
            <section>
              <h3>{en.liveActivity}</h3>
              {ai.data && (
                <div className="agent-summary">
                  <span className="eyebrow">
                    LANGGRAPH ·{' '}
                    {ai.data.mode === 'ai_simulation' ? en.simulation2 : en.realPhoneCalls2}
                  </span>
                  <p>
                    {ai.data.paused
                      ? en.pausedAtASafeBoundary
                      : ai.data.active_agent
                        ? en.agent2(ai.data.active_agent)
                        : en.noActiveAgent}
                  </p>
                  {ai.data.summary_text && (
                    <p>{bookingSummary(s.status, s.completed_attempts, s.total_restaurants)}</p>
                  )}
                  {ai.data.quality_report && (
                    <small>
                      {en.evaluation}{' '}
                      {ai.data.quality_report.passed ? en.checksPassed : en.reviewRequired2}
                    </small>
                  )}
                  {ai.data.error_code && <p className="danger">{ai.data.error_code}</p>}
                </div>
              )}
              <div className="timeline">
                {events.data
                  ?.slice()
                  .reverse()
                  .map((e) => (
                    <div key={e.event_id}>
                      <span
                        className={`timeline-dot ${e.event_type === 'booking.confirmed' ? 'green' : ''}`}
                      />
                      <div>
                        <strong>
                          {e.payload.activity
                            ? activityLabel(e.payload.activity.agent, e.payload.activity.phase)
                            : (eventLabels[e.event_type] ?? e.event_type)}
                        </strong>
                        {e.payload.activity?.tool && <p>{e.payload.activity.tool}</p>}
                        <time>{timestamp(e.timestamp)}</time>
                      </div>
                    </div>
                  ))}
                {events.isError && (
                  <p role="alert">
                    {en.timelineUnavailable}
                    <Button onClick={() => void events.refetch()}>{en.retry}</Button>
                  </p>
                )}
              </div>
            </section>
          </div>
          <div className="detail-actions">
            {activeStatuses.has(s.status) ? (
              <>
                {ai.data && (
                  <Button
                    disabled={busy}
                    onClick={() => void action(ai.data?.paused ? 'ai/resume' : 'ai/pause')}
                  >
                    {ai.data.paused ? <Play size={15} /> : <Pause size={15} />}{' '}
                    {ai.data.paused ? en.resume : en.pauseAfterCurrentAttempt}
                  </Button>
                )}
                <Button variant="danger" disabled={busy} onClick={() => setCancel(true)}>
                  {en.cancelExecution}
                </Button>
              </>
            ) : (
              <Button
                onClick={() =>
                  void editor
                    .switchTo(undefined, b)
                    .then(() => {
                      q.invalidateQueries({ queryKey: ['bookings'] })
                      onClose()
                    })
                    .catch((e) => notice(errorText(e)))
                }
              >
                <FilePenLine size={16} />
                {en.reuseAsANewDraft} <ArrowRight size={15} />
              </Button>
            )}
          </div>
        </div>
      ) : (
        <div className="empty">{en.loadingStoredStatus}</div>
      )}
      <Modal
        open={cancel}
        onOpenChange={setCancel}
        title={en.cancelThisExecution}
        description={en.trackingWillStopAccordingToTheBackendS}
      >
        <div className="modal-actions">
          <Button onClick={() => setCancel(false)}>{en.continueExecution}</Button>
          <Button
            variant="danger"
            disabled={busy}
            onClick={() => void action('cancel').then(() => setCancel(false))}
          >
            {en.confirmCancellation}
          </Button>
        </div>
      </Modal>
    </Modal>
  )
}
