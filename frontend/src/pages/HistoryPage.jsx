import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { diffReports, getCompanyHistory } from '../api'

function DiffLine({ line }) {
  let color = 'text-slate-600'
  if (line.startsWith('+') && !line.startsWith('+++')) color = 'bg-green-50 text-green-800'
  else if (line.startsWith('-') && !line.startsWith('---')) color = 'bg-red-50 text-red-800'
  else if (line.startsWith('@@')) color = 'text-indigo-500'
  return <div className={`whitespace-pre-wrap px-2 font-mono text-xs ${color}`}>{line || ' '}</div>
}

/** History / Past Reports view with diff (Section 2.5). */
export default function HistoryPage() {
  const { ticker } = useParams()
  const [history, setHistory] = useState([])
  const [fromId, setFromId] = useState(null)
  const [toId, setToId] = useState(null)
  const [diff, setDiff] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    getCompanyHistory(ticker).then((rows) => {
      setHistory(rows)
      if (rows.length >= 2) {
        setToId(rows[0].id)
        setFromId(rows[1].id)
      }
    })
  }, [ticker])

  useEffect(() => {
    if (!fromId || !toId || fromId === toId) {
      setDiff(null)
      return
    }
    diffReports(toId, fromId)
      .then(setDiff)
      .catch((err) => setError(err.message))
  }, [fromId, toId])

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="text-2xl font-semibold text-slate-900">{ticker} report history</h1>
      <p className="mt-1 text-sm text-slate-500">
        {history.length} version{history.length === 1 ? '' : 's'}
      </p>

      <ul className="mt-4 divide-y divide-slate-200 rounded-lg border border-slate-200">
        {history.map((r) => (
          <li key={r.id} className="flex items-center justify-between px-4 py-2 text-sm">
            <Link to={`/reports/by-id/${r.id}`} className="font-medium text-indigo-600 hover:underline">
              v{r.version}
            </Link>
            <span className="text-slate-500">{new Date(r.created_at).toLocaleString()}</span>
            {r.flagged_sections > 0 && (
              <span className="text-amber-600">{r.flagged_sections} flagged</span>
            )}
          </li>
        ))}
      </ul>

      {history.length >= 2 && (
        <div className="mt-6">
          <div className="flex items-center gap-2 text-sm">
            <span>Compare</span>
            <select
              value={fromId || ''}
              onChange={(e) => setFromId(e.target.value)}
              className="rounded border border-slate-300 px-2 py-1"
            >
              {history.map((r) => (
                <option key={r.id} value={r.id}>
                  v{r.version}
                </option>
              ))}
            </select>
            <span>against</span>
            <select
              value={toId || ''}
              onChange={(e) => setToId(e.target.value)}
              className="rounded border border-slate-300 px-2 py-1"
            >
              {history.map((r) => (
                <option key={r.id} value={r.id}>
                  v{r.version}
                </option>
              ))}
            </select>
          </div>

          {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

          {diff && (
            <div className="mt-4 space-y-4">
              {Object.entries(diff.sections).map(([name, section]) => (
                <div key={name} className="rounded-lg border border-slate-200">
                  <div className="border-b border-slate-200 bg-slate-50 px-3 py-1.5 text-sm font-medium text-slate-700">
                    {name} {!section.changed && <span className="text-slate-400">(unchanged)</span>}
                  </div>
                  {section.changed && (
                    <div className="py-1">
                      {section.diff_lines.map((line, i) => (
                        <DiffLine key={i} line={line} />
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
