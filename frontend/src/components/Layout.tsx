import { Link, useLocation } from "react-router-dom";
import { TrendingUp, Search } from "lucide-react";
import clsx from "clsx";

const navLinks = [
  { path: "/portfolio", label: "Portfolios" },
  { path: "/",          label: "Screener" },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();

  return (
    <div className="min-h-screen flex flex-col bg-white">
      {/* ── Top nav ── */}
      <header className="bg-white border-b border-gray-200 shadow-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 flex items-center h-14 gap-8">
          {/* Logo */}
          <Link to="/" className="flex items-center gap-2 shrink-0">
            <div className="rounded p-1" style={{ backgroundColor: "#0038B8" }}>
              <TrendingUp className="w-4 h-4 text-white" />
            </div>
            <span className="text-xs font-bold leading-tight text-gray-800 uppercase tracking-tight">
              TASE<br />DIVIDENDS
            </span>
          </Link>

          {/* Nav links */}
          <nav className="flex items-center gap-1 flex-1">
            {navLinks.map(({ path, label }) => {
              const active = pathname === path;
              return (
                <Link
                  key={path}
                  to={path}
                  className={clsx(
                    "px-3 py-1.5 text-sm font-medium rounded transition-colors",
                    active ? "text-gray-900 font-semibold" : "text-gray-500 hover:text-gray-800"
                  )}
                >
                  {label}
                </Link>
              );
            })}
          </nav>

          {/* Search */}
          <div className="relative w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Find a stock or fund"
              className="w-full pl-9 pr-3 py-1.5 text-sm border border-gray-200 rounded-full bg-gray-50 focus:outline-none focus:ring-2 focus:border-transparent transition"
              style={{ "--tw-ring-color": "#0038B8" } as React.CSSProperties}
            />
          </div>

          {/* Avatar */}
          <div className="w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-semibold shrink-0" style={{ backgroundColor: "#0038B8" }}>
            Y
          </div>
        </div>
      </header>

      {/* ── Page content ── */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-6 py-8">
        {children}
      </main>

      <footer className="border-t border-gray-200 bg-white text-center text-xs text-gray-400 py-3">
        TASE Dividend Screener · Data sourced from Maya &amp; TASE official APIs · Not investment advice
      </footer>
    </div>
  );
}
