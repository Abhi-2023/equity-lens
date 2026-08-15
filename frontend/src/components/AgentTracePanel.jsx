const STATUS_STYLES = {
  started: 'border-blue-300 bg-blue-50 text-blue-700',
  running: 'border-blue-300 bg-blue-50 text-blue-700',
  completed: 'border-green-300 bg-green-50 text-green-700',
  error: 'border-red-300 bg-red-50 text-red-700',
}

const NODE_LABELS = {
  planner: 'Planner',
  filings_agent: 'Filings agent',
  market_agent: 'Market agent',
  news_agent: 'News agent',
  evidence_assembly: 'Evidence assembly',
  synthesizer: 'Synthesizer',
  fact_checker: 'Fact-checker',
  finalize: 'Finalize',
  pipeline: 'Pipeline',
}

function StatusDot({ status }) {
  const color =
    status === 'completed'
      ? 'bg-green-500'
      : status === 'error'
        ? 'bg-red-500'
        : 'bg-blue-500 animate-pulse'
  return <span className={`inline-block h-2.5 w-2.5 rounded-full ${color}`} />
}

/** Live Agent Trace panel (Section 2.2) — one card per node, updated in
 * place as SSE events arrive, in the order each node first appeared. */
export default function AgentTracePanel({ events }) {
  const byNode = new Map()
  for (const evt of events) {
    const existing = byNode.get(evt.node) || { messages: [] }
    byNode.set(evt.node, {
      ...existing,
      node: evt.node,
      status: evt.status,
      elapsed_ms: evt.elapsed_ms,
      messages: [...existing.messages, evt.message].filter(Boolean),
    })
  }
  const cards = [...byNode.values()]

  if (cards.length === 0) {
    return <p className="text-sm text-slate-500">Waiting for the pipeline to start…</p>
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {cards.map((card) => (
        <div
          key={card.node}
          className={`rounded-lg border p-3 transition-colors ${STATUS_STYLES[card.status] || 'border-slate-200 bg-white text-slate-700'}`}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 font-medium">
              <StatusDot status={card.status} />
              {NODE_LABELS[card.node] || card.node}
            </div>
            {typeof card.elapsed_ms === 'number' && (
              <span className="text-xs opacity-70">{(card.elapsed_ms / 1000).toFixed(1)}s</span>
            )}
          </div>
          <p className="mt-1 text-sm opacity-90">{card.messages.at(-1)}</p>
        </div>
      ))}
    </div>
  )
}
