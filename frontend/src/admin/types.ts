import type { components } from '../types/api.generated'
export type Observation = components['schemas']['ObservationEventOut']
export type Execution = components['schemas']['ObservedExecutionOut']
export type EventPage = components['schemas']['ObservationPage']
export type GraphVersion = components['schemas']['GraphVersionOut']
export type Call = components['schemas']['CallOut']
export type CallPage = components['schemas']['CallPage']
export type BookingHistory = components['schemas']['BookingHistoryOut']
export type BookingPage = components['schemas']['BookingHistoryPage']
export type Analytics = components['schemas']['AnalyticsOut']
export type AdminSettings = components['schemas']['AdminSettingsOut']
export type Scenario = components['schemas']['AdminScenarioOut']
export type PlaygroundInput = components['schemas']['PlaygroundInput']
export type PlaygroundRun = components['schemas']['PlaygroundOut']
export type Evaluation = components['schemas']['EvaluationOut']
export type Filters = {
  q?: string
  mode?: string
  status?: string
  result?: string
  date_from?: string
  date_to?: string
  model?: string
  prompt?: string
}
export type AdminRequest =
  | {
      operation: 'calls' | 'bookings'
      params: Filters & { limit?: number; offset?: number; sort?: string; direction?: string }
    }
  | { operation: 'call' | 'execution' | 'graph' | 'evaluation'; id: string }
  | {
      operation: 'events'
      params: {
        execution_id: string
        after_event_id?: number
        until_event_id?: number
        limit?: number
      }
    }
  | { operation: 'analytics'; params: Filters }
  | { operation: 'settings' | 'scenarios' }
  | { operation: 'simulate'; input: PlaygroundInput }
export type AdminConnection = 'connecting' | 'connected' | 'disconnected' | 'unauthorized'
export interface AdminBridge {
  request(spec: AdminRequest): Promise<{ status: number; data: unknown }>
  connection(): Promise<{ configured: boolean; backendUrl: string }>
  connect(): void
  openBooker(): void
  onEvent(listener: (event: Observation) => void): () => void
  onConnection(listener: (state: AdminConnection) => void): () => void
  window(action: 'minimize' | 'maximize' | 'close'): void
}
declare global {
  interface Window {
    admin?: AdminBridge
  }
}
