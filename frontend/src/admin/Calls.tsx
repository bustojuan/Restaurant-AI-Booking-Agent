import { en } from '../i18n/en'
import { stateLabel } from '../i18n/presentation'
import { useState, useEffect } from 'react'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  createColumnHelper,
} from '@tanstack/react-table'
import {
  Search,
  List,
  Layers3,
  ChevronDown,
  ChevronRight,
  ArrowUpDown,
  ArrowUpRight,
  Phone,
  RefreshCw,
  CalendarDays,
  ChevronLeft,
} from 'lucide-react'
import { adminApi } from './api'
import type { Call, Filters } from './types'
import { Badge, Button, Empty, ErrorState, Loading, Segments, StateBadge } from './ui'
import { dateTime, duration, modeLabel, resultLabel, short } from './replay'
const column = createColumnHelper<Call>()
export function Calls({ open }: { open: (id: string) => void }) {
  const [view, setView] = useState('calls'),
    [filters, setFilters] = useState<Filters>({}),
    [search, setSearch] = useState(''),
    [page, setPage] = useState(0),
    [sort, setSort] = useState('started_at'),
    [direction, setDirection] = useState('desc'),
    [expanded, setExpanded] = useState<Set<string>>(new Set())
  useEffect(() => {
    const timer = setTimeout(() => {
      setFilters((f) => ({ ...f, q: search || undefined }))
      setPage(0)
    }, 250)
    return () => clearTimeout(timer)
  }, [search])
  const update = (key: keyof Filters, value: string) => {
    setFilters((f) => ({ ...f, [key]: value || undefined }))
    setPage(0)
  }
  const calls = useQuery({
    queryKey: ['admin', 'calls', filters, page, sort, direction],
    queryFn: () => adminApi.calls({ ...filters, offset: page * 20, limit: 20, sort, direction }),
    placeholderData: keepPreviousData,
    enabled: view === 'calls',
    refetchInterval: 15000,
  })
  const bookings = useQuery({
    queryKey: ['admin', 'bookings', filters, page],
    queryFn: () => adminApi.bookings({ ...filters, offset: page * 20, limit: 20 }),
    placeholderData: keepPreviousData,
    enabled: view === 'bookings',
    refetchInterval: 15000,
  })
  const toggleSort = (name: string) => {
    setDirection(sort === name && direction === 'desc' ? 'asc' : 'desc')
    setSort(name)
    setPage(0)
  }
  const sortHeader = (label: string, name: string) => (
    <button className="ac-sort" onClick={() => toggleSort(name)}>
      {label}
      <ArrowUpDown size={12} />
    </button>
  )
  const columns = [
    column.accessor('restaurant_name', {
      header: () => sortHeader(en.restaurant, 'restaurant'),
      cell: ({ row }) => (
        <div className="ac-restaurant">
          <span
            className={`ac-call-icon ${row.original.status === 'RUNNING' || ['ACTIVE', 'DIALING'].includes(row.original.transport_state ?? '') ? 'active' : ''}`}
            title={
              row.original.transport_state
                ? en.transport(row.original.transport_state)
                : row.original.status
            }
          >
            <Phone size={15} />
          </span>
          <div>
            <strong>{row.original.restaurant_name}</strong>
            <small>
              {en.attempt2} {row.original.sequence + 1} · {short(row.original.id)}
            </small>
          </div>
        </div>
      ),
    }),
    column.accessor('started_at', {
      header: () => sortHeader(en.dateAndTime, 'started_at'),
      cell: ({ getValue }) => <span className="ac-nowrap">{dateTime(getValue())}</span>,
    }),
    column.accessor('booking_id', {
      header: en.booking3,
      cell: ({ getValue }) => <code title={getValue()}>#{short(getValue())}</code>,
    }),
    column.accessor('duration_ms', {
      header: () => sortHeader(en.duration, 'duration_ms'),
      cell: ({ getValue }) => <span className="ac-number">{duration(getValue())}</span>,
    }),
    column.accessor('result', {
      header: en.result,
      cell: ({ getValue, row }) => (
        <span className={getValue() === 'CONFIRMED' ? 'ac-green' : ''}>
          {resultLabel(getValue())}
          {((row.original.status === 'FAILED' &&
            ['AMBIGUOUS', 'UNCERTAIN', 'INTERRUPTED'].includes(getValue() ?? '')) ||
            row.original.transport_state === 'UNCERTAIN') && (
            <small className="ac-review-row">{en.reviewRequired}</small>
          )}
        </span>
      ),
    }),
    column.accessor('status', {
      header: () => sortHeader(en.status, 'status'),
      cell: ({ getValue }) => <StateBadge status={getValue()} />,
    }),
    column.accessor('mode', {
      header: en.mode,
      cell: ({ getValue }) => (
        <Badge tone={getValue() === 'real_telephony' ? 'blue' : 'violet'}>
          {modeLabel(getValue())}
        </Badge>
      ),
    }),
    column.accessor('cost_eur', {
      header: en.cost,
      cell: ({ getValue }) =>
        getValue() == null ? (
          <span className="ac-muted">{en.nA}</span>
        ) : (
          `€${getValue()!.toFixed(4)}`
        ),
    }),
    column.display({
      id: 'open',
      header: '',
      cell: () => <ArrowUpRight size={15} className="ac-row-arrow" />,
    }),
  ]
  const table = useReactTable({
    data: calls.data?.items ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
  })
  const query = view === 'calls' ? calls : bookings,
    total = query.data?.total ?? 0
  return (
    <section className="ac-page" data-testid="admin-calls">
      <div className="ac-page-title">
        <div>
          <div className="ac-eyebrow">OBSERVABILITY / CALL HISTORY</div>
          <h1>
            Calls <span className="ac-count">{query.data ? total : '—'}</span>
          </h1>
          <p>{en.fromTheFirstConnectionToTheFinalDecision}</p>
        </div>
        <Button onClick={() => void query.refetch()} aria-label={en.refreshHistory}>
          <RefreshCw size={14} />

          {en.refresh}
        </Button>
      </div>
      <div className="ac-toolbar">
        <Segments
          value={view}
          onChange={(v) => {
            setView(v)
            setPage(0)
          }}
          items={[
            { value: 'calls', label: 'Call view', icon: <List size={14} /> },
            { value: 'bookings', label: 'Booking view', icon: <Layers3 size={14} /> },
          ]}
        />
        <span className="ac-toolbar-note">
          <span className="ac-dot" /> {en.sqliteStoredData}
        </span>
      </div>
      <div className="ac-table-card">
        <div className="ac-filters">
          <div className="ac-search">
            <Search size={15} />
            <input
              aria-label={en.searchCalls}
              placeholder={en.searchRestaurantCallOrBooking}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <select
            aria-label={en.filterStatus}
            value={filters.status ?? ''}
            onChange={(e) => update('status', e.target.value)}
          >
            <option value="">{en.allStatuses}</option>
            {['RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED'].map((s) => (
              <option key={s} value={s}>
                {stateLabel(s)}
              </option>
            ))}
          </select>
          <select
            aria-label={en.filterResult}
            value={filters.result ?? ''}
            onChange={(e) => update('result', e.target.value)}
          >
            <option value="">{en.allResults}</option>
            {[
              'CONFIRMED',
              'NO_AVAILABILITY',
              'INCOMPATIBLE_OFFER',
              'NOT_CONFIRMED',
              'AMBIGUOUS',
              'ERROR',
              'TIMEOUT',
              'USER_APPROVAL_REQUIRED',
            ].map((s) => (
              <option key={s} value={s}>
                {resultLabel(s)}
              </option>
            ))}
          </select>
          <select
            aria-label={en.filterMode}
            value={filters.mode ?? ''}
            onChange={(e) => update('mode', e.target.value)}
          >
            <option value="">{en.allModes}</option>
            <option value="ai_simulation">{en.aiSimulation}</option>
            <option value="simulation">{en.simulation}</option>
            <option value="real_telephony">Real</option>
          </select>
          <div className="ac-date-range">
            <CalendarDays size={14} />
            <input
              type="date"
              aria-label={en.startDate}
              value={filters.date_from ?? ''}
              onChange={(e) => update('date_from', e.target.value)}
            />
            <span>—</span>
            <input
              type="date"
              aria-label={en.endDate}
              value={filters.date_to ?? ''}
              onChange={(e) => update('date_to', e.target.value)}
            />
          </div>
          {Object.values(filters).some(Boolean) && (
            <Button
              onClick={() => {
                setFilters({})
                setSearch('')
                setPage(0)
              }}
            >
              {en.clear}
            </Button>
          )}
        </div>
        {query.isError ? (
          <ErrorState error={query.error} retry={() => void query.refetch()} />
        ) : query.isPending ? (
          <Loading />
        ) : total === 0 ? (
          <Empty title={en.noCallsToDisplay}>{en.storedCallsWillAppearHereRunASimulation}</Empty>
        ) : view === 'calls' ? (
          <div className="ac-table-scroll">
            <table className="ac-table">
              <thead>
                {table.getHeaderGroups().map((group) => (
                  <tr key={group.id}>
                    {group.headers.map((h) => (
                      <th key={h.id}>{flexRender(h.column.columnDef.header, h.getContext())}</th>
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody>
                {table.getRowModel().rows.map((row) => (
                  <tr
                    key={row.id}
                    data-testid={`call-row-${row.original.id}`}
                    tabIndex={0}
                    onClick={() => open(row.original.id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') open(row.original.id)
                    }}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="ac-booking-list">
            {bookings.data?.items.map((b) => (
              <div className="ac-booking-group" key={b.id}>
                <button
                  className="ac-booking-heading"
                  aria-expanded={expanded.has(b.id)}
                  onClick={() =>
                    setExpanded((previous) => {
                      const next = new Set(previous)
                      if (next.has(b.id)) next.delete(b.id)
                      else next.add(b.id)
                      return next
                    })
                  }
                >
                  {expanded.has(b.id) ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  <Layers3 size={17} />
                  <strong>
                    {en.booking2}
                    {short(b.id)}
                  </strong>
                  <span>{dateTime(b.started_at)}</span>
                  <Badge tone="violet">{modeLabel(b.mode)}</Badge>
                  <span>
                    {b.calls.length} {en.calls2}
                  </span>
                  <StateBadge status={b.status} />
                </button>
                {expanded.has(b.id) && (
                  <div className="ac-booking-children">
                    {b.calls.map((c) => (
                      <button key={c.id} onClick={() => open(c.id)}>
                        <span className="ac-sequence">{c.sequence + 1}</span>
                        <strong>{c.restaurant_name}</strong>
                        <span>{duration(c.duration_ms)}</span>
                        <span>{resultLabel(c.result)}</span>
                        <StateBadge status={c.status} />
                        <ArrowUpRight size={15} />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
        <div className="ac-pagination">
          <span>
            {total
              ? en.of(page * 20 + 1, Math.min(total, (page + 1) * 20), total)
              : en.noSearchResults}{' '}
            <span className="ac-muted">· Europe/Madrid</span>
          </span>
          <div>
            <Button
              aria-label={en.previousPage}
              disabled={page === 0 || query.isFetching}
              onClick={() => setPage((p) => p - 1)}
            >
              <ChevronLeft size={14} />
            </Button>
            <span>
              {en.page} {page + 1}
            </span>
            <Button
              aria-label={en.nextPage}
              disabled={(page + 1) * 20 >= total || query.isFetching}
              onClick={() => setPage((p) => p + 1)}
            >
              <ChevronRight size={14} />
            </Button>
          </div>
        </div>
      </div>
      <div className="ac-footnote">
        {en.historyShowsRetainedAttemptsVoiceSandboxSessionsWithout}
      </div>
    </section>
  )
}
