/** Small shared pieces: page shell, stat tiles, loading and error states. */
import { Link, useLocation } from 'react-router-dom'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Footer } from './Footer'

export function Shell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation()
  const tab = (to: string, label: string) => (
    <Link
      to={to}
      className={`rounded-md px-2.5 py-1.5 text-sm sm:px-3 sm:py-2 ${
        pathname === to || (to !== '/' && pathname.startsWith(to))
          ? 'bg-sky-500 text-slate-950'
          : 'text-slate-300 hover:bg-slate-800'
      }`}
    >
      {label}
    </Link>
  )
  return (
    <div className="flex min-h-screen flex-col bg-slate-950 text-slate-100">
      <header className="sticky top-0 z-[1100] border-b border-slate-800 bg-slate-900/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-3 py-2.5 sm:gap-4 sm:px-4 sm:py-3">
          <Link to="/" className="text-lg font-semibold tracking-tight text-slate-50">
            Sky<span className="text-sky-400">Lens</span>
          </Link>
          <span className="hidden text-xs text-slate-400 sm:inline">
            Aviation safety and operations · United States and Canada
          </span>
          <nav className="ml-auto flex gap-1">
            {tab('/', 'Home')}
            {tab('/map', 'Map')}
            {tab('/flight', 'My flight')}
            {tab('/about', 'About')}
          </nav>
        </div>
      </header>
      <main className="flex-1">{children}</main>
      <Footer />
    </div>
  )
}

export function Stat({ label, value, hint, tone = 'plain' }: {
  label: string
  value: ReactNode
  hint?: ReactNode
  tone?: 'plain' | 'good' | 'warn'
}) {
  const colour = tone === 'good' ? 'text-emerald-400' : tone === 'warn' ? 'text-amber-300' : 'text-slate-50'
  return (
    <div className="flex h-full flex-col rounded-xl border border-slate-800 bg-slate-900/70 p-4 shadow-sm shadow-black/20">
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className={`mt-1 text-xl font-semibold sm:text-2xl ${colour}`}>{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-400">{hint}</div>}
    </div>
  )
}

export const Spinner = ({ label = 'Loading' }: { label?: string }) => (
  <div className="flex items-center gap-2 p-6 text-sm text-slate-400">
    <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-700 border-t-slate-600" />
    {label}
  </div>
)

export const Empty = ({ children }: { children: ReactNode }) => (
  <div className="rounded-lg border border-dashed bg-slate-900 p-6 text-sm text-slate-400">{children}</div>
)

export function ErrorBox({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : String(error)
  const asleep = /timed out|unavailable|Failed to fetch/i.test(message)
  return (
    <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-200">
      {message}
      {asleep && <div className="mt-1 text-xs">The database pauses when idle; the first request can take up to a minute.</div>}
    </div>
  )
}

/** A model guessed this value, so say so wherever it appears. */
export const PredictedBadge = ({ confidence }: { confidence?: number | null }) => (
  <span
    title={confidence ? `Model confidence ${(confidence * 100).toFixed(0)}%` : 'Assigned by a model, not by the reporting authority'}
    className="ml-2 rounded border border-violet-400/30 bg-violet-500/15 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-violet-300"
  >
    predicted
  </span>
)

/** Reveal children once they scroll into view. */
export function Reveal({ children, delay = 0 }: { children: ReactNode; delay?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const [shown, setShown] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver(([e]) => e.isIntersecting && setShown(true), { threshold: 0.2 })
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

/** A few degrees of pointer-follow tilt; enough to feel physical, not enough to distract. */
export function Tilt({ children, strength = 1 }: { children: ReactNode; strength?: number }) {
  const [tilt, setTilt] = useState({ x: 0, y: 0 })
  return (
    <div
      style={{ perspective: '1200px' }}
      onPointerMove={e => {
        const r = e.currentTarget.getBoundingClientRect()
        setTilt({
          x: ((e.clientY - r.top) / r.height - 0.5) * -4 * strength,
          y: ((e.clientX - r.left) / r.width - 0.5) * 6 * strength,
        })
      }}
      onPointerLeave={() => setTilt({ x: 0, y: 0 })}
      className="h-full"
    >
      <div
        className="h-full transition-transform duration-300 ease-out will-change-transform"
        style={{ transform: `rotateX(${tilt.x}deg) rotateY(${tilt.y}deg)` }}
      >
        {children}
      </div>
    </div>
  )
}

/** Counts up to `to` the first time it is seen, then stays put. */
export function CountUp({ to, duration = 1400 }: { to: number; duration?: number }) {
  const ref = useRef<HTMLSpanElement>(null)
  const [n, setN] = useState(0)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { setN(to); return }
    let raf = 0
    const io = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return
      io.disconnect()
      const t0 = performance.now()
      const step = (t: number) => {
        const p = Math.min((t - t0) / duration, 1)
        setN(Math.round(to * (1 - Math.pow(1 - p, 3))))     // ease-out cubic
        if (p < 1) raf = requestAnimationFrame(step)
      }
      raf = requestAnimationFrame(step)
    }, { threshold: 0.4 })
    io.observe(el)
    return () => { io.disconnect(); cancelAnimationFrame(raf) }
  }, [to, duration])
  return <span ref={ref}>{n.toLocaleString()}</span>
}
