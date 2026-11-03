import { categoryLabel } from '../../i18n/presentation'
import { en } from '../../i18n/en'
import { useDraggable } from '@dnd-kit/core'
import { Check, ExternalLink, GripVertical, Plus, Star, X, MapPin } from 'lucide-react'
import { useEditor, useUI } from '../../app/context'
import { editor } from '../../services/editor'
import { api, errorText } from '../../services/api'
import { cleanName } from '../../lib/utils'
import { Button } from '../ui/button'
import { RestaurantImage } from '../shared/RestaurantImage'
import type { Restaurant } from '../../types/bridge'
export function RestaurantCard({
  restaurant: r,
  floating = false,
  onClose,
  onLocate,
}: {
  restaurant: Restaurant
  floating?: boolean
  onClose?: () => void
  onLocate?: () => void
}) {
  const { favorite, favorites, notice } = useUI()
  const { booking, saving } = useEditor()
  const selected = booking?.restaurants.some((e) => e.restaurant.id === r.id)
  const editable = booking?.status === 'DRAFT'
  const drag = useDraggable({
    id: `explorer:${r.id}`,
    data: { restaurant: r, origin: 'explorer' },
    disabled: !editable || selected || saving,
  })
  const add = async () => {
    try {
      await editor.mutate((b) => api.insert(b, r.id))
      notice(en.restaurantAddedToBooking)
    } catch (e) {
      notice(errorText(e))
    }
  }
  return (
    <article
      ref={drag.setNodeRef}
      className={`restaurant-card ${floating ? 'floating-card' : ''} ${drag.isDragging ? 'is-dragging' : ''}`}
      data-testid={`restaurant-${r.id}`}
    >
      {onClose && (
        <Button
          variant="ghost"
          icon
          className="card-close"
          aria-label={en.closeRestaurantDetails}
          onClick={onClose}
        >
          <X size={17} />
        </Button>
      )}
      <div
        className={`restaurant-card-body ${editable && !selected && !saving ? 'can-drag' : ''}`}
        onPointerDown={(event) => drag.listeners?.onPointerDown?.(event)}
        title={editable && !selected ? en.dragTheCardIntoSelectedRestaurants : undefined}
      >
        <RestaurantImage restaurant={r} large />
        <div className="restaurant-info">
          <h3>{cleanName(r.name)}</h3>
          <p>{r.cuisine_types.map((c) => categoryLabel('cuisine', c)).join(' · ')}</p>
          {(r.rating !== null || r.price_range !== null) && (
            <p className="rating">
              {r.rating !== null && (
                <>
                  <Star size={14} fill="currentColor" />
                  {r.rating}
                  {r.review_count !== null && ` (${r.review_count})`}
                </>
              )}
              {r.price_range !== null && <span>{'€'.repeat(r.price_range)}</span>}
            </p>
          )}
          <p className="address">
            {r.address ?? (r.municipality || r.region)}
            {r.address && `, ${r.municipality || r.region}`}
          </p>
          <div className="restaurant-tags">
            {r.is_simulated && <span className="mini-badge">{en.simulated2}</span>}
            {selected && (
              <span className="mini-badge blue">
                {en.priority}{' '}
                {(booking?.restaurants.find((e) => e.restaurant.id === r.id)?.position ?? 0) + 1}
              </span>
            )}
          </div>
          {r.source_url && (
            <button
              className="restaurant-source"
              title={r.data_attribution ?? undefined}
              onClick={() => void window.desktop?.openExternal(r.source_url!)}
            >
              {en.openstreetmapRecordOdbl}
            </button>
          )}
        </div>
      </div>
      <div className="restaurant-actions">
        <Button
          icon
          variant="ghost"
          aria-label={en.dragIntoBooking(cleanName(r.name))}
          {...drag.attributes}
          {...drag.listeners}
          disabled={!editable || selected || saving}
          className="drag-handle"
        >
          <GripVertical size={17} />
        </Button>
        {onLocate && (
          <Button icon onClick={onLocate} aria-label={en.viewOnMap}>
            <MapPin size={16} />
          </Button>
        )}
        {r.website_url && (
          <Button onClick={() => void window.desktop?.openExternal(r.website_url!)}>
            <ExternalLink size={14} />

            {en.website}
          </Button>
        )}
        <Button
          onClick={() => void favorite(r)}
          className={favorites.has(r.id) ? 'is-favorite' : ''}
          aria-label={
            favorites.has(r.id)
              ? en.removeFavorite(cleanName(r.name))
              : en.saveFavorite(cleanName(r.name))
          }
        >
          <Star size={17} fill={favorites.has(r.id) ? 'currentColor' : 'none'} />
          {floating ? en.saveFavorite2 : ''}
        </Button>
        <Button
          variant="primary"
          onClick={() => void add()}
          disabled={selected || !editable || saving}
        >
          {selected ? <Check size={16} /> : <Plus size={16} />}{' '}
          {selected ? en.added : floating ? en.addToBooking : en.add}
        </Button>
      </div>
    </article>
  )
}
