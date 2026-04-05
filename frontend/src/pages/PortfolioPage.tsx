import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Plus, Trash2, RefreshCw, CalendarDays, PieChart } from "lucide-react";
import { PieChart as RechartsPie, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from "recharts";

import { fetchPortfolio } from "../api/portfolio";
import type { HoldingIn, PortfolioSummary } from "../api/types";
import Spinner from "../components/Spinner";

const PIE_COLORS = ["#1e40af", "#3b82f6", "#60a5fa", "#93c5fd", "#bfdbfe", "#1d4ed8", "#2563eb"];

const fmt = {
  ils: (v: number | null | undefined) =>
    v == null ? "—" : `₪${v.toLocaleString("he-IL", { maximumFractionDigits: 0 })}`,
  pct: (v: number | null | undefined) => (v == null ? "—" : `${v.toFixed(2)}%`),
};

function SummaryCard({
  label, value, sub, highlight,
}: { label: string; value: string; sub?: string; highlight?: boolean }) {
  return (
    <div className={`rounded-xl border p-5 ${highlight ? "bg-brand-700 border-brand-600 text-white" : "bg-white border-gray-200"}`}>
      <p className={`text-xs mb-1 ${highlight ? "text-brand-200" : "text-gray-500"}`}>{label}</p>
      <p className={`text-2xl font-bold ${highlight ? "text-white" : "text-gray-900"}`}>{value}</p>
      {sub && <p className={`text-xs mt-1 ${highlight ? "text-brand-200" : "text-gray-400"}`}>{sub}</p>}
    </div>
  );
}

// ── Holdings editor ───────────────────────────────────────────────────────────

function HoldingsEditor({
  holdings,
  onChange,
}: {
  holdings: HoldingIn[];
  onChange: (h: HoldingIn[]) => void;
}) {
  const add = () => onChange([...holdings, { ticker: "", shares: 0 }]);
  const remove = (i: number) => onChange(holdings.filter((_, idx) => idx !== i));
  const update = (i: number, field: keyof HoldingIn, value: string | number) =>
    onChange(holdings.map((h, idx) => (idx === i ? { ...h, [field]: value } : h)));

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
      <h3 className="text-sm font-semibold text-gray-700 mb-4">My Holdings</h3>
      <div className="space-y-2 mb-4">
        {holdings.map((h, i) => (
          <div key={i} className="flex gap-2 items-center">
            <input
              type="text"
              placeholder="Ticker"
              value={h.ticker}
              onChange={e => update(i, "ticker", e.target.value.toUpperCase())}
              className="w-28 border border-gray-200 rounded-lg px-3 py-1.5 text-sm font-mono uppercase focus:ring-2 focus:ring-brand-500 focus:border-transparent outline-none"
            />
            <input
              type="number"
              placeholder="Shares"
              min={1}
              value={h.shares || ""}
              onChange={e => update(i, "shares", +e.target.value)}
              className="flex-1 border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-brand-500 focus:border-transparent outline-none"
            />
            <button
              onClick={() => remove(i)}
              className="text-gray-400 hover:text-red-500 transition-colors"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>
      <button
        onClick={add}
        className="flex items-center gap-1.5 text-sm text-brand-600 hover:text-brand-800 font-medium"
      >
        <Plus className="w-4 h-4" /> Add holding
      </button>
    </div>
  );
}

// ── Dividend calendar ─────────────────────────────────────────────────────────

function DividendCalendar({ events }: { events: PortfolioSummary["upcoming_dividends"] }) {
  if (!events.length) return null;

  // Group by month
  const byMonth: Record<string, typeof events> = {};
  events.forEach(e => {
    const month = e.ex_date.slice(0, 7);
    if (!byMonth[month]) byMonth[month] = [];
    byMonth[month].push(e);
  });

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
      <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
        <CalendarDays className="w-4 h-4" /> Upcoming Dividends (90 days)
      </h3>
      <div className="space-y-4">
        {Object.entries(byMonth).map(([month, items]) => (
          <div key={month}>
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">{month}</p>
            <div className="space-y-1.5">
              {items.map(e => (
                <div key={`${e.ticker}-${e.ex_date}`}
                  className="flex items-center justify-between bg-blue-50 rounded-lg px-3 py-2">
                  <div>
                    <span className="font-semibold text-brand-700 text-sm">{e.ticker}</span>
                    <span className="text-gray-400 text-xs ml-2">ex {e.ex_date}</span>
                    {e.payment_date && (
                      <span className="text-gray-400 text-xs ml-1">· pay {e.payment_date}</span>
                    )}
                  </div>
                  <span className="text-sm font-medium text-gray-700">
                    ₪{e.amount_per_share_ils.toFixed(4)}/share
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Sector pie ────────────────────────────────────────────────────────────────

function SectorPie({ data }: { data: PortfolioSummary["sector_breakdown"] }) {
  if (!data.length) return null;
  const pieData = data.map(d => ({ name: d.sector, value: d.value_ils }));

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
      <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
        <PieChart className="w-4 h-4" /> Sector Diversification
      </h3>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <RechartsPie>
            <Pie
              data={pieData}
              cx="50%"
              cy="50%"
              innerRadius={50}
              outerRadius={75}
              paddingAngle={3}
              dataKey="value"
            >
              {pieData.map((_, i) => (
                <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
              ))}
            </Pie>
            <Tooltip formatter={(v) => fmt.ils(v as number)} />
            <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11 }} />
          </RechartsPie>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ── Holdings table ────────────────────────────────────────────────────────────

function HoldingsTable({ holdings }: { holdings: PortfolioSummary["holdings"] }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-x-auto">
      <h3 className="text-sm font-semibold text-gray-700 px-5 pt-4 pb-3 border-b border-gray-100">
        Holdings Breakdown
      </h3>
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-50 border-b border-gray-100 text-xs text-gray-500 uppercase tracking-wide">
            <th className="px-4 py-2 text-left">Stock</th>
            <th className="px-4 py-2 text-left">Sector</th>
            <th className="px-4 py-2 text-right">Shares</th>
            <th className="px-4 py-2 text-right">Price</th>
            <th className="px-4 py-2 text-right">Value</th>
            <th className="px-4 py-2 text-right">Annual Income</th>
            <th className="px-4 py-2 text-right">Yield</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {holdings.map(h => (
            <tr key={h.ticker} className="hover:bg-gray-50">
              <td className="px-4 py-2.5">
                <span className="font-semibold text-brand-700">{h.ticker}</span>
                {h.name_en && <p className="text-xs text-gray-400 truncate max-w-[120px]">{h.name_en}</p>}
              </td>
              <td className="px-4 py-2.5 text-gray-500 text-xs">{h.sector ?? "—"}</td>
              <td className="px-4 py-2.5 text-right">{h.shares.toLocaleString()}</td>
              <td className="px-4 py-2.5 text-right text-gray-600">
                {h.price != null ? `₪${h.price.toFixed(2)}` : "—"}
              </td>
              <td className="px-4 py-2.5 text-right font-medium">{fmt.ils(h.position_value_ils)}</td>
              <td className="px-4 py-2.5 text-right text-green-700 font-medium">
                {fmt.ils(h.annual_income_ils)}
              </td>
              <td className="px-4 py-2.5 text-right">{fmt.pct(h.dividend_yield)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function PortfolioPage() {
  const [holdings, setHoldings] = useState<HoldingIn[]>([
    { ticker: "", shares: 0 },
  ]);

  const mutation = useMutation({
    mutationFn: fetchPortfolio,
  });

  const calculate = () => {
    const valid = holdings.filter(h => h.ticker && h.shares > 0);
    if (valid.length) mutation.mutate(valid);
  };

  const summary = mutation.data;

  return (
    <div className="flex gap-6">
      {/* ── Left panel: holdings input ── */}
      <aside className="w-64 flex-shrink-0 space-y-3">
        <HoldingsEditor holdings={holdings} onChange={setHoldings} />
        <button
          onClick={calculate}
          disabled={mutation.isPending}
          className="w-full flex items-center justify-center gap-2 bg-brand-700 hover:bg-brand-800 text-white rounded-xl px-4 py-2.5 text-sm font-semibold transition-colors disabled:opacity-60"
        >
          {mutation.isPending ? (
            <Spinner className="w-4 h-4" />
          ) : (
            <RefreshCw className="w-4 h-4" />
          )}
          Calculate
        </button>
        {mutation.isError && (
          <p className="text-xs text-red-600">Failed to load portfolio data. Check the API.</p>
        )}
      </aside>

      {/* ── Right: results ── */}
      <div className="flex-1 min-w-0 space-y-6">
        {!summary && !mutation.isPending && (
          <div className="flex flex-col items-center justify-center py-20 text-gray-400">
            <PieChart className="w-12 h-12 mb-3 opacity-30" />
            <p className="text-sm">Enter your holdings and click Calculate</p>
          </div>
        )}

        {mutation.isPending && (
          <div className="flex justify-center py-20">
            <Spinner className="w-8 h-8" />
          </div>
        )}

        {summary && (
          <>
            {/* Summary cards */}
            <div className="grid grid-cols-3 gap-3">
              <SummaryCard
                label="Portfolio Value"
                value={fmt.ils(summary.total_value_ils)}
                highlight
              />
              <SummaryCard
                label="Annual Income"
                value={fmt.ils(summary.annual_income_ils)}
                sub="Projected (trailing 12m)"
              />
              <SummaryCard
                label="Portfolio Yield"
                value={fmt.pct(summary.portfolio_yield)}
                sub="Income / Market Value"
              />
            </div>

            {/* Charts row */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <SectorPie data={summary.sector_breakdown} />
              <DividendCalendar events={summary.upcoming_dividends} />
            </div>

            {/* Holdings table */}
            <HoldingsTable holdings={summary.holdings} />
          </>
        )}
      </div>
    </div>
  );
}
