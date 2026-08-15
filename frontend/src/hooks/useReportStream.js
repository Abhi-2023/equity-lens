import { useEffect, useRef, useState } from 'react'
import { streamReportUrl } from '../api'

/** Consumes the SSE live-trace stream for a report job (Section 2.2).
 * Returns the ordered list of status events and whether the stream is
 * still open. */
export default function useReportStream(jobId) {
  const [events, setEvents] = useState([])
  const [connected, setConnected] = useState(false)
  const sourceRef = useRef(null)

  useEffect(() => {
    if (!jobId) return undefined
    setEvents([])

    const source = new EventSource(streamReportUrl(jobId))
    sourceRef.current = source
    setConnected(true)

    source.addEventListener('status', (evt) => {
      try {
        setEvents((prev) => [...prev, JSON.parse(evt.data)])
      } catch {
        setEvents((prev) => [...prev, { node: 'unknown', status: 'running', message: evt.data }])
      }
    })

    source.onerror = () => {
      setConnected(false)
      source.close()
    }

    return () => {
      source.close()
      setConnected(false)
    }
  }, [jobId])

  return { events, connected }
}
