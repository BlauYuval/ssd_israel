import { Link, useLocation } from "react-router-dom";
import { BarChart2, BriefcaseBusiness } from "lucide-react";
import clsx from "clsx";

const tabs = [
  { path: "/",          label: "Screener",  Icon: BarChart2 },
  { path: "/portfolio", label: "Portfolio", Icon: BriefcaseBusiness },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      {/* ── Header ── */}
      <header className="bg-brand-800 text-white shadow-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-16">
          <div className="flex items-center gap-3">
            <div className="bg-white rounded-md p-1.5">
              <BarChart2 className="w-5 h-5 text-brand-800" />
            </div>
            <span className="text-lg font-semibold tracking-tight">
              TASE Dividend Screener
            </span>
          </div>
          <span className="text-brand-200 text-sm hidden sm:block">
            Israeli Stocks · Tel Aviv Stock Exchange
          </span>
        </div>
      </header>

      {/* ── Tab bar ── */}
      <nav className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex gap-1">
          {tabs.map(({ path, label, Icon }) => {
            const active = pathname === path;
            return (
              <Link
                key={path}
                to={path}
                className={clsx(
                  "flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors",
                  active
                    ? "border-brand-700 text-brand-700"
                    : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
                )}
              >
                <Icon className="w-4 h-4" />
                {label}
              </Link>
            );
          })}
        </div>
      </nav>

      {/* ── Page content ── */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-6">
        {children}
      </main>

      <footer className="bg-white border-t border-gray-200 text-center text-xs text-gray-400 py-3">
        TASE Dividend Screener · Data sourced from Maya &amp; TASE official APIs · Not investment advice
      </footer>
    </div>
  );
}
