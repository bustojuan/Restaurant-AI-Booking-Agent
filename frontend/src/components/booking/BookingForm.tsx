import { en } from '../../i18n/en'
import { useState, useRef, useEffect } from 'react'
import {
  Users,
  CalendarDays,
  Clock3,
  Armchair,
  Heart,
  MessageSquare,
  ChevronDown,
  Minus,
  Plus,
  X,
  UserRound,
  Check,
  LoaderCircle,
  SlidersHorizontal,
} from 'lucide-react'
import { useEditor, useUI } from '../../app/context'
import { editor } from '../../services/editor'
import { errorText } from '../../services/api'
import { todayMadrid } from '../../lib/utils'
import { Button } from '../ui/button'
import { Modal, Pop } from '../ui/overlay'
import type { Configuration } from '../../types/bridge'
function PhoneField({ initial }: { initial: string | null }) {
  const [value, setValue] = useState(initial ?? '')
  const input = useRef<HTMLInputElement>(null)
  const { notice } = useUI()
  useEffect(() => {
    if (document.activeElement !== input.current) setValue(initial ?? '')
  }, [initial])
  return (
    <input
      ref={input}
      aria-label={en.contactPhone}
      aria-invalid={value.length > 0 && value.trim().length < 5}
      placeholder={en.phone}
      type="tel"
      maxLength={30}
      value={value}
      onChange={(e) => {
        const v = e.target.value
        setValue(v)
        editor.edit({ contact_phone: v.trim().length >= 5 ? v.trim() : null })
      }}
      onBlur={() => {
        if (value && value.trim().length < 5) notice(en.enterAtLeast5CharactersToSaveThe)
      }}
    />
  )
}
export function BookingForm() {
  const state = useEditor()
  const c = editor.configuration()
  const { notice } = useUI()
  const [collapsed, setCollapsed] = useState(false),
    [details, setDetails] = useState(false),
    [restriction, setRestriction] = useState(false),
    [code, setCode] = useState(''),
    [kind, setKind] = useState<'celiac' | 'allergy' | 'intolerance' | 'diet' | 'other'>('allergy'),
    [instructions, setInstructions] = useState(''),
    [mandatory, setMandatory] = useState(true)
  if (!state.booking)
    return (
      <div className="configuration-card">
        <h2>{en.bookingSettings}</h2>
        <div className="empty">
          <LoaderCircle className="spin" />

          {en.connectingToYourDraft}
          {state.error && (
            <>
              <p role="alert">{state.error}</p>
              <Button onClick={() => void editor.init().catch((e) => notice(errorText(e)))}>
                {en.retry}
              </Button>
            </>
          )}
        </div>
      </div>
    )
  const edit = (p: Partial<Configuration>) => editor.edit(p)
  const disabled = state.booking.status !== 'DRAFT'
  return (
    <section className="configuration-card">
      <div className="section-heading">
        <h2>{en.bookingSettings}</h2>
        <Button
          icon
          variant="ghost"
          aria-label={collapsed ? en.expandBookingSettings : en.collapseBookingSettings}
          onClick={() => setCollapsed((v) => !v)}
        >
          <ChevronDown size={17} className={collapsed ? '' : 'rotate-180'} />
        </Button>
      </div>
      {!collapsed && (
        <fieldset disabled={disabled}>
          <div className="form-row">
            <label>
              <Users size={18} />

              {en.guests}
            </label>
            <div className="stepper">
              <strong>{c.adults + c.children}</strong>
              <span />
              <Button
                icon
                variant="ghost"
                aria-label={en.removeAdult}
                disabled={c.adults <= 1}
                onClick={() => edit({ adults: c.adults - 1 })}
              >
                <Minus size={16} />
              </Button>
              <i />
              <Button
                icon
                variant="ghost"
                aria-label={en.addAdult}
                disabled={c.adults >= 100}
                onClick={() => edit({ adults: c.adults + 1 })}
              >
                <Plus size={16} />
              </Button>
            </div>
          </div>
          <div className="form-row">
            <label htmlFor="requested-date">
              <CalendarDays size={18} />

              {en.date}
            </label>
            <input
              id="requested-date"
              aria-label={en.bookingDate}
              type="date"
              min={todayMadrid()}
              value={c.requested_date ?? ''}
              onChange={(e) => edit({ requested_date: e.target.value || null })}
            />
          </div>
          <div className="form-row">
            <label htmlFor="preferred-time">
              <Clock3 size={18} />

              {en.time}
            </label>
            <input
              id="preferred-time"
              aria-label={en.bookingTime}
              type="time"
              value={c.preferred_time?.slice(0, 5) ?? ''}
              onChange={(e) => edit({ preferred_time: e.target.value || null })}
            />
          </div>
          <div className="form-group">
            <label>
              <Armchair size={18} />

              {en.tablePreference}
            </label>
            <div className="table-options">
              {[
                ['indifferent', en.noPreference],
                ['terrace', en.terrace],
                ['inside', en.indoor],
              ].map(([value, label]) => (
                <button
                  key={value}
                  className={`option ${c.table_type === value ? 'selected' : ''}`}
                  onClick={() => edit({ table_type: value as Configuration['table_type'] })}
                >
                  {label}
                </button>
              ))}
              <button
                className={`option ${c.requirements.some((r) => r.key === 'views') ? 'selected' : ''}`}
                onClick={() =>
                  edit({
                    requirements: c.requirements.some((r) => r.key === 'views')
                      ? c.requirements.filter((r) => r.key !== 'views')
                      : [...c.requirements, { key: 'views', value: true, mandatory: false }],
                  })
                }
              >
                {en.views}
              </button>
            </div>
          </div>
          <div className="form-group">
            <label>
              <Heart size={18} />

              {en.allergiesDietaryRequirements}
            </label>
            <div className="diet-chips">
              {c.dietary_requirements.map((r) => (
                <span
                  className="diet-chip"
                  key={r.code}
                  title={`${r.kind} · ${r.mandatory ? en.required : en.preference} · ${r.instructions}`}
                >
                  {r.code}
                  <button
                    aria-label={en.removeRequirement(r.code)}
                    onClick={() =>
                      edit({
                        dietary_requirements: c.dietary_requirements.filter(
                          (v) => v.code !== r.code,
                        ),
                      })
                    }
                  >
                    <X size={13} />
                  </button>
                </span>
              ))}
              <Button onClick={() => setRestriction(true)}>
                <Plus size={16} />

                {en.add}
              </Button>
            </div>
          </div>
          <div className="form-group">
            <label htmlFor="booking-notes">
              <MessageSquare size={18} />

              {en.specialRequests}
            </label>
            <textarea
              id="booking-notes"
              rows={2}
              placeholder={en.eGAQuietAreaASpecialOccasion}
              maxLength={2000}
              value={c.notes ?? ''}
              onChange={(e) => edit({ notes: e.target.value || null })}
            />
          </div>
          <div className="contact-row">
            <UserRound size={17} />
            <input
              aria-label={en.contactName}
              placeholder={en.bookingName}
              maxLength={120}
              value={c.customer_name ?? ''}
              onChange={(e) => edit({ customer_name: e.target.value || null })}
            />
            <PhoneField key={state.booking.id} initial={c.contact_phone} />
          </div>
          <Button variant="ghost" className="advanced-button" onClick={() => setDetails((v) => !v)}>
            <SlidersHorizontal size={14} />
            {details ? en.fewerOptions : en.childrenFlexibilityAndMore}
            <ChevronDown size={14} />
          </Button>
          {details && (
            <div className="advanced-fields">
              <div className="field-grid">
                <label>
                  {en.adults}
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={c.adults}
                    onChange={(e) => {
                      if (+e.target.value >= 1 && +e.target.value <= 100)
                        edit({ adults: +e.target.value })
                    }}
                  />
                </label>
                <label>
                  {en.children}
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={c.children}
                    onChange={(e) => {
                      const v = +e.target.value
                      if (v >= 0 && v <= 100)
                        edit({ children: v, high_chairs: Math.min(c.high_chairs, v) })
                    }}
                  />
                </label>
                <label>
                  {en.highChairs}
                  <input
                    type="number"
                    min={0}
                    max={c.children}
                    value={c.high_chairs}
                    onChange={(e) => {
                      if (+e.target.value >= 0 && +e.target.value <= c.children)
                        edit({ high_chairs: +e.target.value })
                    }}
                  />
                </label>
                <label>
                  {en.flexibility}
                  <select
                    value={c.flexibility_minutes}
                    onChange={(e) => edit({ flexibility_minutes: +e.target.value })}
                  >
                    {[0, 15, 30, 60, 90, 120, 180, 240].map((n) => (
                      <option key={n} value={n}>
                        {n ? `± ${n} min` : en.exactTime}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  {en.budgetGuest}
                  <input
                    type="number"
                    min={1}
                    max={10000}
                    placeholder={en.notSet}
                    value={c.budget_per_person ?? ''}
                    onChange={(e) => {
                      const v = +e.target.value
                      if (e.target.value === '')
                        edit({ budget_per_person: null, strict_budget: false })
                      else if (v > 0 && v <= 10000) edit({ budget_per_person: v })
                    }}
                  />
                </label>
                <label>
                  {en.specialOccasion}
                  <input
                    value={c.special_occasion ?? ''}
                    maxLength={200}
                    placeholder={en.birthday}
                    onChange={(e) => edit({ special_occasion: e.target.value || null })}
                  />
                </label>
              </div>
              <label className="check-label">
                <input
                  type="checkbox"
                  checked={c.table_type_mandatory}
                  onChange={(e) => edit({ table_type_mandatory: e.target.checked })}
                />

                {en.requiredTableLocation}
              </label>
              {c.requirements.some((r) => r.key === 'views') && (
                <label className="check-label">
                  <input
                    type="checkbox"
                    checked={c.requirements.find((r) => r.key === 'views')?.mandatory ?? false}
                    onChange={(e) =>
                      edit({
                        requirements: c.requirements.map((r) =>
                          r.key === 'views' ? { ...r, mandatory: e.target.checked } : r,
                        ),
                      })
                    }
                  />

                  {en.viewsRequired}
                </label>
              )}
              <label className="check-label">
                <input
                  type="checkbox"
                  disabled={!c.budget_per_person}
                  checked={c.strict_budget}
                  onChange={(e) => edit({ strict_budget: e.target.checked })}
                />

                {en.strictBudget}
              </label>
              <label className="check-label">
                <input
                  type="checkbox"
                  checked={c.accessibility_required}
                  onChange={(e) => edit({ accessibility_required: e.target.checked })}
                />

                {en.accessibilityRequired}
              </label>
              <label className="check-label">
                <input
                  type="checkbox"
                  checked={c.stroller_space}
                  onChange={(e) => edit({ stroller_space: e.target.checked })}
                />

                {en.spaceForAStroller}
              </label>
            </div>
          )}
        </fieldset>
      )}
      <div className={`save-status ${state.error ? 'error' : ''}`} aria-live="polite">
        {state.error ? (
          <>
            <span>{state.error}</span>
            <Button
              variant="ghost"
              onClick={() => void editor.reload().catch((e) => notice(errorText(e)))}
            >
              {en.reviewCurrentVersion}
            </Button>
            <Button variant="ghost" onClick={() => void editor.flush().catch(() => {})}>
              {en.retrySaving}
            </Button>
          </>
        ) : state.saving || Object.keys(state.dirty).length ? (
          <>
            <LoaderCircle size={12} className="spin" />

            {en.saving}
          </>
        ) : (
          <>
            <Check size={12} />
            {state.booking.status === 'DRAFT'
              ? en.savedAsDraftEuropeMadrid
              : en.settingsLockedEuropeMadrid}
          </>
        )}
      </div>
      <Modal
        open={restriction}
        onOpenChange={setRestriction}
        title={en.addDietaryRequirement}
        description={en.confirmFoodSafetyRequirementsWithEachRestaurant}
      >
        <div className="modal-form">
          <label>
            {en.requirementType}
            <select value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
              <option value="allergy">{en.allergy}</option>
              <option value="celiac">{en.celiacDisease}</option>
              <option value="intolerance">{en.intolerance}</option>
              <option value="diet">{en.dietaryPreference}</option>
              <option value="other">{en.other}</option>
            </select>
          </label>
          <label>
            {en.name}
            <input
              value={code}
              maxLength={80}
              onChange={(e) => setCode(e.target.value)}
              placeholder={en.eGNuts}
            />
          </label>
          <label>
            {en.instructions}
            <textarea
              value={instructions}
              maxLength={500}
              onChange={(e) => setInstructions(e.target.value)}
            />
          </label>
          <label className="check-label">
            <input
              type="checkbox"
              checked={mandatory}
              onChange={(e) => setMandatory(e.target.checked)}
            />

            {en.mandatoryRequirement}
          </label>
          <Button
            variant="primary"
            disabled={
              !code.trim() ||
              c.dietary_requirements.some((r) => r.code === code.trim()) ||
              c.dietary_requirements.length >= 40
            }
            onClick={() => {
              edit({
                dietary_requirements: [
                  ...c.dietary_requirements,
                  { kind, code: code.trim(), instructions, mandatory },
                ],
              })
              setCode('')
              setInstructions('')
              setRestriction(false)
            }}
          >
            <Plus size={16} />

            {en.addDietaryRequirement}
          </Button>
        </div>
      </Modal>
    </section>
  )
}
