import { en } from '../i18n/en'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Play, Pause, SkipBack, SkipForward, ZoomIn, ZoomOut, ListTree, Timer } from 'lucide-react'
import type { Observation } from './types'
import { eventLabel, duration, ordered, spansOf, time } from './replay'
import { Button, Empty } from './ui'
export function Timeline({
  events,
  at,
  onTime,
  selected,
  onSelect,
  playing,
  setPlaying,
  speed,
  setSpeed,
}: {
  events: Observation[]
  at: number
  onTime: (t: number) => void
  selected?: number
  onSelect: (e: Observation) => void
  playing: boolean
  setPlaying: (v: boolean) => void
  speed: number
  setSpeed: (v: number) => void
}) {
  const [zoom, setZoom] = useState(1),
    [show, setShow] = useState('all')
  const sorted = useMemo(() => ordered(events), [events]),
    spans = useMemo(() => spansOf(events), [events])
  const timelineRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (selected !== undefined)
      timelineRef.current
        ?.querySelector(`[data-start-id="${selected}"], [data-end-id="${selected}"]`)
        ?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [selected])
  if (!events.length)
    return <Empty title={en.noRetainedTimeline}>{en.theCallExistsButHasNoStoredReplay}</Empty>
  const min = time(sorted[0]),
    max = time(sorted.at(-1)!),
    range = Math.max(1, max - min)
  const spanEvents = new Set(spans.flatMap((s) => [s.start.id, ...(s.end ? [s.end.id] : [])]))
  const markers = sorted.filter((e) => !spanEvents.has(e.id))
  const rows = [
    ...spans
      .filter((s) => show === 'all' || s.start.kind === show)
      .map((s) => ({ id: s.id, event: s.start, end: s.end, depth: Math.min(s.depth, 5) })),
    ...(show === 'all' || show === 'events'
      ? markers.map((e) => ({ id: `event-${e.id}`, event: e, end: undefined, depth: 0 }))
      : []),
  ].sort((a, b) => time(a.event) - time(b.event) || a.event.id - b.event.id)
  const step = (delta: number) => {
    setPlaying(false)
    const target =
      delta > 0 ? sorted.find((e) => time(e) > at) : [...sorted].reverse().find((e) => time(e) < at)
    if (target) {
      onTime(time(target))
      onSelect(target)
    }
  }
  return (
    <div className="ac-timeline" data-testid="execution-timeline" ref={timelineRef}>
      <div className="ac-panel-head">
        <div className="ac-inline">
          <ListTree size={15} />
          <h3>Execution Timeline</h3>
          <span className="ac-tag">READ-ONLY REPLAY</span>
        </div>
        <div className="ac-actions">
          <select
            aria-label={en.filterTimeline}
            value={show}
            onChange={(e) => setShow(e.target.value)}
          >
            <option value="all">{en.allActivity}</option>
            <option value="agent">{en.agents}</option>
            <option value="tool">{en.tools}</option>
            <option value="events">{en.events2}</option>
          </select>
          <Button
            aria-label={en.zoomOutTimeline}
            disabled={zoom === 1}
            onClick={() => setZoom((z) => Math.max(1, z / 2))}
          >
            <ZoomOut size={13} />
          </Button>
          <Button
            aria-label={en.zoomInTimeline}
            disabled={zoom >= 16}
            onClick={() => setZoom((z) => Math.min(16, z * 2))}
          >
            <ZoomIn size={13} />
          </Button>
        </div>
      </div>
      <div className="ac-replay">
        <Button aria-label={en.previousEvent} onClick={() => step(-1)}>
          <SkipBack size={14} />
        </Button>
        <Button
          primary
          aria-label={playing ? en.pauseReplay : en.playHistory}
          onClick={() => {
            if (at >= max) onTime(min)
            setPlaying(!playing)
          }}
        >
          {playing ? <Pause size={14} /> : <Play size={14} />}
        </Button>
        <Button aria-label={en.nextEvent} onClick={() => step(1)}>
          <SkipForward size={14} />
        </Button>
        <span className="ac-replay-time">
          {duration(at - min)} <span>/ {duration(range)}</span>
        </span>
        <input
          type="range"
          step="any"
          aria-label={en.replayPosition}
          min={min}
          max={max === min ? min + 1 : max}
          value={at}
          onChange={(e) => {
            setPlaying(false)
            onTime(Number(e.target.value))
          }}
        />
        <select
          aria-label={en.replaySpeed}
          value={speed}
          onChange={(e) => setSpeed(Number(e.target.value))}
        >
          {[0.5, 1, 2, 4].map((s) => (
            <option key={s} value={s}>
              {s}×
            </option>
          ))}
        </select>
        <span className="ac-muted">
          <Timer size={13} />

          {en.recordedTime}
        </span>
      </div>
      <div className="ac-waterfall-scroll">
        <div className="ac-waterfall" style={{ width: `${zoom * 100}%` }}>
          <div className="ac-waterfall-ruler">
            <div>SPAN / EVENT</div>
            <div>
              {[0, 0.25, 0.5, 0.75, 1].map((v) => (
                <span style={{ left: `${v * 100}%` }} key={v}>
                  {duration(range * v)}
                </span>
              ))}
            </div>
          </div>
          {rows.map((row) => {
            const event = row.event,
              start = time(event),
              end = row.end ? time(row.end) : start
            const phase =
              start > at
                ? 'future'
                : row.end && time(row.end) <= at
                  ? row.end.phase
                  : row.end
                    ? 'started'
                    : event.phase === 'started'
                      ? 'open'
                      : event.phase
            return (
              <button
                key={row.id}
                data-start-id={event.id}
                data-end-id={row.end?.id}
                className={`ac-waterfall-row ${selected !== undefined && (selected === event.id || selected === row.end?.id) ? 'selected' : ''} ${start > at ? 'future' : ''}`}
                onClick={() => {
                  setPlaying(false)
                  onTime(start)
                  onSelect(event)
                }}
                title={`${event.tool ?? event.agent ?? event.node ?? event.kind} · ${phase}`}
              >
                <div style={{ paddingLeft: 12 + row.depth * 10 }}>
                  <span
                    className={`ac-span-dot ${event.kind === 'tool' ? 'tool' : event.kind === 'agent' ? 'agent' : 'event'}`}
                  />
                  <span>{eventLabel(event)}</span>
                  <small>{event.kind}</small>
                </div>
                <div className="ac-waterfall-track">
                  <span
                    className={`ac-waterfall-bar ${phase} ${event.kind === 'tool' ? 'tool' : ''}`}
                    style={{
                      left: `${((start - min) / range) * 100}%`,
                      width: `${Math.max(0.25, ((end - start) / range) * 100)}%`,
                    }}
                  />
                  <small style={{ left: `${Math.min(92, ((end - min) / range) * 100 + 0.8)}%` }}>
                    {row.end
                      ? duration(row.end.elapsed_ms)
                      : event.phase === 'started'
                        ? 'abierto'
                        : '◆'}
                  </small>
                </div>
              </button>
            )
          })}
          <div
            className="ac-playhead"
            style={{ left: `calc(250px + (100% - 250px) * ${Math.min(1, (at - min) / range)})` }}
          />
        </div>
      </div>
    </div>
  )
}
