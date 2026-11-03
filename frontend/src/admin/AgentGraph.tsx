import { en } from '../i18n/en'
import { useEffect, useMemo, useState } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  MarkerType,
  BaseEdge,
  getSmoothStepPath,
  useReactFlow,
  useStore,
  type NodeProps,
  type Node,
  type Edge,
  type EdgeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Bot, Wrench, Circle, Check, LoaderCircle, AlertTriangle, Workflow } from 'lucide-react'
import type { Observation, GraphVersion } from './types'
import { display, nodeState, time, terminalPhases, type NodeState } from './replay'
import { activeInvocations, contactActivities, pathActive } from './graph-replay'
import { Empty } from './ui'
type AgentNode = Node<
  {
    label: string
    state: NodeState
    invocations: number
    tools: number
    boundary: boolean
    stage?: string
    activities?: { label: string; state: string; event: Observation }[]
    inspect?: (event: Observation) => void
  },
  'agent'
>
const states: Record<NodeState, string> = {
  'not-run': en.noRecordedInvocation,
  pending: en.transitionSelected,
  running: en.running,
  completed: en.completed,
  failed: 'Error',
  interrupted: en.interrupted,
  cancelled: en.cancelled,
}
function AgentNodeView({ data, selected }: NodeProps<AgentNode>) {
  return (
    <div
      className={`ac-graph-node ${data.state} ${selected ? 'selected' : ''} ${data.boundary ? 'boundary' : ''} ${data.activities ? 'contact' : ''}`}
    >
      <Handle id="in-top" type="target" position={Position.Top} />
      <Handle id="in-left" type="target" position={Position.Left} />
      <Handle id="in-right" type="target" position={Position.Right} />
      <Handle id="in-bottom" type="target" position={Position.Bottom} />
      <Handle id="in-return" type="target" position={Position.Bottom} style={{ left: '85%' }} />
      <span className="ac-agent-icon">
        {data.boundary ? <Circle size={14} /> : <Bot size={20} />}
      </span>
      <div>
        <strong>{data.label}</strong>
        {data.stage && <span className="ac-node-stage">{data.stage}</span>}
        <small>{states[data.state]}</small>
      </div>
      {!data.boundary && (
        <div className="ac-node-footer">
          <span>{en.invocationCount(data.invocations)}</span>
          <span>
            <Wrench size={10} />
            {data.tools}
          </span>
        </div>
      )}
      <span className="ac-node-status">
        {data.state === 'running' ? (
          <LoaderCircle className="ac-spin" size={13} />
        ) : data.state === 'completed' ? (
          <Check size={13} />
        ) : data.state === 'failed' ? (
          <AlertTriangle size={13} />
        ) : null}
      </span>
      {data.activities && (
        <div className="ac-contact-activities">
          <span>{en.specialistsObservedDuringContact}</span>
          {data.activities.length ? (
            data.activities.map((a) => (
              <button
                key={a.event.id}
                data-contact-agent={a.event.agent}
                onClick={(e) => {
                  e.stopPropagation()
                  data.inspect?.(a.event)
                }}
              >
                <Bot size={12} />
                <strong>{a.label}</strong>
                <small>{states[a.state as NodeState] ?? a.state}</small>
              </button>
            ))
          ) : (
            <small>{en.noInvocationsRecordedAtThisMoment}</small>
          )}
        </div>
      )}
      <Handle id="out-bottom" type="source" position={Position.Bottom} />
      <Handle id="out-right" type="source" position={Position.Right} />
      <Handle id="out-left" type="source" position={Position.Left} />
      <Handle id="out-top" type="source" position={Position.Top} />
      <Handle id="out-finish" type="source" position={Position.Bottom} style={{ left: '20%' }} />
    </div>
  )
}
const nodeTypes = { agent: AgentNodeView }
function RecordedEdge(props: EdgeProps) {
  const [defaultPath, labelX, labelY] = getSmoothStepPath(props)
  const laneX = props.sourceX - 40,
    laneY = props.targetY + 40
  // Dedicated return corridor between columns, above the closing nodes.
  const path = props.data?.returnLane
    ? `M ${props.sourceX} ${props.sourceY} L ${laneX + 8} ${props.sourceY} Q ${laneX} ${props.sourceY} ${laneX} ${props.sourceY - 8} L ${laneX} ${laneY + 8} Q ${laneX} ${laneY} ${laneX - 8} ${laneY} L ${props.targetX + 8} ${laneY} Q ${props.targetX} ${laneY} ${props.targetX} ${laneY - 8} L ${props.targetX} ${props.targetY}`
    : defaultPath
  const active = props.data?.active === true
  return (
    <g
      data-active-path={active ? 'true' : undefined}
      data-path-source={props.source}
      data-path-target={props.target}
    >
      <BaseEdge
        path={path}
        markerEnd={props.markerEnd}
        style={props.style}
        label={props.label}
        labelX={labelX}
        labelY={labelY}
        labelStyle={props.labelStyle}
        labelBgStyle={props.labelBgStyle}
      />
      {active && (
        <circle className="ac-travel-dot" r="4" fill="#b8d3ff" stroke="#38598d" strokeWidth="2">
          <animateMotion dur="1.8s" repeatCount="indefinite" path={path} />
        </circle>
      )}
    </g>
  )
}
const edgeTypes = { recorded: RecordedEdge }
function FitGraph({ count }: { count: number }) {
  const width = useStore((state) => state.width),
    height = useStore((state) => state.height)
  const { fitView } = useReactFlow()
  useEffect(() => {
    const timer = setTimeout(
      () => void fitView({ padding: 0.16, maxZoom: 1, minZoom: 0.2, duration: 0 }),
      80,
    )
    return () => clearTimeout(timer)
  }, [width, height, count, fitView])
  return null
}
const agentPositions: Record<string, [number, number]> = {
  planning: [0, 30],
  supervisor: [280, 30],
  research: [580, 30],
  voice_session: [880, 30],
  negotiation: [910, 270],
  verification: [580, 270],
  memory: [280, 270],
  evaluation: [0, 270],
  human_approval: [280, 470],
  pause: [580, 470],
}
const knownPositions: Record<string, [number, number]> = {
  __start__: [0, 0],
  load: [0, 85],
  planning: [250, 85],
  supervisor: [500, 85],
  research: [0, 230],
  prepare_call: [250, 230],
  voice_session: [500, 230],
  negotiation: [500, 375],
  verification: [250, 375],
  human_approval: [750, 230],
  pause: [750, 85],
  memory: [0, 375],
  evaluation: [0, 520],
  __end__: [250, 540],
  route: [250, 85],
  negotiate: [0, 230],
  verify: [250, 230],
  requirements: [500, 230],
  decline: [0, 375],
  clarify: [500, 375],
}
export function AgentGraph({
  graph,
  events,
  at,
  selected,
  onSelect,
  invocationHistory,
}: {
  graph?: GraphVersion
  events: Observation[]
  at: number
  selected?: string
  onSelect: (node: string, event?: Observation) => void
  invocationHistory?: Observation[]
}) {
  const [technical, setTechnical] = useState(false)
  const { nodes, edges } = useMemo(() => {
    if (!graph) return { nodes: [], edges: [] }
    const definition = graph.definition as {
      nodes?: { id: string }[]
      edges?: { source: string; target: string; conditional?: boolean; label?: string }[]
    }
    const compact = graph.name === 'booking' && !technical
    const visible = compact
      ? (definition.nodes ?? []).filter(
          (n) =>
            n.id in agentPositions &&
            (!['human_approval', 'pause'].includes(n.id) ||
              events.some(
                (e) => e.node === n.id && e.graph_version === graph.id && e.kind === 'graph.node',
              )),
        )
      : (definition.nodes ?? [])
    const ids = visible.length ? visible : (definition.nodes ?? [])
    const activities = contactActivities(events, at, graph.id)
    const activityGroups = ['negotiation', 'verification'].flatMap((agent) => {
      const matching = activities.filter((s) => s.start.agent === agent)
      const current =
        matching
          .slice()
          .reverse()
          .find((s) => !s.end || time(s.end) > at) ?? matching.at(-1)
      return current
        ? [
            {
              label: `${display(agent)} · ${matching.length}`,
              event: current.start,
              state:
                current.end && time(current.end) <= at && terminalPhases.has(current.end.phase)
                  ? current.end.phase
                  : 'running',
            },
          ]
        : []
    })
    const nodes: AgentNode[] = ids.map((node, index) => {
      const invocations = (invocationHistory ?? events).filter(
        (e) =>
          e.node === node.id &&
          e.graph_version === graph.id &&
          e.kind === 'graph.node' &&
          e.phase === 'started' &&
          time(e) <= at,
      ).length
      const tools = events.filter(
        (e) =>
          e.node === node.id &&
          e.graph_version === graph.id &&
          e.kind === 'tool' &&
          e.phase === 'started' &&
          time(e) <= at,
      ).length
      const [x, y] = (compact ? agentPositions[node.id] : knownPositions[node.id]) ?? [
        (index % 3) * 270,
        Math.floor(index / 3) * 140 + 200,
      ]
      return {
        id: node.id,
        type: 'agent',
        position: { x, y },
        selected: selected === node.id,
        data: {
          label:
            graph.name === 'booking' && node.id === 'negotiation'
              ? en.offerReview
              : graph.name === 'booking' && node.id === 'verification'
                ? en.confirmationReview
                : display(node.id),
          stage:
            graph.name === 'booking' && ['negotiation', 'verification'].includes(node.id)
              ? en.afterContact
              : undefined,
          state: nodeState(events, node.id, at, graph.id),
          invocations,
          tools,
          boundary: node.id.startsWith('__'),
          activities: compact && node.id === 'voice_session' ? activityGroups : undefined,
          inspect: (event) => onSelect(node.id, event),
        },
      }
    })
    // Avoid layout collisions for graph versions with previously unknown nodes.
    const occupied = new Set<string>()
    for (const node of nodes) {
      let key = `${node.position.x}:${node.position.y}`
      while (occupied.has(key)) {
        node.position.y += 145
        key = `${node.position.x}:${node.position.y}`
      }
      occupied.add(key)
    }
    const visibleIds = new Set(ids.map((n) => n.id))
    const paths: {
      source: string
      target: string
      conditional?: boolean
      label?: string
      via: { source: string; target: string }[]
    }[] = []
    // Collapse only defined paths through hidden technical nodes; never infer execution.
    for (const source of ids) {
      const visit = (
        node: string,
        via: (typeof paths)[number]['via'],
        seen: Set<string>,
        conditional = false,
        label?: string,
      ) => {
        for (const edge of (definition.edges ?? []).filter((e) => e.source === node)) {
          const path = [...via, { source: edge.source, target: edge.target }],
            branch = conditional || !!edge.conditional
          if (visibleIds.has(edge.target))
            paths.push({
              source: source.id,
              target: edge.target,
              conditional: branch,
              label: label ?? edge.label,
              via: path,
            })
          else if (!seen.has(edge.target))
            visit(edge.target, path, new Set([...seen, edge.target]), branch, label ?? edge.label)
        }
      }
      visit(source.id, [], new Set([source.id]))
    }
    const edges: Edge[] = paths.map((edge, index) => {
      const used = edge.via.every((link) =>
        events.some(
          (e) =>
            e.kind === 'graph.transition' &&
            e.graph_version === graph.id &&
            e.data.from_node === link.source &&
            e.data.to_node === link.target &&
            time(e) <= at,
        ),
      )
      const active = pathActive(events, at, graph.id, edge.via)
      const source = nodes.find((n) => n.id === edge.source)!,
        target = nodes.find((n) => n.id === edge.target)!
      const horizontal =
        Math.abs(target.position.x - source.position.x) >
        Math.abs(target.position.y - source.position.y)
      let sourceHandle = horizontal
        ? target.position.x > source.position.x
          ? 'out-right'
          : 'out-left'
        : target.position.y > source.position.y
          ? 'out-bottom'
          : 'out-top'
      let targetHandle = horizontal
        ? target.position.x > source.position.x
          ? 'in-left'
          : 'in-right'
        : target.position.y > source.position.y
          ? 'in-top'
          : 'in-bottom'
      if (compact && edge.source === 'verification' && edge.target === 'supervisor') {
        sourceHandle = 'out-left'
        targetHandle = 'in-return'
      }
      if (compact && edge.source === 'supervisor' && edge.target === 'memory') {
        sourceHandle = 'out-finish'
        targetHandle = 'in-top'
      }
      const branch =
        (
          {
            call: en.continue,
            finish: en.completed,
            approval: en.approval,
            pause: en.paused,
          } as Record<string, string>
        )[edge.label ?? ''] ??
        edge.label ??
        en.condition
      return {
        id: `edge-${index}`,
        source: edge.source,
        target: edge.target,
        sourceHandle,
        targetHandle,
        type: 'recorded',
        data: {
          active,
          returnLane: compact && edge.source === 'verification' && edge.target === 'supervisor',
        },
        animated: false,
        className: used ? 'ac-edge-used' : '',
        style: {
          stroke: used ? '#7099ff' : '#343e50',
          strokeWidth: active ? 3 : used ? 2 : 1,
        },
        markerEnd: { type: MarkerType.ArrowClosed, color: used ? '#7099ff' : '#343e50' },
        label: edge.conditional ? en.if(branch) : undefined,
        labelStyle: { fontSize: 10, fill: '#e7bd79' },
        labelBgStyle: { fill: '#111720' },
      }
    })
    return { nodes, edges }
  }, [graph, events, at, selected, technical, onSelect, invocationHistory])
  if (!graph)
    return (
      <Empty title={en.historicalGraphUnavailable}>
        {en.thisExecutionHasNoStoredGraphDefinitionThe}
      </Empty>
    )
  return (
    <div className="ac-graph" data-testid="agent-graph">
      <div className="ac-invocation-context" data-testid="invocation-context">
        {activeInvocations(events, at, graph!.id, invocationHistory).map(
          ({ span, ordinal, entry }) => (
            <span key={span.id}>
              <strong>
                {display(span.start.node!)} {en.invocation} {ordinal}
              </strong>
              {entry
                ? en.receivesControlFromEvent(display(entry.data.from_node!), entry.id)
                : en.originNotRecordedNoIncomingTransitionInferred}
            </span>
          ),
        )}
        {!activeInvocations(events, at, graph!.id).length && (
          <span>{en.noActiveNodesAtThisReplayPosition}</span>
        )}
      </div>
      <ReactFlow
        key={graph.id}
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodeClick={(_, node) => onSelect(node.id)}
        nodesDraggable={false}
        nodesConnectable={false}
        fitView
        fitViewOptions={{ padding: 0.2, minZoom: 0.2, maxZoom: 0.85 }}
        minZoom={0.15}
        maxZoom={1.8}
        colorMode="dark"
      >
        <Background color="#293141" gap={22} size={1} />
        <Controls showInteractive={false} />
        <FitGraph count={nodes.length} />
      </ReactFlow>
      {graph.name === 'booking' && (
        <button
          className="ac-graph-mode"
          aria-pressed={technical}
          onClick={() => setTechnical((v) => !v)}
        >
          {technical ? en.showAgents : en.showTechnicalNodes}
        </button>
      )}
      <div className="ac-graph-caption">
        <Workflow size={12} />
        <span>
          {en.recordedDefinition} {graph.id.slice(0, 10)}
        </span>
      </div>
    </div>
  )
}
