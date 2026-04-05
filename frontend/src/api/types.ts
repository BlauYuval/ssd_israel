export interface ScreenerRow {
  id: number;
  ticker: string;
  name_he: string | null;
  name_en: string | null;
  sector: string | null;
  price: number | null;
  market_cap: number | null;
  week52_high: number | null;
  week52_low: number | null;
  dividend_yield: number | null;
  safety_score: number | null;
  payout_ratio: number | null;
  debt_to_equity: number | null;
}

export interface ScreenerResponse {
  total: number;
  page: number;
  page_size: number;
  results: ScreenerRow[];
}

export interface ScreenerFilters {
  yield_min?: number;
  yield_max?: number;
  safety_min?: number;
  safety_max?: number;
  sector?: string;
  payout_max?: number;
  market_cap_min?: number;
  sort_by?: "yield" | "safety_score" | "payout_ratio" | "market_cap" | "div_growth";
  order?: "asc" | "desc";
  page?: number;
  page_size?: number;
}

export interface ScoreBreakdown {
  score: number;
  max: number;
  label: string;
}

export interface StockDetail {
  id: number;
  ticker: string;
  name_he: string | null;
  name_en: string | null;
  sector: string | null;
  industry: string | null;
  isin: string | null;
  price: number | null;
  market_cap: number | null;
  week52_high: number | null;
  week52_low: number | null;
  dividend_yield: number | null;
  safety_score: number | null;
  safety_score_breakdown: {
    payout: ScoreBreakdown;
    fcf_coverage: ScoreBreakdown;
    debt: ScoreBreakdown;
    history: ScoreBreakdown;
    growth: ScoreBreakdown;
  } | null;
  fiscal_year: number | null;
  revenue: number | null;
  net_income: number | null;
  eps: number | null;
  free_cash_flow: number | null;
  payout_ratio: number | null;
  fcf_payout_ratio: number | null;
  debt_to_equity: number | null;
}

export interface DividendRow {
  ex_date: string;
  payment_date: string | null;
  amount_ils: number;
  dividend_yield_at_declaration: number | null;
  frequency: string | null;
}

export interface HoldingIn {
  ticker: string;
  shares: number;
}

export interface HoldingRow {
  ticker: string;
  name_en: string | null;
  sector: string | null;
  shares: number;
  price: number | null;
  position_value_ils: number | null;
  annual_income_ils: number;
  dividend_yield: number | null;
}

export interface UpcomingDividend {
  ticker: string;
  ex_date: string;
  payment_date: string | null;
  amount_per_share_ils: number;
}

export interface SectorBreakdown {
  sector: string;
  value_ils: number;
  weight_pct: number | null;
}

export interface PortfolioSummary {
  total_value_ils: number;
  annual_income_ils: number;
  portfolio_yield: number | null;
  holdings: HoldingRow[];
  upcoming_dividends: UpcomingDividend[];
  sector_breakdown: SectorBreakdown[];
}
