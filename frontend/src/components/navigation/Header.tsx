import { en } from '../../i18n/en'
import { useState } from 'react'
import {
  Map,
  CalendarDays,
  Star,
  Settings2,
  MapPin,
  Utensils,
  ChevronDown,
  Minus,
  Square,
  X,
  Check,
  WifiOff,
} from 'lucide-react'
import { motion } from 'motion/react'
import { useUI } from '../../app/context'
import { useBookings, activeStatuses } from '../reservations/queries'
import { ReservationsPopover } from '../reservations/ReservationsPopover'
import { Favorites } from '../favorites/Favorites'
import { Settings } from '../settings/Settings'
import { Button } from '../ui/button'
import { Pop } from '../ui/overlay'
export function Header({ onDetail }: { onDetail: (id: string) => void }) {
  const { region, setRegion, select, connection } = useUI()
  const [reservations, setReservations] = useState(false),
    [favorites, setFavorites] = useState(false),
    [settings, setSettings] = useState(false)
  const bookings = useBookings()
  const count = bookings.data?.filter((b) => activeStatuses.has(b.status)).length ?? 0
  return (
    <>
      <div className="titlebar">
        <span className="titlebar-label">
          BARIA <span>—</span> AI Restaurant Booker
        </span>
        <div className="window-controls">
          <button aria-label={en.minimizeWindow} onClick={() => window.desktop?.window('minimize')}>
            <Minus size={13} />
          </button>
          <button aria-label={en.maximizeWindow} onClick={() => window.desktop?.window('maximize')}>
            <Square size={11} />
          </button>
          <button aria-label={en.closeApplication} onClick={() => window.desktop?.window('close')}>
            <X size={14} />
          </button>
        </div>
      </div>
      <header className="main-header">
        <div className="branding">
          <span className="brand-icon">
            <Utensils size={23} />
          </span>
          <strong>AI Restaurant Booker</strong>
          <ChevronDown size={15} className="muted" />
        </div>
        <div className="region-switch" aria-label={en.location}>
          {(['Madrid', 'Navarra'] as const).map((r) => (
            <button
              key={r}
              onClick={() => {
                setRegion(r)
                select(null)
              }}
              aria-pressed={region === r}
            >
              {region === r && (
                <motion.span
                  layoutId="region-selection"
                  className="region-highlight"
                  transition={{ duration: 0.18 }}
                />
              )}
              <span>
                {region === r && <MapPin size={18} />} {r}
              </span>
            </button>
          ))}
        </div>
        <nav>
          <Button
            variant="ghost"
            onClick={() => window.desktop?.openAdmin()}
            title="AI Control Center (Ctrl+Shift+A)"
          >
            AI Control Center
          </Button>
          <Button
            className="nav-active"
            onClick={() => {
              setReservations(false)
              setFavorites(false)
            }}
          >
            <Map size={19} />

            {en.explore}
          </Button>
          <Pop
            open={reservations}
            onOpenChange={(v) => {
              setReservations(v)
              setFavorites(false)
            }}
            trigger={
              <Button variant="ghost" className={reservations ? 'nav-active' : ''}>
                <CalendarDays size={19} />

                {en.bookings}
                {count > 0 && <span className="notification-badge">{count}</span>}
              </Button>
            }
            className="reservations-popover"
            alignOffset={Math.max(
              130,
              Math.min(560, Math.max(370, window.innerWidth * 0.282)) - 215,
            )}
          >
            <ReservationsPopover onDetail={onDetail} onClose={() => setReservations(false)} />
          </Pop>
          <Pop
            open={favorites}
            onOpenChange={(v) => {
              setFavorites(v)
              setReservations(false)
            }}
            trigger={
              <Button variant="ghost" className={favorites ? 'nav-active' : ''}>
                <Star size={20} />

                {en.favorites}
              </Button>
            }
            className="favorites-popover"
          >
            <Favorites onClose={() => setFavorites(false)} />
          </Pop>
          <Button variant="ghost" onClick={() => setSettings(true)}>
            <Settings2 size={19} />

            {en.settings}
            {connection !== 'connected' && (
              <span title={en.reconnectingToTheBackend} className="connection-warning">
                <WifiOff size={12} />
              </span>
            )}
          </Button>
        </nav>
      </header>
      <Settings open={settings} onClose={() => setSettings(false)} />
    </>
  )
}
