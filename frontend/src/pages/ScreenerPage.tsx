import { useState, useCallback, useRef, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { ChevronUp, ChevronDown, Download, Plus, X, RefreshCw, Save, GripVertical } from "lucide-react";
import clsx from "clsx";

import { fetchScreener } from "../api/screener";
import type { ScreenerFilters, ScreenerRow } from "../api/types";
import SafetyBadge from "../components/SafetyBadge";
import Spinner from "../components/Spinner";

// ── Israel blue ───────────────────────────────────────────────────────────────
const BLUE = "#0038B8";

// ── Formatters ────────────────────────────────────────────────────────────────
const fmt = {
  pct:   (v: number | null | undefined) => (v == null ? "—" : `${v.toFixed(2)}%`),
  pct1:  (v: number | null | undefined) => (v == null ? "—" : `${v.toFixed(1)}%`),
  ils:   (v: number | null | undefined) => (v == null ? "—" : `₪${v.toLocaleString("he-IL", { maximumFractionDigits: 2 })}`),
  num:   (v: number | null | undefined, d = 1) => (v == null ? "—" : v.toFixed(d)),
  int:   (v: number | null | undefined) => (v == null ? "—" : v.toFixed(0)),
  mcap:  (v: number | null | undefined) => {
    if (v == null) return "—";
    if (v >= 1_000_000_000) return `₪${(v / 1_000_000_000).toFixed(1)} billion`;
    if (v >= 1_000_000)     return `₪${(v / 1_000_000).toFixed(0)} million`;
    return `₪${(v / 1_000).toFixed(0)}K`;
  },
  capLabel: (v: number | null | undefined) => {
    if (v == null) return null;
    if (v >= 10_000_000_000) return "Large Cap";
    if (v >= 2_000_000_000)  return "Mid Cap";
    if (v >= 300_000_000)    return "Small Cap";
    return "Micro Cap";
  },
  week52: (row: ScreenerRow) => {
    if (row.week52_low == null || row.week52_high == null) return "—";
    return `₪${row.week52_low.toFixed(0)} – ₪${row.week52_high.toFixed(0)}`;
  },
};

// ── Column definitions ────────────────────────────────────────────────────────
type SortBy = NonNullable<ScreenerFilters["sort_by"]>;

interface ColDef {
  key: string;
  label: string;
  sortable?: SortBy;
  align?: "right" | "center" | "left";
  defaultVisible: boolean;
  render: (row: ScreenerRow) => React.ReactNode;
}

const ALL_COLUMNS: ColDef[] = [
  {
    key: "name", label: "Name", defaultVisible: true, align: "left",
    render: (r) => (
      <div>
        <div className="text-xs text-gray-400">{r.ticker} · {r.sector ?? ""}</div>
        <span className="font-semibold text-sm" style={{ color: BLUE }}>{r.name_en ?? r.name_he ?? r.ticker}</span>
      </div>
    ),
  },
  {
    key: "sector", label: "Sector", defaultVisible: true, align: "left",
    render: (r) => <span className="text-xs text-gray-600">{r.sector ?? "—"}</span>,
  },
  {
    key: "market_cap", label: "Market Cap", sortable: "market_cap", defaultVisible: true, align: "right",
    render: (r) => (
      <div className="text-right">
        <div className="text-sm font-medium text-gray-800">{fmt.mcap(r.market_cap)}</div>
        {fmt.capLabel(r.market_cap) && <div className="text-xs text-gray-400">{fmt.capLabel(r.market_cap)}</div>}
      </div>
    ),
  },
  {
    key: "beta", label: "Beta", defaultVisible: false, align: "right",
    render: (r) => <span className="text-sm text-gray-700">{fmt.num(r.beta, 2)}</span>,
  },
  {
    key: "valuation", label: "Valuation", defaultVisible: true, align: "left",
    render: (r) => <span className="text-sm text-gray-600">{r.valuation ?? "—"}</span>,
  },
  {
    key: "dividend_yield", label: "Dividend Yield", sortable: "yield", defaultVisible: true, align: "right",
    render: (r) => (
      <span className="text-sm font-semibold text-gray-800">
        {r.dividend_yield ? `${r.dividend_yield.toFixed(2)}%` : "—"}
      </span>
    ),
  },
  {
    key: "pe_ratio", label: "P/E Ratio", defaultVisible: true, align: "right",
    render: (r) => <span className="text-sm text-gray-700">{fmt.num(r.pe_ratio, 1)}</span>,
  },
  {
    key: "week52", label: "52-Week Range", defaultVisible: false, align: "right",
    render: (r) => <span className="text-xs text-gray-600 whitespace-nowrap">{fmt.week52(r)}</span>,
  },
  {
    key: "safety_score", label: "Dividend Safety", sortable: "safety_score", defaultVisible: true, align: "center",
    render: (r) => <div className="flex justify-center"><SafetyBadge score={r.safety_score} size="sm" /></div>,
  },
  {
    key: "div_growth_1y", label: "Dividend Growth", defaultVisible: true, align: "right",
    render: (r) => <span className="text-sm text-gray-700">{fmt.pct1(r.div_growth_1y)}</span>,
  },
  {
    key: "div_growth_5y", label: "5-Year Div Growth", sortable: "div_growth", defaultVisible: true, align: "right",
    render: (r) => <span className="text-sm text-gray-700">{fmt.pct1(r.div_growth_5y)}</span>,
  },
  {
    key: "div_growth_10y", label: "10-Year Div Growth", defaultVisible: true, align: "right",
    render: (r) => <span className="text-sm text-gray-700">{fmt.pct1(r.div_growth_10y)}</span>,
  },
  {
    key: "div_growth_streak", label: "Div Growth Streak", defaultVisible: true, align: "right",
    render: (r) => <span className="text-sm text-gray-700">{r.div_growth_streak != null ? `${r.div_growth_streak} yrs` : "—"}</span>,
  },
  {
    key: "uninterrupted_streak", label: "Uninterrupted Div Streak", defaultVisible: false, align: "right",
    render: (r) => <span className="text-sm text-gray-700">{r.uninterrupted_streak != null ? `${r.uninterrupted_streak} yrs` : "—"}</span>,
  },
  {
    key: "dividend_taxation", label: "Dividend Taxation", defaultVisible: false, align: "left",
    render: () => <span className="text-xs text-gray-500">25%</span>,
  },
  {
    key: "ex_div_date", label: "Ex-Dividend Date", defaultVisible: false, align: "left",
    render: (r) => <span className="text-sm text-gray-600">{r.ex_div_date ?? "—"}</span>,
  },
  {
    key: "payment_frequency", label: "Payment Frequency", defaultVisible: false, align: "left",
    render: (r) => <span className="text-sm text-gray-600">{r.payment_frequency ?? "—"}</span>,
  },
  {
    key: "payment_schedule", label: "Payment Schedule", defaultVisible: false, align: "left",
    render: (r) => <span className="text-sm text-gray-600">{r.payment_schedule ?? "—"}</span>,
  },
  {
    key: "credit_rating", label: "Credit Rating", defaultVisible: false, align: "center",
    render: (r) => <span className="text-sm font-medium text-gray-700">{r.credit_rating ?? "—"}</span>,
  },
  {
    key: "payout_ratio", label: "Payout Ratio", sortable: "payout_ratio", defaultVisible: false, align: "right",
    render: (r) => <span className="text-sm text-gray-700">{r.payout_ratio != null ? fmt.pct(r.payout_ratio * 100) : "—"}</span>,
  },
  {
    key: "net_debt_to_capital", label: "Net Debt to Capital", defaultVisible: false, align: "right",
    render: (r) => <span className="text-sm text-gray-700">{fmt.pct1(r.net_debt_to_capital)}</span>,
  },
  {
    key: "net_debt_to_ebitda", label: "Net Debt to EBITDA", defaultVisible: false, align: "right",
    render: (r) => <span className="text-sm text-gray-700">{fmt.num(r.net_debt_to_ebitda, 1)}</span>,
  },
  {
    key: "free_cash_flow", label: "Free Cash Flow", defaultVisible: false, align: "right",
    render: (r) => <span className="text-sm text-gray-700">{fmt.ils(r.free_cash_flow)}</span>,
  },
  {
    key: "roic", label: "Return on Invested Capital", defaultVisible: false, align: "right",
    render: (r) => <span className="text-sm text-gray-700">{fmt.pct1(r.roic)}</span>,
  },
  {
    key: "recession_dividend", label: "Recession Dividend", defaultVisible: false, align: "left",
    render: (r) => <span className="text-sm text-gray-600">{r.recession_dividend ?? "—"}</span>,
  },
  {
    key: "recession_return", label: "Recession Return", defaultVisible: false, align: "right",
    render: (r) => <span className="text-sm text-gray-700">{fmt.pct1(r.recession_return)}</span>,
  },
  {
    key: "price", label: "Price", defaultVisible: false, align: "right",
    render: (r) => <span className="text-sm text-gray-700">{fmt.ils(r.price)}</span>,
  },
  {
    key: "data_accuracy", label: "Data Accuracy", defaultVisible: true, align: "center",
    render: (r) => {
      const q = r.data_accuracy === "Questionable";
      return (
        <span className={`text-xs font-medium px-2 py-0.5 rounded ${q ? "bg-amber-100 text-amber-700" : "bg-green-50 text-green-700"}`}>
          {q ? "⚠ Questionable" : "✓ Accurate"}
        </span>
      );
    },
  },
];

// ── Safety filter presets ─────────────────────────────────────────────────────
const SAFETY_PRESETS = [
  { label: "Safe and up (61+)",           min: 61 },
  { label: "Borderline and up (41+)",     min: 41 },
  { label: "All scores",                  min: undefined },
];

// ── Filter chip component ─────────────────────────────────────────────────────
interface ChipProps {
  label: string;
  value?: string;
  active?: boolean;
  onRemove?: () => void;
  onClick?: () => void;
}

function FilterChip({ label, value, active, onRemove, onClick }: ChipProps) {
  if (active && value) {
    return (
      <div
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border-2 bg-blue-50 text-sm font-semibold cursor-default select-none shadow-sm"
        style={{ borderColor: BLUE, color: BLUE }}
      >
        <span className="font-medium text-gray-500 text-xs uppercase tracking-wide">{label}</span>
        <span className="font-bold">{value}</span>
        <button onClick={onRemove} className="ml-0.5 text-gray-400 hover:text-gray-700">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    );
  }
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-gray-200 bg-white text-sm text-gray-600 hover:bg-gray-50 hover:border-gray-400 hover:text-gray-800 transition-colors shadow-sm"
    >
      <Plus className="w-3.5 h-3.5 text-gray-400" />
      {label}
    </button>
  );
}

// ── Popover ───────────────────────────────────────────────────────────────────
function Popover({ open, onClose, children }: { open: boolean; onClose: () => void; children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) onClose(); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div ref={ref} className="absolute top-full left-0 mt-2 z-50 bg-white border border-gray-200 rounded-xl shadow-lg p-4 min-w-[220px]">
      {children}
    </div>
  );
}

// ── More Filters modal ────────────────────────────────────────────────────────
const MORE_FILTER_ITEMS = [
  "10-Year Dividend Growth", "P/E Relative to History",
  "5-Year Dividend Growth",  "Payment Frequency",
  "52-Week Range",           "Payment Schedule",
  "Beta",                    "Payout Ratio",
  "Credit Rating",           "Price",
  "Dividend Taxation",       "Recession Dividend",
  "Ex-Dividend Date",        "Recession Return",
  "Free Cash Flow",          "Return on Invested Capital",
  "Market Cap",              "Uninterrupted Dividend Streak",
  "Net Debt to Capital",     "Yield Relative to History",
  "Net Debt to EBITDA",      "Latest Dividend Raise",
];

function MoreFiltersModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="bg-white rounded-2xl shadow-xl w-[600px] max-h-[80vh] flex flex-col">
        <div className="p-6 border-b border-gray-100">
          <h2 className="text-2xl font-bold text-center text-gray-900">More filters</h2>
        </div>
        <div className="overflow-y-auto flex-1 p-6">
          <div className="grid grid-cols-2 gap-3">
            {MORE_FILTER_ITEMS.map(item => (
              <button
                key={item}
                className="text-left px-4 py-3 rounded-lg bg-gray-50 hover:bg-blue-50 text-sm text-gray-700 transition-colors border border-transparent hover:border-blue-200"
              >
                {item}
              </button>
            ))}
          </div>
        </div>
        <div className="p-4 border-t border-gray-100">
          <button
            onClick={onClose}
            className="w-full py-3 rounded-xl text-white font-semibold text-sm transition-colors"
            style={{ backgroundColor: BLUE }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Columns panel ─────────────────────────────────────────────────────────────
function ColumnsDrawer({
  visible,
  onChange,
  onClose,
}: {
  visible: Set<string>;
  onChange: (key: string, on: boolean) => void;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/20" onClick={onClose} />
      {/* Drawer */}
      <div className="relative bg-white w-80 h-full flex flex-col shadow-2xl border-l border-gray-200">
        <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
          <h3 className="font-bold text-lg text-gray-900 tracking-tight">Columns</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="overflow-y-auto flex-1 py-1">
          {ALL_COLUMNS.map((col) => (
            <label
              key={col.key}
              className="flex items-center gap-3 px-5 py-2.5 cursor-pointer hover:bg-blue-50 transition-colors"
            >
              <input
                type="checkbox"
                checked={visible.has(col.key)}
                onChange={e => onChange(col.key, e.target.checked)}
                className="w-4 h-4 rounded"
                style={{ accentColor: BLUE }}
              />
              <span className="text-sm text-gray-700 flex-1 font-medium">{col.label}</span>
              <GripVertical className="w-4 h-4 text-gray-300" />
            </label>
          ))}
        </div>
        <div className="p-4 border-t border-gray-100">
          <button
            onClick={onClose}
            className="w-full py-2.5 rounded-lg text-white font-semibold text-sm"
            style={{ backgroundColor: BLUE }}
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}

// ── CSV export ────────────────────────────────────────────────────────────────
function exportCsv(rows: ScreenerRow[]) {
  const header = ["Ticker", "Name", "Sector", "Yield %", "Safety Score", "Payout %", "Market Cap (₪)", "Price (₪)"];
  const lines = rows.map(r => [
    r.ticker, r.name_en ?? r.name_he ?? "", r.sector ?? "",
    r.dividend_yield?.toFixed(2) ?? "", r.safety_score?.toFixed(0) ?? "",
    r.payout_ratio != null ? (r.payout_ratio * 100).toFixed(1) : "",
    r.market_cap?.toFixed(0) ?? "", r.price?.toFixed(2) ?? "",
  ]);
  const csv = [header, ...lines].map(row => row.join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a"); a.href = url; a.download = "tase_screener.csv"; a.click();
  URL.revokeObjectURL(url);
}

// ── Mock data ─────────────────────────────────────────────────────────────────
const MOCK_ROWS: ScreenerRow[] = [
  { id:1,  ticker:"LUMI",    name_he:"בנק לאומי",       name_en:"Bank Leumi",            sector:"Financials",      price:2210,  market_cap:38_000_000_000, dividend_yield:5.20, safety_score:72, payout_ratio:0.42, debt_to_equity:1.1, week52_high:2450,  week52_low:1850,  beta:0.85, pe_ratio:8.2,  valuation:"Fair Value",         div_growth_1y:3.1,  div_growth_5y:4.2,  div_growth_10y:3.8,  div_growth_streak:6,  uninterrupted_streak:12, ex_div_date:"2026-03-15", payment_frequency:"Semi-Annual", credit_rating:"A+",  payout_ratio:0.42, net_debt_to_capital:28.1, net_debt_to_ebitda:2.1, free_cash_flow:4_200_000_000,  roic:11.2, recession_dividend:"Maintained", recession_return:-18.2 },
  { id:2,  ticker:"POLI",    name_he:"בנק הפועלים",     name_en:"Bank Hapoalim",         sector:"Financials",      price:3340,  market_cap:52_000_000_000, dividend_yield:4.80, safety_score:68, payout_ratio:0.38, debt_to_equity:0.9, week52_high:3600,  week52_low:2900,  beta:0.92, pe_ratio:7.8,  valuation:"Fair Value",         div_growth_1y:2.8,  div_growth_5y:3.9,  div_growth_10y:3.2,  div_growth_streak:4,  uninterrupted_streak:10, ex_div_date:"2026-04-10", payment_frequency:"Semi-Annual", credit_rating:"A+",  payout_ratio:0.38, net_debt_to_capital:25.4, net_debt_to_ebitda:1.9, free_cash_flow:5_100_000_000,  roic:10.8, recession_dividend:"Maintained", recession_return:-21.3 },
  { id:3,  ticker:"AZRIELI", name_he:"קבוצת עזריאלי",   name_en:"Azrieli Group",         sector:"Real Estate",     price:19200, market_cap:22_000_000_000, dividend_yield:3.10, safety_score:81, payout_ratio:0.55, debt_to_equity:0.7, week52_high:21000, week52_low:16500, beta:0.68, pe_ratio:22.1, valuation:"Fair Value",         div_growth_1y:5.2,  div_growth_5y:6.1,  div_growth_10y:5.8,  div_growth_streak:14, uninterrupted_streak:18, ex_div_date:"2026-05-20", payment_frequency:"Annual",      credit_rating:"AA-", payout_ratio:0.55, net_debt_to_capital:42.3, net_debt_to_ebitda:8.1, free_cash_flow:1_800_000_000,  roic:8.4,  recession_dividend:"Maintained", recession_return:-12.1 },
  { id:4,  ticker:"SANO",    name_he:"סנו",             name_en:"Sano Bruno",            sector:"Consumer Staples",price:4850,  market_cap:1_800_000_000,  dividend_yield:6.10, safety_score:58, payout_ratio:0.65, debt_to_equity:0.5, week52_high:5200,  week52_low:4100,  beta:0.55, pe_ratio:14.3, valuation:"Undervalued",        div_growth_1y:1.0,  div_growth_5y:2.1,  div_growth_10y:1.8,  div_growth_streak:3,  uninterrupted_streak:7,  ex_div_date:"2026-02-28", payment_frequency:"Annual",      credit_rating:"BBB+",payout_ratio:0.65, net_debt_to_capital:18.2, net_debt_to_ebitda:1.4, free_cash_flow:180_000_000,    roic:14.1, recession_dividend:"Cut",        recession_return:-8.5  },
  { id:5,  ticker:"ICL",     name_he:"כיל",             name_en:"ICL Group",             sector:"Materials",       price:790,   market_cap:20_000_000_000, dividend_yield:5.70, safety_score:64, payout_ratio:0.48, debt_to_equity:0.8, week52_high:920,   week52_low:680,   beta:1.12, pe_ratio:11.4, valuation:"Undervalued",        div_growth_1y:0.0,  div_growth_5y:3.8,  div_growth_10y:2.9,  div_growth_streak:2,  uninterrupted_streak:5,  ex_div_date:"2026-04-01", payment_frequency:"Quarterly",   credit_rating:"BBB", payout_ratio:0.48, net_debt_to_capital:31.5, net_debt_to_ebitda:2.8, free_cash_flow:1_200_000_000,  roic:9.7,  recession_dividend:"Cut",        recession_return:-32.1 },
  { id:6,  ticker:"ESLT",    name_he:"אלביט",           name_en:"Elbit Systems",         sector:"Defense",         price:78400, market_cap:18_000_000_000, dividend_yield:1.40, safety_score:88, payout_ratio:0.22, debt_to_equity:0.3, week52_high:85000, week52_low:64000, beta:0.48, pe_ratio:28.6, valuation:"Overvalued",         div_growth_1y:8.5,  div_growth_5y:9.2,  div_growth_10y:8.7,  div_growth_streak:18, uninterrupted_streak:22, ex_div_date:"2026-06-01", payment_frequency:"Semi-Annual", credit_rating:"A",   payout_ratio:0.22, net_debt_to_capital:8.1,  net_debt_to_ebitda:0.6, free_cash_flow:1_500_000_000,  roic:16.8, recession_dividend:"Raised",     recession_return:-5.2  },
  { id:7,  ticker:"TEVA",    name_he:"טבע",             name_en:"Teva Pharmaceutical",   sector:"Health Care",     price:3680,  market_cap:41_000_000_000, dividend_yield:0.00, safety_score:35, payout_ratio:0.00, debt_to_equity:2.1, week52_high:4200,  week52_low:2800,  beta:1.34, pe_ratio:6.1,  valuation:"Undervalued",        div_growth_1y:null, div_growth_5y:null, div_growth_10y:null, div_growth_streak:0,  uninterrupted_streak:0,  ex_div_date:null,         payment_frequency:"N/A",         credit_rating:"BB",  payout_ratio:0.00, net_debt_to_capital:68.4, net_debt_to_ebitda:4.2, free_cash_flow:2_800_000_000,  roic:5.1,  recession_dividend:"Suspended",  recession_return:-44.2 },
  { id:8,  ticker:"BEZQ",    name_he:"בזק",             name_en:"Bezeq",                 sector:"Communication",   price:620,   market_cap:8_500_000_000,  dividend_yield:7.80, safety_score:49, payout_ratio:0.82, debt_to_equity:1.6, week52_high:700,   week52_low:540,   beta:0.72, pe_ratio:10.5, valuation:"Undervalued",        div_growth_1y:-2.1, div_growth_5y:-1.4, div_growth_10y:-3.2, div_growth_streak:0,  uninterrupted_streak:3,  ex_div_date:"2026-03-31", payment_frequency:"Quarterly",   credit_rating:"BBB+",payout_ratio:0.82, net_debt_to_capital:55.2, net_debt_to_ebitda:3.6, free_cash_flow:900_000_000,    roic:7.8,  recession_dividend:"Cut",        recession_return:-28.4 },
  { id:9,  ticker:"NICE",    name_he:"נייס",            name_en:"NICE Systems",          sector:"Technology",      price:38700, market_cap:12_000_000_000, dividend_yield:0.00, safety_score:76, payout_ratio:0.00, debt_to_equity:0.1, week52_high:42000, week52_low:30000, beta:1.21, pe_ratio:34.2, valuation:"Overvalued",         div_growth_1y:null, div_growth_5y:null, div_growth_10y:null, div_growth_streak:0,  uninterrupted_streak:0,  ex_div_date:null,         payment_frequency:"N/A",         credit_rating:"A-",  payout_ratio:0.00, net_debt_to_capital:5.2,  net_debt_to_ebitda:0.3, free_cash_flow:2_100_000_000,  roic:21.4, recession_dividend:"N/A",        recession_return:-31.0 },
  { id:10, ticker:"AMOT",    name_he:"עמות",            name_en:"Amot Investments",      sector:"Real Estate",     price:1120,  market_cap:5_600_000_000,  dividend_yield:6.40, safety_score:62, payout_ratio:0.71, debt_to_equity:0.9, week52_high:1280,  week52_low:950,   beta:0.61, pe_ratio:17.8, valuation:"Fair Value",         div_growth_1y:4.1,  div_growth_5y:4.8,  div_growth_10y:4.3,  div_growth_streak:8,  uninterrupted_streak:11, ex_div_date:"2026-04-25", payment_frequency:"Annual",      credit_rating:"A-",  payout_ratio:0.71, net_debt_to_capital:48.7, net_debt_to_ebitda:9.2, free_cash_flow:420_000_000,    roic:7.2,  recession_dividend:"Maintained", recession_return:-15.6 },
];

// ── Default visible columns ───────────────────────────────────────────────────
const DEFAULT_VISIBLE = new Set(ALL_COLUMNS.filter(c => c.defaultVisible).map(c => c.key));

// ── Main ──────────────────────────────────────────────────────────────────────
const DEFAULT_FILTERS: ScreenerFilters = { sort_by: "yield", order: "desc", page: 1, page_size: 50 };

export default function ScreenerPage() {
  const navigate = useNavigate();
  const [filters, setFilters] = useState<ScreenerFilters>(DEFAULT_FILTERS);
  const [openPopover, setOpenPopover] = useState<string | null>(null);
  const [showMoreFilters, setShowMoreFilters] = useState(false);
  const [showColumns, setShowColumns] = useState(false);
  const [visibleCols, setVisibleCols] = useState<Set<string>>(new Set(DEFAULT_VISIBLE));

  // Popover draft state
  const [draftYieldMin, setDraftYieldMin] = useState("");
  const [draftSector, setDraftSector] = useState("");

  const updateFilters = useCallback((partial: Partial<ScreenerFilters>) => {
    setFilters(prev => ({ ...prev, ...partial, page: 1 }));
  }, []);

  const resetFilters = useCallback(() => {
    setFilters(DEFAULT_FILTERS);
    setDraftYieldMin("");
    setDraftSector("");
  }, []);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["screener", filters],
    queryFn: () => fetchScreener(filters),
    placeholderData: prev => prev,
  });

  const rows: ScreenerRow[] = data?.results ?? (isError ? MOCK_ROWS : []);
  const total = data?.total ?? (isError ? MOCK_ROWS.length : 0);

  const handleSort = (col: SortBy) => {
    setFilters(prev => ({
      ...prev, sort_by: col,
      order: prev.sort_by === col && prev.order === "desc" ? "asc" : "desc",
    }));
  };

  const toggleCol = useCallback((key: string, on: boolean) => {
    setVisibleCols(prev => {
      const next = new Set(prev);
      if (on) next.add(key); else next.delete(key);
      return next;
    });
  }, []);

  const activeColumns = ALL_COLUMNS.filter(c => visibleCols.has(c.key));

  // Active filter labels
  const activeYield  = filters.yield_min  != null ? `> ${filters.yield_min}%` : undefined;
  const activeSafety = filters.safety_min != null
    ? SAFETY_PRESETS.find(p => p.min === filters.safety_min)?.label ?? `≥ ${filters.safety_min}`
    : undefined;
  const activeSector = filters.sector;
  const hasAnyFilter = !!(activeYield || activeSafety || activeSector);

  return (
    <div>
      {/* Title */}
      <div className="mb-6">
        <h1 className="text-3xl font-extrabold tracking-tight mb-0.5" style={{ color: BLUE }}>
          TASE Dividend Screener
        </h1>
        <p className="text-gray-400 text-sm font-medium">Filter and discover dividend-paying Israeli stocks</p>
      </div>

      {/* Filter chips */}
      <div className="flex flex-wrap items-center gap-2 mb-3">

        {/* My Holdings (placeholder) */}
        <FilterChip label="My Holdings" onClick={() => {}} />

        {/* Dividend Safety */}
        <div className="relative">
          <FilterChip
            label="Dividend Safety" value={activeSafety} active={!!activeSafety}
            onRemove={() => updateFilters({ safety_min: undefined, safety_max: undefined })}
            onClick={() => setOpenPopover(openPopover === "safety" ? null : "safety")}
          />
          <Popover open={openPopover === "safety"} onClose={() => setOpenPopover(null)}>
            <p className="text-xs font-semibold text-gray-500 mb-2 uppercase tracking-wide">Minimum Safety Score</p>
            {SAFETY_PRESETS.map(p => (
              <button key={p.label}
                onClick={() => { updateFilters({ safety_min: p.min, safety_max: undefined }); setOpenPopover(null); }}
                className={clsx("w-full text-left px-3 py-2 rounded-lg text-sm hover:bg-blue-50 transition-colors",
                  filters.safety_min === p.min && "bg-blue-50 font-medium")}
                style={filters.safety_min === p.min ? { color: BLUE } : undefined}
              >{p.label}</button>
            ))}
          </Popover>
        </div>

        {/* Dividend Yield */}
        <div className="relative">
          <FilterChip
            label="Dividend Yield" value={activeYield} active={!!activeYield}
            onRemove={() => updateFilters({ yield_min: undefined, yield_max: undefined })}
            onClick={() => setOpenPopover(openPopover === "yield" ? null : "yield")}
          />
          <Popover open={openPopover === "yield"} onClose={() => setOpenPopover(null)}>
            <p className="text-xs font-semibold text-gray-500 mb-2 uppercase tracking-wide">Min Dividend Yield</p>
            <div className="flex gap-2 items-center mb-3">
              <input type="number" placeholder="e.g. 3.0" min={0} max={100} step={0.5}
                value={draftYieldMin} onChange={e => setDraftYieldMin(e.target.value)}
                className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2"
                style={{ "--tw-ring-color": BLUE } as React.CSSProperties}
              />
              <span className="text-gray-500 text-sm">%</span>
            </div>
            <div className="flex gap-2">
              <button onClick={() => { updateFilters({ yield_min: draftYieldMin ? +draftYieldMin : undefined }); setOpenPopover(null); }}
                className="flex-1 text-white text-sm rounded-lg px-3 py-1.5 transition-colors"
                style={{ backgroundColor: BLUE }}>Apply</button>
              <button onClick={() => { setDraftYieldMin(""); updateFilters({ yield_min: undefined }); setOpenPopover(null); }}
                className="flex-1 border border-gray-200 text-sm rounded-lg px-3 py-1.5 hover:bg-gray-50">Clear</button>
            </div>
          </Popover>
        </div>

        {/* Sector */}
        <div className="relative">
          <FilterChip
            label="Sector" value={activeSector} active={!!activeSector}
            onRemove={() => updateFilters({ sector: undefined })}
            onClick={() => setOpenPopover(openPopover === "sector" ? null : "sector")}
          />
          <Popover open={openPopover === "sector"} onClose={() => setOpenPopover(null)}>
            <p className="text-xs font-semibold text-gray-500 mb-2 uppercase tracking-wide">Sector</p>
            {["Financials","Real Estate","Materials","Consumer Staples","Technology","Communication","Health Care","Defense"].map(s => (
              <button key={s} onClick={() => { updateFilters({ sector: s }); setDraftSector(s); setOpenPopover(null); }}
                className={clsx("w-full text-left px-3 py-1.5 rounded-lg text-sm hover:bg-blue-50 transition-colors",
                  filters.sector === s && "bg-blue-50 font-medium")}
                style={filters.sector === s ? { color: BLUE } : undefined}
              >{s}</button>
            ))}
            <button onClick={() => { setDraftSector(""); updateFilters({ sector: undefined }); setOpenPopover(null); }}
              className="w-full text-left px-3 py-1.5 mt-1 rounded-lg text-sm text-gray-400 hover:bg-gray-50">Clear</button>
          </Popover>
        </div>

        {/* Latest Dividend Raise (placeholder) */}
        <FilterChip label="Latest Dividend Raise" onClick={() => {}} />

        {/* Dividend Growth Streak (placeholder) */}
        <FilterChip label="Dividend Growth Streak" onClick={() => {}} />

        {/* Valuation (placeholder) */}
        <FilterChip label="Valuation" onClick={() => {}} />

        {/* More filters */}
        <button
          onClick={() => setShowMoreFilters(true)}
          className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-md text-white text-sm font-semibold transition-colors shadow-sm"
          style={{ backgroundColor: BLUE }}
        >
          <Plus className="w-3.5 h-3.5" /> More filters
        </button>
      </div>

      {/* Reset / Save */}
      <div className="flex items-center gap-5 mb-6 text-sm">
        {hasAnyFilter && (
          <button onClick={resetFilters} className="flex items-center gap-1 text-gray-500 hover:text-gray-800">
            <RefreshCw className="w-3.5 h-3.5" /> Reset
          </button>
        )}
        <button className="flex items-center gap-1 text-gray-500 hover:text-gray-800">
          <Save className="w-3.5 h-3.5" /> Save screen...
        </button>
      </div>

      {/* Toolbar */}
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm font-medium text-gray-700">
          {isLoading ? "Loading…" : `${total} matches`}
          {isError && <span className="ml-2 text-xs text-orange-500">(demo data — API offline)</span>}
        </p>
        <div className="flex gap-2">
          <button
            onClick={() => setShowColumns(v => !v)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-gray-300 rounded-lg bg-white hover:bg-gray-50 font-medium"
          >
            Columns
          </button>
          <button
            onClick={() => exportCsv(rows)} disabled={!rows.length}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-gray-300 rounded-lg bg-white hover:bg-gray-50 disabled:opacity-40 font-medium"
          >
            <Download className="w-4 h-4" /> Export
          </button>
        </div>
      </div>

      {/* Loading */}
      {isLoading && !data && (
        <div className="flex justify-center py-20"><Spinner className="w-8 h-8" /></div>
      )}

      {/* Table */}
      {(data || isError) && (
        <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ backgroundColor: BLUE }}>
                {activeColumns.map(col => {
                  const isSorted = col.sortable && filters.sort_by === col.sortable;
                  return (
                    <th key={col.key}
                      onClick={() => col.sortable && handleSort(col.sortable)}
                      style={isSorted ? { backgroundColor: "#002899" } : undefined}
                      className={clsx(
                        "px-4 py-3 text-xs font-semibold text-white whitespace-nowrap select-none",
                        col.align === "right" && "text-right",
                        col.align === "center" && "text-center",
                        (!col.align || col.align === "left") && "text-left",
                        col.sortable && "cursor-pointer hover:brightness-90 transition-[filter]"
                      )}
                    >
                      <span className={clsx("inline-flex items-center gap-1",
                        col.align === "right" && "justify-end",
                        col.align === "center" && "justify-center"
                      )}>
                        {col.label}
                        {col.sortable && (isSorted
                          ? filters.order === "desc" ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronUp className="w-3.5 h-3.5" />
                          : <ChevronUp className="w-3.5 h-3.5 opacity-40" />
                        )}
                      </span>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={row.id}
                  onClick={() => navigate(`/stock/${row.ticker}`)}
                  className={clsx(
                    "cursor-pointer border-b border-gray-100 hover:bg-blue-50 transition-colors",
                    i % 2 === 0 ? "bg-white" : "bg-gray-50/40"
                  )}
                >
                  {activeColumns.map(col => (
                    <td key={col.key}
                      className={clsx("px-4 py-3",
                        col.align === "right" && "text-right",
                        col.align === "center" && "text-center"
                      )}
                    >
                      {col.render(row)}
                    </td>
                  ))}
                </tr>
              ))}
              {rows.length === 0 && !isLoading && (
                <tr>
                  <td colSpan={activeColumns.length} className="px-4 py-12 text-center text-gray-400">
                    No stocks match the current filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {data && data.total > (filters.page_size ?? 50) && (
        <div className="flex items-center justify-between mt-4 text-sm text-gray-500">
          <span>Page {filters.page} of {Math.ceil(data.total / (filters.page_size ?? 50))}</span>
          <div className="flex gap-2">
            <button disabled={(filters.page ?? 1) <= 1}
              onClick={() => setFilters(p => ({ ...p, page: (p.page ?? 1) - 1 }))}
              className="px-3 py-1 border border-gray-200 rounded-lg bg-white hover:bg-gray-50 disabled:opacity-40">Previous</button>
            <button disabled={(filters.page ?? 1) >= Math.ceil(data.total / (filters.page_size ?? 50))}
              onClick={() => setFilters(p => ({ ...p, page: (p.page ?? 1) + 1 }))}
              className="px-3 py-1 border border-gray-200 rounded-lg bg-white hover:bg-gray-50 disabled:opacity-40">Next</button>
          </div>
        </div>
      )}

      {/* More Filters modal */}
      {showMoreFilters && <MoreFiltersModal onClose={() => setShowMoreFilters(false)} />}

      {/* Columns drawer */}
      {showColumns && <ColumnsDrawer visible={visibleCols} onChange={toggleCol} onClose={() => setShowColumns(false)} />}
    </div>
  );
}
