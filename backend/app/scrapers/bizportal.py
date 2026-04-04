"""
Fundamental data scraper — bizportal.co.il

bizportal.co.il is a major Israeli financial portal that publishes structured
financial data for TASE-listed companies (income statement, balance sheet,
cash flow) in Hebrew. It is used as the primary structured source for
fundamental data before falling back to Maya PDF parsing.

URL pattern for financial reports:
  https://www.bizportal.co.il/capitalmarket/quote/financialreports/
      <bizportal_company_id>?reporttype=annual

The page renders with JS, so we parse the __NEXT_DATA__ JSON payload embedded
in the HTML rather than executing JS — this avoids a headless browser dependency.
"""
import json
import logging
import re
from dataclasses import dataclass, field
from typing import AsyncGenerator

from bs4 import BeautifulSoup

from app.scrapers.base import build_client, fetch_html

logger = logging.getLogger(__name__)

BIZPORTAL_BASE = "https://www.bizportal.co.il"
BIZPORTAL_SEARCH_URL = f"{BIZPORTAL_BASE}/capitalmarket/quote/financialreports"

# Regex to extract the embedded Next.js JSON payload
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)


@dataclass
class FundamentalRecord:
    tase_id: str
    bizportal_id: str
    fiscal_year: int

    revenue: float | None = None
    gross_profit: float | None = None
    operating_income: float | None = None
    net_income: float | None = None
    eps: float | None = None

    operating_cash_flow: float | None = None
    capex: float | None = None
    free_cash_flow: float | None = None
    dividends_paid: float | None = None

    total_assets: float | None = None
    total_liabilities: float | None = None
    shareholders_equity: float | None = None
    total_debt: float | None = None

    # Derived
    payout_ratio: float | None = None
    fcf_payout_ratio: float | None = None
    debt_to_equity: float | None = None

    data_source: str = "bizportal"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").replace("(", "-").replace(")", "").strip())
    except (ValueError, TypeError):
        return None


def _extract_next_data(html: str) -> dict | None:
    match = NEXT_DATA_RE.search(html)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse __NEXT_DATA__: %s", exc)
        return None


def _extract_financial_tables(next_data: dict) -> list[dict]:
    """
    Navigate the Next.js data tree to find the financial report arrays.
    The exact path varies by bizportal page version; we try common paths.
    """
    try:
        props = next_data.get("props", {}).get("pageProps", {})
        # Try several common key paths
        for key in ("financialData", "annualData", "reports", "financialReports"):
            if key in props:
                return props[key] if isinstance(props[key], list) else [props[key]]
        # Deep search for any list with 'year' or 'fiscalYear' keys
        return _deep_find_reports(props)
    except Exception as exc:
        logger.warning("Could not extract financial tables: %s", exc)
        return []


def _deep_find_reports(obj, depth: int = 0) -> list[dict]:
    if depth > 5 or not isinstance(obj, (dict, list)):
        return []
    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        if any(k in obj[0] for k in ("year", "fiscalYear", "Year", "FiscalYear")):
            return obj
    if isinstance(obj, dict):
        for v in obj.values():
            result = _deep_find_reports(v, depth + 1)
            if result:
                return result
    return []


def _map_report(raw: dict, tase_id: str, bizportal_id: str) -> FundamentalRecord | None:
    """Map a raw bizportal annual report dict to a FundamentalRecord."""
    year_raw = raw.get("year") or raw.get("Year") or raw.get("fiscalYear") or raw.get("FiscalYear")
    if not year_raw:
        return None
    try:
        fiscal_year = int(str(year_raw)[:4])
    except ValueError:
        return None

    rec = FundamentalRecord(tase_id=tase_id, bizportal_id=bizportal_id, fiscal_year=fiscal_year)

    # Income statement
    rec.revenue = _safe_float(raw.get("revenue") or raw.get("Revenue") or raw.get("revenues") or raw.get("Revenues"))
    rec.gross_profit = _safe_float(raw.get("grossProfit") or raw.get("GrossProfit"))
    rec.operating_income = _safe_float(raw.get("operatingIncome") or raw.get("OperatingIncome") or raw.get("ebit"))
    rec.net_income = _safe_float(raw.get("netIncome") or raw.get("NetIncome") or raw.get("netProfit"))
    rec.eps = _safe_float(raw.get("eps") or raw.get("EPS") or raw.get("earningsPerShare"))

    # Cash flow
    rec.operating_cash_flow = _safe_float(raw.get("operatingCashFlow") or raw.get("OperatingCashFlow") or raw.get("cashFromOperations"))
    rec.capex = _safe_float(raw.get("capex") or raw.get("Capex") or raw.get("capitalExpenditures"))
    rec.dividends_paid = _safe_float(raw.get("dividendsPaid") or raw.get("DividendsPaid") or raw.get("dividends"))

    # Compute FCF if not provided directly
    if rec.operating_cash_flow is not None and rec.capex is not None:
        rec.free_cash_flow = rec.operating_cash_flow - abs(rec.capex)
    else:
        rec.free_cash_flow = _safe_float(raw.get("freeCashFlow") or raw.get("FreeCashFlow"))

    # Balance sheet
    rec.total_assets = _safe_float(raw.get("totalAssets") or raw.get("TotalAssets"))
    rec.total_liabilities = _safe_float(raw.get("totalLiabilities") or raw.get("TotalLiabilities"))
    rec.shareholders_equity = _safe_float(raw.get("shareholdersEquity") or raw.get("ShareholdersEquity") or raw.get("equity"))
    rec.total_debt = _safe_float(raw.get("totalDebt") or raw.get("TotalDebt") or raw.get("debt"))

    # Derived ratios
    if rec.net_income and rec.dividends_paid is not None:
        try:
            rec.payout_ratio = round(abs(rec.dividends_paid) / abs(rec.net_income), 4)
        except ZeroDivisionError:
            pass

    if rec.free_cash_flow and rec.dividends_paid is not None:
        try:
            rec.fcf_payout_ratio = round(abs(rec.dividends_paid) / abs(rec.free_cash_flow), 4)
        except ZeroDivisionError:
            pass

    if rec.total_debt is not None and rec.shareholders_equity:
        try:
            rec.debt_to_equity = round(rec.total_debt / abs(rec.shareholders_equity), 4)
        except ZeroDivisionError:
            pass

    return rec


# ---------------------------------------------------------------------------
# Public scraper functions
# ---------------------------------------------------------------------------

async def fetch_bizportal_id(company_name_he: str) -> str | None:
    """
    Attempt to resolve a company's bizportal numeric ID via their search.
    Returns the ID string or None if not found.
    """
    search_url = f"{BIZPORTAL_BASE}/capitalmarket/quote/search?q={company_name_he}"
    async with build_client() as client:
        try:
            html = await fetch_html(client, search_url)
            soup = BeautifulSoup(html, "lxml")
            # bizportal embeds company links as /capitalmarket/quote/companyid/<id>
            link = soup.select_one('a[href*="/capitalmarket/quote/companyid/"]')
            if link:
                return link["href"].split("/")[-1]
        except Exception as exc:
            logger.error("bizportal search failed for '%s': %s", company_name_he, exc)
    return None


async def scrape_fundamentals_for_company(
    tase_id: str,
    bizportal_id: str,
) -> AsyncGenerator[FundamentalRecord, None]:
    """
    Scrape all available annual fundamental records for a single company.
    Yields one FundamentalRecord per fiscal year found.
    """
    url = f"{BIZPORTAL_BASE}/capitalmarket/quote/financialreports/{bizportal_id}?reporttype=annual"
    async with build_client() as client:
        try:
            html = await fetch_html(client, url)
        except Exception as exc:
            logger.error("Failed to fetch bizportal page for %s (bizportal_id=%s): %s", tase_id, bizportal_id, exc)
            return

    next_data = _extract_next_data(html)
    if not next_data:
        # Fall back to HTML table parsing
        async for rec in _parse_html_tables(html, tase_id, bizportal_id):
            yield rec
        return

    reports = _extract_financial_tables(next_data)
    for raw in reports:
        rec = _map_report(raw, tase_id, bizportal_id)
        if rec:
            yield rec


async def _parse_html_tables(
    html: str,
    tase_id: str,
    bizportal_id: str,
) -> AsyncGenerator[FundamentalRecord, None]:
    """
    Fallback: parse financial data from HTML <table> elements when the
    Next.js JSON payload is not present (e.g., server-side rendered pages).
    This is a best-effort parser.
    """
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")
    if not tables:
        logger.warning("No tables found on bizportal page for tase_id=%s", tase_id)
        return

    # Look for the first table that has year headers in the <thead>
    for table in tables:
        headers = [th.get_text(strip=True) for th in table.select("thead th")]
        # Year columns look like "2023", "2022", etc.
        year_cols = [h for h in headers if re.match(r"20\d{2}", h)]
        if not year_cols:
            continue

        rows = {}
        for tr in table.select("tbody tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if len(cells) >= 2:
                label = cells[0].strip()
                rows[label] = cells[1:]

        for col_idx, year_str in enumerate(year_cols):
            fiscal_year = int(year_str)
            rec = FundamentalRecord(tase_id=tase_id, bizportal_id=bizportal_id, fiscal_year=fiscal_year)

            def get_val(label_substrings: list[str]) -> float | None:
                for label, values in rows.items():
                    if any(sub in label for sub in label_substrings):
                        if col_idx < len(values):
                            return _safe_float(values[col_idx])
                return None

            rec.revenue = get_val(["הכנסות", "מכירות"])
            rec.gross_profit = get_val(["רווח גולמי"])
            rec.operating_income = get_val(["רווח תפעולי", "EBIT"])
            rec.net_income = get_val(["רווח נקי"])
            rec.eps = get_val(["רווח למניה", "EPS"])
            rec.operating_cash_flow = get_val(["תזרים מפעילות שוטפת", "מזומנים מפעילות"])
            rec.dividends_paid = get_val(["דיבידנד", "דיווידנד"])
            rec.total_assets = get_val(["סך נכסים", "סה\"כ נכסים"])
            rec.shareholders_equity = get_val(["הון עצמי"])
            rec.total_debt = get_val(["חוב", "הלוואות"])

            if rec.net_income and rec.dividends_paid:
                try:
                    rec.payout_ratio = round(abs(rec.dividends_paid) / abs(rec.net_income), 4)
                except ZeroDivisionError:
                    pass

            yield rec
        break  # only process first matching table
