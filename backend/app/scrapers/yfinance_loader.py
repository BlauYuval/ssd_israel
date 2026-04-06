"""
Yahoo Finance data loader for TASE stocks.

TASE stocks trade on Yahoo Finance with the .TA suffix (e.g. LUMI.TA).
This module replaces the direct TASE/Maya API calls which are blocked by
Imperva bot protection.

Provides:
  - A curated list of major TASE dividend-paying stocks
  - Price history (OHLCV)
  - Dividend history
  - Basic fundamentals (PE, payout ratio, market cap, etc.)
"""
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

import yfinance as yf

logger = logging.getLogger(__name__)

# ── Curated TASE stock universe ───────────────────────────────────────────────
# Format: (yahoo_ticker, display_ticker, sector)
TASE_STOCKS = [
    # Banks
    ("LUMI.TA",   "LUMI",   "Financials"),
    ("POLI.TA",   "POLI",   "Financials"),
    ("MZTF.TA",   "MZTF",   "Financials"),
    ("FIBI.TA",   "FIBI",   "Financials"),
    ("DSCT.TA",   "DSCT",   "Financials"),   # Bank Discount
    # Insurance
    ("PHOE.TA",   "PHOE",   "Financials"),
    ("MGDL.TA",   "MGDL",   "Financials"),
    ("IDBH.TA",   "IDBH",   "Financials"),
    # Real Estate
    ("AMOT.TA",   "AMOT",   "Real Estate"),
    ("ALHE.TA",   "ALHE",   "Real Estate"),
    ("ILCO.TA",   "ILCO",   "Real Estate"),
    ("GVNM.TA",   "GVNM",   "Real Estate"),  # Gav-Yam
    # Telecom
    ("BEZQ.TA",   "BEZQ",   "Communication"),
    ("PTNR.TA",   "PTNR",   "Communication"),
    # Materials / Energy
    ("ICL.TA",    "ICL",    "Materials"),
    ("DLEKG.TA",  "DLEKG",  "Energy"),
    ("ENLT.TA",   "ENLT",   "Energy"),
    ("OGLD.TA",   "OGLD",   "Energy"),       # Oil & Gas
    # Defense
    ("ESLT.TA",   "ESLT",   "Defense"),
    ("RAFAEL.TA", "RAFAEL", "Defense"),
    # Technology
    ("NICE.TA",   "NICE",   "Technology"),
    ("MNDO.TA",   "MNDO",   "Technology"),   # MIND C.T.I.
    # Health Care
    ("TEVA.TA",   "TEVA",   "Health Care"),
    ("PMCN.TA",   "PMCN",   "Health Care"),  # Medigus? or Pharmos
    # Consumer / Other
    ("BCOM.TA",   "BCOM",   "Consumer Discretionary"),
]


@dataclass
class StockInfo:
    yahoo_ticker: str
    ticker: str
    name_en: Optional[str]
    sector: str
    market_cap: Optional[float]      # ILS
    price: Optional[float]           # ILS
    week52_high: Optional[float]
    week52_low: Optional[float]
    pe_ratio: Optional[float]
    dividend_yield: Optional[float]  # as percentage (e.g. 4.5 for 4.5%)
    payout_ratio: Optional[float]    # 0–1
    debt_to_equity: Optional[float]
    eps: Optional[float]
    free_cash_flow: Optional[float]
    revenue: Optional[float]
    net_income: Optional[float]


@dataclass
class PriceBar:
    ticker: str
    trade_date: date
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: float
    volume: Optional[int]


@dataclass
class DividendRecord:
    ticker: str
    ex_date: date
    amount_ils: float


def _safe_float(val) -> Optional[float]:
    try:
        if val is None:
            return None
        f = float(val)
        return f if f == f else None  # NaN check
    except (TypeError, ValueError):
        return None


def fetch_stock_info(yahoo_ticker: str, display_ticker: str, sector: str) -> Optional[StockInfo]:
    """Fetch current stock info and fundamentals from Yahoo Finance."""
    try:
        t = yf.Ticker(yahoo_ticker)
        info = t.info

        if not info or info.get("quoteType") == "NONE":
            logger.warning("No info returned for %s", yahoo_ticker)
            return None

        price = _safe_float(info.get("currentPrice") or info.get("regularMarketPrice"))
        if price is None:
            logger.warning("No price for %s — skipping", yahoo_ticker)
            return None

        # yfinance returns dividendYield as a percentage already (e.g. 4.93 for 4.93%)
        div_yield = _safe_float(info.get("dividendYield"))

        return StockInfo(
            yahoo_ticker=yahoo_ticker,
            ticker=display_ticker,
            name_en=info.get("longName") or info.get("shortName"),
            sector=info.get("sector") or sector,
            market_cap=_safe_float(info.get("marketCap")),
            price=price,
            week52_high=_safe_float(info.get("fiftyTwoWeekHigh")),
            week52_low=_safe_float(info.get("fiftyTwoWeekLow")),
            pe_ratio=_safe_float(info.get("trailingPE")),
            dividend_yield=div_yield,
            payout_ratio=_safe_float(info.get("payoutRatio")),
            debt_to_equity=_safe_float(info.get("debtToEquity")),
            eps=_safe_float(info.get("trailingEps")),
            free_cash_flow=_safe_float(info.get("freeCashflow")),
            revenue=_safe_float(info.get("totalRevenue")),
            net_income=_safe_float(info.get("netIncomeToCommon")),
        )
    except Exception as exc:
        logger.error("Failed to fetch info for %s: %s", yahoo_ticker, exc)
        return None


def fetch_price_history(yahoo_ticker: str, display_ticker: str, period: str = "5y") -> list[PriceBar]:
    """Fetch OHLCV price history for a stock."""
    try:
        t = yf.Ticker(yahoo_ticker)
        hist = t.history(period=period, auto_adjust=True)
        if hist.empty:
            logger.warning("No price history for %s", yahoo_ticker)
            return []

        bars = []
        for ts, row in hist.iterrows():
            close = _safe_float(row.get("Close"))
            if close is None:
                continue
            trade_date = ts.date() if hasattr(ts, "date") else ts
            bars.append(PriceBar(
                ticker=display_ticker,
                trade_date=trade_date,
                open=_safe_float(row.get("Open")),
                high=_safe_float(row.get("High")),
                low=_safe_float(row.get("Low")),
                close=close,
                volume=int(row["Volume"]) if row.get("Volume") else None,
            ))
        logger.info("Fetched %d price bars for %s", len(bars), yahoo_ticker)
        return bars
    except Exception as exc:
        logger.error("Failed to fetch price history for %s: %s", yahoo_ticker, exc)
        return []


def fetch_dividends(yahoo_ticker: str, display_ticker: str) -> list[DividendRecord]:
    """Fetch historical dividend payments from Yahoo Finance."""
    try:
        t = yf.Ticker(yahoo_ticker)
        divs = t.dividends
        if divs.empty:
            return []

        records = []
        for ts, amount in divs.items():
            amt = _safe_float(amount)
            if amt is None or amt <= 0:
                continue
            ex_date = ts.date() if hasattr(ts, "date") else ts
            records.append(DividendRecord(
                ticker=display_ticker,
                ex_date=ex_date,
                amount_ils=amt,
            ))
        logger.info("Fetched %d dividend records for %s", len(records), yahoo_ticker)
        return records
    except Exception as exc:
        logger.error("Failed to fetch dividends for %s: %s", yahoo_ticker, exc)
        return []
