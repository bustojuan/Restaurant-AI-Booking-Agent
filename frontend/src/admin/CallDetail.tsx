import { en } from '../i18n/en'
import { stateLabel } from '../i18n/presentation'
import { useEffect, useMemo, useState, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowLeft,
  ChevronRight,
  Phone,
  Clock3,
  Coins,
  AudioLines,
  Network,
  RefreshCw,
  ShieldCheck,
  Radio,
  Bot,
  Wrench,
  GitBranch,
  CircleDot,
  Maximize2,
  Minimize2,
} from 'lucide-react'
import { adminApi } from './api'
import { AgentGraph } from './AgentGraph'
import { Inspector } from './Inspector'
import { Timeline } from './Timeline'
import { AttemptSummary } from './AttemptSummary'
import { Badge, Button, Empty, ErrorState, KeyValue, Loading, StateBadge } from './ui'
import type { Observation } from './types'
import {
  ordered,
  time,
  display,
  eventLabel,
  dateTime,
  duration,
  modeLabel,
  resultLabel,
  short,
} from './replay'
function EventIcon({ event }: { event: Observation }) {
  return event.kind === 'tool' ? (
    <Wrench size={14} />
  ) : event.kind.includes('voice') ? (
    <AudioLines size={14} />
  ) : event.kind.includes('delegation') ? (
    <GitBranch size={14} />
  ) : event.agent ? (
    <Bot size={14} />
  ) : (
    <CircleDot size={14} />
  )
}
export function CallDetail({ id, back }: { id: string; back: () => void }) {
  const call = useQuery({
    queryKey: ['admin', 'call', id],
    queryFn: () => adminApi.call(id),
    refetchInterval: 10000,
  })
  const executionId = call.data?.execution_id
  const run = useQuery({
    queryKey: ['admin', 'execution', executionId],
    queryFn: () => adminApi.execution(executionId!),
    enabled: !!executionId,
  })
  const history = useQuery({
    queryKey: ['admin', 'history', executionId],
    queryFn: () => adminApi.events(executionId!),
    enabled: !!executionId,
    staleTime: Infinity,
  })
  const [graphId, setGraphId] = useState(''),
    [scope, setScope] = useState('call'),
    [at, setAt] = useState<number | null>(null),
    [playing, setPlaying] = useState(false),
    [speed, setSpeed] = useState(1),
    [selected, setSelected] = useState<Observation | null>(null),
    [eventTab, setEventTab] = useState('summary'),
    [height, setHeight] = useState(64),
    [leftWidth, setLeftWidth] = useState(63),
    [live, setLive] = useState(false)
  const detailRef = useRef<HTMLDivElement>(null)
  const [expandedGraph, setExpandedGraph] = useState(false)
  const events = useMemo(
    () =>
      ordered(
        (history.data?.events ?? []).filter(
          (e) => scope === 'execution' || !e.call_attempt_id || e.call_attempt_id === id,
        ),
      ),
    [history.data, scope, id],
  )
  const graphVersions = useMemo(
    () => [
      ...new Set(
        [run.data?.graph_version, ...events.map((e) => e.graph_version)].filter(
          (v): v is string => !!v,
        ),
      ),
    ],
    [run.data, events],
  )
  const currentGraph = graphId || graphVersions[0]
  const graph = useQuery({
    queryKey: ['admin', 'graph', currentGraph],
    queryFn: () => adminApi.graph(currentGraph!),
    enabled: !!currentGraph,
    staleTime: Infinity,
  })
  const min = events.length ? time(events[0]) : 0,
    max = events.length ? time(events.at(-1)!) : 0,
    cursor = Math.max(min, Math.min(at ?? max, max))
  useEffect(() => {
    if (!playing) return
    let last = performance.now()
    const timer = setInterval(() => {
      const now = performance.now(),
        delta = (now - last) * speed
      last = now
      setAt((previous) => {
        const next = Math.min(max, (previous ?? min) + delta)
        if (next >= max) setPlaying(false)
        return next
      })
    }, 40)
    return () => clearInterval(timer)
  }, [playing, speed, min, max])
  useEffect(() => {
    if (!live || !executionId) return
    let timer: ReturnType<typeof setTimeout> | undefined
    const stop = window.admin?.onEvent((e) => {
      if (e.execution_id === executionId && !timer)
        timer = setTimeout(() => {
          timer = undefined
          void history.refetch()
          void run.refetch()
          setAt(null)
        }, 500)
    })
    return () => {
      stop?.()
      clearTimeout(timer)
    }
  }, [live, executionId, history.refetch, run.refetch])
  const select = (event: Observation) => {
    setSelected(event)
    setAt(time(event))
    setPlaying(false)
    setLive(false)
    if (event.graph_version) setGraphId(event.graph_version)
  }
  const selectNode = (node: string) => {
    const agent = node === 'voice_session' ? 'voice' : node
    const agentInvocations = events.filter(
      (e) =>
        e.graph_version === currentGraph &&
        e.node === node &&
        e.kind === 'agent' &&
        e.agent === agent &&
        e.phase === 'started' &&
        time(e) <= cursor,
    )
    const matching = events.filter(
      (e) =>
        e.graph_version === currentGraph &&
        e.node === node &&
        e.kind === 'graph.node' &&
        e.phase === 'started' &&
        time(e) <= cursor,
    )
    const latest = agentInvocations.at(-1) ?? matching.at(-1)
    if (latest) setSelected(latest)
    else setSelected(null)
  }
  const cursorEvent = events
    .slice()
    .reverse()
    .find((event) => time(event) <= cursor)
  const highlightedId = !playing && selected ? selected.id : cursorEvent?.id
  useEffect(() => {
    if (highlightedId != null)
      detailRef.current
        ?.querySelector(`[data-observation-id="${highlightedId}"]`)
        ?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [highlightedId])
  const resize = (axis: 'horizontal' | 'vertical', event: React.PointerEvent) => {
    const bounds = detailRef.current?.getBoundingClientRect()
    if (!bounds) return
    event.currentTarget.setPointerCapture(event.pointerId)
    const move = (e: PointerEvent) => {
      if (axis === 'horizontal')
        setLeftWidth(Math.max(40, Math.min(75, ((e.clientX - bounds.left) / bounds.width) * 100)))
      else setHeight(Math.max(36, Math.min(72, ((e.clientY - bounds.top) / bounds.height) * 100)))
    }
    const target = event.currentTarget
    target.addEventListener('pointermove', move as EventListener)
    target.addEventListener(
      'pointerup',
      () => target.removeEventListener('pointermove', move as EventListener),
      { once: true },
    )
  }
  if (call.isPending) return <Loading />
  if (call.isError)
    return (
      <section className="ac-page">
        <Button onClick={back}>
          <ArrowLeft size={14} />
          Calls
        </Button>
        <ErrorState error={call.error} retry={() => void call.refetch()} />
      </section>
    )
  const c = call.data
  const visibleEvents = events.filter(
    (e) => eventTab === 'events' || /voice|delegation|call\./.test(e.kind),
  )
  return (
    <section className="ac-detail" data-testid="call-detail">
      <div className="ac-breadcrumb">
        <button onClick={back}>Calls</button>
        <ChevronRight size={12} />
        <span>{c.restaurant_name}</span>
        <code>{short(c.id)}</code>
        <div className="ac-actions">
          <Button
            className={live ? 'ac-live-button' : ''}
            disabled={!executionId}
            onClick={() => {
              setLive((v) => !v)
              setPlaying(false)
            }}
          >
            <Radio size={13} />
            {live ? en.followingLive : en.followLive}
          </Button>
          <Button
            aria-label={en.refreshDetails}
            onClick={() => {
              if (executionId) {
                void history.refetch()
                void run.refetch()
              }
              void call.refetch()
            }}
          >
            <RefreshCw size={13} />
          </Button>
        </div>
      </div>
      <div className="ac-detail-header">
        <div className="ac-inline">
          <span className="ac-detail-icon">
            <Phone size={22} />
          </span>
          <div>
            <div className="ac-inline">
              <h1>{c.restaurant_name}</h1>
              <StateBadge status={c.status} />
              {c.transport_state &&
                ['ACTIVE', 'DIALING', 'UNCERTAIN'].includes(c.transport_state) && (
                  <StateBadge status={c.transport_state} />
                )}
              <Badge tone="violet">{modeLabel(c.mode)}</Badge>
            </div>
            <p>
              {dateTime(c.started_at)} <span>·</span> {en.booking2}
              {short(c.booking_id)} <span>·</span> {en.attempt2} {c.sequence + 1}
            </p>
          </div>
        </div>
        <div className="ac-detail-metrics">
          <div>
            <span>{en.result}</span>
            <strong className={c.result === 'CONFIRMED' ? 'ac-green' : ''}>
              {resultLabel(c.result)}
            </strong>
          </div>
          <div>
            <span>
              <Clock3 size={12} />

              {en.duration}
            </span>
            <strong>{duration(c.duration_ms)}</strong>
          </div>
          <div>
            <span>
              <Coins size={12} />

              {en.cost}
            </span>
            <strong>{c.cost_eur == null ? en.nA : `€${c.cost_eur.toFixed(4)}`}</strong>
          </div>
        </div>
      </div>
      <div className="ac-detail-status">
        <ShieldCheck size={13} />
        <span>{en.readOnlyHistoricalReplay}</span>
        <span className="ac-divider" />
        <span>
          {en.coverage} {run.data?.coverage ?? c.coverage}
        </span>
        <span>·</span>
        <span>
          {events.length} {en.events}
        </span>
        <span>·</span>
        <span>Cursor #{history.data?.high ?? '—'}</span>
        <div className="ac-actions">
          <select
            aria-label={en.executionScope}
            value={scope}
            onChange={(e) => {
              setScope(e.target.value)
              setSelected(null)
              setAt(null)
              setPlaying(false)
            }}
          >
            <option value="call">{en.callSharedCoordination}</option>
            <option value="execution">{en.fullBookingExecution}</option>
          </select>
        </div>
      </div>
      {history.isError ? (
        <ErrorState error={history.error} retry={() => void history.refetch()} />
      ) : history.isPending && executionId ? (
        <Loading />
      ) : (
        <div className={`ac-detail-workspace ${selected ? 'with-inspector' : ''}`}>
          <div
            className="ac-detail-panels"
            ref={detailRef}
            style={{
              gridTemplateRows: `minmax(260px, ${height}fr) 7px minmax(190px, ${100 - height}fr)`,
            }}
          >
            <div
              className="ac-detail-top"
              style={{
                gridTemplateColumns: `minmax(${selected ? 300 : 360}px,${leftWidth}fr) 7px minmax(${selected ? 240 : 280}px,${100 - leftWidth}fr)`,
              }}
            >
              <div className={`ac-panel ac-graph-panel ${expandedGraph ? 'expanded' : ''}`}>
                <div className="ac-panel-head">
                  <div className="ac-inline">
                    <Network size={16} />
                    <h3>Agent Graph</h3>
                    <span className="ac-tag">{graph.data?.name ?? 'HISTORICAL'}</span>
                  </div>
                  {graphVersions.length > 1 && (
                    <select
                      aria-label={en.graphVersion}
                      value={currentGraph}
                      onChange={(e) => {
                        setGraphId(e.target.value)
                        setSelected(null)
                      }}
                    >
                      {graphVersions.map((g, i) => (
                        <option key={g} value={g}>
                          {i === 0 ? 'Booking graph' : 'Delegation graph'} · {g.slice(0, 7)}
                        </option>
                      ))}
                    </select>
                  )}
                  <Button
                    aria-label={expandedGraph ? en.restoreGraph : en.expandGraph}
                    onClick={() => setExpandedGraph((v) => !v)}
                  >
                    {expandedGraph ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
                  </Button>
                </div>
                {graph.isError ? (
                  <ErrorState error={graph.error} />
                ) : (
                  <AgentGraph
                    graph={events.length ? graph.data : undefined}
                    events={events}
                    invocationHistory={history.data?.events}
                    at={cursor}
                    selected={
                      selected && time(selected) <= cursor
                        ? (selected.node ?? undefined)
                        : undefined
                    }
                    onSelect={(node, event) => (event ? setSelected(event) : selectNode(node))}
                  />
                )}
                <div className="ac-graph-legend">
                  <span>
                    <i className="ac-dot dim" />

                    {en.notRecorded}
                  </span>
                  <span>
                    <i className="ac-dot" />

                    {en.completed}
                  </span>
                  <span>
                    <i className="ac-dot blue" />

                    {en.running}
                  </span>
                  <span>
                    <i className="ac-dot yellow" />

                    {en.interrupted}
                  </span>
                  <span className="ac-edge-key">{en.movingDotCurrentEntry}</span>
                  <span className="ac-edge-key">{en.ifConditionalRoute}</span>
                </div>
              </div>
              <div
                className="ac-resize-x"
                role="separator"
                aria-label={en.resizePanels}
                aria-orientation="vertical"
                tabIndex={0}
                onPointerDown={(e) => resize('horizontal', e)}
                onKeyDown={(e) => {
                  if (e.key === 'ArrowLeft') setLeftWidth((w) => Math.max(40, w - 5))
                  if (e.key === 'ArrowRight') setLeftWidth((w) => Math.min(75, w + 5))
                }}
              />
              <div className="ac-panel ac-events-panel">
                <div className="ac-panel-head">
                  <h3>Conversation / Events</h3>
                  <AudioLines size={16} />
                </div>
                <div className="ac-events-tabs">
                  <button
                    className={eventTab === 'summary' ? 'active' : ''}
                    onClick={() => setEventTab('summary')}
                  >
                    {en.attemptSummary}
                  </button>
                  <button
                    className={eventTab === 'events' ? 'active' : ''}
                    onClick={() => setEventTab('events')}
                  >
                    {en.allEvents} <span>{events.length}</span>
                  </button>
                  <button
                    className={eventTab === 'voice' ? 'active' : ''}
                    onClick={() => setEventTab('voice')}
                  >
                    {en.voice}
                  </button>
                </div>
                {eventTab === 'summary' ? (
                  <AttemptSummary call={c} events={events} selectEvent={select} />
                ) : (
                  <>
                    <div className="ac-transcript-note">
                      <ShieldCheck size={14} />
                      <span>
                        <span>{en.transcriptUnavailableForThisCall}</span>
                        <small>{en.eventsAndMetadataAreRetainedWithoutAudio}</small>
                      </span>
                    </div>
                    <div className="ac-event-list">
                      {visibleEvents.length ? (
                        visibleEvents.map((event) => (
                          <button
                            key={event.id}
                            className={`ac-event ${time(event) > cursor ? 'future' : ''} ${highlightedId === event.id ? 'selected' : ''}`}
                            data-observation-id={event.id}
                            aria-label={en.event(event.id, event.kind)}
                            onClick={() => select(event)}
                          >
                            <span
                              className={`ac-event-icon ${event.phase === 'failed' ? 'danger' : ''}`}
                            >
                              <EventIcon event={event} />
                            </span>
                            <div>
                              <strong>{eventLabel(event)}</strong>
                              <span>
                                {event.kind} <i>·</i> {event.phase}
                              </span>
                              {event.data.role && (
                                <small>
                                  {event.data.role} · {event.data.characters ?? en.nA}{' '}
                                  {en.charactersTextNotStored}
                                </small>
                              )}
                              {event.data.from_node && (
                                <small>
                                  {event.data.from_node} → {event.data.to_node}
                                </small>
                              )}
                              {event.data.result && <small>{resultLabel(event.data.result)}</small>}
                            </div>
                            <time>{duration(time(event) - min)}</time>
                          </button>
                        ))
                      ) : (
                        <Empty title={en.noAvailableEvents}>
                          {en.noMetadataIsRetainedForThisScope}
                        </Empty>
                      )}
                    </div>
                  </>
                )}
              </div>
            </div>
            <div
              className="ac-resize-y"
              role="separator"
              aria-label={en.resizeTimelineHeight}
              aria-orientation="horizontal"
              tabIndex={0}
              onPointerDown={(e) => resize('vertical', e)}
              onKeyDown={(e) => {
                if (e.key === 'ArrowUp') setHeight((h) => Math.max(36, h - 5))
                if (e.key === 'ArrowDown') setHeight((h) => Math.min(72, h + 5))
              }}
            />
            <div className="ac-panel ac-timeline-panel">
              <Timeline
                events={events}
                at={cursor}
                onTime={(value) => {
                  setAt(value)
                  setLive(false)
                  setSelected(null)
                }}
                selected={highlightedId}
                onSelect={select}
                playing={playing}
                setPlaying={(v) => {
                  setPlaying(v)
                  setLive(false)
                  if (v) setSelected(null)
                }}
                speed={speed}
                setSpeed={setSpeed}
              />
            </div>
          </div>
          {selected && time(selected) <= cursor && (
            <Inspector
              events={events}
              selected={selected}
              at={cursor}
              onSelect={select}
              onClose={() => setSelected(null)}
            />
          )}
        </div>
      )}
      {(!executionId || run.data?.coverage === 'pruned' || run.data?.coverage === 'degraded') && (
        <div className="ac-coverage-note">
          {!executionId
            ? en.thisCallPredatesInstrumentationOrHasNoCorrelated
            : run.data?.coverage === 'pruned'
              ? en.eventsWereRemovedUnderTheRetentionPolicyThe
              : en.theCaptureHasTelemetryGapsOpenSpansAre}
        </div>
      )}
      {c.execution_summary && (
        <details className="ac-call-summary">
          <summary>{en.storedFullExecutionSummaryOriginalLanguage}</summary>
          {c.explanation && (
            <p>
              {en.booking3}: {stateLabel(c.explanation.booking_status)}
            </p>
          )}
          <p>{c.execution_summary}</p>
        </details>
      )}
      <details className="ac-call-identifiers">
        <summary>{en.technicalIdentifiersAndReferences}</summary>
        <KeyValue
          items={[
            [en.call, <code>{c.id}</code>],
            [en.booking3, <code>{c.booking_id}</code>],
            [en.execution, <code>{c.execution_id ?? en.nA}</code>],
            [en.session, <code>{c.call_session_id ?? en.nA}</code>],
            [en.transportStatus, c.transport_state ?? en.nA],
            [en.confirmation, <code>{c.confirmation_id ?? en.nA}</code>],
            [en.configuredModels, c.models.join(', ') || en.nA],
            [
              en.reportedCallModel,
              [
                ...new Set(
                  events
                    .filter((e) => e.call_attempt_id === id && e.reported_model)
                    .map((e) => e.reported_model),
                ),
              ].join(', ') || en.nA,
            ],
          ]}
        />
      </details>
    </section>
  )
}
