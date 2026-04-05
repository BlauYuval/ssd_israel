import { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { ChevronUp, ChevronDown, Download, SlidersHorizontal, X } from "lucide-react";
import clsx from "clsx";

import { fetchScreener } from "../api/screener";
import type { ScreenerFilters, ScreenerRow } from "../api/types";
import SafetyBadge from "../components/SafetyBadge";
import Spinner from "../components/Spinner";

// ── helpers ─────────────────────────────────────────────────────────────────

const fmt = {
  pct: (v: number | null) => (v == null ? "—" : `${v.toFixed(1)}%`),
  ils: (v: number | null) => (v == null ? "—" : `₪${v.toLocaleString("he-IL", { maximumFractionDigits: 2 })}`),
  mcap: (v: number | null) => {
    if (v == null) return "—";
    if (v >= 1_000_000) return `₪${(v / 1_000_000).toFixed(1)}B`;
    if (v >= 1_000) return `₪${(v / 1_000).toFixed(0)}M`;
    return `₪${v.toFixed(0)}K`;
  },
};

const SORT_OPTIONS = [
  { value: "yield",        label: "Yield" },
  { value: "safety_score", label: "Safety Score" },
  { value: "payout_ratio", label: "Payout Ratio" },
  { value: "market_cap",   label: "Market Cap" },
] as const;

type SortBy = typeof SORT_OPTIONS[number]["value"];

const columns: { key: keyof ScreenerRow | "name"; label: string; sortable?: SortBy }[] = [
  { key: "ticker",        label: "Stock" },
  { key: "name",          label: "Name" },
  { key: "sector",        label: "Sector" },
  { key: "dividend_yield", label: "Yield",        sortable: "yield" },
  { key: "safety_score",  label: "Safety Score",  sortable: "safety_score" },
  { key: "payout_ratio",  label: "Payout Ratio",  sortable: "payout_ratio" },
  { key: "market_cap",    label: "Market Cap",    sortable: "market_cap" },
  { key: "price",         label: "Price" },
];

// ── filter panel ─────────────────────────────────────────────────────────────

interface FilterPanelProps {
  filters: ScreenerFilters;
  onChange: (f: Partial<ScreenerFilters>) => void;
  onReset: () => void;
}

function FilterPanel({ filters, onChange, onReset }: FilterPanelProps) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 space-y-5">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
          <SlidersHorizontal className="w-4 h-4" /> Filters
        </h3>
        <button onClick={onReset} className="text-xs text-brand-600 hover:underline flex items-center gap-1">
          <X className="w-3 h-3" /> Reset
        </button>
      </div>

      {/* Dividend Yield */}
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-2">Dividend Yield (%)</label>
        <div className="flex gap-2">
          <input
            type="number" placeholder="Min" min={0} max={100} step={0.5}
            value={filters.yield_min ?? ""}
            onChange={e => onChange({ yield_min: e.target.value ? +e.target.value : undefined })}
            className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-brand-500 focus:border-transparent outline-none"
          />
          <input
            type="number" placeholder="Max" min={0} max={100} step={0.5}
            value={filters.yield_max ?? ""}
            onChange={e => onChange({ yield_max: e.target.value ? +e.target.value : undefined })}
            className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-brand-500 focus:border-transparent outline-none"
          />
        </div>
      </div>

      {/* Safety Score */}
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-2">Safety Score (0–100)</label>
        <div className="flex gap-2">
          <input
            type="number" placeholder="Min" min={0} max={100}
            value={filters.safety_min ?? ""}
            onChange={e => onChange({ safety_min: e.target.value ? +e.target.value : undefined })}
            className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-brand-500 focus:border-transparent outline-none"
          />
          <input
            type="number" placeholder="Max" min={0} max={100}
            value={filters.safety_max ?? ""}
            onChange={e => onChange({ safety_max: e.target.value ? +e.target.value : undefined })}
            className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-brand-500 focus:border-transparent outline-none"
          />
        </div>
      </div>

      {/* Payout Ratio */}
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-2">Max Payout Ratio (%)</label>
        <input
          type="number" placeholder="e.g. 80" min={0} max={500}
          value={filters.payout_max ?? ""}
          onChange={e => onChange({ payout_max: e.target.value ? +e.target.value : undefined })}
          className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-brand-500 focus:border-transparent outline-none"
        />
      </div>

      {/* Market Cap */}
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-2">Min Market Cap (₪ thousands)</label>
        <input
          type="number" placeholder="e.g. 500000"
          value={filters.market_cap_min ?? ""}
          onChange={e => onChange({ market_cap_min: e.target.value ? +e.target.value : undefined })}
          className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-brand-500 focus:border-transparent outline-none"
        />
      </div>

      {/* Sector */}
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-2">Sector</label>
        <input
          type="text" placeholder="e.g. Real Estate"
          value={filters.sector ?? ""}
          onChange={e => onChange({ sector: e.target.value || undefined })}
          className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-brand-500 focus:border-transparent outline-none"
        />
      </div>
    </div>
  );
}

// ── CSV export ────────────────────────────────────────────────────────────────

function exportCsv(rows: ScreenerRow[]) {
  const header = ["Ticker", "Name", "Sector", "Yield %", "Safety Score", "Payout %", "Market Cap", "Price"];
  const lines = rows.map(r => [
    r.ticker,
    r.name_en ?? r.name_he ?? "",
    r.sector ?? "",
    r.dividend_yield?.toFixed(2) ?? "",
    r.safety_score?.toFixed(0) ?? "",
    r.payout_ratio != null ? (r.payout_ratio * 100).toFixed(1) : "",
    r.market_cap?.toFixed(0) ?? "",
    r.price?.toFixed(2) ?? "",
  ]);
  const csv = [header, ...lines].map(row => row.join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "tase_screener.csv";
  a.click();
  URL.revokeObjectURL(url);
}

// ── main component ────────────────────────────────────────────────────────────

const DEFAULT_FILTERS: ScreenerFilters = { sort_by: "yield", order: "desc", page: 1, page_size: 50 };

export default function ScreenerPage() {
  const navigate = useNavigate();
  const [filters, setFilters] = useState<ScreenerFilters>(DEFAULT_FILTERS);

  const updateFilters = useCallback((partial: Partial<ScreenerFilters>) => {
    setFilters(prev => ({ ...prev, ...partial, page: 1 }));
  }, []);

  const resetFilters = useCallback(() => setFilters(DEFAULT_FILTERS), []);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["screener", filters],
    queryFn: () => fetchScreener(filters),
    placeholderData: prev => prev,
  });

  const handleSort = (col: SortBy) => {
    setFilters(prev => ({
      ...prev,
      sort_by: col,
      order: prev.sort_by === col && prev.order === "desc" ? "asc" : "desc",
    }));
  };

  const SortIcon = ({ col }: { col: SortBy }) => {
    if (filters.sort_by !== col) return <ChevronUp className="w-3 h-3 text-gray-300" />;
    return filters.order === "desc"
      ? <ChevronDown className="w-3 h-3 text-brand-600" />
      : <ChevronUp className="w-3 h-3 text-brand-600" />;
  };

  return (
    <div className="flex gap-6">
      {/* ── Sidebar ── */}
      <aside className="w-60 flex-shrink-0">
        <FilterPanel filters={filters} onChange={updateFilters} onReset={resetFilters} />
      </aside>

      {/* ── Table area ── */}
      <div className="flex-1 min-w-0">
        {/* toolbar */}
        <div className="flex items-center justify-between mb-4">
          <p className="text-sm text-gray-500">
            {isLoading ? "Loading…" : `${data?.total ?? 0} stocks`}
          </p>
          <button
            onClick={() => data && exportCsv(data.results)}
            disabled={!data?.results.length}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-gray-200 rounded-lg bg-white hover:bg-gray-50 disabled:opacity-40 transition-colors"
          >
            <Download className="w-4 h-4" /> Export CSV
          </button>
        </div>

        {isError && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 text-sm">
            Failed to load screener data. Make sure the API is running.
          </div>
        )}

        {isLoading && !data && (
          <div className="flex justify-center py-20">
            <Spinner className="w-8 h-8" />
          </div>
        )}

        {data && (
          <>
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100 bg-gray-50">
                    {columns.map(col => (
                      <th
                        key={col.key}
                        onClick={() => col.sortable && handleSort(col.sortable)}
                        className={clsx(
                          "px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap",
                          col.sortable && "cursor-pointer hover:text-gray-700 select-none"
                        )}
                      >
                        <span className="flex items-center gap-1">
                          {col.label}
                          {col.sortable && <SortIcon col={col.sortable} />}
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {data.results.map(row => (
                    <tr
                      key={row.id}
                      onClick={() => navigate(`/stock/${row.ticker}`)}
                      className="hover:bg-brand-50 cursor-pointer transition-colors"
                    >
                      <td className="px-4 py-3 font-semibold text-brand-700">{row.ticker}</td>
                      <td className="px-4 py-3 text-gray-700 max-w-[160px] truncate">
                        {row.name_en ?? row.name_he ?? "—"}
                      </td>
                      <td className="px-4 py-3 text-gray-500 text-xs">{row.sector ?? "—"}</td>
                      <td className="px-4 py-3 font-medium text-green-700">
                        {fmt.pct(row.dividend_yield)}
                      </td>
                      <td className="px-4 py-3">
                        <SafetyBadge score={row.safety_score} size="sm" />
                      </td>
                      <td className="px-4 py-3 text-gray-600">
                        {row.payout_ratio != null ? fmt.pct(row.payout_ratio * 100) : "—"}
                      </td>
                      <td className="px-4 py-3 text-gray-600">{fmt.mcap(row.market_cap)}</td>
                      <td className="px-4 py-3 text-gray-600">{fmt.ils(row.price)}</td>
                    </tr>
                  ))}
                  {data.results.length === 0 && (
                    <tr>
                      <td colSpan={columns.length} className="px-4 py-10 text-center text-gray-400">
                        No stocks match the current filters.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {data.total > (filters.page_size ?? 50) && (
              <div className="flex items-center justify-between mt-4 text-sm text-gray-500">
                <span>
                  Page {filters.page} of {Math.ceil(data.total / (filters.page_size ?? 50))}
                </span>
                <div className="flex gap-2">
                  <button
                    disabled={(filters.page ?? 1) <= 1}
                    onClick={() => setFilters(p => ({ ...p, page: (p.page ?? 1) - 1 }))}
                    className="px-3 py-1 border border-gray-200 rounded-lg bg-white hover:bg-gray-50 disabled:opacity-40"
                  >
                    Previous
                  </button>
                  <button
                    disabled={(filters.page ?? 1) >= Math.ceil(data.total / (filters.page_size ?? 50))}
                    onClick={() => setFilters(p => ({ ...p, page: (p.page ?? 1) + 1 }))}
                    className="px-3 py-1 border border-gray-200 rounded-lg bg-white hover:bg-gray-50 disabled:opacity-40"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
