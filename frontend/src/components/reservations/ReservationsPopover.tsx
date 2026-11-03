import { en, UI_LOCALE, UI_TIME_ZONE } from '../../i18n/en'
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  Clock3,
  FilePenLine,
  LoaderCircle,
  Plus,
  Trash2,
  Users,
  XCircle,
  Phone,
} from 'lucide-react'
import * as Tabs from '@radix-ui/react-tabs'
import { useBookings, activeStatuses } from './queries'
import { useUI, useEditor } from '../../app/context'
import { editor } from '../../services/editor'
import { api, errorText } from '../../services/api'
import { cleanName, dateLabel, statusLabel, resultLabel } from '../../lib/utils'
import { Button } from '../ui/button'
import { Modal } from '../ui/overlay'
import type { Summary } from '../../types/bridge'
export function ReservationsPopover({
  onDetail,
  onClose,
}: {
  onDetail: (id: string) => void
  onClose: () => void
}) {
  const bookings = useBookings()
  const { notice } = useUI()
  const { booking } = useEditor()
  const q = useQueryClient()
  const [deleting, setDeleting] = useState<Summary | null>(null)
  const active = bookings.data?.filter((b) => activeStatuses.has(b.status)) ?? [],
    drafts = bookings.data?.filter((b) => b.status === 'DRAFT') ?? [],
    history =
      bookings.data?.filter((b) => !activeStatuses.has(b.status) && b.status !== 'DRAFT') ?? []
  const show = (b: Summary) => {
    onClose()
    onDetail(b.id)
  }
  return (
    <>
      <div className="reservations-heading">
        <h2>{en.bookings}</h2>
        <Button
          variant="ghost"
          icon
          aria-label={en.createNewDraft}
          onClick={() =>
            void editor
              .switchTo()
              .then(() => {
                onClose()
                q.invalidateQueries({ queryKey: ['bookings'] })
              })
              .catch((e) => notice(errorText(e)))
          }
        >
          <Plus size={18} />
        </Button>
      </div>
      <Tabs.Root defaultValue="active">
        <Tabs.List className="tabs">
          <Tabs.Trigger value="active">
            {en.inProgress2}
            {active.length})
          </Tabs.Trigger>
          <Tabs.Trigger value="drafts">
            {en.drafts}
            {drafts.length})
          </Tabs.Trigger>
          <Tabs.Trigger value="history">
            {en.history}
            {history.length})
          </Tabs.Trigger>
        </Tabs.List>
        <div className="reservations-scroll">
          {bookings.isLoading && (
            <div className="empty">
              <LoaderCircle className="spin" />

              {en.loadingBookings}
            </div>
          )}
          {bookings.isError && (
            <div className="empty" role="alert">
              {en.couldNotLoadBookings}
              <Button onClick={() => void bookings.refetch()}>{en.retry}</Button>
            </div>
          )}
          <Tabs.Content value="active">
            {!active.length && !bookings.isLoading && (
              <div className="empty">
                <Phone size={26} />
                <h3>{en.noBookingsInProgress}</h3>
                <p>{en.planYourNextOutingAndLetAiFind}</p>
              </div>
            )}
            {active.map((b) => (
              <article className="execution-preview" key={b.id}>
                <div className="execution-preview-heading">
                  <span
                    className={`status-dot ${b.status === 'WAITING_FOR_USER' ? 'amber' : 'green'}`}
                  />
                  <strong>{statusLabel[b.status]}</strong>
                  <small>
                    {b.completed_attempts}/{b.total_restaurants} {en.attempts}
                  </small>
                </div>
                <div className="execution-meta">
                  <Users size={13} />
                  {b.party_size}
                  <CalendarDays size={13} />
                  {dateLabel(b.requested_date)}
                  <Clock3 size={13} />
                  {b.preferred_time?.slice(0, 5) ?? en.noTimeSet}
                </div>
                <div className="execution-queue">
                  {b.contacted_restaurants.map((a) => (
                    <div key={a.id} className={a.status === 'RUNNING' ? 'currently-calling' : ''}>
                      <span className="small-priority">{a.sequence + 1}</span>
                      <strong>{cleanName(a.restaurant_name)}</strong>
                      <small>
                        {a.status === 'RUNNING'
                          ? en.calling
                          : a.result
                            ? resultLabel[a.result]
                            : en.noResult}
                      </small>
                    </div>
                  ))}
                  {b.pending_restaurants.map((r) => (
                    <div key={r.id}>
                      <span className="small-priority">{r.position + 1}</span>
                      <span>{cleanName(r.name)}</span>
                      <small>{en.pending}</small>
                    </div>
                  ))}
                </div>
                {b.pending_approvals.length > 0 && (
                  <div className="approval-banner">
                    {en.pendingApprovalCount(b.pending_approvals.length)}
                  </div>
                )}
                <Button variant="ghost" className="details-link" onClick={() => show(b)}>
                  {en.viewDetails} <ArrowRight size={16} />
                </Button>
              </article>
            ))}
          </Tabs.Content>
          <Tabs.Content value="drafts">
            {!drafts.length && !bookings.isLoading && (
              <div className="empty">
                <FilePenLine size={26} />
                <h3>{en.noDrafts}</h3>
                <p>{en.yourSettingsAreSavedAutomatically}</p>
              </div>
            )}
            {drafts.map((b) => (
              <article className="draft-preview" key={b.id} data-testid={`draft-${b.id}`}>
                <div>
                  <strong>
                    {dateLabel(b.requested_date)} ·{' '}
                    {b.preferred_time?.slice(0, 5) ?? en.timePending}
                  </strong>
                  <p>{en.guestsAndRestaurants(b.party_size, b.total_restaurants)}</p>
                  <small>
                    {en.updated}{' '}
                    {new Date(b.updated_at).toLocaleString(UI_LOCALE, {
                      timeZone: UI_TIME_ZONE,
                      day: '2-digit',
                      month: '2-digit',
                      year: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                      hourCycle: 'h23',
                    })}
                    {b.id === booking?.id ? en.active : ''}
                  </small>
                </div>
                <div className="draft-actions">
                  <Button
                    onClick={() =>
                      void editor
                        .switchTo(b.id)
                        .then(() => onClose())
                        .catch((e) => notice(errorText(e)))
                    }
                  >
                    {en.continue}
                  </Button>
                  <Button
                    variant="ghost"
                    icon
                    aria-label={en.deleteDraft}
                    className="delete-button"
                    onClick={() => setDeleting(b)}
                  >
                    <Trash2 size={16} />
                  </Button>
                </div>
              </article>
            ))}
          </Tabs.Content>
          <Tabs.Content value="history">
            {!history.length && !bookings.isLoading && (
              <div className="empty">
                <Clock3 size={26} />
                <h3>{en.yourHistoryStartsHere}</h3>
                <p>{en.completedExecutionsWillAppearHere}</p>
              </div>
            )}
            {history.map((b) => (
              <button className="history-preview" key={b.id} onClick={() => show(b)}>
                {b.status === 'CONFIRMED' ? (
                  <CheckCircle2 className="success" size={19} />
                ) : (
                  <XCircle className={b.status === 'CANCELLED' ? 'muted' : 'danger'} size={19} />
                )}
                <div>
                  <strong>{statusLabel[b.status]}</strong>
                  <p>
                    {dateLabel(b.requested_date)} · {b.preferred_time?.slice(0, 5) ?? '—'} ·{' '}
                    {b.party_size} {en.guests2}
                  </p>
                  <span>
                    {b.confirmation
                      ? cleanName(
                          b.contacted_restaurants.find(
                            (a) => a.restaurant_id === b.confirmation?.restaurant_id,
                          )?.restaurant_name ?? en.confirmedRestaurant,
                        )
                      : en.completedAttempts(b.completed_attempts)}
                  </span>
                  {b.confirmation?.simulated && <small>{en.simulated2}</small>}
                </div>
                <ArrowRight size={16} />
              </button>
            ))}
          </Tabs.Content>
        </div>
      </Tabs.Root>
      <Modal
        open={!!deleting}
        onOpenChange={(v) => !v && setDeleting(null)}
        title={en.deleteDraft}
        description={en.itsSettingsAndRestaurantSelectionWillBeDeleted}
      >
        <div className="modal-actions">
          <Button onClick={() => setDeleting(null)}>{en.keepDraft}</Button>
          <Button
            variant="danger"
            onClick={async () => {
              if (!deleting) return
              try {
                if (deleting.id === booking?.id) {
                  await editor.flush()
                  const target = editor.snapshot().booking!
                  await editor.switchTo()
                  await api.delete(target)
                } else await api.delete(deleting)
                setDeleting(null)
                await q.invalidateQueries({ queryKey: ['bookings'] })
              } catch (e) {
                notice(errorText(e))
              }
            }}
          >
            {en.deleteDraft}
          </Button>
        </div>
      </Modal>
    </>
  )
}
