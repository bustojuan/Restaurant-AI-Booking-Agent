import { categoryLabel } from '../../i18n/presentation'
import { en } from '../../i18n/en'
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Search,
  SlidersHorizontal,
  Star,
  ChevronDown,
  Map as MapIcon,
  List,
  LoaderCircle,
  X,
  ArrowLeft,
  ArrowRight,
  MapPin,
} from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useRestaurants, useUI } from '../../app/context'
import { get } from '../../services/api'
import type { components } from '../../types/api.generated'
import { Button } from '../ui/button'
import { Pop } from '../ui/overlay'
import { RestaurantMap } from '../map/RestaurantMap'
import { RestaurantCard } from './RestaurantCard'
export function Explorer() {
  const { region, view, setView, selected, select } = useUI()
  const [search, setSearch] = useState(''),
    [debounced, setDebounced] = useState(''),
    [cuisines, setCuisines] = useState<string[]>([]),
    [establishments, setEstablishments] = useState<string[]>([]),
    [onlyFavorites, setOnlyFavorites] = useState(false),
    [minRating, setMinRating] = useState(''),
    [maxPrice, setMaxPrice] = useState(''),
    [radius, setRadius] = useState(''),
    [page, setPage] = useState(0),
    [threeD, setThreeD] = useState(true),
    [filtersOpen, setFiltersOpen] = useState(false)
  const [catalogMode, setCatalogMode] = useState('auto')
  const [asian, setAsian] = useState(false)
  const [dietary, setDietary] = useState<string[]>([])
  const [bounds, setBounds] = useState<{ region: string; bbox: string } | null>(null)
  const limit = view === 'map' ? 100 : 40
  const bbox = view === 'map' && !debounced && bounds?.region === region ? bounds.bbox : undefined
  useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 280)
    return () => clearTimeout(t)
  }, [search])
  useEffect(
    () => setPage(0),
    [
      region,
      view,
      debounced,
      cuisines,
      establishments,
      onlyFavorites,
      minRating,
      maxPrice,
      radius,
      catalogMode,
      asian,
      dietary,
      bbox,
    ],
  )
  const data = useRestaurants(
    debounced,
    cuisines,
    establishments,
    onlyFavorites,
    minRating,
    maxPrice,
    radius,
    page,
    { catalog: catalogMode, asian, dietary, bbox, limit },
  )
  const catalog = useQuery({
    queryKey: ['categories'],
    queryFn: () => get<components['schemas']['CategoryCatalog']>('/api/restaurants/categories'),
  })
  const toggle = (id: string) =>
    setCuisines((c) => (c.includes(id) ? c.filter((v) => v !== id) : [...c, id]))
  const reset = () => {
    setCuisines([])
    setEstablishments([])
    setOnlyFavorites(false)
    setMinRating('')
    setMaxPrice('')
    setRadius('')
    setAsian(false)
    setDietary([])
  }
  return (
    <section className={`explorer explorer-${view}`} aria-label={en.restaurantExplorer}>
      {view === 'map' && (
        <RestaurantMap
          restaurants={data.data?.items ?? []}
          threeD={threeD}
          onThreeD={setThreeD}
          onBounds={(region, bbox) => setBounds({ region, bbox })}
        />
      )}
      <div className="explorer-toolbar">
        <div className="search-box">
          <Search size={21} />
          <input
            aria-label={en.searchRestaurantsAreas}
            placeholder={en.searchRestaurantsAreas2}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {data.isFetching ? (
            <LoaderCircle className="spin" size={18} />
          ) : search ? (
            <Button icon variant="ghost" aria-label={en.clearSearch} onClick={() => setSearch('')}>
              <X size={16} />
            </Button>
          ) : null}
          <span className="search-divider" />
          <Pop
            open={filtersOpen}
            onOpenChange={setFiltersOpen}
            trigger={
              <Button icon variant="ghost" aria-label={en.advancedFilters}>
                <SlidersHorizontal size={20} />
              </Button>
            }
            className="filter-popover"
          >
            <h3>{en.refineYourSearch}</h3>
            <p className="muted">{en.filtersPreserveYourSelection}</p>
            <label>
              {en.catalog}
              <select
                aria-label={en.restaurantCatalog}
                value={catalogMode}
                onChange={(e) => setCatalogMode(e.target.value)}
              >
                <option value="auto">{en.automaticRealPlacesWhenAvailable}</option>
                <option value="real">{en.realRestaurantsOnly}</option>
                <option value="simulated">{en.demo}</option>
              </select>
            </label>
            <div className="filter-section">
              <h4>{en.reportedMenuOptions}</h4>
              <p className="muted">{en.informationFromTheSourceConfirmDietaryRequirementsAnd}</p>
              <div className="filter-options">
                {catalog.data?.dietary_options?.map((c) => (
                  <button
                    key={c.id}
                    className={`chip small ${dietary.includes(c.id) ? 'selected' : ''}`}
                    onClick={() =>
                      setDietary((v) =>
                        v.includes(c.id) ? v.filter((id) => id !== c.id) : [...v, c.id],
                      )
                    }
                  >
                    {categoryLabel('dietary', c.id)}
                  </button>
                ))}
              </div>
            </div>
            <div className="filter-section">
              <h4>
                {en.cuisine} <span>{en.combinedUsingAnd}</span>
              </h4>
              <div className="filter-options">
                {catalog.data?.cuisine_types.map((c) => (
                  <button
                    key={c.id}
                    className={`chip small ${cuisines.includes(c.id) ? 'selected' : ''}`}
                    onClick={() => toggle(c.id)}
                  >
                    {categoryLabel('cuisine', c.id)}
                  </button>
                ))}
              </div>
            </div>
            <div className="filter-section">
              <h4>{en.establishmentType}</h4>
              <div className="filter-options">
                {catalog.data?.establishment_types.map((c) => (
                  <button
                    key={c.id}
                    className={`chip small ${establishments.includes(c.id) ? 'selected' : ''}`}
                    onClick={() =>
                      setEstablishments((v) =>
                        v.includes(c.id) ? v.filter((i) => i !== c.id) : [...v, c.id],
                      )
                    }
                  >
                    {categoryLabel('establishment', c.id)}
                  </button>
                ))}
              </div>
            </div>
            <div className="filter-grid">
              <label>
                {en.minimumRating}
                <select value={minRating} onChange={(e) => setMinRating(e.target.value)}>
                  <option value="">{en.any}</option>
                  <option value="3">{en.message3Stars}</option>
                  <option value="4">{en.message4Stars}</option>
                  <option value="4.5">{en.message45Stars}</option>
                </select>
              </label>
              <label>
                {en.maximumPrice}
                <select value={maxPrice} onChange={(e) => setMaxPrice(e.target.value)}>
                  <option value="">{en.any}</option>
                  {[1, 2, 3, 4].map((n) => (
                    <option key={n} value={n}>
                      {'€'.repeat(n)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {en.radiusFromCenter}
                <select value={radius} onChange={(e) => setRadius(e.target.value)}>
                  <option value="">{en.entireRegion}</option>
                  {[2, 5, 10, 25, 50, 100].map((n) => (
                    <option key={n} value={n}>
                      {n} km
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <Button variant="ghost" onClick={reset}>
              {en.clearFilters}
            </Button>
          </Pop>
        </div>
        <div className="cuisine-chips">
          <button
            className={`chip ${!cuisines.length && !establishments.length && !onlyFavorites && !asian && !dietary.length ? 'selected' : ''}`}
            onClick={reset}
          >
            {en.all}
          </button>
          <button
            className={`chip ${onlyFavorites ? 'selected' : ''}`}
            onClick={() => setOnlyFavorites((v) => !v)}
          >
            <Star size={17} fill="currentColor" className="gold" />

            {en.favorites}
          </button>
          {[
            ['italian', en.italian],
            ['japanese', en.japanese],
            ['mexican', en.mexican],
            ['mediterranean', en.mediterranean],
          ].map(([id, label]) => (
            <button
              key={id}
              onClick={() => toggle(id)}
              className={`chip ${cuisines.includes(id) ? 'selected' : ''}`}
            >
              {label}
            </button>
          ))}
          <button className={`chip ${asian ? 'selected' : ''}`} onClick={() => setAsian((v) => !v)}>
            {en.asian}
          </button>
          <button className="chip" onClick={() => setFiltersOpen(true)}>
            {en.more} <ChevronDown size={15} />
          </button>
        </div>
      </div>
      {view === 'map' && (
        <div className="explorer-caption">
          <MapPin size={13} />
          {region}
          <span />
          {data.data?.total ?? '…'} {en.restaurantsInThisView}
          {data.data && data.data.total > limit && (
            <b>
              {en.showing} {limit}
              {en.zoomInOrChangePage}
            </b>
          )}
          {data.data?.items.some((r) => r.is_simulated) && <b>{en.simulatedCatalog}</b>}
        </div>
      )}
      {data.data?.items.some((r) => r.source === 'openstreetmap') && (
        <button
          className="catalog-attribution"
          onClick={() =>
            void window.desktop?.openExternal('https://www.openstreetmap.org/copyright')
          }
        >
          © OpenStreetMap contributors · ODbL 1.0
        </button>
      )}
      {data.isError && (
        <div className="explorer-data-error" role="alert">
          <strong>{en.couldNotLoadTheCatalog}</strong>
          <p>{en.checkTheBackendConnectionInSettings}</p>
          <Button onClick={() => void data.refetch()}>{en.retry}</Button>
        </div>
      )}
      {view === 'map' && selected && (
        <motion.div
          className="map-restaurant-popup"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          key={selected.id}
        >
          <RestaurantCard restaurant={selected} floating onClose={() => select(null)} />
        </motion.div>
      )}
      {view === 'list' && (
        <motion.div className="restaurant-list" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          <div className="list-heading">
            <div>
              <span className="eyebrow">{en.findYourNextTable}</span>
              <h1>
                {en.restaurantsIn} {region}
              </h1>
            </div>
            <span className="muted">
              {data.data?.total ?? '…'} {en.results2}
            </span>
          </div>
          {data.isLoading ? (
            <div className="empty">
              <LoaderCircle className="spin" />

              {en.loadingRestaurants}
            </div>
          ) : !data.data?.items.length ? (
            <div className="empty">
              <Search size={30} />
              <h3>{en.noRestaurantsFound}</h3>
              <p>{en.tryAnotherSearchOrBroadenTheFilters}</p>
              <Button
                onClick={() => {
                  reset()
                  setSearch('')
                }}
              >
                {en.resetSearch}
              </Button>
            </div>
          ) : (
            <div className="restaurant-grid">
              {data.data.items.map((r) => (
                <RestaurantCard
                  key={r.id}
                  restaurant={r}
                  onLocate={() => {
                    if (r.region !== region) return
                    select(r)
                    setView('map')
                  }}
                />
              ))}
            </div>
          )}
        </motion.div>
      )}
      {data.data && data.data.total > limit && (
        <div className="pagination">
          <Button
            icon
            disabled={!page}
            aria-label={en.previousPage}
            onClick={() => setPage((p) => p - 1)}
          >
            <ArrowLeft size={16} />
          </Button>
          <span>
            {page + 1} / {Math.ceil(data.data.total / limit)}
          </span>
          <Button
            icon
            disabled={(page + 1) * limit >= data.data.total}
            aria-label={en.nextPage}
            onClick={() => setPage((p) => p + 1)}
          >
            <ArrowRight size={16} />
          </Button>
        </div>
      )}
      <div className="view-switch">
        <Button className={view === 'map' ? 'active' : ''} onClick={() => setView('map')}>
          <MapIcon size={17} />

          {en.map}
        </Button>
        <Button className={view === 'list' ? 'active' : ''} onClick={() => setView('list')}>
          <List size={18} />

          {en.list}
        </Button>
      </div>
    </section>
  )
}
