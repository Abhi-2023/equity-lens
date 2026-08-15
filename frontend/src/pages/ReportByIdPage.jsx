import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { addToWatchlist, createReport, getReportByReportId, listWatchlist } from '../api'
import ReportView from '../components/ReportView'

/** Renders an already-finished report looked up by its own id (from the
 * Watchlist or History views) — no polling/live-trace needed. */
export default function ReportByIdPage() {
  const { reportId } = useParams()
  const navigate = useNavigate()
  const [report, setReport] = useState(null)
  const [error, setError] = useState(null)
  const [watchlisted, setWatchlisted] = useState(false)
  const [watchlistBusy, setWatchlistBusy] = useState(false)

  useEffect(() => {
    setReport(null)
    setError(null)
    getReportByReportId(reportId)
      .then(setReport)
      .catch((err) => setError(err.message))
  }, [reportId])

  useEffect(() => {
    if (!report?.ticker) return
    listWatchlist()
      .then((entries) => setWatchlisted(entries.some((e) => e.ticker === report.ticker)))
      .catch(() => {})
  }, [report?.ticker])

  async function handleAddToWatchlist() {
    if (!report || watchlistBusy) return
    setWatchlistBusy(true)
    try {
      await addToWatchlist(report.ticker)
      setWatchlisted(true)
    } finally {
      setWatchlistBusy(false)
    }
  }

  async function handleRerun() {
    if (!report) return
    const { job_id } = await createReport(report.company, 'deep')
    navigate(`/reports/${job_id}`)
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      {error && <p className="text-sm text-red-600">{error}</p>}
      {report && (
        <ReportView
          report={report}
          onRerun={handleRerun}
          onAddToWatchlist={handleAddToWatchlist}
          watchlisted={watchlisted}
          watchlistBusy={watchlistBusy}
        />
      )}
    </div>
  )
}
