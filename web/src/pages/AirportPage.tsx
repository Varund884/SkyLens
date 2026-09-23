/** One airport's report: the numbers, how it compares, what happened, and why
 *  each number can be trusted (or not). Everything here was computed in batch;
 *  the page just draws it. */
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ResponsiveContainer,
  Tooltip as ChartTooltip, XAxis, YAxis,
} from 'recharts'
import { api, categoryName, type Occurrence } from '../api'
import { Empty, ErrorBox, PredictedBadge, Spinner, Stat } from '../components/ui'

const SOURCE_NAMES: Record<string, string> = {
  faa: 'FAA tower counts', statcan: 'Statistics Canada', bts: 'US airline schedules',
}

export default function AirportPage() {
  const { ident = '' } = useParams()
  const [category, setCategory] = useState<string | undefined>()
  const [page, setPage] = useState(0)
  const limit = 25

  const report = useQuery({ queryKey: ['report', ident], queryFn: () => api.report(ident) })
  const list = useQuery({
    queryKey: ['occurrences', ident, category, page],
    queryFn: () => api.occurrences(ident, { offset: page * limit, limit, category }),
    placeholderData: prev => prev,
  })

  if (report.isLoading) return <Spinner label={`Loading ${ident}`} />
  if (report.error) {
    return (
      <div className="mx-auto max-w-3xl p-6">
        <ErrorBox error={report.error} />
        <Link to="/" className="mt-4 inline-block text-sm text-sky-400">Back to the map</Link>
      </div>
    )
  }
  const r = report.data!
  const rateTone = r.rate_per_10k == null || r.peer_median_rate_per_10k == null
    ? 'plain'
    : r.rate_per_10k > r.peer_median_rate_per_10k * 1.25 ? 'warn'
    : r.rate_per_10k < r.peer_median_rate_per_10k * 0.8 ? 'good' : 'plain'

  const peerText = r.peer_median_rate_per_10k != null
    ? `Typical ${r.peer_group ?? r.airport_type.replace('_', ' ')}: ${r.peer_median_rate_per_10k}`
    : undefined

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-3 sm:space-y-6 sm:p-6">
      <div>
        <Link to="/" className="text-sm text-sky-400">← Map</Link>
        <h1 className="mt-1 text-xl font-semibold sm:text-2xl">{r.name}</h1>
        <p className="text-sm text-slate-400">
          {r.ident}{r.municipality ? ` · ${r.municipality}` : ''} · {r.country === 'CA' ? 'Canada' : 'United States'} ·{' '}
          {r.airport_type.replace('_', ' ')}
        </p>
      </div>

      <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs leading-relaxed text-amber-200">
        {r.country === 'CA'
          ? 'Transport Canada records every reportable occurrence, including bird sightings, go-arounds and air traffic service reports. Canadian numbers are therefore much larger than US ones and the two cannot be compared. Comparisons on this page are against other Canadian airports of the same size.'
          : 'The NTSB records only accidents and serious incidents, so US numbers are far smaller than Canadian ones and the two cannot be compared. Comparisons on this page are against other US airports of the same size.'}
      </p>

      {r.summary && (
        <p className="rounded-lg border-l-4 border-sky-500 bg-slate-900 p-4 text-sm leading-relaxed text-slate-200">
          {r.summary}
          <span className="mt-2 block text-xs text-slate-500">
            Written from this airport's own occurrence summaries. It describes what was reported; it is not a safety rating.
          </span>
        </p>
      )}

      <div className="grid grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-4">
        <Stat label="Occurrences (12 months)" value={r.occurrences.toLocaleString()}
              hint={`${r.accidents} accident${r.accidents === 1 ? '' : 's'}${r.fatalities ? `, ${r.fatalities} fatalities` : ''}`} />
        <Stat label="Per 10,000 movements" tone={rateTone}
              value={r.rate_per_10k ?? '—'}
              hint={r.rate_per_10k == null ? 'No official traffic count for this airport' : peerText} />
        <Stat label="Aircraft movements" value={r.movements?.toLocaleString() ?? '—'}
              hint={r.movement_source ? SOURCE_NAMES[r.movement_source] ?? r.movement_source : 'None published'} />
        <Stat label="Second half vs first"
              value={r.rate_change_pct_h2_vs_h1 == null ? '—' : `${r.rate_change_pct_h2_vs_h1 > 0 ? '+' : ''}${r.rate_change_pct_h2_vs_h1}%`}
              hint="Change in rate, last 6 months against the first 6" />
      </div>

      {r.operations && (
        <div className="grid grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-4">
          <Stat label="Airline flights" value={r.operations.flights.toLocaleString()} hint="Departures in the window" />
          <Stat label="Cancelled" value={`${r.operations.cancelled_pct}%`} />
          <Stat label="Delayed over 15 min" value={`${r.operations.delayed_over_15_pct}%`} />
          <Stat label="Average departure delay"
                value={r.operations.avg_departure_delay_min == null ? '—' : `${r.operations.avg_departure_delay_min} min`} />
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {r.occurrences === 0 ? (
          <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-6 text-sm text-slate-400">
            Nothing was reported to the NTSB at this airport in the twelve months to June 2026.
            Only accidents and serious incidents are recorded, so a busy airport with none is normal.
            The operations figures above still describe how it ran.
          </section>
        ) : (
        <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
          <h2 className="text-sm font-medium text-slate-200">Occurrences by month</h2>
          <div className="mt-3 h-52 sm:h-60">
            <ResponsiveContainer>
              <LineChart data={r.trend} margin={{ top: 5, right: 10, bottom: 0, left: -20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#94a3b8' }} tickFormatter={m => m.slice(2)} />
                <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} allowDecimals={false} />
                <ChartTooltip contentStyle={{ fontSize: 12, background: '#0f172a', border: '1px solid #334155', borderRadius: 8, color: '#e2e8f0' }}
                              labelStyle={{ color: '#e2e8f0' }}
                              itemStyle={{ color: '#cbd5e1' }} />
                <Line type="monotone" dataKey="occurrences" stroke="#0284c7" strokeWidth={2} dot={false} name="Occurrences" />
                <Line type="monotone" dataKey="rolling_3m" stroke="#64748b" strokeDasharray="4 3" dot={false} name="3-month average" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>
        )}

        {r.categories.length > 0 && (
        <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
          <h2 className="text-sm font-medium text-slate-200">
            What was reported
            {r.categories_predicted > 0 && (
              <span className="ml-2 text-xs font-normal text-violet-300">
                {r.categories_predicted} of {r.occurrences} categorised by a model
              </span>
            )}
          </h2>
          <div className="mt-3 h-52 sm:h-60">
            <ResponsiveContainer>
              <BarChart data={r.categories.slice(0, 8)} layout="vertical" margin={{ left: 60, right: 20 }}>
                <XAxis type="number" tick={{ fontSize: 11, fill: '#94a3b8' }} allowDecimals={false} />
                <YAxis type="category" dataKey="code" width={120} tick={{ fontSize: 11, fill: '#94a3b8' }}
                       tickFormatter={c => categoryName(c)} />
                <ChartTooltip contentStyle={{ fontSize: 12, background: '#0f172a', border: '1px solid #334155', borderRadius: 8, color: '#e2e8f0' }}
                              labelStyle={{ color: '#e2e8f0' }}
                              itemStyle={{ color: '#cbd5e1' }}
                              formatter={(v) => [String(v), 'occurrences']}
                              labelFormatter={c => categoryName(String(c))} />
                <Bar dataKey="occurrences" radius={[0, 4, 4, 0]}>
                  {r.categories.slice(0, 8).map(c => (
                    <Cell key={c.code} fill={category === c.code ? '#0f172a' : '#0ea5e9'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 text-xs text-slate-500">"Other" is left out: it is a quarter of Canadian records and says nothing.</p>
        </section>
        )}
      </div>

      {r.themes.length > 0 && (
        <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
          <h2 className="text-sm font-medium text-slate-200">Recurring themes</h2>
          <div className="mt-2 flex flex-wrap gap-2">
            {r.themes.map(t => (
              <span key={t.label} className="rounded-full border border-slate-700 bg-slate-800 px-3 py-1 text-xs text-slate-200">
                {t.label} · {t.occurrences}
              </span>
            ))}
          </div>
          <p className="mt-2 text-xs text-slate-500">Found by grouping similar US accident reports. Canadian records carry no narrative text.</p>
        </section>
      )}

      {r.occurrences > 0 && (
      <section className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-sm font-medium text-slate-200">Occurrences</h2>
          <button onClick={() => { setCategory(undefined); setPage(0) }}
                  className={`rounded-full px-3 py-1 text-xs ${!category ? 'bg-sky-500 text-slate-950' : 'border border-slate-700 bg-slate-800 text-slate-300'}`}>
            All
          </button>
          {r.categories.slice(0, 6).map(c => (
            <button key={c.code} onClick={() => { setCategory(c.code); setPage(0) }}
                    className={`rounded-full px-3 py-1 text-xs ${category === c.code ? 'bg-sky-500 text-slate-950' : 'border border-slate-700 bg-slate-800 text-slate-300'}`}>
              {categoryName(c.code)}
            </button>
          ))}
        </div>

        {list.isLoading && <Spinner />}
        {list.error && <ErrorBox error={list.error} />}
        {list.data && (list.data.items.length === 0
          ? <Empty>No occurrences match this filter.</Empty>
          : (
            <>
              <ul className="space-y-2">
                {list.data.items.map(o => <OccurrenceRow key={o.occurrence_key} o={o} />)}
              </ul>
              <div className="flex items-center gap-3 text-sm">
                <button disabled={page === 0} onClick={() => setPage(p => p - 1)}
                        className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1 text-slate-200 disabled:opacity-40">Previous</button>
                <span className="text-slate-400">
                  {page * limit + 1}–{Math.min((page + 1) * limit, list.data.total)} of {list.data.total.toLocaleString()}
                </span>
                <button disabled={(page + 1) * limit >= list.data.total} onClick={() => setPage(p => p + 1)}
                        className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1 text-slate-200 disabled:opacity-40">Next</button>
              </div>
            </>
          ))}
      </section>
      )}

      <p className="pb-6 text-xs text-slate-500">
        Report generated {r.generated_at.slice(0, 16)} from Transport Canada CADORS, NTSB CAROL, FAA ATADS,
        Statistics Canada and US BTS data for July 2025 to June 2026.
      </p>
    </div>
  )
}

function OccurrenceRow({ o }: { o: Occurrence }) {
  const [open, setOpen] = useState(false)
  return (
    <li className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
      <div className="flex flex-wrap items-baseline gap-2 text-xs text-slate-400">
        <span className="font-medium text-slate-200">{o.date}{o.time_utc ? ` ${o.time_utc}Z` : ''}</span>
        <span>{o.occurrence_type}</span>
        <span className="rounded bg-slate-800 px-1.5 py-0.5"
              title={o.category_code ? undefined
                : 'The NTSB assigns a cause only when it publishes the final report, which can take over a year'}>
          {o.category_code ? categoryName(o.category_code)
            : o.authority === 'NTSB' ? 'Awaiting final report' : 'Uncategorised'}
          {o.category_is_predicted && <PredictedBadge confidence={o.category_confidence} />}
        </span>
        {o.flight_number && <span>{o.flight_number}</span>}
        {o.registration && <span>{o.registration}</span>}
        {(o.fatalities ?? 0) > 0 && <span className="font-medium text-red-400">{o.fatalities} fatalities</span>}
      </div>
      <p className="mt-1 text-sm text-slate-100">
        {o.summary ?? (o.authority === 'NTSB'
          ? 'The NTSB has not yet published its report on this accident.'
          : 'No description was published for this record.')}
      </p>
      <button onClick={() => setOpen(v => !v)} className="mt-1 text-xs text-sky-400">
        {open ? 'Hide sources' : 'Sources'}
      </button>
      {open && (
        <div className="mt-2 rounded-lg bg-slate-950/80 p-2 text-xs text-slate-300">
          <div>Reported by {o.authority} as {o.source_record_id}.</div>
          {o.citation_ids.length > 0 && (
            <div className="mt-1">
              Summary written from: {o.citation_ids.map(c => c.replace(/-\d+$/, '').replace(/_/g, ' ')).join(', ')}
            </div>
          )}
        </div>
      )}
    </li>
  )
}
