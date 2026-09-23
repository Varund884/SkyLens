/** Operations view, behind Entra ID sign-in.
 *
 *  Static Web Apps handles the sign-in itself: the /admin route is declared
 *  with allowedRoles ["authenticated"] in staticwebapp.config.json, so an
 *  anonymous request never reaches this component — it is redirected to
 *  /.auth/login/aad first. The identity of whoever did sign in is available
 *  from /.auth/me, which the platform serves; there is no token handling and
 *  no client secret anywhere in this code.
 *
 *  Running locally there is no auth layer, so /.auth/me returns nothing and
 *  the page says so rather than pretending to be signed in.
 */
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import { ErrorBox, Spinner, Stat } from '../components/ui'

interface ClientPrincipal {
  identityProvider: string
  userId: string
  userDetails: string
  userRoles: string[]
}

export default function AdminPage() {
  const [user, setUser] = useState<ClientPrincipal | null | undefined>(undefined)

  useEffect(() => {
    fetch('/.auth/me')
      .then(r => (r.ok ? r.json() : null))
      .then(d => setUser(d?.clientPrincipal ?? null))
      .catch(() => setUser(null))
  }, [])

  const health = useQuery({ queryKey: ['health'], queryFn: api.health, retry: false })

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-4 sm:p-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-50">Operations</h1>
        <p className="mt-1 text-sm text-slate-400">
          What is currently loaded, and who is signed in. Not linked from anywhere on the site.
        </p>
      </div>

      <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
        <h2 className="text-sm font-medium text-slate-200">Signed in as</h2>
        {user === undefined && <p className="mt-2 text-sm text-slate-400">Checking…</p>}
        {user === null && (
          <p className="mt-2 text-sm text-slate-400">
            No sign-in layer here — this page is only protected once it is served by Static Web Apps.
          </p>
        )}
        {user && (
          <dl className="mt-2 space-y-1 text-sm">
            <div className="flex gap-2">
              <dt className="w-28 shrink-0 text-slate-500">Account</dt>
              <dd className="text-slate-200">{user.userDetails}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="w-28 shrink-0 text-slate-500">Directory</dt>
              <dd className="text-slate-200">{user.identityProvider}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="w-28 shrink-0 text-slate-500">Roles</dt>
              <dd className="text-slate-200">{user.userRoles.join(', ') || '—'}</dd>
            </div>
          </dl>
        )}
        {user && (
          <a href="/.auth/logout" className="mt-3 inline-block text-sm text-sky-400 hover:underline">
            Sign out
          </a>
        )}
      </section>

      <section>
        <h2 className="text-sm font-medium text-slate-200">Data currently served</h2>
        {health.isLoading && <Spinner label="Asking the API" />}
        {health.error && <ErrorBox error={health.error} />}
        {health.data && (
          <div className="mt-3 grid grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-4">
            <Stat label="API" value={health.data.status} tone={health.data.status === 'ok' ? 'good' : 'warn'} />
            <Stat label="Airports" value={(health.data.airports ?? 0).toLocaleString()} />
            <Stat label="Occurrences in window" value={(health.data.occurrences_in_window ?? 0).toLocaleString()} />
            <Stat label="Airport reports" value={(health.data.airport_reports ?? 0).toLocaleString()} />
          </div>
        )}
        <p className="mt-3 text-xs text-slate-500">
          These counts come straight from the database. If the numbers here disagree with the site, a batch job ran
          and the browser is holding a cached response.
        </p>
      </section>
    </div>
  )
}
