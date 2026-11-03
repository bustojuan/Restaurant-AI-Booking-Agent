export const MAP_STYLE =
  import.meta.env.VITE_MAP_STYLE ?? 'https://tiles.openfreemap.org/styles/liberty'
export const CAMERAS = {
  Madrid: { center: [-3.7007, 40.4187] as [number, number], zoom: 15.3, bearing: -22, pitch: 58 },
  Navarra: { center: [-1.6435, 42.814] as [number, number], zoom: 15.3, bearing: -18, pitch: 58 },
}
export const MAP_ATTRIBUTION = '© OpenFreeMap · © OpenMapTiles · © OpenStreetMap contributors'
