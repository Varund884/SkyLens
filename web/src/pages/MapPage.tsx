/** Map of US and Canadian airports.
 *
 * Only the airports inside the current view are fetched, the way a game only
 * draws what the camera sees: 36,132 airports would be pointless to send and
 * slow to draw. Requests wait until panning stops, and TanStack Query caches
 * each view, so going back to an area you already looked at is instant.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CircleMarker, MapContainer, TileLayer, Tooltip, ZoomControl, useMap, useMapEvents } from 'react-leaflet'
import { useQuery } from '@tanstack/react-query'
import { api, type AirportPin } from '../api'
import { Spinner } from '../components/ui'

type Box = { north: number; south: number; east: number; west: number }

const round = (n: number) => Math.round(n * 100) / 100   // stable cache keys while panning

/** Colour by rate, not by count: a busy airport has more of everything. */
function colour(p: AirportPin) {
  if (p.rate_per_10k == null) return p.occurrences > 0 ? '#475569' : '#94a3b8'
  if (p.rate_per_10k >= 40) return '#dc2626'
  if (p.rate_per_10k >= 25) return '#f97316'
  if (p.rate_per_10k >= 12) return '#eab308'
  return '#16a34a'
}

const radius = (p: AirportPin) =>
  p.occurrences === 0 ? 2.5 : Math.min(5 + Math.sqrt(p.occurrences) * 0.9, 17)

function ViewWatcher({ onChange }: { onChange: (b: Box) => void }) {
  const map = useMap()
  const send = useCallback(() => {
    const b = map.getBounds()
    onChange({ north: round(b.getNorth()), south: round(b.getSouth()), east: round(b.getEast()), west: round(b.getWest()) })
  }, [map, onChange])
  useMapEvents({ moveend: send, zoomend: send })
  useEffect(() => { send() }, [send])
  return null
}

export default function MapPage({ embedded = false }: { embedded?: boolean } = {}) {
  const [box, setBox] = useState<Box | null>(null)
  const [search, setSearch] = useState('')
  // On a phone the legend would cover the map, so it starts collapsed there.
  const [legendOpen, setLegendOpen] = useState(() => window.innerWidth >= 640)
  const navigate = useNavigate()

  // Debounce: dragging fires many move events, but only the last one matters.
  const [debounced, setDebounced] = useState<Box | null>(null)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(box), 300)
    return () => clearTimeout(t)
  }, [box])

  const { data, isFetching, error } = useQuery({
    queryKey: ['airports', debounced],
    queryFn: () => api.airports(debounced ?? undefined),
    staleTime: 5 * 60 * 1000,
    placeholderData: prev => prev,
  })

  const pins = data ?? []
  const withReports = useMemo(() => pins.filter(p => p.has_report), [pins])

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const q = search.trim().toUpperCase()
    if (q) navigate(`/airport/${q}`)
  }

  return (
    <div className="relative">
      <div className="absolute left-3 top-3 z-[1000] w-[min(20rem,calc(100%-1.5rem))] space-y-2">
        <form onSubmit={submit} className="flex gap-2 rounded-xl border border-slate-800 bg-slate-900/70 p-2 shadow-sm">
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Airport code, e.g. CYYZ"
            className="w-full rounded-lg border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-100 placeholder:text-slate-500 outline-none focus:border-sky-400"
          />
          <button className="rounded bg-slate-900 px-3 py-1 text-sm text-white">Go</button>
        </form>
        <button
          onClick={() => setLegendOpen(o => !o)}
          className="w-full rounded-xl border border-slate-800 bg-slate-900/80 px-3 py-2 text-left text-xs text-slate-300 shadow-sm sm:hidden"
        >
          {legendOpen ? 'Hide legend' : 'Show legend'} · {isFetching ? 'loading…' : `${pins.length} airports`}
        </button>
        <div className={`${legendOpen ? 'block' : 'hidden'} rounded-xl border border-slate-800 bg-slate-900/80 p-3 text-xs shadow-sm backdrop-blur sm:block`}>
          {embedded && (
            <div className="mb-2 rounded bg-slate-800 px-2 py-1 text-[11px] text-slate-300">
              Scrolling moves the page here. Zoom with + and −, or open the full map.
            </div>
          )}
          <div className="mb-2 font-medium text-slate-200">
            Occurrences per 10,000 aircraft movements
          </div>
          {[['#16a34a', 'under 12'], ['#eab308', '12 to 25'], ['#f97316', '25 to 40'], ['#dc2626', '40 or more'],
            ['#475569', 'no official traffic count'], ['#94a3b8', 'nothing reported']].map(([c, label]) => (
            <div key={label} className="flex items-center gap-2 py-0.5 text-slate-300">
              <span className="inline-block h-3 w-3 rounded-full ring-1 ring-white" style={{ background: c }} />
              {label}
            </div>
          ))}
          <div className="mt-2 border-t pt-2 text-slate-400">
            {isFetching ? 'Loading this area…' : `${pins.length} airports here, ${withReports.length} with a report`}
          </div>
          <div className="mt-2 rounded bg-amber-500/10 p-2 text-[11px] leading-snug text-amber-200">
            <b>Compare within a country, not across the border.</b> Canada records every reportable
            occurrence, including bird sightings and go-arounds; the United States records only
            accidents and serious incidents. Canadian airports therefore look busier here for
            reasons of paperwork, not safety.
          </div>
        </div>
        {error && (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200 shadow-sm">
            Could not load airports. The database pauses when idle; try again in a moment.
          </div>
        )}
      </div>

      {/* Embedded in the landing page the wheel must scroll the page, not zoom
          the map, or you get trapped. Zoom with the buttons or hold Command. */}
      <MapContainer
        center={[47, -95]} zoom={4} minZoom={3}
        scrollWheelZoom={!embedded}
        zoomControl={false}
        className={embedded ? 'h-[70svh] w-full sm:h-[85vh]' : 'h-[calc(100svh-57px)] w-full'}
      >
        {/* OpenStreetMap's own tiles: free and keyless. CARTO's "light" basemap
            looks better but now watermarks every tile unless you buy a key. */}
        {/* Top-left belongs to the search panel, so the zoom buttons move across. */}
        <ZoomControl position="topright" />
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          maxZoom={19}
        />
        <ViewWatcher onChange={setBox} />
        {pins.map(p => (
          <CircleMarker
            key={p.ident}
            center={[p.latitude, p.longitude]}
            radius={radius(p)}
            pathOptions={{ color: '#ffffff', fillColor: colour(p), fillOpacity: 0.95, weight: 1.5 }}
            eventHandlers={{ click: () => p.has_report && navigate(`/airport/${p.ident}`) }}
          >
            <Tooltip>
              <div className="text-xs">
                <div className="font-medium">{p.name}</div>
                <div className="text-slate-400">{p.ident}{p.municipality ? ` · ${p.municipality}` : ''}</div>
                <div className="mt-1">
                  {p.occurrences === 0
                    ? 'No occurrences reported in the last 12 months'
                    : <>{p.occurrences} occurrence{p.occurrences === 1 ? '' : 's'}
                        {p.rate_per_10k != null
                          ? ` · ${p.rate_per_10k} per 10,000 movements`
                          : ' · no official traffic count'}</>}
                </div>
                {p.has_report && <div className="mt-1 text-sky-400">Click for the full report</div>}
              </div>
            </Tooltip>
          </CircleMarker>
        ))}
      </MapContainer>

      {isFetching && !data && (
        <div className="absolute inset-0 z-[900] grid place-items-center bg-slate-950/70">
          <Spinner label="Loading airports" />
        </div>
      )}
    </div>
  )
}
