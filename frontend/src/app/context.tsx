import {
  createContext,
  useContext,
  useEffect,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from 'react'
import { QueryClient, QueryClientProvider, useQueryClient, useQuery } from '@tanstack/react-query'
import { editor } from '../services/editor'
import { api, get, request, queryString, errorText } from '../services/api'
import { EventCursor } from '../services/events'
import type { components } from '../types/api.generated'
import type { Restaurant, Connection } from '../types/bridge'
type UI = {
  region: 'Madrid' | 'Navarra'
  setRegion: (v: 'Madrid' | 'Navarra') => void
  view: 'map' | 'list'
  setView: (v: 'map' | 'list') => void
  selected: Restaurant | null
  select: (v: Restaurant | null) => void
  notice: (v: string) => void
  favorite: (r: Restaurant) => Promise<void>
  favorites: Set<string>
  connection: Connection
}
const Context = createContext<UI | null>(null)
export const useUI = () => {
  const value = useContext(Context)
  if (!value) throw new Error('UI provider missing')
  return value
}
export const useEditor = () => useSyncExternalStore(editor.subscribe, editor.snapshot)
const client = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 15000, refetchOnWindowFocus: true },
    mutations: { retry: false },
  },
})
function State({ children }: { children: ReactNode }) {
  const q = useQueryClient()
  const [region, setRegion] = useState<'Madrid' | 'Navarra'>(() =>
    sessionStorage.getItem('region') === 'Navarra' ? 'Navarra' : 'Madrid',
  )
  const [view, setView] = useState<'map' | 'list'>('map'),
    [selected, select] = useState<Restaurant | null>(null),
    [message, notice] = useState(''),
    [connection, setConnection] = useState<Connection>('connecting')
  const favorites = useQuery({
    queryKey: ['favorites'],
    queryFn: async () => {
      let items: Restaurant[] = []
      let offset = 0
      while (true) {
        const p = await get<components['schemas']['RestaurantPage']>(
          `/api/favorites?limit=100&offset=${offset}`,
        )
        items = items.concat(p.items)
        offset += p.items.length
        if (offset >= p.total || !p.items.length) return items
      }
    },
  })
  useEffect(() => {
    sessionStorage.setItem('region', region)
  }, [region])
  useEffect(() => {
    void editor.init().catch(() => {})
    const cursor = new EventCursor()
    const off = window.desktop?.onEvent((e) => {
      if (!cursor.accept(e)) return
      q.invalidateQueries({ queryKey: ['bookings'] })
      q.invalidateQueries({ queryKey: ['booking', e.booking_id] })
      q.invalidateQueries({ queryKey: ['events', e.booking_id] })
      q.invalidateQueries({ queryKey: ['ai', e.booking_id] })
      const current = editor.snapshot().booking
      if (current?.id === e.booking_id && e.payload.summary.version > current.version)
        void api
          .booking(current.id)
          .then((b) => editor.receive(b))
          .catch(() => {})
    })
    const offStatus = window.desktop?.onConnection((s) => {
      setConnection(s)
      if (s === 'connected') {
        q.invalidateQueries()
        const b = editor.snapshot().booking
        if (b)
          void api
            .booking(b.id)
            .then((next) => editor.receive(next))
            .catch(() => {})
      }
    })
    window.desktop?.connectEvents()
    return () => {
      off?.()
      offStatus?.()
    }
  }, [q])
  useEffect(() => {
    if (!message) return
    const t = setTimeout(() => notice(''), 4200)
    return () => clearTimeout(t)
  }, [message])
  const favorite = async (r: Restaurant) => {
    try {
      const exists = favorites.data?.some((f) => f.id === r.id)
      await request({
        method: exists ? 'DELETE' : 'POST',
        path: exists ? `/api/favorites/${r.id}` : '/api/favorites',
        body: exists ? undefined : { restaurant_id: r.id },
      })
      await q.invalidateQueries({ queryKey: ['favorites'] })
      await q.invalidateQueries({ queryKey: ['restaurants'] })
    } catch (e) {
      notice(errorText(e))
    }
  }
  return (
    <Context.Provider
      value={{
        region,
        setRegion,
        view,
        setView,
        selected,
        select,
        notice,
        favorite,
        favorites: new Set(favorites.data?.map((r) => r.id)),
        connection,
      }}
    >
      {children}
      {message && (
        <div className="toast" role="status">
          {message}
        </div>
      )}
    </Context.Provider>
  )
}
export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={client}>
      <State>{children}</State>
    </QueryClientProvider>
  )
}
export function useRestaurants(
  search: string,
  cuisine: string[],
  establishment: string[],
  onlyFavorites: boolean,
  minRating: string,
  maxPrice: string,
  radius: string,
  page: number,
  options: { catalog: string; asian: boolean; dietary: string[]; bbox?: string; limit: number },
) {
  const { region } = useUI()
  return useQuery({
    queryKey: [
      'restaurants',
      region,
      search,
      cuisine,
      establishment,
      onlyFavorites,
      minRating,
      maxPrice,
      radius,
      page,
      options,
    ],
    placeholderData: (previous, query) => (query?.queryKey[1] === region ? previous : undefined),
    queryFn: () =>
      get<components['schemas']['RestaurantPage']>(
        '/api/restaurants?' +
          queryString({
            region,
            q: search,
            cuisine_types: cuisine,
            establishment_types: establishment,
            favorites_only: onlyFavorites,
            catalog: options.catalog,
            cuisine_group: options.asian ? 'asian' : undefined,
            dietary_options: options.dietary,
            bbox: options.bbox,
            min_rating: minRating,
            max_price: maxPrice,
            radius_km: radius,
            latitude: radius ? (region === 'Madrid' ? 40.4168 : 42.8125) : undefined,
            longitude: radius ? (region === 'Madrid' ? -3.7038 : -1.6458) : undefined,
            limit: options.limit,
            offset: page * options.limit,
          }),
      ),
  })
}
