import { NavLink } from 'react-router-dom'

const linkClass = ({ isActive }) =>
  `rounded-md px-3 py-1.5 text-sm font-medium ${
    isActive ? 'bg-indigo-600 text-white' : 'text-slate-600 hover:bg-slate-100'
  }`

export default function Nav() {
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-3">
        <NavLink to="/" className="text-lg font-semibold text-slate-900">
          EquityLens
        </NavLink>
        <nav className="flex gap-1">
          <NavLink to="/" end className={linkClass}>
            Search
          </NavLink>
          <NavLink to="/watchlist" className={linkClass}>
            Watchlist
          </NavLink>
        </nav>
      </div>
    </header>
  )
}
