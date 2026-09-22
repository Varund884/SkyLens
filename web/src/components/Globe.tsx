/** A slowly turning Earth on a canvas, with airliners tracing great-circle
 *  routes between real cities.
 *
 *  Continents come from Natural Earth's 110m land outlines (the `world-atlas`
 *  package), projected orthographically by hand: no WebGL, no map tiles, about
 *  56 KB of coastline. North American airports are drawn on top from the live
 *  API, coloured by how much is reported there, because that is what this site
 *  is about.
 *
 *  `progress` (0 to 1) is the page's scroll position. It speeds the spin up,
 *  tilts the globe and brightens the flight paths, so scrolling feels like
 *  pulling away from the planet rather than merely fading it out.
 */
import { useEffect, useRef } from 'react'
import { feature } from 'topojson-client'
import type { Topology } from 'topojson-specification'
import land110m from 'world-atlas/land-110m.json'
import { api, type AirportPin } from '../api'

const RAD = Math.PI / 180
type LngLat = [number, number]

const LAND: LngLat[][] = (() => {
  const geo = feature(land110m as unknown as Topology, (land110m as unknown as Topology).objects.land) as
    GeoJSON.FeatureCollection<GeoJSON.MultiPolygon | GeoJSON.Polygon>
  const rings: LngLat[][] = []
  for (const f of geo.features) {
    const polys = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates
    for (const poly of polys) for (const ring of poly) rings.push(ring as LngLat[])
  }
  return rings
})()

/** Busy real-world routes, so the sky looks alive rather than decorated. */
const ROUTES: { from: LngLat; to: LngLat; offset: number; speed: number }[] = [
  { from: [-79.63, 43.68], to: [-118.24, 34.05], offset: 0.00, speed: 1.00 },   // Toronto - Los Angeles
  { from: [-73.78, 40.64], to: [-0.45, 51.47], offset: 0.35, speed: 0.80 },     // New York - London
  { from: [-123.18, 49.19], to: [140.39, 35.76], offset: 0.60, speed: 0.65 },   // Vancouver - Tokyo
  { from: [-99.07, 19.44], to: [-58.54, -34.82], offset: 0.15, speed: 0.85 },   // Mexico City - Buenos Aires
  { from: [2.55, 49.01], to: [55.36, 25.25], offset: 0.45, speed: 0.95 },       // Paris - Dubai
  { from: [103.99, 1.36], to: [151.18, -33.94], offset: 0.72, speed: 0.90 },    // Singapore - Sydney
  { from: [28.04, -26.13], to: [4.76, 52.31], offset: 0.25, speed: 0.70 },      // Johannesburg - Amsterdam
  { from: [-87.90, 41.98], to: [-46.47, -23.43], offset: 0.85, speed: 0.75 },   // Chicago - Sao Paulo
  { from: [77.10, 28.57], to: [-0.45, 51.47], offset: 0.05, speed: 0.88 },      // Delhi - London
  { from: [116.60, 40.08], to: [-122.38, 37.62], offset: 0.50, speed: 0.60 },   // Beijing - San Francisco
]

function along(a: LngLat, b: LngLat, f: number): LngLat {
  const [lo1, la1, lo2, la2] = [a[0] * RAD, a[1] * RAD, b[0] * RAD, b[1] * RAD]
  const d = 2 * Math.asin(Math.sqrt(Math.sin((la2 - la1) / 2) ** 2 +
    Math.cos(la1) * Math.cos(la2) * Math.sin((lo2 - lo1) / 2) ** 2))
  if (!d) return a
  const A = Math.sin((1 - f) * d) / Math.sin(d)
  const B = Math.sin(f * d) / Math.sin(d)
  const x = A * Math.cos(la1) * Math.cos(lo1) + B * Math.cos(la2) * Math.cos(lo2)
  const y = A * Math.cos(la1) * Math.sin(lo1) + B * Math.cos(la2) * Math.sin(lo2)
  const z = A * Math.sin(la1) + B * Math.sin(la2)
  return [Math.atan2(y, x) / RAD, Math.atan2(z, Math.hypot(x, y)) / RAD]
}

type Star = { x: number; y: number; r: number; a: number; twinkle: number }

export default function Globe({ className = '', progress = 0 }: { className?: string; progress?: number }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const airports = useRef<AirportPin[]>([])
  const scroll = useRef(0)

  scroll.current = progress

  useEffect(() => {
    let alive = true
    api.airports().then(rows => { if (alive) airports.current = rows }).catch(() => {})
    return () => { alive = false }
  }, [])

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')!
    const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let raf = 0
    let spin = -100
    let stars: Star[] = []

    const resize = () => {
      const r = canvas.getBoundingClientRect()
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      canvas.width = r.width * dpr
      canvas.height = r.height * dpr
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      // Fewer stars and simpler strokes on a phone: the canvas redraws every
      // frame, and a mid-range phone should not be asked to do desktop work.
      const starCount = r.width < 640 ? 90 : 220
      stars = Array.from({ length: starCount }, () => ({
        x: Math.random() * r.width, y: Math.random() * r.height,
        r: Math.random() * 1.2 + 0.2, a: Math.random() * 0.5 + 0.2,
        twinkle: Math.random() * 6,
      }))
    }
    resize()
    window.addEventListener('resize', resize)

    const draw = (t: number) => {
      const w = canvas.clientWidth
      const h = canvas.clientHeight
      const p = scroll.current
      const cx = w / 2
      const cy = h / 2 + p * h * 0.12                      // sinks slightly as you scroll
      const small = w < 640
      const R = Math.min(w, h) * ((small ? 0.40 : 0.36) + p * 0.10)         // and grows
      const tilt = 16 + p * 18                             // and tips away
      ctx.clearRect(0, 0, w, h)

      // starfield, drifting with scroll
      for (const s of stars) {
        const a = s.a * (0.6 + 0.4 * Math.sin(t / 900 + s.twinkle))
        ctx.fillStyle = `rgba(226,232,240,${a * (1 - p * 0.5)})`
        ctx.beginPath()
        ctx.arc(s.x, (s.y - p * 120 + h) % h, s.r, 0, 7)
        ctx.fill()
      }

      const project = (lon: number, lat: number) => {
        const phi = lat * RAD
        const lam = (lon - spin) * RAD
        const tp = tilt * RAD
        const x = Math.cos(phi) * Math.sin(lam)
        const y = Math.cos(tp) * Math.sin(phi) - Math.sin(tp) * Math.cos(phi) * Math.cos(lam)
        const z = Math.sin(tp) * Math.sin(phi) + Math.cos(tp) * Math.cos(phi) * Math.cos(lam)
        return { x: cx + R * x, y: cy - R * y, visible: z > 0, depth: z }
      }

      // atmosphere
      const glow = ctx.createRadialGradient(cx, cy, R * 0.85, cx, cy, R * 1.6)
      glow.addColorStop(0, `rgba(56,189,248,${0.22 + p * 0.1})`)
      glow.addColorStop(1, 'rgba(2,6,23,0)')
      ctx.fillStyle = glow
      ctx.beginPath(); ctx.arc(cx, cy, R * 1.6, 0, 7); ctx.fill()

      // ocean, lit from the upper left
      const sea = ctx.createRadialGradient(cx - R * 0.4, cy - R * 0.45, R * 0.05, cx, cy, R)
      sea.addColorStop(0, '#173a5e')
      sea.addColorStop(0.65, '#0d2340')
      sea.addColorStop(1, '#07172c')
      ctx.fillStyle = sea
      ctx.beginPath(); ctx.arc(cx, cy, R, 0, 7); ctx.fill()

      // graticule
      ctx.strokeStyle = 'rgba(148,163,184,0.13)'
      ctx.lineWidth = 1
      const step = small ? 6 : 3
      for (let lat = -60; lat <= 60; lat += 30) {
        ctx.beginPath()
        let started = false
        for (let lon = -180; lon <= 180; lon += step) {
          const q = project(lon, lat)
          if (!q.visible) { started = false; continue }
          started ? ctx.lineTo(q.x, q.y) : (ctx.moveTo(q.x, q.y), started = true)
        }
        ctx.stroke()
      }
      for (let lon = -180; lon < 180; lon += 30) {
        ctx.beginPath()
        let started = false
        for (let lat = -90; lat <= 90; lat += step) {
          const q = project(lon, lat)
          if (!q.visible) { started = false; continue }
          started ? ctx.lineTo(q.x, q.y) : (ctx.moveTo(q.x, q.y), started = true)
        }
        ctx.stroke()
      }

      // land
      ctx.fillStyle = 'rgba(34,73,96,0.92)'
      ctx.strokeStyle = 'rgba(94,234,212,0.35)'
      ctx.lineWidth = 0.7
      for (const ring of LAND) {
        ctx.beginPath()
        let started = false
        for (const [lon, lat] of ring) {
          const q = project(lon, lat)
          if (!q.visible) { started = false; continue }
          started ? ctx.lineTo(q.x, q.y) : (ctx.moveTo(q.x, q.y), started = true)
        }
        ctx.closePath(); ctx.fill(); ctx.stroke()
      }

      // North American airports from the live data
      for (const a of airports.current) {
        if (small && a.occurrences === 0) continue
        const q = project(a.longitude, a.latitude)
        if (!q.visible) continue
        const n = a.occurrences
        ctx.fillStyle = n > 300 ? `rgba(248,113,113,${0.4 + q.depth * 0.6})`
          : n > 50 ? `rgba(251,146,60,${0.35 + q.depth * 0.6})`
          : n > 0 ? `rgba(250,204,21,${0.3 + q.depth * 0.55})`
          : `rgba(125,211,252,${0.12 + q.depth * 0.35})`
        ctx.beginPath(); ctx.arc(q.x, q.y, n > 0 ? 1 + Math.sqrt(n) * 0.13 : 0.7, 0, 7); ctx.fill()
      }

      // flight paths and aircraft
      for (const r of (small ? ROUTES.slice(0, 5) : ROUTES)) {
        const path: { x: number; y: number; visible: boolean }[] = []
        for (let f = 0; f <= 1.0001; f += small ? 0.04 : 0.02) {
          const [lon, lat] = along(r.from, r.to, f)
          path.push(project(lon, lat))
        }
        ctx.strokeStyle = `rgba(56,189,248,${0.18 + p * 0.35})`
        ctx.lineWidth = 1
        ctx.setLineDash([3, 6])
        ctx.beginPath()
        let started = false
        for (const q of path) {
          if (!q.visible) { started = false; continue }
          started ? ctx.lineTo(q.x, q.y) : (ctx.moveTo(q.x, q.y), started = true)
        }
        ctx.stroke()
        ctx.setLineDash([])

        const f = ((t / 16000) * r.speed + r.offset) % 1
        const [lon, lat] = along(r.from, r.to, f)
        const now = project(lon, lat)
        if (!now.visible) continue
        const [lon2, lat2] = along(r.from, r.to, Math.min(f + 0.015, 1))
        const next = project(lon2, lat2)

        // comet trail behind the aircraft
        const trail = ctx.createLinearGradient(now.x, now.y, next.x, next.y)
        trail.addColorStop(0, 'rgba(125,211,252,0)')
        trail.addColorStop(1, 'rgba(186,230,253,0.8)')
        ctx.strokeStyle = trail
        ctx.lineWidth = 1.6
        ctx.beginPath()
        for (let k = small ? 5 : 8; k >= 0; k--) {
          const [tl, ta] = along(r.from, r.to, Math.max(f - k * 0.012, 0))
          const q = project(tl, ta)
          k === (small ? 5 : 8) ? ctx.moveTo(q.x, q.y) : ctx.lineTo(q.x, q.y)
        }
        ctx.stroke()

        ctx.save()
        ctx.translate(now.x, now.y)
        ctx.rotate(Math.atan2(next.y - now.y, next.x - now.x))
        ctx.fillStyle = '#f0f9ff'
        ctx.shadowColor = 'rgba(56,189,248,0.9)'
        ctx.shadowBlur = 8
        ctx.beginPath()
        ctx.moveTo(6, 0); ctx.lineTo(-2.5, 3); ctx.lineTo(-0.8, 0); ctx.lineTo(-2.5, -3)
        ctx.closePath(); ctx.fill()
        ctx.restore()
        ctx.shadowBlur = 0
      }

      // rim light
      ctx.strokeStyle = `rgba(125,211,252,${0.35 + p * 0.3})`
      ctx.lineWidth = 1.2
      ctx.beginPath(); ctx.arc(cx, cy, R, 0, 7); ctx.stroke()

      if (!still) spin = (spin + 0.045 + p * 0.5) % 360        // scrolling spins it faster
      // Past the hero the globe is invisible, so stop burning frames on it.
      raf = requestAnimationFrame(p >= 0.999 ? idle : draw)
    }
    const idle = () => {
      raf = requestAnimationFrame(scroll.current >= 0.999 ? idle : draw)
    }
    raf = requestAnimationFrame(draw)
    return () => { cancelAnimationFrame(raf); window.removeEventListener('resize', resize) }
  }, [])

  return <canvas ref={ref} className={className} aria-hidden />
}
