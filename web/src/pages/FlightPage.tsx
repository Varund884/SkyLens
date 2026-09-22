/** Look up a US domestic flight number and see how it actually ran:
 *  delays, cancellations and every leg in the 12-month window. */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip as ChartTooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { Empty, ErrorBox, Spinner, Stat } from '../components/ui'

const EXAMPLES = ['AA1', 'AS64', 'WN1', 'DL2', 'UA500']

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

  return (
    <div className="mx-auto max-w-5xl space-y-5 p-3 sm:space-y-6 sm:p-6">
      <div>
        <h1 className="text-2xl font-semibold">My flight</h1>
        <p className="mt-1 text-sm text-slate-400">
          How a flight number actually performed, July 2025 to June 2026. US domestic flights by reporting carriers.
        </p>
      </div>

      <form onSubmit={submit} className="flex flex-wrap gap-2">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="Flight number, e.g. AA1"
          className="w-56 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 outline-none focus:border-sky-400"
        />
        <button className="rounded-lg bg-slate-900 px-4 py-2 text-sm text-white">Look up</button>
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <span>Try:</span>
          {EXAMPLES.map(e => (
            <button key={e} type="button" onClick={() => { setInput(e); setNumber(e) }}
                    className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-slate-300 hover:bg-slate-700">{e}</button>
          ))}
        </div>
      </form>

      {!number && <Empty>Enter a flight number to see its delay and cancellation history.</Empty>}
      {q.isLoading && number && <Spinner label={`Looking up ${number}`} />}
      {q.error && <ErrorBox error={q.error} />}

      {q.data && (
        <>
          <div>
            <h2 className="text-lg font-medium">
              {q.data.flight_number}
              {q.data.operator && <span className="ml-2 text-sm font-normal text-slate-400">{q.data.operator}</span>}
            </h2>
            <p className="text-sm text-slate-400">{q.data.routes.join(', ') || 'Route not recorded'}</p>
          </div>

          <div className="grid grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-4">
            <Stat label="Flights in the year" value={q.data.legs_found.toLocaleString()} />
            <Stat label="Left within 15 min"
                  tone={(q.data.on_time_pct ?? 0) >= 80 ? 'good' : 'warn'}
                  value={q.data.on_time_pct == null ? '—' : `${q.data.on_time_pct}%`} />
            <Stat label="Cancelled"
                  tone={(q.data.cancelled_pct ?? 0) > 2 ? 'warn' : 'good'}
                  value={q.data.cancelled_pct == null ? '—' : `${q.data.cancelled_pct}%`} />
            <Stat label="Typical departure"
                  value={q.data.median_departure_delay_min == null ? '—'
                    : q.data.median_departure_delay_min <= 0
                      ? `${Math.abs(q.data.median_departure_delay_min)} min early`
                      : `${q.data.median_departure_delay_min} min late`}
                  hint={q.data.worst_delay_min != null ? `Worst delay ${Math.round(q.data.worst_delay_min / 60)} h ${q.data.worst_delay_min % 60} min` : undefined} />
          </div>

          <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
            <h3 className="text-sm font-medium text-slate-200">Departure delay, most recent {legs.length} flights</h3>
            <div className="mt-3 h-48 sm:h-56">
              <ResponsiveContainer>
                <BarChart data={chart} margin={{ top: 5, right: 10, bottom: 0, left: -20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#94a3b8' }} interval="preserveStartEnd" />
                  <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} unit="m" />
                  <ChartTooltip contentStyle={{ fontSize: 12, background: '#0f172a', border: '1px solid #334155', borderRadius: 8, color: '#e2e8f0' }}
                                formatter={(v, _name, item) => [
                                  (item as { payload?: { cancelled?: boolean } }).payload?.cancelled ? 'cancelled' : `${v} min`,
                                  'departure',
                                ]} />
                  <Bar dataKey="delay">
                    {chart.map((c, i) => (
                      <Cell key={i} fill={c.cancelled ? '#b91c1c' : c.delay > 15 ? '#ea580c' : '#15803d'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <p className="mt-2 text-xs text-slate-500">Green left on time, orange more than 15 minutes late, red cancelled. Bars below zero left early.</p>
          </section>

          <section className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/70">
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
                  <tr key={i} className="border-t border-slate-800">
                    <td className="px-3 py-2">{l.date}</td>
                    <td className="px-3 py-2 text-slate-300">{l.origin} → {l.destination}</td>
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
          <p className="pb-6 text-xs text-slate-500">
            Source: US Bureau of Transportation Statistics on-time performance. Percentages cover every flight in the
            window; the table lists the most recent {legs.length}.
          </p>
        </>
      )}
    </div>
  )
}
