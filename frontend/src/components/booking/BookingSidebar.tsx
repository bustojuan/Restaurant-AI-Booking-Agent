import { scenarioLabel } from '../../i18n/presentation'
import { en } from '../../i18n/en'
import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Phone, Plus, FlaskConical, LoaderCircle } from 'lucide-react'
import { useEditor, useUI } from '../../app/context'
import { editor } from '../../services/editor'
import { api, get, errorText } from '../../services/api'
import { dateLabel, statusLabel, todayMadrid, isFutureMadrid } from '../../lib/utils'
import type { StartRequest } from '../../types/bridge'
import type { components } from '../../types/api.generated'
import { BookingForm } from './BookingForm'
import { Queue } from './Queue'
import { Button } from '../ui/button'
import { Modal } from '../ui/overlay'
export function BookingSidebar({ onTrack }: { onTrack: (id: string) => void }) {
  const { booking, saving, dirty, error } = useEditor()
  const { notice } = useUI()
  const q = useQueryClient()
  const [confirm, setConfirm] = useState(false),
    [starting, setStarting] = useState(false),
    [mode, setMode] = useState<StartRequest['mode']>('ai_simulation'),
    [scenario, setScenario] = useState('priority-success'),
    [consent, setConsent] = useState(false),
    [budget, setBudget] = useState(''),
    [duration, setDuration] = useState(60),
    [maxCalls, setMaxCalls] = useState(1)
  const capabilities = useQuery({ queryKey: ['capabilities'], queryFn: api.capabilities })
  const scenarios = useQuery({
    queryKey: ['scenarios'],
    queryFn: () => get<components['schemas']['ScenarioOut'][]>('/api/simulations/scenarios'),
  })
  const c = editor.configuration()
  const valid =
    booking &&
    booking.status === 'DRAFT' &&
    booking.restaurants.length > 0 &&
    !!c.customer_name?.trim() &&
    (c.contact_phone?.length ?? 0) >= 5 &&
    !!c.requested_date &&
    c.requested_date >= todayMadrid() &&
    !!c.preferred_time &&
    isFutureMadrid(c.requested_date, c.preferred_time) &&
    !saving &&
    !error
  const begin = async () => {
    if (!booking) return
    setStarting(true)
    try {
      await editor.flush()
      const latest = editor.snapshot().booking!
      const payload: StartRequest = { mode, scenario_id: scenario }
      if (mode === 'real_telephony')
        payload.call_authorization = {
          explicit_authorization: true,
          own_test_numbers_only: true,
          audio_processing_consent: true,
          max_calls: maxCalls,
          max_duration_seconds: duration,
          max_estimated_cost_eur: +budget,
          expires_at: new Date(Date.now() + 10 * 60000).toISOString(),
        }
      await api.start(latest, payload)
      await editor.reload()
      await q.invalidateQueries({ queryKey: ['bookings'] })
      setConfirm(false)
      onTrack(latest.id)
    } catch (e) {
      notice(errorText(e))
    } finally {
      setStarting(false)
    }
  }
  return (
    <aside className="booking-sidebar">
      <div className="sidebar-scroll">
        <BookingForm />
        <Queue />
        {booking && booking.status !== 'DRAFT' && (
          <div className="active-booking-note">
            <strong>{statusLabel[booking.status]}</strong>
            <Button onClick={() => onTrack(booking.id)}>{en.trackBooking}</Button>
            <Button
              onClick={() =>
                void editor
                  .switchTo()
                  .then(() => q.invalidateQueries({ queryKey: ['bookings'] }))
                  .catch((e) => notice(errorText(e)))
              }
            >
              <Plus size={15} />

              {en.newDraft}
            </Button>
          </div>
        )}
      </div>
      <footer className="booking-footer">
        <div className="execution-mode">
          <span>
            <FlaskConical size={13} />

            {en.simulationAvailable}
          </span>
          <button
            onClick={() =>
              void editor
                .switchTo()
                .then(() => q.invalidateQueries({ queryKey: ['bookings'] }))
                .catch((e) => notice(errorText(e)))
            }
            disabled={saving}
          >
            {en.newDraft} <Plus size={12} />
          </button>
        </div>
        <Button
          variant="primary"
          className="start-button"
          disabled={!valid}
          onClick={async () => {
            try {
              await editor.flush()
              setConfirm(true)
            } catch (e) {
              notice(errorText(e))
            }
          }}
        >
          <Phone size={20} fill="currentColor" />

          {en.startAiBooking}
        </Button>
        {!valid && booking?.status === 'DRAFT' && (
          <p className="start-help">
            {!booking.restaurants.length
              ? en.addARestaurantToGetStarted
              : !c.customer_name || !c.contact_phone
                ? en.enterAContactNameAndPhoneNumber
                : !c.requested_date || !c.preferred_time
                  ? en.chooseTheBookingDateAndTime
                  : error
                    ? en.checkThatTheDraftHasBeenSaved
                    : en.reviewTheSettingsBeforeContinuing}
          </p>
        )}
      </footer>
      <Modal
        open={confirm}
        onOpenChange={(v) => {
          if (!starting) setConfirm(v)
        }}
        title={en.readyToFindATable}
        description={en.restaurantsGuestsEuropeMadrid(
          booking?.restaurants.length ?? 0,
          c.adults + c.children,
          dateLabel(c.requested_date),
          c.preferred_time?.slice(0, 5) ?? '',
        )}
      >
        <div className="modal-form">
          <label>
            {en.executionMode}
            <select
              aria-label={en.executionMode}
              value={mode}
              onChange={(e) => {
                setMode(e.target.value as StartRequest['mode'])
                setConsent(false)
              }}
            >
              <option value="ai_simulation">{en.multiAgentSimulationLanggraph}</option>
              <option value="simulation">{en.classicSimulation}</option>
              <option
                disabled={
                  !capabilities.data?.real_telephony_enabled ||
                  !capabilities.data.openai_credentials_configured
                }
                value="real_telephony"
              >
                {en.realCallsAuthorizedNumbersYouOwn}
              </option>
            </select>
          </label>
          {mode !== 'real_telephony' ? (
            <>
              <div className="info-box">
                <FlaskConical size={20} />
                <div>
                  <strong>{en.thisExecutionIsASimulation}</strong>
                  <p>{en.noRestaurantsWillBeCalledAndNoPaid}</p>
                </div>
              </div>
              <label>
                {en.scenario}
                <select
                  aria-label={en.scenario}
                  value={scenario}
                  onChange={(e) => setScenario(e.target.value)}
                >
                  {scenarios.data?.map((s) => (
                    <option value={s.id} key={s.id}>
                      {scenarioLabel(s.id)}
                    </option>
                  ))}
                </select>
              </label>
            </>
          ) : (
            <>
              <div className="warning-box">{en.paidCallsWillOnlyBeMadeToYour}</div>
              <div className="field-grid">
                <label>
                  {en.maximumCalls}
                  <input
                    type="number"
                    min={1}
                    max={10}
                    value={maxCalls}
                    onChange={(e) => setMaxCalls(+e.target.value)}
                  />
                </label>
                <label>
                  {en.maximumDurationS}
                  <input
                    type="number"
                    min={10}
                    max={600}
                    value={duration}
                    onChange={(e) => setDuration(+e.target.value)}
                  />
                </label>
                <label>
                  {en.maximumBudget}
                  <input
                    type="number"
                    min={0.01}
                    max={100}
                    step={0.01}
                    value={budget}
                    onChange={(e) => setBudget(e.target.value)}
                  />
                </label>
              </div>
              <label className="check-label">
                <input
                  type="checkbox"
                  checked={consent}
                  onChange={(e) => setConsent(e.target.checked)}
                />

                {en.iAuthorizeTheseTestCallsToNumbersI}
              </label>
            </>
          )}
          <div className="modal-actions">
            <Button disabled={starting} onClick={() => setConfirm(false)}>
              {en.back}
            </Button>
            <Button
              variant="primary"
              disabled={
                starting ||
                !capabilities.data ||
                (mode === 'real_telephony' &&
                  (!consent ||
                    +budget <= 0 ||
                    +budget > 100 ||
                    maxCalls < 1 ||
                    maxCalls > 10 ||
                    duration < 10 ||
                    duration > 600))
              }
              onClick={() => void begin()}
            >
              {starting ? <LoaderCircle size={17} className="spin" /> : <Phone size={17} />}{' '}
              {mode === 'real_telephony' ? en.authorizeAndStartCalls : en.startSimulation}
            </Button>
          </div>
        </div>
      </Modal>
    </aside>
  )
}
