import { en } from '../i18n/en'
import { useQuery } from '@tanstack/react-query'
import {
  Cpu,
  FileCode2,
  Radio,
  ShieldCheck,
  Database,
  Server,
  LockKeyhole,
  CheckCircle2,
} from 'lucide-react'
import { adminApi } from './api'
import { Badge, ErrorState, KeyValue, Loading, PanelHead } from './ui'
export function Settings() {
  const query = useQuery({
    queryKey: ['admin', 'settings'],
    queryFn: adminApi.settings,
    refetchInterval: 15000,
  })
  const connection = useQuery({
    queryKey: ['admin', 'connection'],
    queryFn: () => window.admin?.connection(),
  })
  const s = query.data
  return (
    <section className="ac-page" data-testid="admin-settings">
      <div className="ac-page-title">
        <div>
          <div className="ac-eyebrow">WORKSPACE / CONFIGURATION</div>
          <h1>Settings</h1>
          <p>{en.effectiveBackendConfigurationAndObservabilityPolicies}</p>
        </div>
        <Badge>
          <LockKeyhole size={11} />

          {en.readOnly}
        </Badge>
      </div>
      {query.isError ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : query.isPending ? (
        <Loading />
      ) : (
        s && (
          <div className="ac-settings-grid">
            <div className="ac-panel">
              <PanelHead title={en.backendConnection} subtitle={en.localExecutionService}>
                <Server size={17} />
              </PanelHead>
              <div className="ac-settings-body">
                <div className="ac-backend-online">
                  <span className="ac-online-icon">
                    <CheckCircle2 size={20} />
                  </span>
                  <div>
                    <strong>{en.backendConnected}</strong>
                    <small>{connection.data?.backendUrl ?? 'Localhost'}</small>
                  </div>
                  <Badge tone="success">Online</Badge>
                </div>
                <KeyValue
                  items={[
                    [en.administrativeApi, en.authenticatedWithASeparateToken],
                    [en.authentication, 'Electron Main → FastAPI'],
                    [en.persistence, en.sqliteSourceOfTruth],
                    [en.changes, en.managedThroughBackendEnv],
                  ]}
                />
              </div>
            </div>
            <div className="ac-panel">
              <PanelHead title={en.models} subtitle={en.configuredAliasesResolvedByTheProvider}>
                <Cpu size={17} />
              </PanelHead>
              <div className="ac-settings-body">
                <KeyValue
                  items={[
                    ['Reasoning', <code>{s.reasoning_model}</code>],
                    ['Voice', <code>{s.voice_model}</code>],
                    [en.extraction, <Badge tone="blue">{s.extraction_mode}</Badge>],
                    [
                      'Playground',
                      s.playground_available
                        ? en.availableDeterministic
                        : en.deterministicExtractionRequired,
                    ],
                  ]}
                />
              </div>
            </div>
            <div className="ac-panel ac-settings-prompts">
              <PanelHead
                title={en.versionedPrompts}
                subtitle={en.eachExecutionRetainsTheVersionAndHashUsed}
              >
                <FileCode2 size={17} />
              </PanelHead>
              <div className="ac-table-scroll">
                <table className="ac-table ac-small-table">
                  <thead>
                    <tr>
                      <th>{en.agent}</th>
                      <th>{en.version}</th>
                      <th>SHA-256</th>
                      <th>{en.access}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(s.prompts).map(([name, p]) => (
                      <tr key={name}>
                        <td>
                          <span className="ac-agent-label">
                            <FileCode2 size={13} />
                            {name}
                          </span>
                        </td>
                        <td>
                          <code>{p.version}</code>
                        </td>
                        <td>
                          <code title={p.sha256}>{p.sha256.slice(0, 24)}…</code>
                        </td>
                        <td>
                          <span className="ac-readonly">
                            <LockKeyhole size={11} />

                            {en.readOnly}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="ac-panel">
              <PanelHead title={en.providers} subtitle={en.effectiveCapabilities}>
                <Radio size={17} />
              </PanelHead>
              <div className="ac-settings-body">
                <KeyValue
                  items={[
                    [en.voiceProvider, s.voice_provider],
                    [en.telephoneProvider, s.telephone_provider],
                    [
                      en.voiceSandbox,
                      <Badge tone={s.voice_enabled ? 'success' : 'neutral'}>
                        {s.voice_enabled ? en.enabled : en.disabled}
                      </Badge>,
                    ],
                    [
                      en.realPhoneCalls,
                      <Badge tone={s.telephony_enabled ? 'warning' : 'neutral'}>
                        {s.telephony_enabled ? en.enabledWithAuthorization : en.disabled}
                      </Badge>,
                    ],
                  ]}
                />
              </div>
            </div>
            <div className="ac-panel">
              <PanelHead
                title={en.observabilityRetention}
                subtitle={en.minimalCorrelatedAndPersistentData}
              >
                <ShieldCheck size={17} />
              </PanelHead>
              <div className="ac-settings-body">
                <KeyValue
                  items={[
                    [en.instrumentation, <Badge tone="success">{en.enabled}</Badge>],
                    [en.traceRetention, en.days(s.retention_days)],
                    [en.content, en.metadataAndRedactedProjections],
                    [en.storedAudio, en.disabled],
                    [en.fullTranscripts, en.disabled],
                    ['Replay', en.readOnlyNoReExecution],
                  ]}
                />
              </div>
            </div>
          </div>
        )
      )}
      <p className="ac-footnote">{en.keysAndTokensRemainInElectronMainAnd}</p>
    </section>
  )
}
