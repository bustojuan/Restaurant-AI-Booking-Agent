import { scenarioLabel } from '../i18n/presentation'
import { en } from '../i18n/en'
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Play,
  FlaskConical,
  ArrowUpRight,
  CheckCircle2,
  Circle,
  Clock3,
  ShieldCheck,
  Workflow,
  ChevronRight,
  AlertTriangle,
  RotateCcw,
} from 'lucide-react'
import { adminApi } from './api'
import {
  Badge,
  Button,
  Empty,
  ErrorState,
  Field,
  KeyValue,
  Loading,
  PanelHead,
  StateBadge,
} from './ui'
import { duration, short } from './replay'
export function Playground({ open }: { open: (id: string) => void }) {
  const [scenario, setScenario] = useState('priority-success'),
    [adults, setAdults] = useState(4),
    [flexibility, setFlexibility] = useState(30),
    [bookingId, setBookingId] = useState<string | null>(null)
  const client = useQueryClient()
  const scenarios = useQuery({ queryKey: ['admin', 'scenarios'], queryFn: adminApi.scenarios })
  const run = useMutation({
    mutationFn: () =>
      adminApi.simulate({ scenario_id: scenario, adults, flexibility_minutes: flexibility }),
    onSuccess: (result) => {
      setBookingId(result.booking_id)
      void client.invalidateQueries({ queryKey: ['admin', 'calls'] })
    },
  })
  const evaluation = useQuery({
    queryKey: ['admin', 'evaluation', bookingId],
    queryFn: () => adminApi.evaluation(bookingId!),
    enabled: !!bookingId,
    refetchInterval: (query) => (query.state.data?.passed == null ? 1000 : false),
  })
  const calls = useQuery({
    queryKey: ['admin', 'playground-calls', bookingId],
    queryFn: () => adminApi.calls({ q: bookingId!, limit: 100 }),
    enabled: !!bookingId,
    refetchInterval: evaluation.data?.passed == null ? 1000 : false,
  })
  const chosen = scenarios.data?.find((s) => s.id === scenario)
  return (
    <section className="ac-page" data-testid="admin-playground">
      <div className="ac-page-title">
        <div>
          <div className="ac-eyebrow">DEVELOPMENT / SIMULATION LAB</div>
          <h1>
            Playground <Badge tone="violet">SIMULATION ONLY</Badge>
          </h1>
          <p>{en.exploreSystemDecisionsAndLimitsInADeterministic}</p>
        </div>
        <span className="ac-readonly">
          <ShieldCheck size={14} />

          {en.noAudioNoPhoneCallsNoPaidModels}
        </span>
      </div>
      <div className="ac-playground-layout">
        <div className="ac-panel ac-scenarios">
          <PanelHead title={en.scenarios} subtitle={en.backendCatalog} />
          <div>
            {scenarios.isError ? (
              <ErrorState error={scenarios.error} />
            ) : scenarios.isPending ? (
              <Loading />
            ) : (
              scenarios.data.map((s) => (
                <button
                  disabled={run.isPending || !!bookingId}
                  aria-pressed={s.id === scenario}
                  key={s.id}
                  onClick={() => setScenario(s.id)}
                >
                  <span className="ac-scenario-icon">
                    <FlaskConical size={15} />
                  </span>
                  <span>
                    <strong>{scenarioLabel(s.id)}</strong>
                    <small>{s.id}</small>
                  </span>
                  <ChevronRight size={13} />
                </button>
              ))
            )}
          </div>
        </div>
        <div className="ac-lab">
          <div className="ac-panel">
            <PanelHead title={en.simulationSettings} subtitle={en.langgraphExistingAgentsAndTools}>
              <Badge tone="blue">Deterministic</Badge>
            </PanelHead>
            <div className="ac-lab-config">
              <Field label={en.selectedScenario}>
                <input readOnly value={scenarioLabel(scenario)} />
              </Field>
              <div className="ac-form-row">
                <Field label={en.guests}>
                  <input
                    type="number"
                    aria-label={en.simulationGuests}
                    min={1}
                    max={20}
                    value={adults}
                    disabled={!!bookingId || run.isPending}
                    onChange={(e) => setAdults(Number(e.target.value))}
                  />
                </Field>
                <Field label={en.flexibilityMinutes}>
                  <select
                    aria-label={en.simulationFlexibility}
                    value={flexibility}
                    disabled={!!bookingId || run.isPending}
                    onChange={(e) => setFlexibility(Number(e.target.value))}
                  >
                    {[0, 15, 30, 60, 120].map((v) => (
                      <option key={v} value={v}>
                        {v} {en.minutes}
                      </option>
                    ))}
                  </select>
                </Field>
              </div>
              <div className="ac-info">
                <ShieldCheck size={15} />
                <span>{en.eachRunCreatesASeparateSimulationBookingWith}</span>
              </div>
              {scenario === 'missing-evidence' && (
                <p className="ac-footnote">
                  {en.simulatedCeliacDiseaseTheRestaurantMustVerifyGluten}
                </p>
              )}
              {chosen && !chosen.available && (
                <div className="ac-error">
                  <AlertTriangle size={16} />

                  {en.theBackendMustUseDeterministicExtractionToRun}
                </div>
              )}
              <div className="ac-lab-actions">
                {bookingId ? (
                  <Button
                    onClick={() => {
                      setBookingId(null)
                      run.reset()
                    }}
                  >
                    <RotateCcw size={14} />

                    {en.newSimulation}
                  </Button>
                ) : (
                  <Button
                    primary
                    disabled={
                      !chosen?.available ||
                      run.isPending ||
                      adults < 1 ||
                      adults > 20 ||
                      !Number.isInteger(adults)
                    }
                    onClick={() => run.mutate()}
                  >
                    <Play size={14} />
                    {run.isPending ? en.starting : en.runSimulation}
                  </Button>
                )}
                <span>{en.promptComparisonUnavailable}</span>
              </div>
              {run.isError && <ErrorState error={run.error} />}
            </div>
          </div>
          <div className="ac-panel ac-lab-results">
            <PanelHead
              title={en.executionResult}
              subtitle={bookingId ? en.booking4(short(bookingId)) : en.resultsComeFromTheBackend}
            />
            {!bookingId ? (
              <Empty title={en.theLabIsReady}>{en.selectAScenarioAndRunASimulationTo}</Empty>
            ) : evaluation.isError ? (
              <ErrorState error={evaluation.error} retry={() => void evaluation.refetch()} />
            ) : evaluation.isPending ? (
              <Loading />
            ) : (
              <div className="ac-lab-result-body">
                <div className="ac-lab-result-summary">
                  <StateBadge status={evaluation.data.status} />
                  <span>
                    <Clock3 size={13} />
                    {duration(evaluation.data.duration_ms)}
                  </span>
                  <Badge tone={evaluation.data.passed ? 'success' : 'neutral'}>
                    {evaluation.data.passed == null
                      ? en.evaluationPending
                      : evaluation.data.passed
                        ? en.evaluationPassed
                        : en.evaluationFailed}
                  </Badge>
                </div>
                <KeyValue
                  items={[
                    [en.recordedAgents, evaluation.data.agent_count],
                    [en.tools, evaluation.data.tools.join(', ') || en.pending],
                    [en.mode, 'ai_simulation'],
                  ]}
                />
                {Object.entries(evaluation.data.checks).length > 0 && (
                  <div className="ac-checks">
                    {Object.entries(evaluation.data.checks).map(([name, passed]) => (
                      <div key={name}>
                        {passed ? (
                          <CheckCircle2 size={14} className="ac-green" />
                        ) : (
                          <AlertTriangle size={14} className="ac-red" />
                        )}
                        {name.replaceAll('_', ' ')}
                      </div>
                    ))}
                  </div>
                )}
                <div className="ac-simulation-calls">
                  {calls.data?.items.map((c) => (
                    <button key={c.id} onClick={() => open(c.id)}>
                      <Workflow size={16} />
                      <div>
                        <strong>{c.restaurant_name}</strong>
                        <small>
                          {en.attempt2} {c.sequence + 1} · {c.result ?? en.inProgress}
                        </small>
                      </div>
                      <span>{en.openGraphAndTimeline}</span>
                      <ArrowUpRight size={15} />
                    </button>
                  ))}
                </div>
                {evaluation.data.status === 'WAITING_FOR_USER' && (
                  <div className="ac-info">{en.thisScenarioPausedForApprovalManageTheDecision}</div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
