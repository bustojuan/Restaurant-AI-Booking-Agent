import { en } from '../../i18n/en'
import { useEffect, useRef, useState } from 'react'
import { useDndContext } from '@dnd-kit/core'
import * as maplibregl from 'maplibre-gl'
import type { GeoJSONSource } from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import 'maplibre-gl/dist/maplibre-gl.css'
import { Crosshair, Minus, Plus, Navigation2, Layers } from 'lucide-react'
import { createPortal } from 'react-dom'
import { useUI } from '../../app/context'
import { Button } from '../ui/button'
import { MAP_STYLE, CAMERAS } from './config'
import type { Restaurant } from '../../types/bridge'
import { RestaurantMarker } from './RestaurantMarker'
maplibregl.setWorkerUrl(workerUrl)
export function RestaurantMap({
  restaurants,
  threeD,
  onThreeD,
  onBounds,
}: {
  restaurants: Restaurant[]
  threeD: boolean
  onThreeD: (v: boolean) => void
  onBounds: (region: string, bbox: string) => void
}) {
  const host = useRef<HTMLDivElement>(null),
    map = useRef<maplibregl.Map | null>(null),
    markers = useRef<maplibregl.Marker[]>([])
  const { region, selected, setView } = useUI()
  const { active } = useDndContext()
  const boundsCallback = useRef(onBounds)
  boundsCallback.current = onBounds
  const activeRegion = useRef(region)
  activeRegion.current = region
  const [error, setError] = useState(''),
    [ready, setReady] = useState(false),
    [buildingCount, setBuildingCount] = useState(0)
  const [markerPortals, setMarkerPortals] = useState<
    { restaurant: Restaurant; element: HTMLDivElement }[]
  >([])
  useEffect(() => {
    if (!host.current) return
    let instance: maplibregl.Map
    try {
      instance = new maplibregl.Map({
        container: host.current,
        style: MAP_STYLE,
        ...CAMERAS[region],
        attributionControl: { compact: false },
        maxPitch: 65,
        canvasContextAttributes: { antialias: true },
        renderWorldCopies: false,
      })
      map.current = instance
    } catch {
      setError(en.graphicsAccelerationCouldNotStartYouCanContinue)
      return
    }
    const timeout = setTimeout(() => {
      if (!instance.isStyleLoaded()) setError(en.theMapCouldNotLoadCheckYourConnection)
    }, 18000)
    instance.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-right')
    let boundsTimer: ReturnType<typeof setTimeout>
    const publishBounds = () => {
      clearTimeout(boundsTimer)
      boundsTimer = setTimeout(() => {
        const b = instance.getBounds()
        const west = Math.max(-180, b.getWest()),
          east = Math.min(180, b.getEast())
        const south = Math.max(-90, b.getSouth()),
          north = Math.min(90, b.getNorth())
        if (west < east && south < north)
          boundsCallback.current(
            activeRegion.current,
            [west, south, east, north].map((v) => v.toFixed(5)).join(','),
          )
      }, 350)
    }
    instance.on('moveend', publishBounds)
    instance.on('style.load', () => {
      clearTimeout(timeout)
      setError('')
      for (const layer of instance.getStyle().layers ?? []) {
        if (
          layer.type === 'symbol' &&
          'source-layer' in layer &&
          ['poi', 'housenumber', 'transportation_name', 'waterway'].includes(
            layer['source-layer'] ?? '',
          )
        )
          instance.setLayoutProperty(layer.id, 'visibility', 'none')
        if (layer.type === 'background')
          instance.setPaintProperty(layer.id, 'background-color', '#eeeade')
        if (layer.type === 'fill' && /water/.test(layer.id))
          instance.setPaintProperty(layer.id, 'fill-color', '#a7d4df')
        if (layer.type === 'fill' && /(park|grass|wood|forest)/.test(layer.id))
          instance.setPaintProperty(layer.id, 'fill-color', '#c8d7b0')
        if (layer.type === 'fill' && /building/.test(layer.id))
          instance.setPaintProperty(layer.id, 'fill-color', '#e3dbcd')
      }
      const source = Object.entries(instance.getStyle().sources).find(
        ([, s]) => s.type === 'vector',
      )?.[0]
      if (source) {
        const before = instance
          .getStyle()
          .layers?.find((l) => l.type === 'symbol' && l.layout?.['text-field'])?.id
        instance.addLayer(
          {
            id: 'baria-buildings',
            source,
            'source-layer': 'building',
            type: 'fill-extrusion',
            minzoom: 13,
            paint: {
              'fill-extrusion-color': [
                'interpolate',
                ['linear'],
                ['coalesce', ['get', 'render_height'], 8],
                0,
                '#f4eee1',
                30,
                '#e4dbc9',
                100,
                '#cdc7bb',
              ],
              'fill-extrusion-height': ['coalesce', ['get', 'render_height'], ['get', 'height'], 8],
              'fill-extrusion-base': ['coalesce', ['get', 'render_min_height'], 0],
              'fill-extrusion-vertical-gradient': false,
              'fill-extrusion-opacity': 0.97,
            },
          },
          before,
        )
      }
      instance.addSource('restaurants', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
        cluster: true,
        clusterMaxZoom: 13,
        clusterRadius: 48,
      })
      instance.addLayer({
        id: 'restaurant-clusters',
        type: 'circle',
        source: 'restaurants',
        filter: ['has', 'point_count'],
        paint: {
          'circle-color': '#0866ff',
          'circle-radius': 23,
          'circle-stroke-width': 5,
          'circle-stroke-color': '#ffffff',
        },
      })
      instance.addLayer({
        id: 'restaurant-cluster-count',
        type: 'symbol',
        source: 'restaurants',
        filter: ['has', 'point_count'],
        layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-size': 13 },
        paint: { 'text-color': '#fff' },
      })
      instance.on('click', 'restaurant-clusters', async (e) => {
        const f = e.features?.[0]
        if (!f || f.geometry.type !== 'Point') return
        const zoom = await (
          instance.getSource('restaurants') as GeoJSONSource
        ).getClusterExpansionZoom(Number(f.properties.cluster_id))
        instance.easeTo({ center: f.geometry.coordinates as [number, number], zoom })
      })
      setReady(true)
      publishBounds()
    })
    instance.on('error', (e) => {
      if (!instance.isStyleLoaded()) setError(en.mapUnavailableListViewIsStillAvailable)
      else if (/tile|fetch/i.test(e.error.message)) setError(en.someMapTilesCouldNotLoadCheckYour)
    })
    instance.on('idle', () => {
      const source = Object.entries(instance.getStyle().sources).find(
        ([, s]) => s.type === 'vector',
      )?.[0]
      if (source) {
        const count = instance.querySourceFeatures(source, { sourceLayer: 'building' }).length
        setBuildingCount(count)
      }
    })
    const resize = new ResizeObserver(() => instance.resize())
    resize.observe(host.current)
    const openAttribution = (event: MouseEvent) => {
      const link = event.target instanceof Element ? event.target.closest('a') : null
      if (link instanceof HTMLAnchorElement) {
        event.preventDefault()
        void window.desktop?.openExternal(link.href)
      }
    }
    const container = host.current
    container.addEventListener('click', openAttribution)
    return () => {
      clearTimeout(timeout)
      clearTimeout(boundsTimer)
      resize.disconnect()
      container.removeEventListener('click', openAttribution)
      markers.current.forEach((m) => {
        m.remove()
      })
      markers.current = []
      instance.remove()
      map.current = null
    }
  }, [])
  useEffect(() => {
    map.current?.flyTo({
      ...CAMERAS[region],
      pitch: threeD ? CAMERAS[region].pitch : 0,
      duration: 1100,
      essential: false,
    })
  }, [region])
  useEffect(() => {
    map.current?.easeTo({ pitch: threeD ? 58 : 0, bearing: threeD ? -22 : 0, duration: 450 })
  }, [threeD])
  useEffect(() => {
    if (selected)
      map.current?.flyTo({
        center: [selected.longitude, selected.latitude],
        zoom: 15.3,
        padding: { left: 0, right: 0, top: 80, bottom: 150 },
        duration: 850,
      })
  }, [selected?.id])
  useEffect(() => {
    const instance = map.current
    if (!instance || !ready || active) return
    const previous = new Map(markers.current.map((m) => [m.getElement().dataset.restaurantId, m]))
    const nextMarkers: maplibregl.Marker[] = []
    const source = instance.getSource('restaurants') as GeoJSONSource
    source.setData({
      type: 'FeatureCollection',
      features: restaurants.map((r) => ({
        type: 'Feature',
        properties: { id: r.id },
        geometry: { type: 'Point', coordinates: [r.longitude, r.latitude] },
      })),
    })
    // DOM markers are hidden below cluster zoom; clusters provide the low-zoom view.
    const portals = restaurants.map((r) => {
      let marker = previous.get(r.id)
      if (!marker) {
        const element = document.createElement('div')
        element.dataset.restaurantId = r.id
        marker = new maplibregl.Marker({ element, anchor: 'bottom' })
          .setLngLat([r.longitude, r.latitude])
          .addTo(instance)
      }
      marker.setLngLat([r.longitude, r.latitude])
      previous.delete(r.id)
      nextMarkers.push(marker)
      const el = marker.getElement() as HTMLDivElement
      return { restaurant: r, element: el }
    })
    previous.forEach((m) => m.remove())
    markers.current = nextMarkers
    setMarkerPortals(portals)
    const show = () => {
      markers.current.forEach((m) => {
        m.getElement().style.display = instance.getZoom() >= 14 ? '' : 'none'
      })
    }
    show()
    instance.on('zoom', show)
    return () => {
      instance.off('zoom', show)
    }
  }, [restaurants, ready, active?.id])
  return (
    <>
      {markerPortals.map(({ restaurant, element }) =>
        createPortal(<RestaurantMarker restaurant={restaurant} />, element, restaurant.id),
      )}
      <div
        ref={host}
        className="map-surface"
        data-testid="map"
        data-loaded={ready}
        data-buildings={buildingCount}
      />
      {error && (
        <div className="map-error" role="status">
          <Layers size={17} />
          <span>{error}</span>
          <Button onClick={() => setView('list')}>{en.showList}</Button>
          <Button
            variant="ghost"
            onClick={() => {
              setError('')
              map.current?.setStyle(MAP_STYLE)
              setReady(false)
            }}
          >
            {en.retry}
          </Button>
        </div>
      )}
      <div className="map-controls">
        <Button
          icon
          aria-label={en.resetOrientation}
          onClick={() => map.current?.easeTo({ bearing: 0, pitch: threeD ? 58 : 0 })}
        >
          <Navigation2 size={21} className="compass" />
        </Button>
        <div className="zoom-controls">
          <Button icon aria-label={en.zoomInMap} onClick={() => map.current?.zoomIn()}>
            <Plus size={21} />
          </Button>
          <Button icon aria-label={en.zoomOutMap} onClick={() => map.current?.zoomOut()}>
            <Minus size={21} />
          </Button>
        </div>
        <Button
          icon
          aria-label={en.centerMapOn(region)}
          onClick={() => map.current?.flyTo({ ...CAMERAS[region], pitch: threeD ? 58 : 0 })}
        >
          <Crosshair size={21} />
        </Button>
      </div>
      <div className="map-dimensions">
        <Button className={!threeD ? 'active' : ''} onClick={() => onThreeD(false)}>
          2D
        </Button>
        <Button className={threeD ? 'active' : ''} onClick={() => onThreeD(true)}>
          3D
        </Button>
      </div>
    </>
  )
}
