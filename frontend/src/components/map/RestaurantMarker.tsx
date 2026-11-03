import { en } from '../../i18n/en'
import { useDraggable } from '@dnd-kit/core'
import { Utensils } from 'lucide-react'
import { useEditor, useUI } from '../../app/context'
import { cleanName } from '../../lib/utils'
import type { Restaurant } from '../../types/bridge'

export function RestaurantMarker({ restaurant: r }: { restaurant: Restaurant }) {
  const { booking, saving } = useEditor()
  const { selected, select } = useUI()
  const position = booking?.restaurants.find((e) => e.restaurant.id === r.id)?.position
  const canDrag = booking?.status === 'DRAFT' && position === undefined && !saving
  const drag = useDraggable({
    id: `map:${r.id}`,
    data: { restaurant: r, origin: 'explorer' },
    disabled: !canDrag,
  })
  const calling =
    booking?.summary.current_restaurant?.id === r.id &&
    booking.summary.current_call_status === 'RUNNING'
  return (
    <button
      ref={drag.setNodeRef}
      {...drag.attributes}
      {...drag.listeners}
      aria-disabled={false}
      aria-roledescription={canDrag ? en.draggableMarker : en.restaurantMarker}
      aria-label={en.view(cleanName(r.name))}
      data-testid={`map-pin-${r.id}`}
      title={canDrag ? en.clickToViewDetailsOrDragIntoThe : cleanName(r.name)}
      className={`map-pin ${selected?.id === r.id ? 'selected' : ''} ${position !== undefined ? 'queued' : ''} ${calling ? 'calling' : ''} ${canDrag ? 'can-drag' : ''} ${drag.isDragging ? 'is-dragging' : ''}`}
      onPointerDown={(event) => {
        event.stopPropagation()
        drag.listeners?.onPointerDown?.(event)
      }}
      onMouseDown={(event) => event.stopPropagation()}
      onClick={() => select(r)}
    >
      {position !== undefined ? <span>{position + 1}</span> : <Utensils size={18} />}
    </button>
  )
}
