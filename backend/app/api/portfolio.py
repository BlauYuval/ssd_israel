"""
Portfolio endpoints.

GET  /portfolio           — aggregated metrics for a list of holdings
POST /portfolio/holdings  — compute portfolio summary from provided holdings
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Stock, Price, Dividend
from app.api.schemas import HoldingIn, PortfolioSummary

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.post("", response_model=PortfolioSummary)
async def compute_portfolio(
    holdings: list[HoldingIn],
    db: AsyncSession = Depends(get_db),
):
    """
    Accepts a list of {ticker, shares} and returns:
    - Total portfolio value (ILS)
    - Projected annual dividend income (ILS)
    - Portfolio yield %
    - Per-holding breakdown
    - Upcoming ex-dates (next 90 days)
    - Sector diversification
    """
    if not holdings:
        return PortfolioSummary(
            total_value_ils=0,
            annual_income_ils=0,
            portfolio_yield=0,
            holdings=[],
            upcoming_dividends=[],
            sector_breakdown=[],
        )

    tickers = [h.ticker.upper() for h in holdings]
    ticker_to_shares = {h.ticker.upper(): h.shares for h in holdings}

    # Fetch stocks
    stocks_result = await db.execute(
        select(Stock).where(Stock.ticker.in_(tickers))
    )
    stocks = {s.ticker: s for s in stocks_result.scalars()}

    # Latest prices
    stock_ids = [s.id for s in stocks.values()]
    latest_price_sq = (
        select(Price.stock_id, func.max(Price.trade_date).label("max_date"))
        .where(Price.stock_id.in_(stock_ids))
        .group_by(Price.stock_id)
        .subquery()
    )
    prices_result = await db.execute(
        select(Price)
        .join(latest_price_sq, (Price.stock_id == latest_price_sq.c.stock_id) &
              (Price.trade_date == latest_price_sq.c.max_date))
    )
    prices = {p.stock_id: p for p in prices_result.scalars()}

    # Trailing 12m dividends per stock
    cutoff_12m = date.today() - timedelta(days=365)
    divs_result = await db.execute(
        select(Dividend.stock_id, func.sum(Dividend.amount_ils).label("annual_div"))
        .where(Dividend.stock_id.in_(stock_ids))
        .where(Dividend.ex_date >= cutoff_12m)
        .group_by(Dividend.stock_id)
    )
    annual_divs = {row.stock_id: float(row.annual_div) for row in divs_result}

    # Upcoming dividends (next 90 days)
    upcoming_cutoff = date.today() + timedelta(days=90)
    upcoming_result = await db.execute(
        select(Dividend, Stock.ticker)
        .join(Stock, Dividend.stock_id == Stock.id)
        .where(Dividend.stock_id.in_(stock_ids))
        .where(Dividend.ex_date >= date.today())
        .where(Dividend.ex_date <= upcoming_cutoff)
        .order_by(Dividend.ex_date)
    )
    upcoming_dividends = [
        {
            "ticker": row.ticker,
            "ex_date": str(row.Dividend.ex_date),
            "payment_date": str(row.Dividend.payment_date) if row.Dividend.payment_date else None,
            "amount_per_share_ils": float(row.Dividend.amount_ils),
        }
        for row in upcoming_result
    ]

    # Build per-holding rows
    total_value = 0.0
    total_annual_income = 0.0
    sector_totals: dict[str, float] = {}
    holding_rows = []

    for ticker, stock in stocks.items():
        shares = ticker_to_shares.get(ticker, 0)
        price_obj = prices.get(stock.id)
        close = float(price_obj.close) if price_obj else None
        position_value = close * shares if close else None
        annual_div_per_share = annual_divs.get(stock.id, 0.0)
        annual_income = annual_div_per_share * shares
        div_yield = (annual_div_per_share / close * 100) if close and annual_div_per_share else None

        if position_value:
            total_value += position_value
        total_annual_income += annual_income

        sector = stock.sector or "Unknown"
        sector_totals[sector] = sector_totals.get(sector, 0) + (position_value or 0)

        holding_rows.append({
            "ticker": ticker,
            "name_en": stock.name_en,
            "sector": stock.sector,
            "shares": shares,
            "price": close,
            "position_value_ils": position_value,
            "annual_income_ils": annual_income,
            "dividend_yield": div_yield,
        })

    portfolio_yield = (total_annual_income / total_value * 100) if total_value else None

    sector_breakdown = [
        {
            "sector": sector,
            "value_ils": value,
            "weight_pct": round(value / total_value * 100, 1) if total_value else None,
        }
        for sector, value in sorted(sector_totals.items(), key=lambda x: -x[1])
    ]

    return PortfolioSummary(
        total_value_ils=round(total_value, 2),
        annual_income_ils=round(total_annual_income, 2),
        portfolio_yield=round(portfolio_yield, 2) if portfolio_yield else None,
        holdings=holding_rows,
        upcoming_dividends=upcoming_dividends,
        sector_breakdown=sector_breakdown,
    )
