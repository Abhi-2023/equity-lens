const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8002'

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail || detail
    } catch {
      // no JSON body
    }
    throw new Error(detail)
  }
  if (res.status === 204) return null
  return res.json()
}

export function createReport(company, depth) {
  return request('/reports', { method: 'POST', body: JSON.stringify({ company, depth }) })
}

export function listRecentReports(limit = 5) {
  return request(`/reports?limit=${limit}`)
}

export function getReportStatus(jobId) {
  return request(`/reports/${jobId}/status`)
}

export function getReport(jobId) {
  return request(`/reports/${jobId}`)
}

export function getReportByReportId(reportId) {
  return request(`/reports/by-id/${reportId}`)
}

export function streamReportUrl(jobId) {
  return `${BASE_URL}/reports/${jobId}/stream`
}

export function listWatchlist() {
  return request('/watchlist')
}

export function addToWatchlist(company, refreshCadenceDays = 7) {
  return request('/watchlist', {
    method: 'POST',
    body: JSON.stringify({ company, refresh_cadence_days: refreshCadenceDays }),
  })
}

export function removeFromWatchlist(entryId) {
  return request(`/watchlist/${entryId}`, { method: 'DELETE' })
}

export function getCompanyHistory(ticker) {
  return request(`/companies/${ticker}/history`)
}

export function diffReports(reportId, otherReportId) {
  return request(`/reports/${reportId}/diff/${otherReportId}`)
}
