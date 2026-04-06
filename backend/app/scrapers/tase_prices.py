"""
TASE daily price data pipeline.

Uses the TASE public REST API:
  https://api.tase.co.il/api/security/trading/history
      ?secId=<tase_security_id>
      &fromDate=YYYY-MM-DD
      &toDate=YYYY-MM-DD

Also fetches the securities list to map tickers → secId:
  https://api.tase.co.il/api/security/list

Response fields of interest (snake_case after normalization):
  tradeDate, openPrice, highPrice, lowPrice, closePrice,
  volume, marketCap
"""
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import AsyncGenerator

import httpx

from app.scrapers.base import build_client, fetch_json
from app.core.config import settings

logger = logging.getLogger(__name__)

TASE_SECURITIES_URL = f"{settings.TASE_API_BASE_URL}/security/list"
TASE_HISTORY_URL = f"{settings.TASE_API_BASE_URL}/security/trading/history"
TASE_MARKET_CAP_URL = f"{settings.TASE_API_BASE_URL}/security/marketcap"

# TASE API requires browser-like headers (returns 403 otherwise)
TASE_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://www.tase.co.il",
    "Referer": "https://www.tase.co.il/",
}


@dataclass
class PriceBar:
    tase_id: str
    trade_date: date
    open: float | None
    high: float | None
    low: float | None
    close: float
    volume: int | None
    market_cap: float | None  # thousands ILS


def _norm(raw: dict, *keys: str, default=None):
    """Try multiple key variants (camel / pascal / snake) and return first hit."""
    for k in keys:
        if k in raw:
            return raw[k]
    return default


def _parse_price_bar(raw: dict, tase_id: str) -> PriceBar | None:
    try:
        trade_date_str = _norm(raw, "tradeDate", "TradeDate", "date", "Date")
        if not trade_date_str:
            return None

        close = _norm(raw, "closePrice", "ClosePrice", "close", "Close")
        if close is None:
            return None

        return PriceBar(
            tase_id=tase_id,
            trade_date=date.fromisoformat(str(trade_date_str)[:10]),
            open=_norm(raw, "openPrice", "OpenPrice", "open", "Open"),
            high=_norm(raw, "highPrice", "HighPrice", "high", "High"),
            low=_norm(raw, "lowPrice", "LowPrice", "low", "Low"),
            close=float(close),
            volume=_norm(raw, "volume", "Volume"),
            market_cap=_norm(raw, "marketCap", "MarketCap"),
        )
    except Exception as exc:
        logger.error("Failed to parse price bar %s: %s", raw, exc)
        return None


async def fetch_securities_list(client: httpx.AsyncClient) -> list[dict]:
    """
    Retrieve the full list of TASE securities (stocks only).
    Returns a list with at minimum: secId, ticker, name, secTypeId.
    secTypeId == 1 typically means ordinary shares.
    """
    logger.info("Fetching TASE securities list…")
    try:
        data = await fetch_json(client, TASE_SECURITIES_URL, headers=TASE_HEADERS)
        securities = data if isinstance(data, list) else data.get("securities", data.get("Securities", []))
        # Filter to ordinary shares / equity only
        equities = [
            s for s in securities
            if str(_norm(s, "secTypeId", "SecTypeId", "type", "Type", default="")) in ("1", "equity", "stock")
        ]
        logger.info("Found %d equity securities on TASE", len(equities))
        return equities
    except Exception as exc:
        logger.error("Failed to fetch securities list: %s", exc)
        return []


async def fetch_price_history(
    client: httpx.AsyncClient,
    tase_id: str,
    from_date: date,
    to_date: date,
) -> AsyncGenerator[PriceBar, None]:
    """Fetch OHLCV history for one security between two dates."""
    params = {
        "secId": tase_id,
        "fromDate": from_date.isoformat(),
        "toDate": to_date.isoformat(),
    }
    try:
        data = await fetch_json(client, TASE_HISTORY_URL, params=params, headers=TASE_HEADERS)
    except httpx.HTTPStatusError as exc:
        logger.warning("HTTP %s fetching prices for %s: %s", exc.response.status_code, tase_id, exc)
        return
    except Exception as exc:
        logger.error("Error fetching prices for %s: %s", tase_id, exc)
        return

    rows = data if isinstance(data, list) else data.get("history", data.get("History", data.get("data", [])))
    for raw in rows:
        bar = _parse_price_bar(raw, tase_id)
        if bar:
            yield bar


async def scrape_daily_prices(target_date: date | None = None) -> AsyncGenerator[PriceBar, None]:
    """
    Fetch previous trading day prices for all TASE equity securities.
    Called by the daily scheduler after market close.
    """
    if target_date is None:
        target_date = date.today() - timedelta(days=1)

    async with build_client() as client:
        securities = await fetch_securities_list(client)
        for sec in securities:
            tase_id = str(_norm(sec, "secId", "SecId", "id", "Id") or "")
            if not tase_id:
                continue
            async for bar in fetch_price_history(client, tase_id, target_date, target_date):
                yield bar


async def scrape_price_history_bulk(
    tase_id: str,
    years_back: int = 5,
) -> AsyncGenerator[PriceBar, None]:
    """
    Backfill historical prices for a single security.
    Used during initial data load.
    """
    to_date = date.today()
    from_date = to_date.replace(year=to_date.year - years_back)

    async with build_client() as client:
        async for bar in fetch_price_history(client, tase_id, from_date, to_date):
            yield bar
