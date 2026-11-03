import { en } from '../i18n/en'
import { useEffect, useState } from 'react'
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query'
import { motion, MotionConfig } from 'motion/react'
import {
  AudioLines,
  Phone,
  ChartNoAxesCombined,
  FlaskConical,
  Settings2,
  ChevronDown,
  Minus,
  Square,
  X,
  ShieldCheck,
  Command,
  CircleHelp,
  PanelLeftClose,
  UtensilsCrossed,
  ArrowUpRight,
} from 'lucide-react'
import { Calls } from './Calls'
import { CallDetail } from './CallDetail'
import { Analytics } from './Analytics'
import { Playground } from './Playground'
import { Settings } from './Settings'
import './admin.css'
import type { AdminConnection } from './types'
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 10000, refetchOnWindowFocus: false } },
})
const tabs = [
  { id: 'calls', label: 'Calls', icon: Phone },
  { id: 'analytics', label: 'Analytics', icon: ChartNoAxesCombined },
  { id: 'playground', label: 'Playground', icon: FlaskConical },
  { id: 'settings', label: 'Settings', icon: Settings2 },
]
function Workspace() {
  const [tab, setTab] = useState('calls'),
    [detail, setDetail] = useState<string | null>(null),
    [connection, setConnection] = useState<AdminConnection>('connecting'),
    [help, setHelp] = useState(false)
  const client = useQueryClient()
  useEffect(() => {
    document.title = 'AI Control Center'
    let timer: ReturnType<typeof setTimeout> | undefined
    const off = window.admin?.onEvent(() => {
      if (!timer)
        timer = setTimeout(() => {
          timer = undefined
          void client.invalidateQueries({ queryKey: ['admin', 'calls'] })
          void client.invalidateQueries({ queryKey: ['admin', 'bookings'] })
          void client.invalidateQueries({ queryKey: ['admin', 'analytics'] })
        }, 500)
    })
    const offConnection = window.admin?.onConnection((state) => {
      setConnection(state)
      if (state === 'connected') void client.invalidateQueries({ queryKey: ['admin', 'calls'] })
    })
    window.admin?.connect()
    if (!window.admin) setConnection('disconnected')
    return () => {
      off?.()
      offConnection?.()
      clearTimeout(timer)
    }
  }, [client])
  return (
    <div className="admin-app">
      <div className="ac-titlebar">
        <span>
          <span className="ac-title-dot" />
          BARIA <span className="ac-title-separator">/</span> AI Control Center
        </span>
        <div>
          <button
            aria-label={en.minimizeAdministrator}
            onClick={() => window.admin?.window('minimize')}
          >
            <Minus size={13} />
          </button>
          <button
            aria-label={en.maximizeAdministrator}
            onClick={() => window.admin?.window('maximize')}
          >
            <Square size={11} />
          </button>
          <button aria-label={en.closeAdministrator} onClick={() => window.admin?.window('close')}>
            <X size={14} />
          </button>
        </div>
      </div>
      <aside className="ac-sidebar">
        <div className="ac-brand">
          <span>
            <AudioLines size={23} />
          </span>
          <div>
            AI Control Center<small>AGENT OBSERVABILITY</small>
          </div>
        </div>
        <div className="ac-workspace-switch">
          <span className="ac-workspace-avatar">B</span>
          <div>
            BARIA Workspace<small>Local environment</small>
          </div>
          <ChevronDown size={13} />
        </div>
        <div className="ac-nav-label">WORKSPACE</div>
        <nav>
          {tabs.map((item) => (
            <button
              key={item.id}
              aria-current={tab === item.id ? 'page' : undefined}
              onClick={() => {
                setTab(item.id)
                setDetail(null)
              }}
            >
              {tab === item.id && (
                <motion.span
                  className="ac-nav-active"
                  layoutId="admin-navigation"
                  transition={{ duration: 0.17 }}
                />
              )}
              <item.icon size={17} />
              <span>{item.label}</span>
              {item.id === 'calls' && <kbd>01</kbd>}
            </button>
          ))}
        </nav>
        <div className="ac-sidebar-bottom">
          <button className="ac-open-booker" onClick={() => window.admin?.openBooker()}>
            <UtensilsCrossed size={17} />
            <span>{en.bookingApp}</span>
            <ArrowUpRight size={15} />
          </button>
          <div className="ac-capture-card">
            <ShieldCheck size={17} />
            <strong>Privacy by design</strong>
            <p>
              {en.correlatedMetadata}
              <br />

              {en.noAudioOrTranscripts}
            </p>
            <span>
              <i className="ac-dot" />
              Instrumentation enabled
            </span>
          </div>
          <button className="ac-help" onClick={() => setHelp((v) => !v)}>
            <CircleHelp size={16} />

            {en.controlCenterGuide}
            <ChevronDown size={12} />
          </button>
          {help && <div className="ac-help-text">{en.callsShowsTheBackendHistorySelectACall}</div>}
          <div className="ac-profile">
            <span>JB</span>
            <div>
              Local administrator<small>{en.inspectionAccess}</small>
            </div>
            <ShieldCheck size={15} />
          </div>
        </div>
      </aside>
      <div className="ac-main">
        <header className="ac-topbar">
          <div>
            <span>Workspace</span>
            <span>/</span>
            <strong>{detail ? 'Call detail' : tabs.find((t) => t.id === tab)?.label}</strong>
          </div>
          <div>
            <span className={`ac-connection ${connection === 'connected' ? 'connected' : ''}`}>
              <i />
              {connection === 'connected'
                ? 'Live connection'
                : connection === 'connecting'
                  ? 'Connecting…'
                  : connection === 'unauthorized'
                    ? en.accessNotConfigured
                    : 'Disconnected'}
            </span>
            <span className="ac-environment">LOCAL</span>
            <span className="ac-avatar">JB</span>
          </div>
        </header>
        <main className={detail ? 'ac-content detail' : 'ac-content'}>
          {detail ? (
            <CallDetail key={detail} id={detail} back={() => setDetail(null)} />
          ) : tab === 'calls' ? (
            <Calls open={setDetail} />
          ) : tab === 'analytics' ? (
            <Analytics />
          ) : tab === 'playground' ? (
            <Playground open={setDetail} />
          ) : (
            <Settings />
          )}
        </main>
      </div>
    </div>
  )
}
export function AdminApp() {
  return (
    <QueryClientProvider client={queryClient}>
      <MotionConfig reducedMotion="user">
        <Workspace />
      </MotionConfig>
    </QueryClientProvider>
  )
}
