/** The contiguous United States, drawn once at module load from Natural Earth's
 *  110m country outlines (the `world-atlas` package this project already uses
 *  for the globe). Alaska, Hawaii and the territories are dropped so the shape
 *  fills its box: this is decoration on the flight ticket, not a real map, and
 *  the flight data behind it is US domestic anyway.
 *
 *  Projected by hand — longitude squeezed by cos(38°) so the country is not
 *  stretched sideways the way a raw lon/lat plot leaves it.
 */
import { feature } from 'topojson-client'
import type { Topology } from 'topojson-specification'
import countries110m from 'world-atlas/countries-110m.json'

type LngLat = [number, number]
const K = Math.cos((38 * Math.PI) / 180)
const project = ([lon, lat]: LngLat): LngLat => [lon * K, -lat]
const inside = ([lon, lat]: LngLat) => lon > -126 && lon < -66 && lat > 23 && lat < 51

const { d, box } = (() => {
  const topo = countries110m as unknown as Topology
  const fc = feature(topo, topo.objects.countries) as GeoJSON.FeatureCollection
  const us = fc.features.find(f => f.id === '840')
  const geom = us?.geometry as GeoJSON.MultiPolygon | GeoJSON.Polygon | undefined
  const polys = !geom ? [] : geom.type === 'Polygon' ? [geom.coordinates] : geom.coordinates

  const kept: LngLat[][] = []
  for (const poly of polys) {
    for (const ring of poly) {
      const pts = ring as LngLat[]
      // Keep a ring only if it is mostly in the lower 48; that drops Alaska,
      // Hawaii and the Caribbean without clipping the mainland coastline.
      if (pts.filter(inside).length > pts.length * 0.8) kept.push(pts.map(project))
    }
  }

  let [x0, y0, x1, y1] = [Infinity, Infinity, -Infinity, -Infinity]
  for (const ring of kept) for (const [x, y] of ring) {
    x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y)
  }
  const path = kept
    .map(ring => ring.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(2)} ${y.toFixed(2)}`).join('') + 'Z')
    .join('')
  return { d: path, box: { x0, y0, w: x1 - x0, h: y1 - y0 } }
})()

/** Hubs, so the outline reads as an airline map rather than a country. */
const HUBS: { code: string; at: LngLat }[] = [
  { code: 'SEA', at: [-122.31, 47.45] },
  { code: 'PDX', at: [-122.60, 45.59] },
  { code: 'SFO', at: [-122.38, 37.62] },
  { code: 'LAX', at: [-118.41, 33.94] },
  { code: 'SAN', at: [-117.19, 32.73] },
  { code: 'LAS', at: [-115.15, 36.08] },
  { code: 'PHX', at: [-112.01, 33.43] },
  { code: 'SLC', at: [-111.98, 40.79] },
  { code: 'DEN', at: [-104.67, 39.86] },
  { code: 'DFW', at: [-97.04, 32.90] },
  { code: 'IAH', at: [-95.34, 29.98] },
  { code: 'MSP', at: [-93.22, 44.88] },
  { code: 'STL', at: [-90.37, 38.75] },
  { code: 'ORD', at: [-87.90, 41.98] },
  { code: 'BNA', at: [-86.68, 36.12] },
  { code: 'ATL', at: [-84.43, 33.64] },
  { code: 'DTW', at: [-83.35, 42.21] },
  { code: 'MCO', at: [-81.31, 28.43] },
  { code: 'CLT', at: [-80.94, 35.21] },
  { code: 'MIA', at: [-80.29, 25.79] },
  { code: 'DCA', at: [-77.04, 38.85] },
  { code: 'PHL', at: [-75.24, 39.87] },
  { code: 'JFK', at: [-73.78, 40.64] },
  { code: 'BOS', at: [-71.01, 42.36] },
]
const LINKS: [string, string][] = [
  ['LAX', 'JFK'], ['SEA', 'ORD'], ['DFW', 'MIA'], ['SFO', 'DEN'],
  ['PHX', 'DTW'], ['LAS', 'MSP'], ['SAN', 'IAH'], ['BOS', 'ORD'],
  ['ATL', 'LAX'], ['PDX', 'SLC'], ['MCO', 'PHL'], ['BNA', 'DCA'],
  ['STL', 'CLT'],
]

const at = (code: string) => project(HUBS.find(h => h.code === code)!.at)

/** Bow the line away from the straight path so it reads as a flight, not a chord. */
function arc(a: LngLat, b: LngLat) {
  const [mx, my] = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
  const [dx, dy] = [b[0] - a[0], b[1] - a[1]]
  const lift = 0.14
  return `M${a[0]} ${a[1]} Q${mx + dy * lift} ${my - dx * lift} ${b[0]} ${b[1]}`
}

export function UsMap({ className = '' }: { className?: string }) {
  return (
    <svg
      viewBox={`${box.x0} ${box.y0} ${box.w} ${box.h}`}
      className={className}
      fill="none"
      aria-hidden
    >
      <path d={d} className="fill-stone-900/[0.07] stroke-stone-900/25" strokeWidth={0.18} />
      {LINKS.map(([a, b], i) => (
        <path
          key={a + b}
          d={arc(at(a), at(b))}
          className="sl-arc stroke-sky-800/40"
          strokeWidth={0.14}
          style={{ animationDelay: `${(i % 5) * 0.4}s`, animationDuration: `${2.2 + (i % 3) * 0.6}s` }}
        />
      ))}
      {HUBS.map((h, i) => {
        const [x, y] = project(h.at)
        return (
          <circle
            key={h.code}
            cx={x}
            cy={y}
            r={0.26}
            className="sl-pulse fill-sky-800"
            style={{ animationDelay: `${(i % 7) * 0.45}s` }}
          />
        )
      })}
    </svg>
  )
}
