import { en } from '../../i18n/en'
import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CheckCircle2,
  Server,
  ShieldCheck,
  Map,
  FlaskConical,
  Mic,
  Phone,
  RefreshCw,
} from 'lucide-react'
import { api, get, errorText } from '../../services/api'
import { useUI } from '../../app/context'
import { editor } from '../../services/editor'
import { Modal } from '../ui/overlay'
import { Button } from '../ui/button'
import { MAP_STYLE } from '../map/config'
export function Settings({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { notice, connection } = useUI()
  const q = useQueryClient()
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const settings = useQuery({
    queryKey: ['settings'],
    queryFn: () => window.desktop!.settings(),
    enabled: open && !!window.desktop,
  })
  const caps = useQuery({ queryKey: ['capabilities'], queryFn: api.capabilities, enabled: open })
  const health = useQuery({
    queryKey: ['health'],
    queryFn: () => get<{ status: string; mode: string }>('/api/health'),
    enabled: open,
    retry: false,
  })
  return (
    <Modal
      open={open}
      onOpenChange={(v) => !v && onClose()}
      title={en.settings}
      description={en.localConnectionMapAndAvailableCapabilities}
    >
      <div className="settings-content">
        <section>
          <h3>
            <Server size={17} />

            {en.localBackend}
          </h3>
          <label>
            {en.fastapiUrl}
            <div className="backend-url">
              <input
                aria-label={en.backendUrl}
                value={url || settings.data?.backendUrl || 'http://127.0.0.1:8001'}
                onChange={(e) => setUrl(e.target.value)}
              />
              <Button
                disabled={busy}
                onClick={async () => {
                  setBusy(true)
                  try {
                    await editor.flush()
                    await window.desktop!.setBackend(
                      url || settings.data?.backendUrl || 'http://127.0.0.1:8001',
                    )
                    await q.invalidateQueries()
                    notice(en.connectionUpdatedTheWorkspaceWillReload)
                    window.location.reload()
                  } catch (e) {
                    notice(errorText(e))
                  } finally {
                    setBusy(false)
                  }
                }}
              >
                {en.connect}
              </Button>
            </div>
          </label>
          <div className="settings-status">
            <span className={`status-dot ${health.data?.status === 'ok' ? 'green' : 'amber'}`} />
            {health.data?.status === 'ok' ? en.fastapiAvailable : en.backendOffline}
            <Button
              icon
              variant="ghost"
              aria-label={en.checkConnection}
              onClick={() => void health.refetch()}
            >
              <RefreshCw size={14} />
            </Button>
          </div>
          <p className="muted">
            {en.events3}{' '}
            {connection === 'connected'
              ? en.connected
              : connection === 'connecting'
                ? en.connecting
                : en.reconnecting}{' '}
            {en.localToken} {settings.data?.tokenConfigured ? en.configured : en.notConfigured}
          </p>
          <p className="settings-note">
            <ShieldCheck size={15} />

            {en.theMainProcessReadsLocalApiTokenFrom}
          </p>
        </section>
        <section>
          <h3>
            <Map size={17} />

            {en.map}
          </h3>
          <strong>OpenFreeMap · OpenStreetMap</strong>
          <p className="muted">{en.interactiveVectorMapAndExtrudedBuildingsBasedOn}</p>
          <code className="settings-code">{MAP_STYLE}</code>
          <p className="muted">{en.internetRequiredNoPrivateKeyNeededConfigureThe}</p>
          <Button
            variant="ghost"
            onClick={() =>
              void window.desktop?.openExternal('https://openfreemap.org/quick_start/')
            }
          >
            {en.providerAndAttribution}
          </Button>
        </section>
        <section>
          <h3>
            <FlaskConical size={17} />

            {en.aiExecution}
          </h3>
          <div className="capability-row">
            <span>{en.classicSimulation}</span>
            <span className="success">{en.available}</span>
          </div>
          <div className="capability-row">
            <span>LangGraph</span>
            <span>{caps.data?.ai_simulation ? en.available : en.offline}</span>
          </div>
          <div className="capability-row">
            <span>{en.reasoningModel}</span>
            <code>{caps.data?.reasoning_model ?? '—'}</code>
          </div>
          <div className="capability-row">
            <span>{en.extraction}</span>
            <span>{caps.data?.extraction_mode ?? '—'}</span>
          </div>
          <div className="capability-row">
            <span>{en.openaiCredentials}</span>
            <span>{caps.data?.openai_credentials_configured ? en.configured : en.pending}</span>
          </div>
        </section>
        <section>
          <h3>
            <Mic size={17} />

            {en.voicePhoneCalls}
          </h3>
          <div className="capability-row">
            <span>{en.voiceSandbox}</span>
            <span>{caps.data?.voice_sandbox_enabled ? en.enabledInBackend : en.disabled}</span>
          </div>
          <div className="capability-row">
            <span>{en.voiceModel}</span>
            <code>{caps.data?.voice_model ?? '—'}</code>
          </div>
          <div className="capability-row">
            <span>{en.realPhoneCalls}</span>
            <span>{caps.data?.real_telephony_enabled ? en.enabledInBackend : en.disabled}</span>
          </div>
          <p className="settings-note">
            <Phone size={15} />

            {en.phoneCallsRequireLimitsAndExplicitAuthorizationEach}
          </p>
          <p className="muted">{en.testTheSandboxMicrophoneThroughScriptsVoiceSandbox}</p>
        </section>
      </div>
    </Modal>
  )
}
