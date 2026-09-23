/** Site footer: attribution, the honest disclaimer, and where to reach the author. */
const REPO = 'https://github.com/Varund884/SkyLens'
const LINKEDIN = 'https://www.linkedin.com/in/varun-dawrha/'

const link = 'text-slate-400 transition-colors hover:text-slate-100 hover:underline underline-offset-4'

export function Footer() {
  return (
    <footer className="mt-16 border-t border-slate-800 bg-slate-950">
      <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6">
        <div className="flex flex-col gap-8 sm:flex-row sm:items-start sm:justify-between">
          <div className="max-w-md">
            <div className="text-lg font-semibold tracking-tight text-slate-50">
              Sky<span className="text-sky-400">Lens</span>
            </div>
            <p className="mt-2 text-sm leading-relaxed text-slate-400">
              Built from public data published by Transport Canada, the NTSB, the FAA,
              the Bureau of Transportation Statistics and Statistics Canada. Not an
              official source, and not for operational use.
            </p>
          </div>

          <nav className="flex flex-col gap-2 text-sm sm:text-right">
            <a className={link} href={REPO} target="_blank" rel="noreferrer">
              Source code
            </a>
            <a className={link} href={LINKEDIN} target="_blank" rel="noreferrer">
              LinkedIn
            </a>
            <a className={link} href={`${REPO}/issues/new`} target="_blank" rel="noreferrer">
              Report a problem
            </a>
          </nav>
        </div>

        <p className="mt-8 border-t border-slate-800/70 pt-6 text-xs text-slate-500">
          © {new Date().getFullYear()} Varun Dawrha
        </p>
      </div>
    </footer>
  )
}
