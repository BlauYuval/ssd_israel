"""
init_data.py — Data backfill script.

Primary source: EODHD (full TASE universe — ~537 common stocks)
Fallback for fundamentals: yfinance (limited to ~57 validated tickers)

Usage:
    cd backend
    python init_data.py                    # full load
    python init_data.py --stocks-only      # stock master only
    python init_data.py --prices-only      # price history only
    python init_data.py --dividends-only   # dividend history only
    python init_data.py --fundamentals-only  # yfinance fundamentals for known tickers
"""
import asyncio
import argparse
import logging
import sys
import time
from datetime import date, timedelta

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
from app.scrapers.eodhd_loader import (
    fetch_all_tase_stocks,
    fetch_price_history,
    fetch_dividends,
    KNOWN_SECTORS,
)

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select, func, update

engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def create_tables():
    logger.info("Creating database tables…")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Tables ready.")


async def load_stocks():
    """Upsert all TASE common stocks from EODHD into the stocks table."""
    logger.info("Fetching TASE stock universe from EODHD…")
    stocks = fetch_all_tase_stocks()
    logger.info("Upserting %d stocks into DB…", len(stocks))

    async with Session() as db:
        for s in stocks:
            sector = KNOWN_SECTORS.get(s.code)
            stmt = pg_insert(Stock).values(
                ticker=s.code,
                name_en=s.name,
                name_he=None,
                sector=sector,
                isin=None,             # skipped: some stocks share ISINs (class shares)
                tase_id=f"{s.code}.TA",
                pays_dividend=False,   # updated after dividend load
                is_active=True,
            ).on_conflict_do_update(
                index_elements=["ticker"],
                set_=dict(
                    name_en=s.name,
                    tase_id=f"{s.code}.TA",
                )
            )
            await db.execute(stmt)

        await db.commit()
    logger.info("Stocks upserted.")


async def load_prices(from_date: str = "2021-01-01", delay: float = 0.15):
    """Fetch OHLCV history from EODHD and bulk-insert into prices table."""
    logger.info("Loading price history (from %s)…", from_date)

    async with Session() as db:
        result = await db.execute(select(Stock.id, Stock.ticker))
        stock_map = {row.ticker: row.id for row in result}

    logger.info("Processing %d stocks…", len(stock_map))

    for ticker, stock_id in stock_map.items():
        bars = fetch_price_history(ticker, from_date=from_date)
        if not bars:
            time.sleep(delay)
            continue

        # Compute 52-week window for high/low
        cutoff_52w = date.today() - timedelta(days=365)
        prices_52w = [b.close for b in bars if b.trade_date >= cutoff_52w and b.close]
        week52_high = max(prices_52w) if prices_52w else None
        week52_low = min(prices_52w) if prices_52w else None

        rows = [
            dict(
                stock_id=stock_id,
                trade_date=bar.trade_date,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                market_cap=None,
                week52_high=None,
                week52_low=None,
            )
            for bar in bars
        ]

        async with Session() as db:
            stmt = pg_insert(Price).values(rows).on_conflict_do_nothing(
                index_elements=["stock_id", "trade_date"]
            )
            await db.execute(stmt)

            # Store 52-week stats on the latest row
            if bars:
                latest_date = max(b.trade_date for b in bars)
                await db.execute(
                    update(Price)
                    .where(Price.stock_id == stock_id)
                    .where(Price.trade_date == latest_date)
                    .values(week52_high=week52_high, week52_low=week52_low)
                )

            await db.commit()

        logger.info("  ✓ %s — %d bars  52w H/L: %.2f / %.2f",
                    ticker, len(bars),
                    week52_high or 0, week52_low or 0)
        time.sleep(delay)

    logger.info("Price history loaded.")


async def load_dividends(delay: float = 0.15):
    """Fetch dividend history from EODHD and bulk-insert into dividends table."""
    logger.info("Loading dividend history…")

    async with Session() as db:
        result = await db.execute(select(Stock.id, Stock.ticker))
        stock_map = {row.ticker: row.id for row in result}

    paying_tickers: set[str] = set()

    for ticker, stock_id in stock_map.items():
        records = fetch_dividends(ticker)
        if not records:
            time.sleep(delay)
            continue

        paying_tickers.add(ticker)

        rows = [
            dict(
                stock_id=stock_id,
                maya_filing_id=f"eodhd_{ticker}_{r.ex_date}",
                declared_date=r.declared_date,
                ex_date=r.ex_date,
                payment_date=r.payment_date,
                record_date=r.record_date,
                amount_ils=r.amount_ils,
                frequency=None,
            )
            for r in records
        ]

        async with Session() as db:
            # asyncpg caps parameters at 32767; batch to avoid the limit
            chunk_size = 500
            for i in range(0, len(rows), chunk_size):
                chunk = rows[i: i + chunk_size]
                ins = pg_insert(Dividend).values(chunk)
                stmt = ins.on_conflict_do_update(
                    index_elements=["stock_id", "ex_date"],
                    set_=dict(
                        amount_ils=ins.excluded.amount_ils,
                        payment_date=ins.excluded.payment_date,
                        record_date=ins.excluded.record_date,
                        declared_date=ins.excluded.declared_date,
                    )
                )
                await db.execute(stmt)
            await db.commit()

        logger.info("  ✓ %s — %d dividends", ticker, len(records))
        time.sleep(delay)

    # Mark pays_dividend on stocks that have dividend records
    async with Session() as db:
        for ticker in paying_tickers:
            await db.execute(
                update(Stock)
                .where(Stock.ticker == ticker)
                .values(pays_dividend=True)
            )
        await db.commit()
    logger.info("Marked %d stocks as dividend-paying.", len(paying_tickers))
    logger.info("Dividend history loaded.")


async def load_fundamentals_yfinance():
    """
    Load fundamentals from yfinance for the ~57 validated TASE tickers.
    This covers payout_ratio, debt_to_equity, PE, EPS, FCF, revenue, net_income.
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed — skipping fundamentals")
        return

    from app.scrapers.yfinance_loader import TASE_STOCKS

    logger.info("Loading fundamentals from yfinance (%d tickers)…", len(TASE_STOCKS))

    async with Session() as db:
        for yahoo_ticker, display_ticker, default_sector in TASE_STOCKS:
            result = await db.execute(select(Stock).where(Stock.ticker == display_ticker))
            stock = result.scalar_one_or_none()
            if not stock:
                logger.warning("  Stock %s not in DB — skipping", display_ticker)
                continue

            try:
                t = yf.Ticker(yahoo_ticker)
                info = t.info
                if not info or info.get("quoteType") == "NONE":
                    continue

                def sf(k):
                    v = info.get(k)
                    if v is None:
                        return None
                    try:
                        f = float(v)
                        return f if f == f else None
                    except (TypeError, ValueError):
                        return None

                fund_stmt = pg_insert(Fundamental).values(
                    stock_id=stock.id,
                    fiscal_year=2025,
                    revenue=sf("totalRevenue"),
                    net_income=sf("netIncomeToCommon"),
                    eps=sf("trailingEps"),
                    free_cash_flow=sf("freeCashflow"),
                    payout_ratio=sf("payoutRatio"),
                    fcf_payout_ratio=None,
                    debt_to_equity=sf("debtToEquity"),
                    data_source="yfinance",
                    is_complete=False,
                ).on_conflict_do_update(
                    index_elements=["stock_id", "fiscal_year"],
                    set_=dict(
                        revenue=sf("totalRevenue"),
                        net_income=sf("netIncomeToCommon"),
                        eps=sf("trailingEps"),
                        free_cash_flow=sf("freeCashflow"),
                        payout_ratio=sf("payoutRatio"),
                        debt_to_equity=sf("debtToEquity"),
                        data_source="yfinance",
                    )
                )
                await db.execute(fund_stmt)
                logger.info("  ✓ %s — PE %.1f  payout %.0f%%",
                            display_ticker,
                            sf("trailingPE") or 0,
                            (sf("payoutRatio") or 0) * 100)
            except Exception as exc:
                logger.error("  ✗ %s — %s", display_ticker, exc)

        await db.commit()
    logger.info("Fundamentals (yfinance) loaded.")


async def main(args):
    await create_tables()

    run_all = not any([
        args.stocks_only, args.prices_only,
        args.dividends_only, args.fundamentals_only,
    ])

    if run_all or args.stocks_only:
        await load_stocks()

    if run_all or args.prices_only:
        await load_prices()

    if run_all or args.dividends_only:
        await load_dividends()

    if run_all or args.fundamentals_only:
        await load_fundamentals_yfinance()

    logger.info("Init complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stocks-only",        action="store_true")
    parser.add_argument("--prices-only",         action="store_true")
    parser.add_argument("--dividends-only",      action="store_true")
    parser.add_argument("--fundamentals-only",   action="store_true")
    args = parser.parse_args()

    asyncio.run(main(args))
