/** Landing page: a turning globe, then scroll-driven panels explaining what a
 *  visitor can actually do here, then the map itself.
 *
 *  The globe is pinned while the opening copy scrolls over it and fades, the
 *  way product pages do it; each panel reveals as it enters the viewport.
 */
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import Globe from '../components/Globe'
import MapPage from './MapPage'

/** Reveal children once they scroll into view. */
function Reveal({ children, delay = 0 }: { children: React.ReactNode; delay?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const [shown, setShown] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver(
      ([e]) => e.isIntersecting && setShown(true),
      { threshold: 0.25 },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [])
  return (
    <div
      ref={ref}
      style={{ transitionDelay: `${delay}ms` }}
      className={`transition-all duration-700 ease-out ${shown ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0'}`}
    >
      {children}
    </div>
  )
}

const THINGS = [
  {
    title: 'See how often things happen at your airport',
    body: 'Every airport in the United States and Canada, on one map. Colour shows how often something was reported for every 10,000 take-offs and landings, so a small airfield and a major hub can be compared fairly.',
  },
  {
    title: 'Read what happened, in plain English',
    body: 'Official reports are written in code: "RI-VAP", "CFIT", "Missed approach/Go-around". Every occurrence here comes with one sentence anyone can read, written from the report and the official glossary, with its sources shown.',
  },
  {
    title: 'Check your flight before you fly',
    body: 'Type a US flight number and see how it actually ran over the past year: how often it left on time, how often it was cancelled, and its worst delay.',
  },
]

export default function HomePage() {
  const [progress, setProgress] = useState(0)   // 0 at the top, 1 once the hero has scrolled away

  useEffect(() => {
    const onScroll = () => {
      const p = Math.min(window.scrollY / Math.max(window.innerHeight, 1), 1)
      setProgress(p)
    }
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <div className="overflow-x-hidden bg-slate-950">
      {/* Pinned globe behind the opening copy */}
      <section className="relative h-[100svh]">
        {/* Pinned to the top of the viewport, with the content padded down to
            clear the sticky header, so the globe and the copy stay centred on
            every screen size instead of being offset by a guessed header height. */}
        <div className="sticky top-0 h-[100svh] overflow-hidden">
          <div
            className="absolute inset-0"
            style={{
              opacity: 1 - progress * 0.7,
              filter: `blur(${progress * 2.5}px)`,
              transition: 'opacity 120ms linear, filter 200ms linear',
            }}
          >
            <Globe className="h-full w-full" progress={progress} />
          </div>

          <div
            className="relative flex h-full flex-col items-center justify-center px-5 pt-14 text-center sm:px-6"
            style={{ transform: `translateY(${progress * -60}px)`, opacity: 1 - progress * 1.4 }}
          >
            <p className="text-xs uppercase tracking-[0.3em] text-sky-400">United States · Canada</p>
            <h1 className="mt-4 max-w-3xl text-3xl font-semibold leading-[1.15] text-slate-50 sm:text-5xl lg:text-6xl">
              What actually happens<br />at the airports you fly through
            </h1>
            <p className="mt-4 max-w-xl text-sm text-slate-300 sm:mt-5 sm:text-lg">
              Twelve months of official aviation reports, turned into numbers you can compare
              and sentences you can read.
            </p>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
              <Link to="/map" className="rounded-full bg-sky-500 px-5 py-2.5 text-sm font-medium text-slate-950 hover:bg-sky-400">
                Open the map
              </Link>
              <Link to="/flight" className="rounded-full border border-slate-700 px-5 py-2.5 text-sm text-slate-200 hover:bg-slate-800">
                Look up a flight
              </Link>
            </div>
            <div className="mt-10 flex flex-col items-center gap-2 text-slate-400 sm:mt-14"
                 style={{ opacity: 1 - progress * 3 }}>
              <span className="text-xs uppercase tracking-widest">Scroll</span>
              <svg className="h-5 w-5 animate-bounce" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M12 5v14M5 12l7 7 7-7" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
          </div>
        </div>
      </section>

      {/* What you can do here */}
      <section className="relative z-10 mx-auto max-w-3xl space-y-12 px-5 pb-16 pt-10 sm:space-y-16 sm:px-6">
        {/* soft light behind the copy, so the section has depth without images */}
        <div aria-hidden className="pointer-events-none absolute left-1/2 top-0 -z-10 h-[32rem] w-[32rem] -translate-x-1/2 rounded-full bg-sky-500/10 blur-[120px]" />

        {THINGS.map((t, i) => (
          <Reveal key={t.title} delay={i * 80}>
            <div className="group flex flex-col items-start gap-5 sm:flex-row sm:items-center sm:gap-8">
              <div className="relative shrink-0">
                <div className="absolute inset-0 rounded-2xl bg-sky-500/20 blur-xl transition group-hover:bg-sky-400/30" />
                <div className="relative grid h-16 w-16 place-items-center rounded-2xl border border-slate-700/80 bg-gradient-to-br from-slate-800 to-slate-900 text-xl font-semibold text-sky-300 shadow-lg shadow-black/40 transition duration-500 group-hover:-translate-y-1 group-hover:border-sky-500/50">
                  {String(i + 1).padStart(2, '0')}
                </div>
              </div>
              <div className="min-w-0">
                <h2 className="text-xl font-semibold text-slate-50 sm:text-3xl">{t.title}</h2>
                <p className="mt-2 text-sm leading-relaxed text-slate-300 sm:mt-3 sm:text-base">{t.body}</p>
              </div>
            </div>
          </Reveal>
        ))}

        <Reveal>
          <div className="relative">
            <div aria-hidden className="absolute -inset-px rounded-2xl bg-gradient-to-r from-sky-500/30 via-transparent to-violet-500/30 blur-[2px]" />
            <div className="relative grid divide-y divide-slate-800 rounded-2xl border border-slate-800 bg-slate-900/70 backdrop-blur sm:grid-cols-3 sm:divide-x sm:divide-y-0">
              {[['42,347', 'occurrence reports', 'Canada and the United States'],
                ['7 million', 'flights', 'US airline departures and arrivals'],
                ['36,132', 'airports', 'every field, strip and heliport']].map(([n, l, sub]) => (
                <div key={l} className="flex flex-col items-center justify-center gap-1 px-6 py-7 text-center">
                  <div className="bg-gradient-to-b from-sky-200 to-sky-500 bg-clip-text text-3xl font-semibold tabular-nums text-transparent sm:text-4xl">{n}</div>
                  <div className="text-sm font-medium text-slate-200">{l}</div>
                  <div className="text-xs text-slate-500">{sub}</div>
                </div>
              ))}
            </div>
          </div>
        </Reveal>

        <Reveal>
          <p className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-4 text-center text-sm leading-relaxed text-amber-200">
            One thing to know before you look: Canada records every reportable occurrence, down to bird
            sightings, while the United States records only accidents and serious incidents. Canadian
            airports therefore show far bigger numbers. Compare airports within a country, never across
            the border.
          </p>
        </Reveal>

        <Reveal>
          <div className="flex flex-col items-center gap-3 pt-2 text-center">
            <p className="text-sm text-slate-400">Keep scrolling for the map</p>
            <svg className="h-5 w-5 animate-bounce text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M12 5v14M5 12l7 7 7-7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
        </Reveal>
      </section>

      {/* The map itself, so the page ends where the work begins */}
      <section className="relative z-10 border-t border-slate-800">
        <div className="mx-auto max-w-3xl px-5 pt-10 sm:px-6">
          <h2 className="text-2xl font-semibold text-slate-50">Every airport, on one map</h2>
          <p className="mt-2 text-sm text-slate-400">
            Colour shows occurrences per 10,000 aircraft movements. Click any airport for its report,
            or <Link to="/map" className="text-sky-400 underline-offset-2 hover:underline">open the full map</Link>.
          </p>
        </div>
        <div className="mt-6">
          <MapPage embedded />
        </div>
      </section>
    </div>
  )
}
