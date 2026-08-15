import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { addToWatchlist, listWatchlist, removeFromWatchlist } from '../api'
import { timeAgo } from '../lib/time'

/** Watchlist Dashboard (Section 2.4): grid of saved companies with
 * last-updated timestamp and a headline metric (price change, key risk
 * flag). Auto-refreshed server-side by the scheduler in
 * app/services/watchlist_scheduler.py — this page just reflects that state. */
export default function WatchlistPage() {
  const navigate = useNavigate()
  const [entries, setEntries] = useState([])
  const [company, setCompany] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  function load() {
    listWatchlist().then(setEntries).catch((err) => setError(err.message))
  }

  useEffect(load, [])

  async function handleAdd(e) {
    e.preventDefault()
    if (!company.trim()) return
    setBusy(true)
    setError(null)
    try {
      await addToWatchlist(company)
      setCompany('')
      load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function handleRemove(id) {
    await removeFromWatchlist(id)
    setEntries((prev) => prev.filter((e) => e.id !== id))
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <h1 className="text-2xl font-semibold text-slate-900">Watchlist</h1>
      <p className="mt-1 text-sm text-slate-500">
        Auto-refreshed on each company's own cadence — no manual trigger needed.
      </p>

      <form onSubmit={handleAdd} className="mt-4 flex gap-2">
        <input
          value={company}
          onChange={(e) => setCompany(e.target.value)}
          placeholder="Add a company or ticker…"
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 focus:border-indigo-500 focus:outline-none"
        />
        <button
          type="submit"
          disabled={busy}
          className="rounded-md bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-500 disabled:bg-slate-300"
        >
          Add
        </button>
      </form>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        {entries.map((entry) => (
          <div key={entry.id} className="rounded-lg border border-slate-200 bg-white p-4">
            <div className="flex items-start justify-between">
              <div>
                <h2 className="font-semibold text-slate-900">{entry.ticker}</h2>
                <p className="text-sm text-slate-500">{entry.company}</p>
              </div>
              <button
                onClick={() => handleRemove(entry.id)}
                className="text-xs text-slate-400 hover:text-red-600"
                aria-label={`Remove ${entry.ticker}`}
              >
                Remove
              </button>
            </div>

            <div className="mt-3 flex items-center justify-between">
              <div>
                {entry.last_price != null ? (
                  <span className="text-lg font-medium text-slate-900">${entry.last_price.toFixed(2)}</span>
                ) : (
                  <span className="text-sm text-slate-400">Price unavailable</span>
                )}
                {typeof entry.day_change_pct === 'number' && (
                  <span className={entry.day_change_pct >= 0 ? 'ml-2 text-green-600' : 'ml-2 text-red-600'}>
                    {entry.day_change_pct >= 0 ? '+' : ''}
                    {entry.day_change_pct}%
                  </span>
                )}
              </div>
              {entry.flagged_sections > 0 && (
                <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
                  {entry.flagged_sections} risk flag(s)
                </span>
              )}
            </div>

            <p className="mt-2 text-xs text-slate-400">
              Last refreshed: {entry.last_refreshed_at ? timeAgo(entry.last_refreshed_at) : 'not yet'} · every{' '}
              {entry.refresh_cadence_days}d
            </p>

            <div className="mt-3 flex gap-2 text-sm">
              {entry.latest_report_id && (
                <button
                  onClick={() => navigate(`/reports/by-id/${entry.latest_report_id}`)}
                  className="text-indigo-600 hover:underline"
                >
                  View latest report
                </button>
              )}
              <Link to={`/history/${entry.ticker}`} className="text-indigo-600 hover:underline">
                History
              </Link>
            </div>
          </div>
        ))}
        {entries.length === 0 && <p className="text-sm text-slate-500">No companies on your watchlist yet.</p>}
      </div>
    </div>
  )
}
