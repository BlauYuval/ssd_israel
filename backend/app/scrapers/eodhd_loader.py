"""
EODHD (End-of-Day Historical Data) loader for TASE stocks.

Exchange code: TA  (Tel Aviv Stock Exchange)
Ticker format: CODE.TA  (e.g. LUMI.TA)

IMPORTANT — unit conversion:
  EODHD quotes TASE prices and dividends in ILA (Israeli Agora = 1/100 ILS).
  All monetary values are divided by 100 before storage so the DB holds ILS.

Endpoints used:
  /api/exchange-symbol-list/TA  — full stock list (~537 common stocks)
  /api/eod/{CODE}.TA            — daily OHLCV
  /api/div/{CODE}.TA            — dividend history
"""
import logging
import time
from dataclasses import dataclass
from datetime import date
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://eodhd.com/api"
ILA_TO_ILS = 0.01  # 1 ILA = 0.01 ILS

# Sector mapping for known tickers (from yfinance validation)
KNOWN_SECTORS: dict[str, str] = {
    "LUMI":  "Financials",
    "POLI":  "Financials",
    "MZTF":  "Financials",
    "FIBI":  "Financials",
    "DSCT":  "Financials",
    "PHOE":  "Financials",
    "MGDL":  "Financials",
    "CLIS":  "Financials",
    "MNRV":  "Financials",
    "HARL":  "Financials",
    "AMOT":  "Real Estate",
    "ALHE":  "Real Estate",
    "ILCO":  "Real Estate",
    "AZRG":  "Real Estate",
    "NFTA":  "Real Estate",
    "ISRS":  "Real Estate",
    "ELCO":  "Real Estate",
    "AZRT":  "Real Estate",
    "BRAN":  "Real Estate",
    "AFRE":  "Real Estate",
    "EMCO":  "Real Estate",
    "WLFD":  "Real Estate",
    "CRSR":  "Real Estate",
    "ILDC":  "Real Estate",
    "GNRS":  "Real Estate",
    "MLSR":  "Real Estate",
    "DIMRI": "Real Estate",
    "SLARL": "Real Estate",
    "SKLN":  "Real Estate",
    "ISCN":  "Real Estate",
    "BEZQ":  "Communication",
    "PTNR":  "Communication",
    "CEL":   "Communication",
    "ICL":   "Materials",
    "PCBT":  "Industrials",
    "DLEKG": "Energy",
    "ENLT":  "Energy",
    "SPEN":  "Energy",
    "NOFR":  "Energy",
    "OPCE":  "Energy",
    "ESLT":  "Defense",
    "NICE":  "Technology",
    "TSEM":  "Technology",
    "AUDC":  "Technology",
    "CAMT":  "Technology",
    "GILT":  "Technology",
    "ORBI":  "Technology",
    "RSEL":  "Technology",
    "TEVA":  "Health Care",
    "CGEN":  "Health Care",
    "BRMG":  "Health Care",
    "ELAL":  "Industrials",
    "AFHL":  "Industrials",
    "KRUR":  "Industrials",
    "HRON":  "Industrials",
    "FTAL":  "Consumer Discretionary",
    "PLCR":  "Industrials",
}


@dataclass
class EODHDStock:
    code: str
    name: str
    isin: Optional[str]
    currency: str  # "ILA" for most TASE stocks


@dataclass
class PriceBar:
    ticker: str
    trade_date: date
    open: Optional[float]    # ILS
    high: Optional[float]    # ILS
    low: Optional[float]     # ILS
    close: float             # ILS
    volume: Optional[int]


@dataclass
class DividendRecord:
    ticker: str
    ex_date: date
    payment_date: Optional[date]
    record_date: Optional[date]
    declared_date: Optional[date]
    amount_ils: float


def _get(path: str, params: dict | None = None) -> list | dict:
    url = f"{BASE_URL}/{path}"
    p = {"api_token": settings.EODHD_API_KEY, "fmt": "json"}
    if params:
        p.update(params)
    resp = httpx.get(url, params=p, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _safe_float(val) -> Optional[float]:
    try:
        f = float(val)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _parse_date(s) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def fetch_all_tase_stocks() -> list[EODHDStock]:
    """Fetch complete TASE common stock universe from EODHD."""
    data = _get("exchange-symbol-list/TA")
    stocks = []
    for item in data:
        if item.get("Type") != "Common Stock":
            continue
        stocks.append(EODHDStock(
            code=item["Code"],
            name=item.get("Name", item["Code"]),
            isin=item.get("Isin") or None,
            currency=item.get("Currency", "ILA"),
        ))
    logger.info("Fetched %d common stocks from EODHD TA exchange", len(stocks))
    return stocks


def fetch_price_history(
    code: str,
    from_date: str = "2021-01-01",
) -> list[PriceBar]:
    """Fetch daily OHLCV for a stock, converting ILA → ILS."""
    try:
        data = _get(f"eod/{code}.TA", {"from": from_date, "period": "d"})
        if not isinstance(data, list):
            logger.warning("Unexpected price response for %s: %s", code, str(data)[:100])
            return []

        bars: list[PriceBar] = []
        for row in data:
            close_raw = _safe_float(row.get("close"))
            if close_raw is None:
                continue
            trade_date = _parse_date(row.get("date"))
            if trade_date is None:
                continue

            bars.append(PriceBar(
                ticker=code,
                trade_date=trade_date,
                open=_safe_float(row.get("open")) * ILA_TO_ILS if row.get("open") else None,
                high=_safe_float(row.get("high")) * ILA_TO_ILS if row.get("high") else None,
                low=_safe_float(row.get("low")) * ILA_TO_ILS if row.get("low") else None,
                close=close_raw * ILA_TO_ILS,
                volume=int(row["volume"]) if row.get("volume") else None,
            ))

        logger.info("Fetched %d price bars for %s", len(bars), code)
        return bars
    except Exception as exc:
        logger.error("Price history failed for %s: %s", code, exc)
        return []


def fetch_bulk_quotes(codes: list[str], batch_size: int = 100) -> dict[str, dict]:
    """
    Fetch latest quotes for many tickers in batches.
    Returns dict keyed by ticker code (e.g. "LUMI") → quote dict with ILS prices.
    """
    results: dict[str, dict] = {}
    for i in range(0, len(codes), batch_size):
        batch = codes[i: i + batch_size]
        try:
            first = f"{batch[0]}.TA"
            rest = ",".join(f"{c}.TA" for c in batch[1:])
            params = {"s": rest} if rest else {}
            data = _get(f"real-time/{first}", params)
            if isinstance(data, dict):
                data = [data]
            for q in data:
                code = q.get("code", "").replace(".TA", "")
                if not code:
                    continue

                def _ila(val):
                    f = _safe_float(val)
                    return f * ILA_TO_ILS if f is not None else None

                results[code] = {
                    "open":      _ila(q.get("open")),
                    "high":      _ila(q.get("high")),
                    "low":       _ila(q.get("low")),
                    "close":     _ila(q.get("close")),
                    "volume":    int(q["volume"]) if q.get("volume") and str(q["volume"]).lstrip("-").isdigit() else None,
                    "timestamp": q.get("timestamp"),
                }
        except Exception as exc:
            logger.error("Bulk quote fetch failed for batch starting %s: %s", batch[0], exc)
    logger.info("Fetched bulk quotes for %d/%d tickers", len(results), len(codes))
    return results


def fetch_dividends(code: str) -> list[DividendRecord]:
    """Fetch dividend history for a stock, converting ILA → ILS."""
    try:
        data = _get(f"div/{code}.TA")
        if not isinstance(data, list):
            return []

        records: list[DividendRecord] = []
        for row in data:
            amount_raw = _safe_float(row.get("value"))
            if amount_raw is None or amount_raw <= 0:
                continue

            # EODHD returns TASE (.TA) dividend values in ILA (agoras).
            # The `currency` field sometimes says "ILS" (the ISO code) even
            # though the value is still quoted in agoras — so we always divide
            # by 100 for .TA stocks, regardless of the currency label.
            # Exception: USD-denominated TASE stocks keep their USD value and
            # would need a separate FX conversion (not yet implemented).
            currency = (row.get("currency") or "ILA").upper()
            if currency == "USD":
                # USD-denominated stock on TASE — store raw (USD); yield calc
                # will be inaccurate but at least not off by 100x.
                amount_ils = amount_raw
            else:
                # "ILA", "ILS", or anything else → treat as agoras
                amount_ils = amount_raw * ILA_TO_ILS

            ex_date = _parse_date(row.get("date"))
            if ex_date is None:
                continue

            records.append(DividendRecord(
                ticker=code,
                ex_date=ex_date,
                payment_date=_parse_date(row.get("paymentDate")),
                record_date=_parse_date(row.get("recordDate")),
                declared_date=_parse_date(row.get("declarationDate")),
                amount_ils=amount_ils,
            ))

        logger.info("Fetched %d dividends for %s", len(records), code)
        return records
    except Exception as exc:
        logger.error("Dividend fetch failed for %s: %s", code, exc)
        return []
