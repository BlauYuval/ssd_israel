import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, TrendingUp, Building2, CalendarDays } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";

import { fetchStockDetail, fetchStockDividends } from "../api/screener";
import SafetyBadge from "../components/SafetyBadge";
import ScoreBar from "../components/ScoreBar";
import Spinner from "../components/Spinner";

const fmt = {
  pct: (v: number | null | undefined) => (v == null ? "—" : `${v.toFixed(1)}%`),
  ils: (v: number | null | undefined) =>
    v == null ? "—" : `₪${v.toLocaleString("he-IL", { maximumFractionDigits: 2 })}`,
  big: (v: number | null | undefined) => {
    if (v == null) return "—";
    if (Math.abs(v) >= 1_000_000) return `₪${(v / 1_000_000).toFixed(1)}B`;
    if (Math.abs(v) >= 1_000) return `₪${(v / 1_000).toFixed(0)}M`;
    return `₪${v.toFixed(0)}K`;
  },
};

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className="text-xl font-semibold text-gray-900">{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  );
}

export default function StockDetailPage() {
  const { ticker = "" } = useParams<{ ticker: string }>();
  const navigate = useNavigate();

  const { data: stock, isLoading, isError } = useQuery({
    queryKey: ["stock", ticker],
    queryFn: () => fetchStockDetail(ticker),
    enabled: !!ticker,
  });

  const { data: dividends } = useQuery({
    queryKey: ["dividends", ticker],
    queryFn: () => fetchStockDividends(ticker, 20),
    enabled: !!ticker,
  });

  if (isLoading) {
    return (
      <div className="flex justify-center py-20">
        <Spinner className="w-8 h-8" />
      </div>
    );
  }

  if (isError || !stock) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-red-700">
        Stock "{ticker}" not found or API is unavailable.
      </div>
    );
  }

  const chartData = dividends?.map(d => ({
    date: d.ex_date.slice(0, 7),
    amount: d.amount_ils,
  })).reverse() ?? [];

  const breakdown = stock.safety_score_breakdown;

  return (
    <div className="space-y-6">
      {/* Back + header */}
      <div>
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1 text-sm text-brand-600 hover:underline mb-3"
        >
          <ArrowLeft className="w-4 h-4" /> Back to Screener
        </button>

        <div className="flex items-start justify-between flex-wrap gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{stock.ticker}</h1>
            <p className="text-gray-500 text-sm mt-0.5">
              {stock.name_en ?? stock.name_he ?? ""}
              {stock.sector && <span className="ml-2 text-gray-400">· {stock.sector}</span>}
              {stock.isin && <span className="ml-2 text-gray-300">· {stock.isin}</span>}
            </p>
          </div>
          <SafetyBadge score={stock.safety_score} size="lg" />
        </div>
      </div>

      {/* Key stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="Price" value={fmt.ils(stock.price)} />
        <StatCard
          label="Dividend Yield"
          value={fmt.pct(stock.dividend_yield)}
          sub="Trailing 12 months"
        />
        <StatCard
          label="Payout Ratio"
          value={stock.payout_ratio != null ? fmt.pct(stock.payout_ratio * 100) : "—"}
          sub={`FY${stock.fiscal_year ?? ""}`}
        />
        <StatCard
          label="Market Cap"
          value={fmt.big(stock.market_cap)}
        />
      </div>

      {/* 52-week range */}
      {stock.week52_high != null && stock.week52_low != null && (
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <p className="text-xs font-medium text-gray-500 mb-2 flex items-center gap-1">
            <TrendingUp className="w-3.5 h-3.5" /> 52-Week Range
          </p>
          <div className="flex items-center gap-3 text-sm">
            <span className="text-gray-500">{fmt.ils(stock.week52_low)}</span>
            <div className="flex-1 relative h-2 bg-gray-100 rounded-full">
              {stock.price != null && (
                <div
                  className="absolute top-0 h-2 w-2 bg-brand-600 rounded-full -translate-x-1/2"
                  style={{
                    left: `${Math.min(100, Math.max(0,
                      ((stock.price - stock.week52_low) / (stock.week52_high - stock.week52_low)) * 100
                    ))}%`,
                  }}
                />
              )}
            </div>
            <span className="text-gray-500">{fmt.ils(stock.week52_high)}</span>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Safety score breakdown */}
        {breakdown && (
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h2 className="text-sm font-semibold text-gray-700 mb-4">
              Dividend Safety Score · {stock.safety_score?.toFixed(0)}/100
            </h2>
            <div className="space-y-3">
              <ScoreBar label="Payout Ratio"   score={breakdown.payout.score}       max={breakdown.payout.max}       detail={breakdown.payout.label} />
              <ScoreBar label="FCF Coverage"   score={breakdown.fcf_coverage.score} max={breakdown.fcf_coverage.max} detail={breakdown.fcf_coverage.label} />
              <ScoreBar label="Debt / Equity"  score={breakdown.debt.score}         max={breakdown.debt.max}         detail={breakdown.debt.label} />
              <ScoreBar label="Div. History"   score={breakdown.history.score}      max={breakdown.history.max}      detail={breakdown.history.label} />
              <ScoreBar label="Div. Growth"    score={breakdown.growth.score}       max={breakdown.growth.max}       detail={breakdown.growth.label} />
            </div>
            <p className="text-xs text-gray-400 mt-4">
              Each component is scored transparently. Methodology based on plan v1.0.
            </p>
          </div>
        )}

        {/* Fundamentals */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-1.5">
            <Building2 className="w-4 h-4" />
            Financials {stock.fiscal_year ? `(FY${stock.fiscal_year})` : ""}
          </h2>
          <div className="space-y-2 text-sm">
            {[
              { label: "Revenue",         value: fmt.big(stock.revenue) },
              { label: "Net Income",      value: fmt.big(stock.net_income) },
              { label: "Free Cash Flow",  value: fmt.big(stock.free_cash_flow) },
              { label: "EPS",             value: fmt.ils(stock.eps) },
              { label: "FCF Payout",      value: stock.fcf_payout_ratio != null ? fmt.pct(stock.fcf_payout_ratio * 100) : "—" },
              { label: "Debt / Equity",   value: stock.debt_to_equity?.toFixed(2) ?? "—" },
            ].map(({ label, value }) => (
              <div key={label} className="flex justify-between border-b border-gray-50 pb-1 last:border-0">
                <span className="text-gray-500">{label}</span>
                <span className="font-medium text-gray-800">{value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Dividend history */}
      {dividends && dividends.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-1.5">
            <CalendarDays className="w-4 h-4" /> Dividend History
          </h2>

          {chartData.length >= 2 && (
            <div className="h-36 mb-5">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} barSize={16}>
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
                  <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={48}
                    tickFormatter={v => `₪${v.toFixed(2)}`} />
                  <Tooltip formatter={(v) => [`₪${(v as number).toFixed(4)}`, "Amount"]} />
                  <Bar dataKey="amount" radius={[3, 3, 0, 0]}>
                    {chartData.map((_, i) => (
                      <Cell key={i} fill={i === chartData.length - 1 ? "#1e40af" : "#93c5fd"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-100 text-gray-400">
                <th className="text-left py-1.5 pr-4">Ex-Date</th>
                <th className="text-left py-1.5 pr-4">Payment Date</th>
                <th className="text-right py-1.5 pr-4">Amount (₪)</th>
                <th className="text-right py-1.5">Yield at Declaration</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {dividends.map(d => (
                <tr key={d.ex_date} className="text-gray-700">
                  <td className="py-1.5 pr-4">{d.ex_date}</td>
                  <td className="py-1.5 pr-4">{d.payment_date ?? "—"}</td>
                  <td className="py-1.5 pr-4 text-right font-medium">{d.amount_ils.toFixed(4)}</td>
                  <td className="py-1.5 text-right text-gray-500">
                    {d.dividend_yield_at_declaration != null
                      ? `${d.dividend_yield_at_declaration.toFixed(2)}%`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
