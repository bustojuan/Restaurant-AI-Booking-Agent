import type { components } from './api.generated'
export type Restaurant = components['schemas']['RestaurantOut']
export type Booking = Omit<components['schemas']['BookingDetail'], 'configuration'> & {
  configuration: Configuration
}
export type Summary = components['schemas']['BookingSummary']
// Pydantic materializes every default in responses; OpenAPI also uses this schema for input.
export type Configuration = Required<components['schemas']['BookingConfiguration']>
export type BookingEvent = components['schemas']['EventOut']
export type StartRequest = components['schemas']['StartRequest']
export type Capabilities = {
  ai_simulation: boolean
  voice_sandbox_enabled: boolean
  real_telephony_enabled: boolean
  openai_credentials_configured: boolean
  reasoning_model: string
  voice_model: string
  extraction_mode: string
  recording_enabled: boolean
}
export type RequestSpec = {
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  path: string
  body?: unknown
  version?: number
}
export type Reply = { status: number; data: unknown }
export type Connection = 'connecting' | 'connected' | 'disconnected'
export type DesktopSettings = { backendUrl: string; tokenConfigured: boolean }
export interface DesktopBridge {
  request(spec: RequestSpec): Promise<Reply>
  settings(): Promise<DesktopSettings>
  setBackend(url: string): Promise<DesktopSettings>
  openExternal(url: string): Promise<void>
  window(action: 'minimize' | 'maximize' | 'close'): void
  connectEvents(): void
  openAdmin(): void
  onEvent(listener: (event: BookingEvent) => void): () => void
  onConnection(listener: (state: Connection) => void): () => void
}
declare global {
  interface Window {
    desktop?: DesktopBridge
  }
}
