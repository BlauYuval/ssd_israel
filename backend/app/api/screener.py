"""
GET /screener — filtered & sorted list of dividend-paying TASE stocks.

Query parameters:
  yield_min / yield_max     — dividend yield % range
  safety_min / safety_max   — safety score range (0–100)
  sector                    — sector name filter
  payout_max                — max payout ratio %
  market_cap_min            — minimum market cap (thousands ILS)
  sort_by                   — field to sort by (yield, safety_score, payout_ratio, market_cap, div_growth)
  order                     — asc | desc
  page / page_size          — pagination
"""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Stock, Price, Dividend, Fundamental
from app.api.schemas import ScreenerRow, ScreenerResponse

router = APIRouter(prefix="/screener", tags=["screener"])


@router.get("", response_model=ScreenerResponse)
async def get_screener(
    yield_min: float | None = Query(None, ge=0, description="Minimum dividend yield %"),
    yield_max: float | None = Query(None, le=100, description="Maximum dividend yield %"),
    safety_min: float | None = Query(None, ge=0, le=100),
    safety_max: float | None = Query(None, ge=0, le=100),
    sector: str | None = Query(None),
    payout_max: float | None = Query(None, ge=0, le=500, description="Max payout ratio %"),
    market_cap_min: float | None = Query(None, ge=0, description="Min market cap (thousands ILS)"),
    sort_by: Literal["yield", "safety_score", "payout_ratio", "market_cap", "div_growth"] = "yield",
    order: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns a paginated, filtered, sorted list of dividend-paying TASE stocks
    with all metrics required by the Screener tab.
    """
    # -- Latest price subquery --
    latest_price_sq = (
        select(
            Price.stock_id,
            func.max(Price.trade_date).label("max_date"),
        )
        .group_by(Price.stock_id)
        .subquery()
    )

    latest_price = (
        select(Price)
        .join(latest_price_sq, and_(
            Price.stock_id == latest_price_sq.c.stock_id,
            Price.trade_date == latest_price_sq.c.max_date,
        ))
        .subquery()
    )

    # -- Latest fundamentals subquery --
    latest_fund_sq = (
        select(
            Fundamental.stock_id,
            func.max(Fundamental.fiscal_year).label("max_year"),
        )
        .group_by(Fundamental.stock_id)
        .subquery()
    )

    latest_fund = (
        select(Fundamental)
        .join(latest_fund_sq, and_(
            Fundamental.stock_id == latest_fund_sq.c.stock_id,
            Fundamental.fiscal_year == latest_fund_sq.c.max_year,
        ))
        .subquery()
    )

    # -- Main query --
    stmt = (
        select(
            Stock.id,
            Stock.ticker,
            Stock.name_he,
            Stock.name_en,
            Stock.sector,
            latest_price.c.close.label("price"),
            latest_price.c.market_cap,
            latest_price.c.week52_high,
            latest_price.c.week52_low,
            latest_fund.c.payout_ratio,
            latest_fund.c.debt_to_equity,
        )
        .join(latest_price, Stock.id == latest_price.c.stock_id, isouter=True)
        .join(latest_fund, Stock.id == latest_fund.c.stock_id, isouter=True)
        .where(Stock.pays_dividend.is_(True))
        .where(Stock.is_active.is_(True))
    )

    # Apply filters
    if sector:
        stmt = stmt.where(Stock.sector.ilike(f"%{sector}%"))
    if market_cap_min is not None:
        stmt = stmt.where(latest_price.c.market_cap >= market_cap_min)
    if payout_max is not None:
        stmt = stmt.where(
            (latest_fund.c.payout_ratio.is_(None)) |
            (latest_fund.c.payout_ratio * 100 <= payout_max)
        )

    # Execute base query
    result = await db.execute(stmt)
    rows = result.mappings().all()

    # -- Enrich with dividend yield and safety score (computed in Python) --
    # (In a future optimisation these can be materialised views)
    enriched: list[ScreenerRow] = []
    for row in rows:
        div_yield = await _calc_yield(db, row["id"], row["price"])
        safety = await _calc_safety_score(db, row["id"], row)

        if yield_min is not None and (div_yield is None or div_yield < yield_min):
            continue
        if yield_max is not None and (div_yield is None or div_yield > yield_max):
            continue
        if safety_min is not None and (safety is None or safety < safety_min):
            continue
        if safety_max is not None and (safety is None or safety > safety_max):
            continue

        enriched.append(ScreenerRow(
            id=row["id"],
            ticker=row["ticker"],
            name_he=row["name_he"],
            name_en=row["name_en"],
            sector=row["sector"],
            price=row["price"],
            market_cap=row["market_cap"],
            week52_high=row["week52_high"],
            week52_low=row["week52_low"],
            dividend_yield=div_yield,
            safety_score=safety,
            payout_ratio=row["payout_ratio"],
            debt_to_equity=row["debt_to_equity"],
        ))

    # Sort
    reverse = order == "desc"
    sort_key_map = {
        "yield": "dividend_yield",
        "safety_score": "safety_score",
        "payout_ratio": "payout_ratio",
        "market_cap": "market_cap",
        "div_growth": "dividend_yield",  # placeholder until growth is stored
    }
    sort_key = sort_key_map.get(sort_by, "dividend_yield")
    enriched.sort(
        key=lambda r: (getattr(r, sort_key) is None, getattr(r, sort_key) or 0),
        reverse=reverse,
    )

    # Paginate
    total = len(enriched)
    start = (page - 1) * page_size
    paginated = enriched[start: start + page_size]

    return ScreenerResponse(total=total, page=page, page_size=page_size, results=paginated)


async def _calc_yield(db: AsyncSession, stock_id: int, price: float | None) -> float | None:
    """Compute trailing 12-month dividend yield = sum(dividends last 12m) / price * 100."""
    if not price or price <= 0:
        return None
    from datetime import date, timedelta
    cutoff = date.today() - timedelta(days=365)
    result = await db.execute(
        select(func.sum(Dividend.amount_ils))
        .where(Dividend.stock_id == stock_id)
        .where(Dividend.ex_date >= cutoff)
    )
    total_div = result.scalar()
    if not total_div:
        return None
    return round(float(total_div) / float(price) * 100, 2)


async def _calc_safety_score(db: AsyncSession, stock_id: int, fund_row) -> float | None:
    """Compute the safety score using the safety_score module."""
    from datetime import date, timedelta
    from app.core.safety_score import SafetyScoreInput, calculate

    # Dividend history: count consecutive years with at least one dividend
    result = await db.execute(
        select(
            func.count(func.distinct(
                func.extract("year", Dividend.ex_date)
            ))
        )
        .where(Dividend.stock_id == stock_id)
        .where(Dividend.ex_date >= date.today() - timedelta(days=365 * 11))
    )
    years_paying = int(result.scalar() or 0)

    # Annualised dividends paid (last 12 months)
    result = await db.execute(
        select(func.sum(Dividend.amount_ils))
        .where(Dividend.stock_id == stock_id)
        .where(Dividend.ex_date >= date.today() - timedelta(days=365))
    )
    annual_div = result.scalar()

    # Latest price for FCF coverage context
    payout_ratio = fund_row.get("payout_ratio")
    debt_to_equity = fund_row.get("debt_to_equity")

    # FCF from fundamentals (not in flat row — fetch separately)
    fund_result = await db.execute(
        select(Fundamental.free_cash_flow, Fundamental.dividends_paid)
        .where(Fundamental.stock_id == stock_id)
        .order_by(Fundamental.fiscal_year.desc())
        .limit(1)
    )
    fund = fund_result.first()
    fcf = fund.free_cash_flow if fund else None
    div_paid = fund.dividends_paid if fund else (float(annual_div) if annual_div else None)

    inp = SafetyScoreInput(
        payout_ratio=float(payout_ratio) if payout_ratio is not None else None,
        annual_dividends_paid=float(div_paid) if div_paid is not None else None,
        free_cash_flow=float(fcf) if fcf is not None else None,
        debt_to_equity=float(debt_to_equity) if debt_to_equity is not None else None,
        years_of_consecutive_dividends=years_paying,
    )
    return calculate(inp).total
