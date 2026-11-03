import { en } from '../i18n/en'
import { useState } from 'react'
import { Bot, X, Wrench, Copy } from 'lucide-react'
import type { Observation } from './types'
import { display, eventLabel, spansOf, duration, dateTime, time } from './replay'
import { Button, Empty, KeyValue, Segments, StateBadge } from './ui'
export function Inspector({
  events,
  selected,
  at,
  onSelect,
  onClose,
}: {
  events: Observation[]
  selected: Observation
  at: number
  onSelect: (e: Observation) => void
  onClose: () => void
}) {
  const [tab, setTab] = useState('overview')
  const [copyState, setCopyState] = useState<string>(en.copyEventId)
  const spans = spansOf(events)
  const invocations = spans.filter(
    (s) =>
      s.start.kind === selected.kind &&
      s.start.graph_version === selected.graph_version &&
      s.start.agent === selected.agent &&
      (selected.node ? s.start.node === selected.node : s.start.agent === selected.agent) &&
      (selected.tool ? s.start.tool === selected.tool : true),
  )
  const span = spans.find((s) => s.id === selected.span_id && s.start.kind === selected.kind)
  const end = span?.end && time(span.end) <= at ? span.end : undefined
  const start = span?.start ?? selected
  const visiblePhase = span ? (end?.phase ?? 'started') : selected.phase
  const children = spans.filter(
    (s) =>
      s.start.kind === 'tool' &&
      time(s.start) <= at &&
      (s.start.parent_span_id === start.span_id ||
        (s.start.agent_run_id && s.start.agent_run_id === start.agent_run_id) ||
        (start.kind === 'graph.node' &&
          s.start.node === start.node &&
          s.start.graph_version === start.graph_version &&
          time(s.start) >= time(start) &&
          (!span?.end || time(s.start) <= time(span.end)))),
  )
  const title = selected.tool ?? selected.agent ?? selected.node ?? selected.kind
  return (
    <aside className="ac-inspector" data-testid="agent-inspector">
      <div className="ac-panel-head">
        <div className="ac-inline">
          <span className="ac-inspector-icon">
            {selected.tool ? <Wrench size={18} /> : <Bot size={18} />}
          </span>
          <div>
            <small className="ac-eyebrow">INVOCATION INSPECTOR</small>
            <h3>{eventLabel(selected)}</h3>
          </div>
        </div>
        <Button aria-label={en.closeInspector} onClick={onClose}>
          <X size={14} />
        </Button>
      </div>
      <div className="ac-inspector-body">
        <StateBadge status={visiblePhase} />
        {invocations.length > 1 && (
          <label className="ac-field">
            <span>{en.invocation2}</span>
            <select
              aria-label={en.selectInvocation}
              value={start.span_id ?? ''}
              onChange={(e) => {
                const invocation = invocations.find((s) => s.id === e.target.value)
                if (invocation) onSelect(invocation.start)
              }}
            >
              {invocations.map((s, index) => (
                <option key={s.id} value={s.id}>
                  #{index + 1} · {dateTime(s.start.occurred_at)}
                </option>
              ))}
            </select>
          </label>
        )}
        <Segments
          value={tab}
          onChange={setTab}
          items={[
            { value: 'overview', label: 'Overview' },
            { value: 'io', label: 'I/O' },
            { value: 'tools', label: 'Tools' },
            { value: 'timing', label: 'Timing' },
            { value: 'errors', label: 'Errors' },
          ]}
        />
        {tab === 'overview' && (
          <KeyValue
            items={[
              [en.type, start.kind],
              [en.agent, start.agent ? display(start.agent) : en.nA],
              [en.node, start.node ?? en.nA],
              [en.configuredModel, start.model ?? en.nA],
              [en.reportedModel, end?.reported_model ?? en.nA],
              ['Prompt', start.prompt_version ?? en.nA],
              ['Prompt SHA-256', <code>{start.prompt_sha256 ?? en.nA}</code>],
              [en.execution, <code>{start.execution_id}</code>],
              ['Span', <code>{start.span_id ?? en.nA}</code>],
              ['Parent span', <code>{start.parent_span_id ?? en.nA}</code>],
              [en.callSession, <code>{start.call_session_id ?? en.nA}</code>],
              [en.langgraphThread, <code>{start.graph_thread_id ?? en.nA}</code>],
              ['Checkpoint', <code>{start.checkpoint_id ?? en.nA}</code>],
              [en.result, end?.data.output?.status ?? end?.data.result ?? en.nA],
              [
                en.usage,
                end?.data.usage ? (
                  <pre>
                    {JSON.stringify(end.data.usage, (_key, value) => value ?? undefined, 2)}
                  </pre>
                ) : (
                  en.nA
                ),
              ],
            ]}
          />
        )}
        {tab === 'io' && (
          <>
            <div className="ac-info">{en.onlyAuthorizedProjectionsAreShownFreeFormInputs}</div>
            <h4>Input</h4>
            <pre>
              {start.data.input
                ? JSON.stringify(start.data.input, (_key, value) => value ?? undefined, 2)
                : en.unavailable}
            </pre>
            <h4>Output</h4>
            <pre>
              {end?.data.output
                ? JSON.stringify(end.data.output, (_key, value) => value ?? undefined, 2)
                : en.unavailableAtThisMoment}
            </pre>
            <h4>{en.eventMetadata}</h4>
            <pre>{JSON.stringify(selected.data, (_key, value) => value ?? undefined, 2)}</pre>
          </>
        )}
        {tab === 'tools' &&
          (children.length ? (
            <div className="ac-tool-list">
              {children.map((s) => (
                <button key={s.id} onClick={() => onSelect(s.start)}>
                  <Wrench size={14} />
                  <span>
                    {s.start.tool}
                    <small>{duration(s.end && time(s.end) <= at ? s.end.elapsed_ms : null)}</small>
                  </span>
                  <StateBadge status={s.end && time(s.end) <= at ? s.end.phase : 'started'} />
                </button>
              ))}
            </div>
          ) : (
            <Empty title={en.noAssociatedTools}>{en.noToolInvocationsAreRecordedForThisSpan}</Empty>
          ))}
        {tab === 'timing' && (
          <KeyValue
            items={[
              [en.start, dateTime(start.occurred_at)],
              [en.end, end ? dateTime(end.occurred_at) : en.noEndRecordedAtThisMoment],
              [en.recordedDuration, duration(end?.elapsed_ms)],
              [en.executionOffset, duration(start.execution_offset_ms)],
              [en.callOffset, duration(start.call_offset_ms)],
              [en.received, dateTime(start.received_at)],
            ]}
          />
        )}
        {tab === 'errors' &&
          (end?.data.error_type || selected.data.error_type ? (
            <KeyValue
              items={[
                [en.type, end?.data.error_type ?? selected.data.error_type],
                [en.code, end?.data.error_code ?? selected.data.error_code ?? en.nA],
              ]}
            />
          ) : (
            <Empty title={en.noRecordedErrors}>{en.freeFormExceptionTextIsNotRetained}</Empty>
          ))}
        <Button
          className="ac-copy"
          onClick={() => {
            void navigator.clipboard
              .writeText(start.event_id)
              .then(() => setCopyState(en.idCopied))
              .catch(() => setCopyState(en.selectTheIdToCopyIt))
          }}
        >
          <Copy size={13} />
          {copyState}
        </Button>
      </div>
    </aside>
  )
}
