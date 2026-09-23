/** Written for the people who use the site: travellers, aviation students and
 *  airport staff. Anything an engineer would want is in the repository. */
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { CountUp, Reveal, Tilt } from '../components/ui'

const AUDIENCE: [string, string, string][] = [
  ['If you fly',
   'Passenger',
   'Look up the airport you are flying from and see what actually gets reported there — and what almost all of it really is: birds near the runway, a go-around, a laser pointed at a cockpit.'],
  ['If you are learning to fly',
   'Student pilot',
   'Read a year of real occurrences at your home field. Runway incursions, circuit conflicts and missed approaches, described the way they were reported rather than in codes.'],
  ['If you work at an airport',
   'Operations',
   'Compare your field against airports of the same size and country, watch the month-by-month trend, and see which categories are driving it.'],
]

const DO: [string, string, string][] = [
  ['Explore the map', 'Every airport in the United States and Canada, sized and coloured by what is reported there.', '/map'],
  ['Open an airport report', 'A year in one page: the trend, the categories, how it compares to similar airports, and a written summary.', '/map'],
  ['Look up your flight', 'Type a flight number and see how often it left late, how often it was cancelled, and the route it flew. US domestic flights only.', '/flight'],
]

const SOURCES: [string, string][] = [
  ['Transport Canada', 'CADORS — the official Canadian record of civil aviation occurrences.'],
  ['NTSB', 'CAROL — US accident and incident reports, with the investigator narrative where one has been published.'],
  ['FAA', 'ATADS — the official count of aircraft movements at 528 towered US airports.'],
  ['Statistics Canada', 'Table 23-10-0296 — official movements at 121 Canadian airports.'],
  ['Bureau of Transportation Statistics', 'On-time performance for around 7 million US airline flights.'],
  ['OurAirports', 'Airport names, locations and codes.'],
]

const COUNTRIES: { name: string; tone: 'sky' | 'amber'; airports: number; pct: number; lines: string[] }[] = [
  {
    name: 'United States',
    tone: 'sky',
    airports: 528,
    pct: 100,
    lines: [
      'Occurrence reports from the NTSB',
      'Official movement counts from the FAA',
      'Flight delay and cancellation lookup for domestic flights',
    ],
  },
  {
    name: 'Canada',
    tone: 'amber',
    airports: 121,
    pct: 23,
    lines: [
      'Occurrence reports from Transport Canada',
      'Official movement counts from Statistics Canada',
      'No flight lookup — Canadian carriers do not publish flight-level data',
    ],
  },
]

const FAQ: [string, string][] = [
  ['Does a high number mean an airport is dangerous?',
   'No. It mostly means people there report things diligently. Aviation safety depends on crews and controllers filing reports for small events, and an airport with a strong reporting culture will show more of them than one where the same events go unfiled. Read the numbers as a picture of what gets reported, not a ranking of danger.'],
  ['Why does the site use rates instead of totals?',
   'Because a busy airport sees more of everything. A hub handling half a million movements a year will always file more reports than a regional field, without either being safer. Dividing by the traffic each airport actually handled is what makes the two comparable; comparing totals would tell you only which airport is bigger.'],
  ['Why does my airport show a count but no rate?',
   'A rate needs an official traffic count, and not every airport publishes one. Rather than estimate the missing number, the site shows what is known and leaves the rest blank.'],
  ['Why do flight-training airports look so busy?',
   'Canadian movement counts include local training circuits, so a field where students fly laps all day records enormous traffic and files a lot of routine reports. If you are comparing airports, compare like with like — the report pages already do this by country and airport size.'],
  ['Why only twelve months?',
   'The window runs from 1 July 2025 to 30 June 2026, which is the most recent period where every source has complete published data. A fixed window keeps every airport on the page comparable.'],
  ['Why can I only look up US flights?',
   'US carriers are required to publish flight-level on-time data and Canadian carriers are not, so there is no equivalent record to show for a Canadian flight number.'],
]

/** Grows to its width the first time it scrolls into view. */
function GrowBar({ pct, tone }: { pct: number; tone: 'sky' | 'amber' }) {
  const ref = useRef<HTMLDivElement>(null)
  const [w, setW] = useState(0)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) { setW(pct); io.disconnect() }
    }, { threshold: 0.4 })
    io.observe(el)
    return () => io.disconnect()
  }, [pct])
  return (
    <div ref={ref} className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
      <div
        className={`h-full rounded-full transition-[width] duration-1000 ease-out ${tone === 'sky' ? 'bg-sky-500' : 'bg-amber-400'}`}
        style={{ width: `${w}%` }}
      />
    </div>
  )
}

const Card = ({ children }: { children: ReactNode }) => (
  <div className="flex h-full flex-col rounded-xl border border-slate-800 bg-slate-900/60 p-5 transition-colors hover:border-slate-700 hover:bg-slate-900">
    {children}
  </div>
)

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6 sm:py-14">
      {/* ---- hero ---- */}
      <section className="relative isolate">
        <div
          className="pointer-events-none absolute inset-x-[-20%] top-[-40%] -z-10 h-[140%] blur-3xl"
          style={{ background: 'radial-gradient(ellipse at 50% 40%, rgba(56,189,248,0.16), transparent 68%)' }}
        />
        <p className="text-xs uppercase tracking-[0.2em] text-sky-400/80">About</p>
        <h1 className="mt-3 max-w-2xl bg-gradient-to-br from-white via-slate-200 to-slate-400 bg-clip-text text-3xl font-semibold tracking-tight text-transparent sm:text-4xl">
          The airports you&rsquo;ve flown through, and the ones you&rsquo;re headed to
        </h1>
        <p className="mt-4 max-w-2xl text-sm leading-relaxed text-slate-400">
          Every year, pilots and controllers across the United States and Canada file tens of thousands of safety
          reports. They are all public — and almost unreadable, buried in spreadsheets and codes. SkyLens gathers a
          full year of them, works out how often things happen relative to how busy each airport is, and writes each
          one out in a sentence anyone can follow.
        </p>

        <div className="mt-8 grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[
            [<CountUp key="a" to={19162} />, 'reports from the last twelve months'],
            [<CountUp key="b" to={495} />, 'airports with a full report page'],
            [<CountUp key="c" to={722} />, 'airports with official traffic counts'],
            ['7M', 'airline flights measured for delays'],
          ].map(([value, label], i) => (
            <Reveal key={i} delay={i * 90}>
              <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
                <div className="text-2xl font-semibold text-slate-50">{value}</div>
                <div className="mt-1 text-xs leading-snug text-slate-400">{label}</div>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ---- who it is for ---- */}
      <section className="mt-16">
        <h2 className="text-lg font-medium text-slate-100">Who it is for</h2>
        <div className="mt-5 grid gap-3 lg:grid-cols-3">
          {AUDIENCE.map(([title, tag, body], i) => (
            <Reveal key={title} delay={i * 110}>
              <Tilt strength={0.7}>
                <Card>
                  <span className="w-fit rounded-full border border-sky-500/30 bg-sky-500/10 px-2.5 py-1 text-[10px] uppercase tracking-wider text-sky-300">
                    {tag}
                  </span>
                  <h3 className="mt-3 text-sm font-medium text-slate-100">{title}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-slate-400">{body}</p>
                </Card>
              </Tilt>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ---- what you can do ---- */}
      <section className="mt-16">
        <h2 className="text-lg font-medium text-slate-100">What you can do here</h2>
        <div className="mt-5 grid gap-3 lg:grid-cols-3">
          {DO.map(([title, body, to], i) => (
            <Reveal key={title} delay={i * 110}>
              <Link to={to} className="block h-full">
                <Card>
                  <h3 className="text-sm font-medium text-slate-100">{title}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-slate-400">{body}</p>
                  <span className="mt-auto pt-4 text-xs text-sky-400">Open →</span>
                </Card>
              </Link>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ---- two countries on one map ---- */}
      <section className="mt-16 grid gap-6 lg:grid-cols-2">
        <Reveal>
          <div>
            <h2 className="text-lg font-medium text-slate-100">One map, two countries</h2>
            <p className="mt-3 text-sm leading-relaxed text-slate-400">
              The United States and Canada each run their own reporting system, publish in their own formats and
              count traffic in their own way. SkyLens puts both on a single map, so you can search any airport on the
              continent in one place instead of learning two government websites.
            </p>
            <p className="mt-3 text-sm leading-relaxed text-slate-400">
              Where an airport has an official traffic count, every report page leads with a rate — occurrences for
              every 100,000 aircraft movements — alongside the median for airports of the same size and country. That
              is what lets a quiet regional field and a major hub be compared fairly, rather than by size alone.
            </p>
          </div>
        </Reveal>

        <Reveal delay={120}>
          <Tilt strength={0.6}>
            <div className="space-y-6 rounded-xl border border-slate-800 bg-slate-900/60 p-5">
              {COUNTRIES.map(c => (
                <div key={c.name}>
                  <div className="flex items-baseline justify-between">
                    <span className="text-sm font-medium text-slate-100">{c.name}</span>
                    <span className="text-xs text-slate-500">{c.airports} airports with traffic counts</span>
                  </div>
                  <div className="mt-2">
                    <GrowBar pct={c.pct} tone={c.tone} />
                  </div>
                  <ul className="mt-3 space-y-1.5">
                    {c.lines.map(l => (
                      <li key={l} className="flex gap-2 text-xs leading-relaxed text-slate-400">
                        <span className={`mt-1.5 h-1 w-1 shrink-0 rounded-full ${c.tone === 'sky' ? 'bg-sky-400' : 'bg-amber-400'}`} />
                        {l}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </Tilt>
        </Reveal>
      </section>

      {/* ---- sources ---- */}
      <section className="mt-16">
        <h2 className="text-lg font-medium text-slate-100">Where the information comes from</h2>
        <p className="mt-1 text-sm text-slate-400">
          Everything here is official public data from the aviation authorities themselves. Nothing is crowd-sourced.
        </p>
        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {SOURCES.map(([name, body], i) => (
            <Reveal key={name} delay={(i % 3) * 90}>
              <Tilt strength={0.7}>
                <Card>
                  <h3 className="text-sm font-medium text-slate-100">{name}</h3>
                  <p className="mt-1.5 text-xs leading-relaxed text-slate-400">{body}</p>
                </Card>
              </Tilt>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ---- questions ---- */}
      <section className="mt-16">
        <h2 className="text-lg font-medium text-slate-100">Questions people ask</h2>
        <div className="mt-5 divide-y divide-slate-800 overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60">
          {FAQ.map(([q, a]) => (
            <details key={q} className="group px-5 py-4 transition-colors open:bg-slate-900">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-sm font-medium text-slate-100 [&::-webkit-details-marker]:hidden">
                {q}
                <span className="shrink-0 text-slate-500 transition-transform duration-300 group-open:rotate-45">+</span>
              </summary>
              <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-400">{a}</p>
            </details>
          ))}
        </div>
      </section>

      <Reveal>
        <div className="mt-14 text-center">
          <p className="text-sm text-slate-300">
            Start with the{' '}
            <Link to="/map" className="text-sky-400 underline-offset-4 hover:underline">map</Link>, or look up{' '}
            <Link to="/flight" className="text-sky-400 underline-offset-4 hover:underline">a flight number</Link>.
          </p>
          <p className="mt-3 text-xs text-slate-500">
            SkyLens is an independent project built on public data, and is not affiliated with any aviation authority.
          </p>
        </div>
      </Reveal>
    </div>
  )
}
