"""
Pydantic response schemas for the API.
"""
from pydantic import BaseModel, ConfigDict


class ScreenerRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    name_he: str | None
    name_en: str | None
    sector: str | None
    price: float | None
    market_cap: float | None
    week52_high: float | None
    week52_low: float | None
    dividend_yield: float | None         # trailing 12m, %
    safety_score: float | None           # 0–100
    payout_ratio: float | None           # fraction (0.45 = 45%)
    debt_to_equity: float | None
    # Dividend growth (computed from dividend history)
    div_growth_1y: float | None          # YoY growth %, prior full year vs year before
    div_growth_5y: float | None          # 5-year CAGR %
    div_growth_10y: float | None         # 10-year CAGR %
    div_growth_streak: int | None        # consecutive years of dividend growth
    uninterrupted_streak: int | None     # consecutive years with any dividend paid
    ex_div_date: str | None              # most recent or next upcoming ex-date
    payment_frequency: str | None        # Monthly / Quarterly / Semi-Annual / Annual / Irregular
    data_accuracy: str | None            # "Accurate" | "Questionable" (outlier dividend detected)


class ScreenerResponse(BaseModel):
    total: int
    page: int
    page_size: int
    results: list[ScreenerRow]


class StockDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    name_he: str | None
    name_en: str | None
    sector: str | None
    industry: str | None
    isin: str | None

    # Latest price data
    price: float | None
    market_cap: float | None
    week52_high: float | None
    week52_low: float | None

    # Dividend metrics
    dividend_yield: float | None
    safety_score: float | None
    safety_score_breakdown: dict | None   # component scores

    # Fundamentals (latest year)
    fiscal_year: int | None
    revenue: float | None
    net_income: float | None
    eps: float | None
    free_cash_flow: float | None
    payout_ratio: float | None
    fcf_payout_ratio: float | None
    debt_to_equity: float | None


class DividendRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ex_date: str
    payment_date: str | None
    amount_ils: float
    dividend_yield_at_declaration: float | None
    frequency: str | None


class HoldingIn(BaseModel):
    ticker: str
    shares: float


class PortfolioSummary(BaseModel):
    total_value_ils: float | None
    annual_income_ils: float | None
    portfolio_yield: float | None
    holdings: list[dict]
    upcoming_dividends: list[dict]
    sector_breakdown: list[dict]
