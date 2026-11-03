import { en } from '../i18n/en'
import { useState, useEffect, useRef } from 'react'
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  pointerWithin,
  closestCenter,
  MeasuringStrategy,
  type DragEndEvent,
  type DragOverEvent,
} from '@dnd-kit/core'
import { sortableKeyboardCoordinates, arrayMove } from '@dnd-kit/sortable'
import { MotionConfig } from 'motion/react'
import { InsertionContext } from './drag'
import { Header } from '../components/navigation/Header'
import { Explorer } from '../components/restaurants/Explorer'
import { BookingSidebar } from '../components/booking/BookingSidebar'
import { ExecutionDetail } from '../components/reservations/ExecutionDetail'
import { RestaurantImage } from '../components/shared/RestaurantImage'
import { Providers, useUI } from './context'
import { editor } from '../services/editor'
import { api, errorText } from '../services/api'
import { cleanName } from '../lib/utils'
import type { Restaurant } from '../types/bridge'
function DesktopApp() {
  const { notice } = useUI()
  const pointer = useRef<{ x: number; y: number } | null>(null)
  useEffect(() => {
    const track = (event: PointerEvent) => {
      pointer.current = { x: event.clientX, y: event.clientY }
    }
    document.addEventListener('pointermove', track, true)
    return () => document.removeEventListener('pointermove', track, true)
  }, [])
  const [detail, setDetail] = useState<string | null>(null),
    [drag, setDrag] = useState<Restaurant | null>(null),
    [insertAt, setInsertAt] = useState<number | null>(null)
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )
  const insertion = (e: DragOverEvent | DragEndEvent) => {
    if (e.over && String(e.over.id).startsWith('slot:')) {
      const position = e.over.data.current?.position
      if (typeof position === 'number') return position
    }
    if (
      'clientY' in e.activatorEvent &&
      typeof e.activatorEvent.clientY === 'number' &&
      'clientX' in e.activatorEvent &&
      typeof e.activatorEvent.clientX === 'number'
    ) {
      // DnD delta includes scroll compensation; insertion needs the physical pointer.
      const { x, y } = pointer.current ?? {
        x: e.activatorEvent.clientX + e.delta.x,
        y: e.activatorEvent.clientY + e.delta.y,
      }
      const list = document.querySelector('.queue-list'),
        bounds = list?.getBoundingClientRect()
      if (
        !bounds ||
        x < bounds.left ||
        x > bounds.right ||
        y < bounds.top - 8 ||
        y > bounds.bottom + 8
      )
        return null
      const rows = Array.from(list!.querySelectorAll('.queue-item'))
      const index = rows.findIndex((row) => {
        const rect = row.getBoundingClientRect()
        return y < rect.top + rect.height / 2
      })
      return index < 0 ? rows.length : index
    }
    if (!e.over) return null
    const pos = e.over.data.current?.position
    return typeof pos === 'number' ? pos : null
  }
  const end = async (e: DragEndEvent) => {
    setDrag(null)
    setInsertAt(null)
    if (!e.over) return
    const b = editor.snapshot().booking
    if (!b || b.status !== 'DRAFT') return
    const r = e.active.data.current?.restaurant as Restaurant | undefined
    if (!r) return
    const origin = e.active.data.current?.origin
    try {
      if (origin === 'queue') {
        const from = b.restaurants.findIndex((q) => q.restaurant.id === r.id)
        const target = e.over.data.current?.position
        if (typeof target !== 'number') return
        const to = String(e.over.id).startsWith('slot:')
          ? Math.max(0, Math.min(b.restaurants.length - 1, target > from ? target - 1 : target))
          : target
        if (from !== to)
          await editor.mutate((latest) =>
            api.order(
              latest,
              arrayMove(
                latest.restaurants.map((q) => q.restaurant.id),
                from,
                to,
              ),
            ),
          )
      } else {
        if (b.restaurants.some((q) => q.restaurant.id === r.id)) {
          notice(en.thisRestaurantIsAlreadyInTheBooking)
          return
        }
        const position = insertion(e)
        if (position === null) return
        await editor.mutate((latest) => api.insert(latest, r.id, position))
        notice(en.restaurantAddedAtPosition(position + 1))
      }
    } catch (error) {
      notice(errorText(error))
    }
  }
  return (
    <MotionConfig reducedMotion="user">
      <DndContext
        sensors={sensors}
        measuring={{ droppable: { strategy: MeasuringStrategy.Always } }}
        collisionDetection={(args) => {
          if (!args.pointerCoordinates) return closestCenter(args)
          const hits = pointerWithin(args)
          return hits.sort(
            (a, b) =>
              Number(String(b.id).startsWith('slot:')) - Number(String(a.id).startsWith('slot:')) ||
              Number(a.id === 'booking-drop') - Number(b.id === 'booking-drop'),
          )
        }}
        onDragStart={(e) => setDrag(e.active.data.current?.restaurant ?? null)}
        onDragOver={(e) => setInsertAt(insertion(e))}
        onDragCancel={() => {
          setDrag(null)
          setInsertAt(null)
        }}
        onDragEnd={(e) => void end(e)}
      >
        <InsertionContext.Provider value={insertAt}>
          <div
            className={`desktop-app ${drag ? 'drag-active' : ''}`}
            data-insert-at={insertAt ?? ''}
          >
            <Header onDetail={setDetail} />
            <main>
              <Explorer />
              <BookingSidebar onTrack={setDetail} />
            </main>
          </div>
        </InsertionContext.Provider>
        <DragOverlay dropAnimation={{ duration: 180, easing: 'ease-out' }}>
          {drag && (
            <div className="drag-preview">
              <RestaurantImage restaurant={drag} />
              <div>
                <strong>{cleanName(drag.name)}</strong>
                <span>{en.dropAtTheDesiredPosition}</span>
              </div>
            </div>
          )}
        </DragOverlay>
      </DndContext>
      <ExecutionDetail id={detail} onClose={() => setDetail(null)} />
    </MotionConfig>
  )
}
export function App() {
  return (
    <Providers>
      <DesktopApp />
    </Providers>
  )
}
