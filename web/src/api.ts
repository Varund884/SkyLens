/** Types and fetch helpers for the SkyLens API. Mirrors api/models.py. */

export interface AirportPin {
  ident: string
  name: string
  municipality: string | null
  country: string
  airport_type: string
  latitude: number
  longitude: number
  occurrences: number
  rate_per_10k: number | null
  has_report: boolean
}

export interface TrendPoint { month: string; occurrences: number; rolling_3m: number }
export interface CategoryCount { code: string; occurrences: number }
export interface ThemeCount { label: string; occurrences: number }

export interface AirportReport {
  ident: string
  name: string
  municipality: string | null
  country: string
  airport_type: string
  latitude: number
  longitude: number
  occurrences: number
  accidents: number
  fatalities: number
  severity: Record<string, number>
  movements: number | null
  movement_source: string | null
  movement_is_estimated: boolean | null
  rate_per_10k: number | null
  rate_change_pct_h2_vs_h1: number | null
  trend: TrendPoint[]
  categories: CategoryCount[]
  categories_predicted: number
  themes: ThemeCount[]
  seasonality: { month: string; hour: number; n: number }[]
  peer_median_rate_per_10k: number | null
  peer_group?: string
  peer_count?: number
  operations?: {
    flights: number
    cancelled_pct: number
    delayed_over_15_pct: number
    avg_departure_delay_min: number | null
  }
  summary: string | null
  generated_at: string
}

export interface Occurrence {
  occurrence_key: number
  date: string
  time_utc: string | null
  authority: string
  source_record_id: string
  occurrence_type: string | null
  category_code: string | null
  category_label: string | null
  category_is_predicted: boolean
  category_confidence: number | null
  severity_tier: string | null
  fatalities: number | null
  injuries: number | null
  aircraft_count: number | null
  flight_number: string | null
  registration: string | null
  operator_name: string | null
  summary: string | null
  citation_ids: string[]
  theme: string | null
}

export interface OccurrencePage { total: number; offset: number; limit: number; items: Occurrence[] }

export interface FlightLeg {
  date: string
  origin: string | null
  destination: string | null
  scheduled_departure: string | null
  actual_departure: string | null
  departure_delay_min: number | null
  arrival_delay_min: number | null
  cancelled: boolean
  cancellation_reason: string | null
  diverted: boolean
  tail_number: string | null
}

export interface FlightHistory {
  flight_number: string
  operator: string | null
  legs_found: number
  on_time_pct: number | null
  cancelled_pct: number | null
  median_departure_delay_min: number | null
  worst_delay_min: number | null
  routes: string[]
  legs: FlightLeg[]
}

export interface Category { code: string; label: string; occurrences: number }

const BASE = import.meta.env.VITE_API_URL ?? '/api'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`)
  if (!r.ok) {
    const body = await r.json().catch(() => ({}))
    throw new ApiError(r.status, typeof body.detail === 'string' ? body.detail : r.statusText)
  }
  return r.json() as Promise<T>
}

export const api = {
  airports: (b?: { north: number; south: number; east: number; west: number }) =>
    get<AirportPin[]>(b ? `/airports?north=${b.north}&south=${b.south}&east=${b.east}&west=${b.west}` : '/airports'),
  report: (ident: string) => get<AirportReport>(`/airports/${ident}/report`),
  occurrences: (ident: string, opts: { offset?: number; limit?: number; category?: string } = {}) => {
    const q = new URLSearchParams({ offset: String(opts.offset ?? 0), limit: String(opts.limit ?? 25) })
    if (opts.category) q.set('category', opts.category)
    return get<OccurrencePage>(`/airports/${ident}/occurrences?${q}`)
  },
  flight: (number: string) => get<FlightHistory>(`/flights/${encodeURIComponent(number)}`),
  categories: () => get<Category[]>('/categories'),
}

/** Category codes are jargon; these are the plain labels the pages show. */
export const CATEGORY_NAMES: Record<string, string> = {
  ARC: 'Hard or abnormal landing', AMAN: 'Abrupt manoeuvre', ADRM: 'Aerodrome',
  ATM: 'Air traffic service', BIRD: 'Bird strike', CABIN: 'Cabin safety',
  CFIT: 'Flew into terrain', CTOL: 'Hit obstacle on takeoff or landing',
  EVAC: 'Evacuation', EXTL: 'External load', 'F-NI': 'Fire or smoke',
  'F-POST': 'Fire after impact', FUEL: 'Fuel problem', GCOL: 'Ground collision',
  GTOW: 'Glider towing', ICE: 'Icing', LALT: 'Low-altitude flying',
  'LOC-G': 'Lost control on the ground', 'LOC-I': 'Lost control in flight',
  LOLI: 'Loss of lift', MAC: 'Loss of separation', MED: 'Medical',
  NAV: 'Navigation error', OTHR: 'Other', RAMP: 'Ground handling',
  RE: 'Ran off the runway', RI: 'Runway incursion',
  'SCF-NP': 'System or component failure', 'SCF-PP': 'Engine failure',
  SEC: 'Security', TURB: 'Turbulence', UIMC: 'Flew into cloud unintentionally',
  UNK: 'Undetermined', USOS: 'Landed short or long', WILD: 'Wildlife',
  WSTRW: 'Wind shear or thunderstorm',
}

export const categoryName = (code: string | null) =>
  code ? (CATEGORY_NAMES[code] ?? code) : 'Uncategorised'
