"""
init_data.py — One-time data backfill script.

Uses Yahoo Finance (yfinance) for all data since the TASE/Maya APIs
are protected by Imperva bot protection.

Usage:
    cd backend
    python init_data.py [--stocks-only] [--prices-only] [--dividends-only] [--fundamentals-only]
"""
import asyncio
import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("init_data")

sys.path.insert(0, ".")
from app.core.config import settings
from app.database import Base
from app.models import Stock, Price, Dividend, Fundamental
from app.scrapers.yfinance_loader import (
    TASE_STOCKS, fetch_stock_info, fetch_price_history, fetch_dividends
)

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select

engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def create_tables():
    logger.info("Creating database tables…")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Tables ready.")


async def load_stocks_and_fundamentals():
    """Fetch stock info + fundamentals for all stocks and upsert to DB."""
    logger.info("Loading stocks from Yahoo Finance (%d tickers)…", len(TASE_STOCKS))
    async with Session() as db:
        for yahoo_ticker, display_ticker, default_sector in TASE_STOCKS:
            logger.info("  Fetching %s (%s)…", display_ticker, yahoo_ticker)
            info = fetch_stock_info(yahoo_ticker, display_ticker, default_sector)
            if not info:
                continue

            # Upsert stock
            stmt = pg_insert(Stock).values(
                ticker=info.ticker,
                name_en=info.name_en,
                name_he=None,
                sector=info.sector,
                isin=None,
                tase_id=yahoo_ticker,
                pays_dividend=bool(info.dividend_yield and info.dividend_yield > 0),
                is_active=True,
            ).on_conflict_do_update(
                index_elements=["ticker"],
                set_=dict(
                    name_en=info.name_en,
                    sector=info.sector,
                    pays_dividend=bool(info.dividend_yield and info.dividend_yield > 0),
                )
            )
            await db.execute(stmt)
            await db.flush()

            result = await db.execute(select(Stock).where(Stock.ticker == info.ticker))
            stock = result.scalar_one_or_none()
            if not stock:
                continue

            # Upsert fundamentals
            fund_stmt = pg_insert(Fundamental).values(
                stock_id=stock.id,
                fiscal_year=2025,
                revenue=info.revenue,
                net_income=info.net_income,
                eps=info.eps,
                free_cash_flow=info.free_cash_flow,
                payout_ratio=info.payout_ratio,
                fcf_payout_ratio=None,
                debt_to_equity=info.debt_to_equity,
                data_source="yfinance",
                is_complete=False,
            ).on_conflict_do_update(
                index_elements=["stock_id", "fiscal_year"],
                set_=dict(
                    revenue=info.revenue,
                    net_income=info.net_income,
                    eps=info.eps,
                    free_cash_flow=info.free_cash_flow,
                    payout_ratio=info.payout_ratio,
                    debt_to_equity=info.debt_to_equity,
                    data_source="yfinance",
                )
            )
            await db.execute(fund_stmt)
            logger.info("  ✓ %s — %s — ₪%.0f — yield %.1f%%",
                        info.ticker, info.name_en or "?",
                        info.price or 0, info.dividend_yield or 0)

        await db.commit()
    logger.info("Stocks and fundamentals loaded.")


async def load_prices():
    """Fetch 5-year price history for all stocks and bulk insert."""
    logger.info("Loading price history from Yahoo Finance…")
    async with Session() as db:
        for yahoo_ticker, display_ticker, _ in TASE_STOCKS:
            result = await db.execute(select(Stock).where(Stock.ticker == display_ticker))
            stock = result.scalar_one_or_none()
            if not stock:
                logger.warning("Stock %s not in DB — run stocks first", display_ticker)
                continue

            bars = fetch_price_history(yahoo_ticker, display_ticker, period="5y")
            if not bars:
                continue

            rows = [
                dict(
                    stock_id=stock.id,
                    trade_date=bar.trade_date,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                    market_cap=None,
                )
                for bar in bars
            ]

            stmt = pg_insert(Price).values(rows).on_conflict_do_nothing(
                index_elements=["stock_id", "trade_date"]
            )
            await db.execute(stmt)
            await db.commit()
            logger.info("  ✓ %s — %d price bars", display_ticker, len(bars))

    logger.info("Price history loaded.")


async def load_dividends():
    """Fetch dividend history for all stocks and bulk insert."""
    logger.info("Loading dividend history from Yahoo Finance…")
    async with Session() as db:
        for yahoo_ticker, display_ticker, _ in TASE_STOCKS:
            result = await db.execute(select(Stock).where(Stock.ticker == display_ticker))
            stock = result.scalar_one_or_none()
            if not stock:
                continue

            records = fetch_dividends(yahoo_ticker, display_ticker)
            if not records:
                logger.info("  — %s: no dividends", display_ticker)
                continue

            rows = [
                dict(
                    stock_id=stock.id,
                    maya_filing_id=f"yf_{display_ticker}_{r.ex_date}",
                    declared_date=None,
                    ex_date=r.ex_date,
                    payment_date=None,
                    record_date=None,
                    amount_ils=r.amount_ils,
                    frequency=None,
                )
                for r in records
            ]

            stmt = pg_insert(Dividend).values(rows).on_conflict_do_nothing(
                index_elements=["stock_id", "ex_date"]
            )
            await db.execute(stmt)
            await db.commit()
            logger.info("  ✓ %s — %d dividends", display_ticker, len(records))

    logger.info("Dividend history loaded.")


async def main(args):
    await create_tables()

    run_all = not any([args.stocks_only, args.prices_only, args.dividends_only, args.fundamentals_only])

    if run_all or args.stocks_only or args.fundamentals_only:
        await load_stocks_and_fundamentals()

    if run_all or args.prices_only:
        await load_prices()

    if run_all or args.dividends_only:
        await load_dividends()

    logger.info("Init complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stocks-only",       action="store_true")
    parser.add_argument("--prices-only",       action="store_true")
    parser.add_argument("--dividends-only",    action="store_true")
    parser.add_argument("--fundamentals-only", action="store_true")
    args = parser.parse_args()

    asyncio.run(main(args))
