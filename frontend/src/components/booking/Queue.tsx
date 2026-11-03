import { en } from '../../i18n/en'
import { useDroppable } from '@dnd-kit/core'
import { SortableContext, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { ArrowDown, ArrowUp, GripVertical, Plus, Star, Trash2, Utensils } from 'lucide-react'
import { useState, useEffect, useContext } from 'react'
import { InsertionContext } from '../../app/drag'
import { useEditor, useUI } from '../../app/context'
import { editor } from '../../services/editor'
import { api, errorText } from '../../services/api'
import { cleanName } from '../../lib/utils'
import { RestaurantImage } from '../shared/RestaurantImage'
import { Button } from '../ui/button'
import { Modal } from '../ui/overlay'
import type { Restaurant } from '../../types/bridge'
export function DropSlot({ position, disabled }: { position: number; disabled: boolean }) {
  const target = useContext(InsertionContext)
  const { setNodeRef, isOver } = useDroppable({
    id: `slot:${position}`,
    data: { position },
    disabled,
  })
  return (
    <div
      ref={setNodeRef}
      className={`drop-slot ${isOver || target === position ? 'over' : ''}`}
      data-testid={`drop-slot-${position}`}
    >
      <span>
        <Plus size={13} />

        {en.insertHere}
      </span>
    </div>
  )
}
function QueueItem({
  restaurant: r,
  index,
  total,
  disabled,
  move,
}: {
  restaurant: Restaurant
  index: number
  total: number
  disabled: boolean
  move: (from: number, to: number) => void
}) {
  const { favorite, favorites, notice } = useUI()
  const sortable = useSortable({
    id: `queue:${r.id}`,
    data: { restaurant: r, origin: 'queue', position: index },
    disabled,
  })
  return (
    <article
      ref={sortable.setNodeRef}
      style={{
        transform: CSS.Transform.toString(sortable.transform),
        transition: sortable.transition,
        opacity: sortable.isDragging ? 0.3 : 1,
      }}
      className="queue-item"
      data-testid={`queue-${r.id}`}
    >
      <Button
        icon
        variant="ghost"
        className="drag-handle"
        {...sortable.attributes}
        {...sortable.listeners}
        disabled={disabled}
        aria-label={en.reorder(cleanName(r.name))}
      >
        <GripVertical size={20} />
      </Button>
      <span className={`priority ${index === 0 ? 'first' : ''}`}>{index + 1}</span>
      <RestaurantImage restaurant={r} />
      <div className="queue-info">
        <strong>{cleanName(r.name)}</strong>
        <span>
          {r.address ?? (r.municipality || r.region)}
          {r.is_simulated ? en.simulated : ''}
        </span>
        <div className="queue-keyboard">
          <button
            disabled={disabled || index === 0}
            aria-label={en.moveUp(cleanName(r.name))}
            onClick={() => move(index, index - 1)}
          >
            <ArrowUp size={12} />
          </button>
          <button
            disabled={disabled || index === total - 1}
            aria-label={en.moveDown(cleanName(r.name))}
            onClick={() => move(index, index + 1)}
          >
            <ArrowDown size={12} />
          </button>
        </div>
      </div>
      <Button
        icon
        variant="ghost"
        aria-label={
          favorites.has(r.id)
            ? en.removeFavorite(cleanName(r.name))
            : en.saveFavorite(cleanName(r.name))
        }
        className={favorites.has(r.id) ? 'is-favorite' : ''}
        onClick={() => void favorite(r)}
      >
        <Star size={19} fill={favorites.has(r.id) ? 'currentColor' : 'none'} />
      </Button>
      <Button
        icon
        variant="ghost"
        className="delete-button"
        disabled={disabled}
        aria-label={en.removeFromBooking(cleanName(r.name))}
        onClick={() =>
          void editor.mutate((b) => api.remove(b, r.id)).catch((e) => notice(errorText(e)))
        }
      >
        <Trash2 size={17} />
      </Button>
    </article>
  )
}
export function Queue() {
  const { booking, saving } = useEditor()
  const { notice } = useUI()
  const [clear, setClear] = useState(false),
    [optimistic, setOptimistic] = useState<Restaurant[] | null>(null)
  const disabled = booking?.status !== 'DRAFT' || saving
  const restaurants = optimistic ?? booking?.restaurants.map((e) => e.restaurant) ?? []
  const drop = useDroppable({
    id: 'booking-drop',
    data: { position: restaurants.length },
    disabled,
  })
  useEffect(() => setOptimistic(null), [booking?.version])
  const move = async (from: number, to: number) => {
    if (from === to || disabled) return
    const next = [...restaurants]
    next.splice(to, 0, next.splice(from, 1)[0])
    setOptimistic(next)
    try {
      await editor.mutate((b) =>
        api.order(
          b,
          next.map((r) => r.id),
        ),
      )
    } catch (e) {
      notice(errorText(e))
    } finally {
      setOptimistic(null)
    }
  }
  return (
    <section className="queue-section">
      <div className="section-heading">
        <h2>
          {en.selectedRestaurants} <span>({restaurants.length})</span>
        </h2>
        <Button
          variant="ghost"
          className="delete-button clear-button"
          disabled={disabled || !restaurants.length}
          onClick={() => setClear(true)}
        >
          <Trash2 size={14} />

          {en.clearList}
        </Button>
      </div>
      <div ref={drop.setNodeRef} className="queue-list" data-testid="booking-queue">
        <SortableContext
          items={restaurants.map((r) => `queue:${r.id}`)}
          strategy={verticalListSortingStrategy}
        >
          <DropSlot position={0} disabled={disabled} />
          {restaurants.map((r, i) => (
            <div key={r.id}>
              <QueueItem
                restaurant={r}
                index={i}
                total={restaurants.length}
                disabled={disabled}
                move={(a, b) => void move(a, b)}
              />
              <DropSlot position={i + 1} disabled={disabled} />
            </div>
          ))}
        </SortableContext>
        {!restaurants.length && (
          <div className="queue-empty">
            <div>
              <Utensils size={24} />
              <Plus size={13} />
            </div>
            <strong>{en.yourNextTableStartsHere}</strong>
            <p>{en.selectRestaurantsFromTheMapOrList}</p>
            <span>{en.dragACardHereOrSelectAdd}</span>
          </div>
        )}
      </div>
      <Modal
        open={clear}
        onOpenChange={setClear}
        title={en.clearSelectedRestaurants}
        description={en.theSettingsForThisDraftWillBePreserved}
      >
        <div className="modal-actions">
          <Button onClick={() => setClear(false)}>{en.keepList}</Button>
          <Button
            variant="danger"
            onClick={async () => {
              try {
                await editor.mutate(async (b) => {
                  let next = b
                  for (const entry of b.restaurants)
                    next = await api.remove(next, entry.restaurant.id)
                  return next
                })
                setClear(false)
              } catch (e) {
                await editor.reload().catch(() => {})
                notice(errorText(e))
              }
            }}
          >
            {en.clearList}
          </Button>
        </div>
      </Modal>
    </section>
  )
}
