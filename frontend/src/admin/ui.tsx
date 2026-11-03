import { stateLabel } from '../i18n/presentation'
import { en } from '../i18n/en'
import type { ReactNode, ButtonHTMLAttributes } from 'react'
import * as Tabs from '@radix-ui/react-tabs'
import { AlertCircle, LoaderCircle, Inbox } from 'lucide-react'
import { cn } from '../lib/utils'
export function Button({
  className,
  primary,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { primary?: boolean }) {
  return <button className={cn('ac-button', primary && 'primary', className)} {...props} />
}
export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: string }) {
  return (
    <span className={`ac-badge ${tone}`}>
      <i />
      {children}
    </span>
  )
}
export function StateBadge({ status }: { status: string | null | undefined }) {
  const tone = ['CONFIRMED', 'completed', 'COMPLETED'].includes(status ?? '')
    ? 'success'
    : ['FAILED', 'failed', 'ERROR', 'TIMEOUT'].includes(status ?? '')
      ? 'danger'
      : ['RUNNING', 'running', 'ACTIVE', 'started'].includes(status ?? '')
        ? 'live'
        : ['WAITING_FOR_USER', 'interrupted', 'UNCERTAIN'].includes(status ?? '')
          ? 'warning'
          : 'neutral'
  return <Badge tone={tone}>{stateLabel(status)}</Badge>
}
export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="ac-empty">
      <Inbox size={30} />
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  )
}
export function Loading() {
  return (
    <div className="ac-empty" role="status">
      <LoaderCircle className="ac-spin" size={24} />
      <p>{en.loadingBackendData}</p>
    </div>
  )
}
export function ErrorState({ error, retry }: { error: Error; retry?: () => void }) {
  return (
    <div className="ac-error" role="alert">
      <AlertCircle size={20} />
      <div>
        <strong>{en.couldNotLoadData}</strong>
        <p>{error.message}</p>
        {retry && <Button onClick={retry}>{en.retry}</Button>}
      </div>
    </div>
  )
}
export function PanelHead({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle?: string
  children?: ReactNode
}) {
  return (
    <div className="ac-panel-head">
      <div>
        <h3>{title}</h3>
        {subtitle && <p>{subtitle}</p>}
      </div>
      <div className="ac-actions">{children}</div>
    </div>
  )
}
export function Segments({
  value,
  onChange,
  items,
}: {
  value: string
  onChange: (v: string) => void
  items: { value: string; label: string; icon?: ReactNode }[]
}) {
  return (
    <Tabs.Root className="ac-segments" value={value} onValueChange={onChange}>
      <Tabs.List>
        {items.map((i) => (
          <Tabs.Trigger key={i.value} value={i.value}>
            {i.icon}
            {i.label}
          </Tabs.Trigger>
        ))}
      </Tabs.List>
    </Tabs.Root>
  )
}
export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="ac-field">
      <span>{label}</span>
      {children}
    </label>
  )
}
export function Metric({
  label,
  value,
  note,
  icon,
}: {
  label: string
  value: ReactNode
  note?: string
  icon?: ReactNode
}) {
  return (
    <div className="ac-metric">
      <div>
        <span>{label}</span>
        {icon}
      </div>
      <strong>{value}</strong>
      {note && <small>{note}</small>}
    </div>
  )
}
export function KeyValue({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="ac-kv">
      {items.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value ?? en.nA}</dd>
        </div>
      ))}
    </dl>
  )
}
