import { en, UI_LOCALE } from '../i18n/en'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  AreaChart,
  Area,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
} from 'recharts'
import {
  Phone,
  Layers3,
  CircleCheck,
  Clock3,
  Coins,
  ArrowUpRight,
  CalendarDays,
  Bot,
  Wrench,
  Activity,
} from 'lucide-react'
import { adminApi } from './api'
import { Empty, ErrorState, Loading, Metric, PanelHead, Segments, Badge } from './ui'
import { duration, display, resultLabel } from './replay'
import type { Filters } from './types'
const colors = ['#5b8fff', '#56d7aa', '#a38af7', '#f4bd68', '#fa7d88', '#6dd3ed', '#a4b3cc']
const tooltipStyle = {
  background: '#1a2230',
  border: '1px solid #344056',
  borderRadius: 8,
  color: '#e4ebf8',
  fontSize: 12,
}
const day = (offset: number) => {
  const d = new Date()
  d.setDate(d.getDate() - offset)
  return new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Madrid' }).format(d)
}
export function Analytics() {
  const [period, setPeriod] = useState('30'),
    [filters, setFilters] = useState<Filters>({
      date_from: day(29),
      date_to: day(0),
      mode: 'ai_simulation',
    }),
    [chart, setChart] = useState('calls')
  const query = useQuery({
    queryKey: ['admin', 'analytics', filters],
    queryFn: () => adminApi.analytics(filters),
    refetchInterval: 30000,
  })
  const update = (key: keyof Filters, value: string) =>
    setFilters((f) => ({ ...f, [key]: value || undefined }))
  const data = query.data
  return (
    <section className="ac-page" data-testid="admin-analytics">
      <div className="ac-page-title">
        <div>
          <div className="ac-eyebrow">OBSERVABILITY / PERFORMANCE</div>
          <h1>Analytics</h1>
          <p>{en.verifiedOutcomesObservedPerformance}</p>
        </div>
        <Badge tone="blue">
          {filters.mode === 'real_telephony'
            ? en.realPhoneCallData
            : filters.mode
              ? en.simulationData
              : en.combinedModesExplicitFilter}
        </Badge>
      </div>
      <div className="ac-analytics-filters">
        <CalendarDays size={15} />
        <select
          aria-label={en.analyticsPeriod}
          value={period}
          onChange={(e) => {
            setPeriod(e.target.value)
            if (e.target.value !== 'custom')
              setFilters((f) => ({
                ...f,
                date_from: day(Number(e.target.value) - 1),
                date_to: day(0),
              }))
          }}
        >
          <option value="7">{en.last7Days}</option>
          <option value="30">{en.last30Days}</option>
          <option value="90">{en.last90Days}</option>
          <option value="custom">{en.customPeriod}</option>
        </select>
        {period === 'custom' && (
          <>
            <input
              type="date"
              aria-label={en.analyticsFrom}
              value={filters.date_from ?? ''}
              onChange={(e) => update('date_from', e.target.value)}
            />
            <span>—</span>
            <input
              type="date"
              aria-label={en.analyticsTo}
              value={filters.date_to ?? ''}
              onChange={(e) => update('date_to', e.target.value)}
            />
          </>
        )}
        <select
          aria-label={en.analyticsMode}
          value={filters.mode ?? ''}
          onChange={(e) => update('mode', e.target.value)}
        >
          <option value="ai_simulation">{en.aiSimulation}</option>
          <option value="simulation">{en.classicSimulation}</option>
          <option value="real_telephony">{en.realPhoneCalls}</option>
          <option value="">{en.allModesCombined}</option>
        </select>
        <select
          aria-label={en.analyticsModel}
          value={filters.model ?? ''}
          onChange={(e) => update('model', e.target.value)}
        >
          <option value="">{en.allModels}</option>
          {[...new Set([...(data?.models ?? []), filters.model].filter(Boolean))].map((m) => (
            <option key={m}>{m}</option>
          ))}
        </select>
        <select
          aria-label={en.analyticsPrompt}
          value={filters.prompt ?? ''}
          onChange={(e) => update('prompt', e.target.value)}
        >
          <option value="">{en.allPrompts}</option>
          {[...new Set([...(data?.prompt_versions ?? []), filters.prompt].filter(Boolean))].map(
            (p) => (
              <option key={p}>{p}</option>
            ),
          )}
        </select>
        <span className="ac-muted">Europe/Madrid</span>
      </div>
      {query.isError ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : query.isPending ? (
        <Loading />
      ) : (
        data && (
          <>
            <div className="ac-kpis">
              <Metric
                label={en.totalCalls}
                value={data.calls.toLocaleString(UI_LOCALE)}
                note={en.bookingsAttemptsBooking(
                  data.bookings,
                  data.attempts_per_booking?.toFixed(1) ?? en.nA,
                )}
                icon={<Phone size={15} />}
              />
              <Metric
                label={en.confirmedBookings}
                value={data.confirmed_bookings}
                note={
                  data.confirmation_rate == null
                    ? en.rateUnavailable
                    : en.ofBookingsInThisPeriod((data.confirmation_rate * 100).toFixed(1))
                }
                icon={<CircleCheck size={15} />}
              />
              <Metric
                label={en.averageDuration}
                value={duration(data.average_duration_ms)}
                note={en.attemptsWithRecordedDuration}
                icon={<Clock3 size={15} />}
              />
              <Metric
                label={en.knownTotalCost}
                value={data.known_cost_eur == null ? en.nA : `€${data.known_cost_eur.toFixed(4)}`}
                note={en.callsWithRecordedCost(data.cost_coverage)}
                icon={<Coins size={15} />}
              />
            </div>
            <div className="ac-analytics-main">
              <div className="ac-panel ac-chart-panel">
                <PanelHead title={en.callActivity} subtitle={en.dailyCallsAndConfirmations}>
                  <Segments
                    value={chart}
                    onChange={setChart}
                    items={[
                      { value: 'calls', label: en.calls },
                      { value: 'average_ms', label: en.duration },
                    ]}
                  />
                </PanelHead>
                <div className="ac-chart">
                  {data.days.length ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart
                        data={data.days}
                        margin={{ top: 12, right: 16, left: 4, bottom: 0 }}
                      >
                        <defs>
                          <linearGradient id="calls-fill" x1="0" x2="0" y1="0" y2="1">
                            <stop offset="0%" stopColor="#578bff" stopOpacity={0.25} />
                            <stop offset="100%" stopColor="#578bff" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid stroke="#252e3e" strokeDasharray="3 4" vertical={false} />
                        <XAxis
                          dataKey="date"
                          tick={{ fill: '#8490a5', fontSize: 11 }}
                          axisLine={false}
                          tickLine={false}
                          tickFormatter={(d) => `${d.slice(8, 10)}/${d.slice(5, 7)}`}
                        />
                        <YAxis
                          tick={{ fill: '#8490a5', fontSize: 11 }}
                          axisLine={false}
                          tickLine={false}
                          width={44}
                          allowDecimals={chart !== 'calls'}
                          tickFormatter={(v) => (chart === 'average_ms' ? duration(v) : String(v))}
                        />
                        <Tooltip contentStyle={tooltipStyle} />
                        <Area
                          type="monotone"
                          dataKey={chart}
                          name={chart === 'calls' ? en.calls : en.durationMs}
                          stroke="#719cff"
                          strokeWidth={2}
                          fill="url(#calls-fill)"
                          isAnimationActive={false}
                        />
                        {chart === 'calls' && (
                          <Area
                            type="monotone"
                            dataKey="confirmations"
                            name={en.confirmations}
                            stroke="#56d7aa"
                            fill="transparent"
                            strokeWidth={2}
                            isAnimationActive={false}
                          />
                        )}
                      </AreaChart>
                    </ResponsiveContainer>
                  ) : (
                    <Empty title={en.noActivityInThisPeriod}>
                      {en.adjustTheModeOrDatesToExploreThe}
                    </Empty>
                  )}
                </div>
                <div className="ac-chart-legend">
                  <span>
                    <i style={{ background: colors[0] }} />
                    {chart === 'calls' ? en.calls : en.averageDuration}
                  </span>
                  {chart === 'calls' && (
                    <span>
                      <i style={{ background: colors[1] }} />

                      {en.confirmations}
                    </span>
                  )}
                </div>
              </div>
              <div className="ac-panel ac-results-chart">
                <PanelHead title={en.results} subtitle={en.attemptOutcomes} />
                <div className="ac-donut">
                  {data.results.length ? (
                    <>
                      <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                          <Pie
                            data={data.results}
                            dataKey="count"
                            nameKey="name"
                            innerRadius="66%"
                            outerRadius="84%"
                            paddingAngle={3}
                            stroke="none"
                            isAnimationActive={false}
                          >
                            {data.results.map((r, i) => (
                              <Cell key={r.name} fill={colors[i % colors.length]} />
                            ))}
                          </Pie>
                          <Tooltip contentStyle={tooltipStyle} />
                        </PieChart>
                      </ResponsiveContainer>
                      <div>
                        <strong>{data.calls}</strong>
                        <span>{en.calls2}</span>
                      </div>
                    </>
                  ) : (
                    <Empty title={en.noResults} />
                  )}
                </div>
                <div className="ac-result-legend">
                  {data.results.map((r, i) => (
                    <div key={r.name}>
                      <i style={{ background: colors[i % colors.length] }} />
                      <span>{resultLabel(r.name)}</span>
                      <strong>{r.count}</strong>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div className="ac-analytics-secondary">
              <div className="ac-panel">
                <PanelHead
                  title={en.agentPerformance}
                  subtitle={en.instrumentedExecutions(data.instrumented_executions)}
                >
                  <Bot size={16} />
                </PanelHead>
                {data.agents.length ? (
                  <div className="ac-table-scroll">
                    <table className="ac-table ac-small-table">
                      <thead>
                        <tr>
                          <th>{en.agent}</th>
                          <th>{en.invocations2}</th>
                          <th>{en.average}</th>
                          <th>{en.errors}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.agents.map((a) => (
                          <tr key={a.name}>
                            <td>
                              <span className="ac-agent-label">
                                <Bot size={13} />
                                {display(a.name)}
                              </span>
                            </td>
                            <td>{a.invocations}</td>
                            <td>{duration(a.average_ms)}</td>
                            <td>
                              <span className={a.errors ? 'ac-red' : 'ac-muted'}>{a.errors}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <Empty title={en.noAgentSpans}>{en.timingIsCalculatedOnlyFromStoredEvents}</Empty>
                )}
              </div>
              <div className="ac-panel">
                <PanelHead title={en.tools} subtitle={en.recordedInvocations}>
                  <Wrench size={15} />
                </PanelHead>
                {data.tools.length ? (
                  <div className="ac-tool-bars">
                    {data.tools.slice(0, 7).map((t) => (
                      <div key={t.name}>
                        <span>
                          {display(t.name)}
                          <strong>{t.count}</strong>
                        </span>
                        <div>
                          <i
                            style={{
                              width: `${(t.count / Math.max(...data.tools.map((t) => t.count))) * 100}%`,
                            }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <Empty title={en.noRecordedTools} />
                )}
                <div className="ac-mini-metrics">
                  <div>
                    <span>{en.averageModelLatency}</span>
                    <strong>{duration(data.model_latency_ms)}</strong>
                  </div>
                  <div>
                    <span>{en.inputOutputTokens}</span>
                    <strong>
                      {data.input_tokens ?? en.nA} / {data.output_tokens ?? en.nA}
                    </strong>
                  </div>
                  <div>
                    <span>{en.callErrors}</span>
                    <strong>{data.errors}</strong>
                  </div>
                  <div>
                    <span>{en.humanDecisions}</span>
                    <strong>{data.human_interventions}</strong>
                  </div>
                </div>
              </div>
            </div>
            <p className="ac-footnote">{en.latencyAndUsageAreCalculatedFromStoredSpans}</p>
          </>
        )
      )}
    </section>
  )
}
