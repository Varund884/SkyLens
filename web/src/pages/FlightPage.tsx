/** Look up a US domestic flight number and see how it actually ran:
 *  delays, cancellations and every leg in the 12-month window. */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip as ChartTooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { ErrorBox, Stat, Tilt } from '../components/ui'
import { UsMap } from '../components/UsMap'

const EXAMPLES = ['AA1', 'AS64', 'WN1', 'DL2', 'UA500']

/** Material's flight glyph, turned to point along the route line. */
const Plane = ({ className = '' }: { className?: string }) => (
  <svg viewBox="0 0 24 24" fill="currentColor" className={`rotate-90 ${className}`} aria-hidden>
    <path d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" />
  </svg>
)

/** A route code that leads somewhere: the table shows JFK, the report lives at KJFK. */
function AirportLink({ code, ident }: { code: string | null; ident: string | null }) {
  if (!code) return <>—</>
  if (!ident) return <>{code}</>
  return (
    <Link to={`/airport/${ident}`} className="underline-offset-4 hover:text-sky-300 hover:underline">
      {code}
    </Link>
  )
}

function LoadingCard({ number }: { number: string }) {
  return (
    <div className="relative h-44 overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/70">
      <div className="sl-route absolute inset-x-10 top-1/2 h-0.5" />
      <span className="absolute left-10 top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-slate-600" />
      <span className="absolute right-10 top-1/2 h-2 w-2 translate-x-1/2 -translate-y-1/2 rounded-full bg-slate-600" />
      <div className="sl-plane text-sky-400">
        <Plane className="h-6 w-6 drop-shadow-[0_0_10px_rgba(56,189,248,0.55)]" />
      </div>
      <div className="absolute inset-x-0 bottom-6 text-center">
        <p className="text-sm text-slate-300">Searching {number}</p>
        <p className="mt-1 text-xs text-slate-500">Reading twelve months of flight records</p>
      </div>
    </div>
  )
}

export default function FlightPage() {
  const [input, setInput] = useState('')
  const [number, setNumber] = useState('')

  const q = useQuery({
    queryKey: ['flight', number],
    queryFn: () => api.flight(number),
    enabled: number.length > 0,
    retry: false,
  })

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    setNumber(input.trim().toUpperCase())
  }

  const legs = q.data?.legs ?? []
  const chart = [...legs].reverse().map(l => ({
    date: l.date.slice(5),
    delay: l.cancelled ? 0 : (l.departure_delay_min ?? 0),
    cancelled: l.cancelled,
  }))

  /* The same controls sit on the cream ticket and on the dark results bar. */
  const field = (cream: boolean) => (
    <input
      value={input}
      onChange={e => setInput(e.target.value)}
      placeholder="AA1"
      aria-label="Flight number"
      className={`w-40 rounded-lg border px-3 py-2.5 text-lg font-medium uppercase tracking-widest outline-none transition placeholder:tracking-normal focus:ring-4 focus:ring-sky-500/20 ${
        cream
          ? 'border-stone-300 bg-white/80 text-stone-900 placeholder:text-stone-400 focus:border-sky-600'
          : 'border-slate-700 bg-slate-950/60 text-slate-100 placeholder:text-slate-600 focus:border-sky-400'
      }`}
    />
  )
  const goButton = (cream: boolean) => (
    <button
      className={`rounded-lg px-5 py-2.5 text-sm font-medium transition active:scale-[0.97] ${
        cream
          ? 'bg-stone-900 text-stone-50 hover:bg-stone-800'
          : 'bg-sky-500 text-slate-950 hover:bg-sky-400'
      }`}
    >
      Look up
    </button>
  )
  const examples = (cream: boolean) => (
    <div className={`flex flex-wrap items-center gap-2 text-xs ${cream ? 'text-stone-500' : 'text-slate-500'}`}>
      <span>Try</span>
      {EXAMPLES.map(e => (
        <button
          key={e}
          type="button"
          onClick={() => { setInput(e); setNumber(e) }}
          className={`rounded border px-2 py-1 transition hover:-translate-y-0.5 ${
            cream
              ? 'border-stone-300 bg-stone-100 text-stone-700 hover:border-sky-600/50 hover:text-sky-800'
              : 'border-slate-700 bg-slate-800/70 text-slate-300 hover:border-sky-500/50 hover:text-sky-300'
          }`}
        >
          {e}
        </button>
      ))}
    </div>
  )

  return (
    <div className="mx-auto flex min-h-[calc(100svh-3.5rem)] max-w-5xl flex-col gap-5 p-3 sm:gap-6 sm:p-6">
      {!number ? (
        /* ---- nothing searched yet: the boarding pass is the whole page ---- */
        <div className="relative isolate flex flex-1 flex-col justify-center py-6">
          {/* Lift the page out of near-black so the cream ticket sits in light, not a void. */}
          <div
            className="pointer-events-none absolute inset-x-[-25%] top-[-15%] -z-10 h-[85%] blur-3xl"
            style={{
              background:
                'radial-gradient(ellipse at 50% 35%, rgba(148,163,184,0.26), rgba(56,189,248,0.14) 42%, transparent 72%)',
            }}
          />
          <Tilt>
            <div className="relative overflow-hidden rounded-2xl border border-stone-300/60 bg-gradient-to-br from-[#fdfaf3] via-[#f7f1e4] to-[#eee5d3] shadow-2xl shadow-black/50">
              <div
                className="pointer-events-none absolute inset-0 opacity-[0.06]"
                style={{ backgroundImage: 'radial-gradient(#1c1917 1px, transparent 1px)', backgroundSize: '22px 22px' }}
              />
              {/* Fills the dead space to the right of the copy; decoration, not a real map. */}
              <UsMap className="pointer-events-none absolute right-44 top-1/2 hidden h-[48%] -translate-y-1/2 sm:block" />

              <div className="relative grid sm:grid-cols-[1fr_auto]">
                <div className="p-6 sm:p-9">
                  <p className="text-xs uppercase tracking-[0.2em] text-sky-800/80">Flight history</p>
                  <h1 className="mt-2 text-3xl font-semibold tracking-tight text-stone-900 sm:text-4xl">
                    How did your flight really do?
                  </h1>
                  <p className="mt-3 max-w-md text-sm leading-relaxed text-stone-600">
                    Type a US domestic flight number and see every time it ran between July 2025 and
                    June 2026 — how late it left, how often it was cancelled, and which route it flew.
                  </p>

                  <form onSubmit={submit} className="mt-6 flex flex-wrap items-center gap-2">
                    {field(true)}
                    {goButton(true)}
                  </form>
                  <div className="mt-3">{examples(true)}</div>
                </div>

                {/* perforated stub */}
                <div className="relative hidden w-36 flex-col items-center justify-center border-l border-dashed border-stone-400 sm:flex">
                  <span className="absolute -top-2.5 left-0 h-5 w-5 -translate-x-1/2 rounded-full bg-slate-950" />
                  <span className="absolute -bottom-2.5 left-0 h-5 w-5 -translate-x-1/2 rounded-full bg-slate-950" />
                  <Plane className="h-7 w-7 text-stone-400" />
                  <p className="mt-3 text-center text-[10px] uppercase tracking-[0.18em] text-stone-500">
                    On-time
                    <br />
                    record
                  </p>
                </div>
              </div>
            </div>
          </Tilt>

          <div className="mt-6 grid gap-3 sm:grid-cols-3">
            {[
              ['Every leg', 'Date, route, aircraft tail number and the minutes it left early or late.'],
              ['The pattern', 'A year of departures charted, so a habitual delay is obvious at a glance.'],
              ['Cancellations', 'How often it was called off, and the reason the airline filed.'],
            ].map(([title, body], i) => (
              <div
                key={title}
                className="sl-rise rounded-xl border border-slate-800 bg-slate-900/50 p-4 transition hover:-translate-y-1 hover:border-slate-700 hover:bg-slate-900"
                style={{ animationDelay: `${120 + i * 90}ms` }}
              >
                <h2 className="text-sm font-medium text-slate-100">{title}</h2>
                <p className="mt-1.5 text-xs leading-relaxed text-slate-400">{body}</p>
              </div>
            ))}
          </div>

          <p className="mt-6 text-center text-xs text-slate-600">
            Source: US Bureau of Transportation Statistics. Canadian carriers do not publish
            flight-level on-time data, so this page covers US domestic flights only.
          </p>
        </div>
      ) : (
        <>
          {/* ---- searched: compact bar, results below ---- */}
          <form onSubmit={submit} className="flex flex-wrap items-center gap-2">
            {field(false)}
            {goButton(false)}
            {examples(false)}
          </form>

          {q.isLoading && <LoadingCard number={number} />}
          {q.error && <ErrorBox error={q.error} />}

          {q.data && (
            <div className="flex flex-col gap-5 sm:gap-6">
              <div className="sl-rise">
                <h1 className="text-2xl font-semibold">
                  {q.data.flight_number}
                  {q.data.operator && <span className="ml-2 text-sm font-normal text-slate-400">{q.data.operator}</span>}
                </h1>
                <p className="text-sm text-slate-400">{q.data.routes.join(', ') || 'Route not recorded'}</p>
              </div>

              <div className="grid grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-4">
                {[
                  <Stat key="n" label="Flights in the year" value={q.data.legs_found.toLocaleString()} />,
                  <Stat key="o" label="Left within 15 min"
                        tone={(q.data.on_time_pct ?? 0) >= 80 ? 'good' : 'warn'}
                        value={q.data.on_time_pct == null ? '—' : `${q.data.on_time_pct}%`} />,
                  <Stat key="c" label="Cancelled"
                        tone={(q.data.cancelled_pct ?? 0) > 2 ? 'warn' : 'good'}
                        value={q.data.cancelled_pct == null ? '—' : `${q.data.cancelled_pct}%`} />,
                  <Stat key="d" label="Typical departure"
                        value={q.data.median_departure_delay_min == null ? '—'
                          : q.data.median_departure_delay_min <= 0
                            ? `${Math.abs(q.data.median_departure_delay_min)} min early`
                            : `${q.data.median_departure_delay_min} min late`}
                        hint={q.data.worst_delay_min != null ? `Worst delay ${Math.round(q.data.worst_delay_min / 60)} h ${q.data.worst_delay_min % 60} min` : undefined} />,
                ].map((tile, i) => (
                  <div key={i} className="sl-rise h-full transition hover:-translate-y-0.5" style={{ animationDelay: `${i * 70}ms` }}>
                    {tile}
                  </div>
                ))}
              </div>

              <section className="sl-rise rounded-xl border border-slate-800 bg-slate-900/70 p-4" style={{ animationDelay: '300ms' }}>
                <h2 className="text-sm font-medium text-slate-200">Departure delay, most recent {legs.length} flights</h2>
                <div className="mt-3 h-48 sm:h-56">
                  <ResponsiveContainer>
                    <BarChart data={chart} margin={{ top: 5, right: 10, bottom: 0, left: -20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                      <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#94a3b8' }} interval="preserveStartEnd" />
                      <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} unit="m" />
                      <ChartTooltip contentStyle={{ fontSize: 12, background: '#0f172a', border: '1px solid #334155', borderRadius: 8, color: '#e2e8f0' }}
                              labelStyle={{ color: '#e2e8f0' }}
                              itemStyle={{ color: '#cbd5e1' }}
                                    cursor={{ fill: '#1e293b55' }}
                                    formatter={(v, _name, item) => [
                                      (item as { payload?: { cancelled?: boolean } }).payload?.cancelled ? 'cancelled' : `${v} min`,
                                      'departure',
                                    ]} />
                      <Bar dataKey="delay" animationDuration={700}>
                        {chart.map((c, i) => (
                          <Cell key={i} fill={c.cancelled ? '#b91c1c' : c.delay > 15 ? '#ea580c' : '#15803d'} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <p className="mt-2 text-xs text-slate-500">Green left on time, orange more than 15 minutes late, red cancelled. Bars below zero left early.</p>
              </section>

              <section className="sl-rise overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/70" style={{ animationDelay: '380ms' }}>
                <table className="w-full text-sm">
                  <thead className="bg-slate-950 text-left text-xs uppercase tracking-wide text-slate-400">
                    <tr>
                      {['Date', 'Route', 'Scheduled', 'Actual', 'Departure', 'Arrival', 'Aircraft'].map(h => (
                        <th key={h} className="px-3 py-2 font-medium">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {legs.map((l, i) => (
                      <tr key={i} className="border-t border-slate-800 transition-colors hover:bg-slate-800/40">
                        <td className="px-3 py-2">{l.date}</td>
                        <td className="px-3 py-2 text-slate-300">
                          <AirportLink code={l.origin} ident={l.origin_ident} />
                          {' → '}
                          <AirportLink code={l.destination} ident={l.destination_ident} />
                        </td>
                        <td className="px-3 py-2 text-slate-300">{l.scheduled_departure ?? '—'}</td>
                        <td className="px-3 py-2 text-slate-300">{l.actual_departure ?? '—'}</td>
                        <td className="px-3 py-2">
                          {l.cancelled
                            ? <span className="text-red-400">cancelled{l.cancellation_reason ? ` (${l.cancellation_reason})` : ''}</span>
                            : l.departure_delay_min == null ? '—'
                            : <span className={l.departure_delay_min > 15 ? 'text-amber-400' : 'text-emerald-400'}>
                                {l.departure_delay_min > 0 ? `+${l.departure_delay_min}` : l.departure_delay_min} min
                              </span>}
                        </td>
                        <td className="px-3 py-2 text-slate-300">
                          {l.diverted ? 'diverted' : l.arrival_delay_min == null ? '—'
                            : `${l.arrival_delay_min > 0 ? '+' : ''}${l.arrival_delay_min} min`}
                        </td>
                        <td className="px-3 py-2 text-slate-400">{l.tail_number ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>

              <p className="text-xs text-slate-500">
                Safety occurrence reports are filed against an aircraft and an airport, not against a flight number, so
                there is no per-flight incident history to show here. The airport codes above link to the full safety
                report for each end of the route.
                <br />
                <br />
                Source: US Bureau of Transportation Statistics on-time performance. Percentages cover every flight in the
                window; the table lists the most recent {legs.length}.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  )
}
