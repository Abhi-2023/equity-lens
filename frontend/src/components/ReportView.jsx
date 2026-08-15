const SECTION_LABELS = {
  company_snapshot: 'Company snapshot',
  financial_health: 'Financial health',
  recent_developments: 'Recent developments',
  key_risks: 'Key risks',
  outlook_notes: 'Outlook notes',
}

const SECTION_ORDER = [
  'company_snapshot',
  'financial_health',
  'recent_developments',
  'key_risks',
  'outlook_notes',
]

function GroundednessBadge({ groundedness }) {
  const styles = {
    verified: 'bg-green-100 text-green-800',
    flagged: 'bg-amber-100 text-amber-800',
    unverified: 'bg-slate-100 text-slate-600',
  }
  const labels = {
    verified: 'Verified',
    flagged: 'Flagged — review',
    unverified: 'Unverified',
  }
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${styles[groundedness] || styles.unverified}`}>
      {labels[groundedness] || groundedness}
    </span>
  )
}

/** Report View (Section 2.3): structured sections with inline citation
 * markers resolved to a source list, plus a per-section groundedness badge
 * produced by the fact-checker agent. */
export default function ReportView({ report, onRerun, onAddToWatchlist, watchlisted, watchlistBusy }) {
  const flaggedCount = Object.values(report.sections).filter((s) => s.groundedness === 'flagged').length

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">
            {report.company} {report.ticker && <span className="text-slate-400">({report.ticker})</span>}
          </h1>
          <p className="text-sm text-slate-500">
            Version {report.version} · Generated {new Date(report.created_at).toLocaleString()} ·{' '}
            {flaggedCount === 0 ? (
              <span className="text-green-700">All claims verified</span>
            ) : (
              <span className="text-amber-700">{flaggedCount} section(s) flagged — review</span>
            )}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={onRerun}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Re-run with deeper research
          </button>
          <button
            onClick={onAddToWatchlist}
            disabled={watchlisted || watchlistBusy}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {watchlisted ? 'On watchlist' : watchlistBusy ? 'Adding…' : 'Add to watchlist'}
          </button>
        </div>
      </div>

      {SECTION_ORDER.filter((name) => report.sections[name]).map((name) => {
        const section = report.sections[name]
        return (
          <section key={name}>
            <div className="mb-1 flex items-center gap-2">
              <h2 className="text-lg font-semibold text-slate-900">{SECTION_LABELS[name] || name}</h2>
              <GroundednessBadge groundedness={section.groundedness} />
            </div>
            <p className="whitespace-pre-wrap text-slate-700">{section.content}</p>
            {section.citations.length > 0 && (
              <ul className="mt-2 space-y-1 text-xs text-slate-500">
                {section.citations.map((c) => (
                  <li key={c.id}>
                    [{c.id}]{' '}
                    {c.url ? (
                      <a href={c.url} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">
                        {c.source}
                      </a>
                    ) : (
                      c.source
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        )
      })}

      <p className="border-t border-slate-200 pt-4 text-xs text-slate-400">
        EquityLens is a research/summarization tool, not an advisory service. Nothing above is
        investment advice.
      </p>
    </div>
  )
}
