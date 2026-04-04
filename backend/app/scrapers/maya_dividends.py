"""
Maya dividend announcements scraper.

Maya (maya.tase.co.il) is the mandatory disclosure system for all TASE-listed
companies. Dividend declarations are event type 21 (ChDividend).

API reference discovered from hasadna/stock-scraper and manual inspection:
  GET https://maya.tase.co.il/api/company/events
      ?companyId=<tase_id>
      &eventType=21
      &page=<n>
      &pageSize=20

Each event contains:
  - EventDate (declaration date)
  - ExDate
  - PaymentDate
  - RecordDate
  - DividendPerShare (agorot → we convert to ILS / 100)
  - FilingId (unique Maya reference)
"""
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import AsyncGenerator

import httpx

from app.scrapers.base import build_client, fetch_json
from app.core.config import settings

logger = logging.getLogger(__name__)

MAYA_EVENTS_URL = f"{settings.MAYA_BASE_URL}/api/company/events"
MAYA_COMPANIES_URL = f"{settings.MAYA_BASE_URL}/api/company/list"

EVENT_TYPE_DIVIDEND = 21
PAGE_SIZE = 50


@dataclass
class DividendEvent:
    tase_id: str
    maya_filing_id: str
    declared_date: date | None
    ex_date: date
    payment_date: date | None
    record_date: date | None
    amount_ils: float  # per share


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value[:19], fmt).date()
        except ValueError:
            continue
    logger.warning("Could not parse date: %s", value)
    return None


def _parse_event(raw: dict, tase_id: str) -> DividendEvent | None:
    """Parse a single Maya event dict into a DividendEvent."""
    try:
        ex_date = _parse_date(raw.get("ExDate") or raw.get("exDate"))
        if ex_date is None:
            return None

        # Dividend amount is reported in agorot (1/100 ILS) on Maya
        amount_agorot = float(raw.get("DividendPerShare") or raw.get("dividendPerShare") or 0)
        amount_ils = round(amount_agorot / 100, 6)
        if amount_ils <= 0:
            return None

        return DividendEvent(
            tase_id=tase_id,
            maya_filing_id=str(raw.get("FilingId") or raw.get("filingId") or ""),
            declared_date=_parse_date(raw.get("EventDate") or raw.get("eventDate")),
            ex_date=ex_date,
            payment_date=_parse_date(raw.get("PaymentDate") or raw.get("paymentDate")),
            record_date=_parse_date(raw.get("RecordDate") or raw.get("recordDate")),
            amount_ils=amount_ils,
        )
    except Exception as exc:
        logger.error("Failed to parse dividend event %s: %s", raw, exc)
        return None


async def fetch_company_list(client: httpx.AsyncClient) -> list[dict]:
    """
    Retrieve the full list of TASE companies (id + name) from Maya.
    Returns a list of dicts with at least: companyId, companyName, ticker.
    """
    logger.info("Fetching TASE company list from Maya…")
    try:
        data = await fetch_json(client, MAYA_COMPANIES_URL)
        companies = data if isinstance(data, list) else data.get("companies", data.get("Companies", []))
        logger.info("Found %d companies on Maya", len(companies))
        return companies
    except Exception as exc:
        logger.error("Failed to fetch company list: %s", exc)
        return []


async def fetch_dividends_for_company(
    client: httpx.AsyncClient,
    tase_id: str,
    max_pages: int = 20,
) -> AsyncGenerator[DividendEvent, None]:
    """
    Yield all dividend events for a single TASE company.
    Paginates through Maya API until no more results.
    """
    for page in range(1, max_pages + 1):
        params = {
            "companyId": tase_id,
            "eventType": EVENT_TYPE_DIVIDEND,
            "page": page,
            "pageSize": PAGE_SIZE,
        }
        try:
            data = await fetch_json(client, MAYA_EVENTS_URL, params=params)
        except httpx.HTTPStatusError as exc:
            logger.warning("HTTP %s for company %s page %d", exc.response.status_code, tase_id, page)
            break
        except Exception as exc:
            logger.error("Error fetching dividends for %s page %d: %s", tase_id, page, exc)
            break

        events_raw = data if isinstance(data, list) else data.get("events", data.get("Events", []))
        if not events_raw:
            break

        for raw in events_raw:
            event = _parse_event(raw, tase_id)
            if event:
                yield event

        # If the page returned fewer items than the page size, we're on the last page
        if len(events_raw) < PAGE_SIZE:
            break


async def scrape_all_dividends() -> AsyncGenerator[DividendEvent, None]:
    """
    Full scrape: iterate every TASE company and yield all dividend events.
    This is the entry point for the daily Maya watcher job.
    """
    async with build_client() as client:
        companies = await fetch_company_list(client)
        for company in companies:
            tase_id = str(company.get("companyId") or company.get("CompanyId") or "")
            if not tase_id:
                continue
            logger.info("Scraping dividends for company %s", tase_id)
            async for event in fetch_dividends_for_company(client, tase_id):
                yield event


async def scrape_recent_dividends(days_back: int = 7) -> AsyncGenerator[DividendEvent, None]:
    """
    Lightweight daily check: fetch only events with ex_date in the last N days.
    Uses Maya's date-range filter if available; otherwise falls back to full scan.
    """
    from datetime import timedelta
    cutoff = date.today() - timedelta(days=days_back)

    async with build_client() as client:
        companies = await fetch_company_list(client)
        for company in companies:
            tase_id = str(company.get("companyId") or company.get("CompanyId") or "")
            if not tase_id:
                continue
            async for event in fetch_dividends_for_company(client, tase_id, max_pages=3):
                if event.ex_date >= cutoff:
                    yield event
