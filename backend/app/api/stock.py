"""
GET /stock/{ticker} — full detail view for a single stock.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Stock, Price, Dividend, Fundamental
from app.api.schemas import StockDetail, DividendRow
from app.core.safety_score import SafetyScoreInput, SafetyScoreResult, calculate
from datetime import date, timedelta

router = APIRouter(prefix="/stock", tags=["stock"])


@router.get("/{ticker}", response_model=StockDetail)
async def get_stock(ticker: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Stock).where(Stock.ticker == ticker.upper())
    )
    stock = result.scalar_one_or_none()
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock '{ticker}' not found")

    # Latest price
    price_result = await db.execute(
        select(Price)
        .where(Price.stock_id == stock.id)
        .order_by(Price.trade_date.desc())
        .limit(1)
    )
    price = price_result.scalar_one_or_none()

    # Latest fundamentals
    fund_result = await db.execute(
        select(Fundamental)
        .where(Fundamental.stock_id == stock.id)
        .order_by(Fundamental.fiscal_year.desc())
        .limit(1)
    )
    fund = fund_result.scalar_one_or_none()

    # Trailing 12m dividends
    cutoff = date.today() - timedelta(days=365)
    div_result = await db.execute(
        select(func.sum(Dividend.amount_ils))
        .where(Dividend.stock_id == stock.id)
        .where(Dividend.ex_date >= cutoff)
    )
    annual_div = div_result.scalar()

    # Dividend yield
    close = float(price.close) if price else None
    div_yield = None
    if close and annual_div:
        div_yield = round(float(annual_div) / close * 100, 2)

    # Safety score
    years_result = await db.execute(
        select(func.count(func.distinct(func.extract("year", Dividend.ex_date))))
        .where(Dividend.stock_id == stock.id)
        .where(Dividend.ex_date >= date.today() - timedelta(days=365 * 11))
    )
    years_paying = int(years_result.scalar() or 0)

    score_input = SafetyScoreInput(
        payout_ratio=float(fund.payout_ratio) if fund and fund.payout_ratio else None,
        annual_dividends_paid=float(fund.dividends_paid) if fund and fund.dividends_paid else (float(annual_div) if annual_div else None),
        free_cash_flow=float(fund.free_cash_flow) if fund and fund.free_cash_flow else None,
        debt_to_equity=float(fund.debt_to_equity) if fund and fund.debt_to_equity else None,
        sector=stock.sector,
        years_of_consecutive_dividends=years_paying,
    )
    score: SafetyScoreResult = calculate(score_input)

    return StockDetail(
        id=stock.id,
        ticker=stock.ticker,
        name_he=stock.name_he,
        name_en=stock.name_en,
        sector=stock.sector,
        industry=stock.industry,
        isin=stock.isin,
        price=close,
        market_cap=float(price.market_cap) if price and price.market_cap else None,
        week52_high=float(price.week52_high) if price and price.week52_high else None,
        week52_low=float(price.week52_low) if price and price.week52_low else None,
        dividend_yield=div_yield,
        safety_score=score.total,
        safety_score_breakdown={
            "payout": {"score": score.payout_score, "max": 25, "label": score.payout_label},
            "fcf_coverage": {"score": score.fcf_score, "max": 25, "label": score.fcf_label},
            "debt": {"score": score.debt_score, "max": 20, "label": score.debt_label},
            "history": {"score": score.history_score, "max": 20, "label": score.history_label},
            "growth": {"score": score.growth_score, "max": 10, "label": score.growth_label},
        },
        fiscal_year=fund.fiscal_year if fund else None,
        revenue=float(fund.revenue) if fund and fund.revenue else None,
        net_income=float(fund.net_income) if fund and fund.net_income else None,
        eps=float(fund.eps) if fund and fund.eps else None,
        free_cash_flow=float(fund.free_cash_flow) if fund and fund.free_cash_flow else None,
        payout_ratio=float(fund.payout_ratio) if fund and fund.payout_ratio else None,
        fcf_payout_ratio=float(fund.fcf_payout_ratio) if fund and fund.fcf_payout_ratio else None,
        debt_to_equity=float(fund.debt_to_equity) if fund and fund.debt_to_equity else None,
    )


@router.get("/{ticker}/dividends", response_model=list[DividendRow])
async def get_stock_dividends(
    ticker: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Stock).where(Stock.ticker == ticker.upper())
    )
    stock = result.scalar_one_or_none()
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock '{ticker}' not found")

    divs = await db.execute(
        select(Dividend)
        .where(Dividend.stock_id == stock.id)
        .order_by(Dividend.ex_date.desc())
        .limit(limit)
    )
    return [
        DividendRow(
            ex_date=str(d.ex_date),
            payment_date=str(d.payment_date) if d.payment_date else None,
            amount_ils=float(d.amount_ils),
            dividend_yield_at_declaration=float(d.dividend_yield_at_declaration) if d.dividend_yield_at_declaration else None,
            frequency=d.frequency,
        )
        for d in divs.scalars()
    ]
