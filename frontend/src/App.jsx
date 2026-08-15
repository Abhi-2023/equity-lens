import { Route, Routes } from 'react-router-dom'
import Nav from './components/Nav'
import SearchPage from './pages/SearchPage'
import ReportPage from './pages/ReportPage'
import ReportByIdPage from './pages/ReportByIdPage'
import WatchlistPage from './pages/WatchlistPage'
import HistoryPage from './pages/HistoryPage'

export default function App() {
  return (
    <div className="min-h-screen bg-slate-50">
      <Nav />
      <Routes>
        <Route path="/" element={<SearchPage />} />
        <Route path="/reports/by-id/:reportId" element={<ReportByIdPage />} />
        <Route path="/reports/:jobId" element={<ReportPage />} />
        <Route path="/watchlist" element={<WatchlistPage />} />
        <Route path="/history/:ticker" element={<HistoryPage />} />
      </Routes>
    </div>
  )
}
