import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createReport, listWatchlist, listRecentReports } from '../api'
import { timeAgo } from '../lib/time'

const DEPTHS = [
  { value: 'quick', label: 'Quick brief' },
  { value: 'standard', label: 'Standard' },
  { value: 'deep', label: 'Deep dive' },
]

export default function SearchPage() {
  const navigate = useNavigate()
  const [company, setCompany] = useState('')
  const [depth, setDepth] = useState('standard')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [watchlist, setWatchlist] = useState([])
  const [recent, setRecent] = useState([])

  useEffect(() => {
    listWatchlist().then(setWatchlist).catch(() => {})
    listRecentReports().then(setRecent).catch(() => {})
  }, [])

  async function submit(companyOverride) {
    const target = companyOverride ?? company
    if (!target.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      const { job_id } = await createReport(target, depth)
      navigate(`/reports/${job_id}`)
    } catch (err) {
      setError(err.message)
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      <h1 className="text-center text-3xl font-semibold text-slate-900">EquityLens</h1>
      <p className="mt-2 text-center text-slate-500">
        Grounded, cited equity research — enter a company name or ticker.
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
        className="mt-8 space-y-4"
      >
        <input
          value={company}
          onChange={(e) => setCompany(e.target.value)}
          placeholder="Enter a company name or ticker (e.g., AAPL, Tesla, Zomato)"
          className="w-full rounded-lg border border-slate-300 px-4 py-3 text-lg focus:border-indigo-500 focus:outline-none"
        />

        <div className="flex justify-center gap-2">
          {DEPTHS.map((d) => (
            <button
              key={d.value}
              type="button"
              onClick={() => setDepth(d.value)}
              className={`rounded-full px-4 py-1.5 text-sm font-medium ${
                depth === d.value ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {d.label}
            </button>
          ))}
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-indigo-600 py-3 text-lg font-medium text-white hover:bg-indigo-500 disabled:bg-slate-300"
        >
          {submitting ? 'Starting research…' : 'Generate report'}
        </button>
        {error && <p className="text-center text-sm text-red-600">{error}</p>}
      </form>

      {watchlist.length > 0 && (
        <div className="mt-10">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Watchlist</h2>
          <div className="mt-2 flex flex-wrap gap-2">
            {watchlist.map((w) => (
              <button
                key={w.id}
                onClick={() => submit(w.ticker)}
                className="rounded-full border border-slate-300 px-3 py-1 text-sm text-slate-700 hover:bg-slate-50"
              >
                {w.ticker}
                {typeof w.day_change_pct === 'number' && (
                  <span className={w.day_change_pct >= 0 ? 'ml-1 text-green-600' : 'ml-1 text-red-600'}>
                    {w.day_change_pct >= 0 ? '+' : ''}
                    {w.day_change_pct}%
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      {recent.length > 0 && (
        <div className="mt-10">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Recent reports</h2>
          <ul className="mt-2 divide-y divide-slate-200 rounded-lg border border-slate-200">
            {recent.map((r) => (
              <li key={r.id}>
                <button
                  onClick={() => navigate(`/reports/${r.job_id}`)}
                  className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-slate-50"
                >
                  <span className="font-medium text-slate-800">
                    {r.company} {r.ticker && <span className="text-slate-400">({r.ticker})</span>}
                  </span>
                  <span className="text-xs text-slate-500">
                    data as of {timeAgo(r.created_at)}
                    {r.flagged_sections > 0 && (
                      <span className="ml-2 text-amber-600">{r.flagged_sections} flagged</span>
                    )}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
