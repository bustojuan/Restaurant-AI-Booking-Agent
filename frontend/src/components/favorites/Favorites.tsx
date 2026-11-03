import { en } from '../../i18n/en'
import { categoryLabel } from '../../i18n/presentation'
import { useQuery } from '@tanstack/react-query'
import { Star, MapPin, Plus, LoaderCircle } from 'lucide-react'
import { useUI, useEditor } from '../../app/context'
import { RestaurantImage } from '../shared/RestaurantImage'
import { Button } from '../ui/button'
import { editor } from '../../services/editor'
import { api, errorText } from '../../services/api'
import { cleanName } from '../../lib/utils'
import type { Restaurant } from '../../types/bridge'
export function Favorites({ onClose }: { onClose: () => void }) {
  const { favorite, notice, region, setRegion, select, setView } = useUI()
  const { booking, saving } = useEditor()
  const favorites = useQuery<Restaurant[]>({ queryKey: ['favorites'] })
  return (
    <>
      <div className="reservations-heading">
        <h2>
          <Star size={19} className="gold" />

          {en.yourFavorites}
        </h2>
        <span className="count-badge">{favorites.data?.length ?? 0}</span>
      </div>
      <p className="muted favorites-subtitle">{en.yourSavedPlacesAlwaysAtHand}</p>
      <div className="favorites-list">
        {favorites.isLoading && (
          <div className="empty">
            <LoaderCircle className="spin" />

            {en.loadingFavorites}
          </div>
        )}
        {favorites.isError && <p role="alert">{en.couldNotLoadFavorites}</p>}
        {!favorites.data?.length && !favorites.isLoading && (
          <div className="empty">
            <Star size={30} />
            <h3>{en.saveYourNextOuting}</h3>
            <p>{en.selectARestaurantSStarToFindIt}</p>
          </div>
        )}
        {favorites.data?.map((r) => (
          <article className="favorite-item" key={r.id}>
            <RestaurantImage restaurant={r} />
            <div>
              <strong>{cleanName(r.name)}</strong>
              <p>
                {r.address ?? r.municipality} · {r.region}
              </p>
              <small>
                {r.cuisine_types.map((id) => categoryLabel('cuisine', id)).join(' · ')}
                {r.is_simulated ? en.simulated : ''}
              </small>
              <div>
                <Button
                  variant="ghost"
                  onClick={() => {
                    if (r.region !== region) {
                      notice(en.theMapWillSwitchToToShowThis(r.region))
                      setRegion(r.region === 'Navarra' ? 'Navarra' : 'Madrid')
                    }
                    select(r)
                    setView('map')
                    onClose()
                  }}
                >
                  <MapPin size={13} />

                  {en.showMap}
                </Button>
                <Button
                  disabled={
                    saving ||
                    booking?.status !== 'DRAFT' ||
                    booking.restaurants.some((e) => e.restaurant.id === r.id)
                  }
                  onClick={() =>
                    void editor
                      .mutate((b) => api.insert(b, r.id))
                      .catch((e) => notice(errorText(e)))
                  }
                >
                  <Plus size={13} />

                  {en.add}
                </Button>
              </div>
            </div>
            <Button
              icon
              variant="ghost"
              className="is-favorite"
              aria-label={en.removeFavorite(cleanName(r.name))}
              onClick={() => void favorite(r)}
            >
              <Star size={18} fill="currentColor" />
            </Button>
          </article>
        ))}
      </div>
    </>
  )
}
