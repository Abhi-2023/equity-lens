import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { addToWatchlist, createReport, getReport, getReportStatus, listWatchlist } from '../api'
import useReportStream from '../hooks/useReportStream'
import AgentTracePanel from '../components/AgentTracePanel'
import ReportView from '../components/ReportView'

const POLL_MS = 2000

export default function ReportPage() {
  const { jobId } = useParams()
  const navigate = useNavigate()
  const { events } = useReportStream(jobId)

  const [status, setStatus] = useState(null)
  const [report, setReport] = useState(null)
  const [watchlisted, setWatchlisted] = useState(false)

  const refreshStatus = useCallback(async () => {
    try {
      const s = await getReportStatus(jobId)
      setStatus(s)
      if (s.status === 'completed') {
        const r = await getReport(jobId)
        setReport(r)
      }
    } catch {
      // job not found yet right after creation — the next poll will catch up
    }
  }, [jobId])

  useEffect(() => {
    setStatus(null)
    setReport(null)
    refreshStatus()
    const interval = setInterval(() => {
      setStatus((current) => {
        if (current && current.status !== 'running') {
          clearInterval(interval)
          return current
        }
        refreshStatus()
        return current
      })
    }, POLL_MS)
    return () => clearInterval(interval)
  }, [jobId, refreshStatus])

  useEffect(() => {
    if (!report?.ticker) return
    listWatchlist()
      .then((entries) => setWatchlisted(entries.some((e) => e.ticker === report.ticker)))
      .catch(() => {})
  }, [report?.ticker])

  async function handleAddToWatchlist() {
    if (!report) return
    await addToWatchlist(report.ticker)
    setWatchlisted(true)
  }

  async function handleRerun() {
    if (!report) return
    const { job_id } = await createReport(report.company, 'deep')
    navigate(`/reports/${job_id}`)
  }

  const isRunning = !status || status.status === 'running'
  const isFailed = status?.status === 'failed'
  const isLoadingReport = status?.status === 'completed' && !report

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      {isRunning && (
        <>
          <h1 className="mb-4 text-xl font-semibold text-slate-900">
            Researching {status?.company_input || '…'}
          </h1>
          <AgentTracePanel events={events} />
        </>
      )}

      {isFailed && (
        <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-red-800">
          <h1 className="font-semibold">Report generation failed</h1>
          <p className="mt-1 text-sm">{status.error}</p>
        </div>
      )}

      {isLoadingReport && <p className="text-sm text-slate-500">Loading finished report…</p>}

      {report && (
        <div className={isRunning ? 'mt-8' : ''}>
          <ReportView
            report={report}
            onRerun={handleRerun}
            onAddToWatchlist={handleAddToWatchlist}
            watchlisted={watchlisted}
          />
        </div>
      )}
    </div>
  )
}
