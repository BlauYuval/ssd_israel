"""
APScheduler-based job scheduler.

Jobs:
  1. daily_price_job      — runs after TASE market close (Sun–Thu 18:30 IL time)
                            uses EODHD bulk real-time endpoint (~6 HTTP calls for all 537 stocks)
  2. weekly_dividend_job  — runs Saturday 06:00, checks EODHD for new dividends
  3. weekly_fund_job      — runs Saturday 07:00, refreshes fundamentals via yfinance
"""
import logging
import time
from datetime import date, datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import AsyncSessionLocal
from app.models import Stock, Price, Dividend, Fundamental
from app.scrapers.eodhd_loader import fetch_bulk_quotes, fetch_dividends

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="Asia/Jerusalem")


# ---------------------------------------------------------------------------
# Helper: resolve today's trade date from a Unix timestamp
# ---------------------------------------------------------------------------

def _ts_to_date(ts: int | None) -> date:
    if ts:
        return datetime.fromtimestamp(ts, tz=timezone.utc).date()
    return date.today()


# ---------------------------------------------------------------------------
# Job 1: Daily price update
# ---------------------------------------------------------------------------

async def daily_price_job():
    """
    Fetch today's closing prices for all active TASE stocks via EODHD bulk
    real-time endpoint and upsert into the prices table.
    Called after TASE market close (Sun–Thu 18:30 IL).
    """
    logger.info("daily_price_job: starting")

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Stock.id, Stock.ticker).where(Stock.is_active.is_(True))
        )
        rows = result.all()
        stock_map = {r.ticker: r.id for r in rows}  # code → db id

    codes = list(stock_map.keys())
    quotes = fetch_bulk_quotes(codes)

    upserted = 0
    async with AsyncSessionLocal() as db:
        for code, q in quotes.items():
            stock_id = stock_map.get(code)
            if not stock_id or q["close"] is None:
                continue

            trade_date = _ts_to_date(q.get("timestamp"))

            stmt = pg_insert(Price).values(
                stock_id=stock_id,
                trade_date=trade_date,
                open=q["open"],
                high=q["high"],
                low=q["low"],
                close=q["close"],
                volume=q["volume"],
                market_cap=None,
                week52_high=None,
                week52_low=None,
            ).on_conflict_do_update(
                index_elements=["stock_id", "trade_date"],
                set_=dict(
                    open=q["open"],
                    high=q["high"],
                    low=q["low"],
                    close=q["close"],
                    volume=q["volume"],
                )
            )
            await db.execute(stmt)
            upserted += 1

        # Recompute 52-week high/low for all touched stocks
        await _refresh_52w(db, list(stock_map.values()))
        await db.commit()

    logger.info("daily_price_job: done — %d prices upserted", upserted)


async def _refresh_52w(db, stock_ids: list[int]):
    """Recompute and store 52-week high/low on each stock's latest price row."""
    cutoff = date.today() - timedelta(days=365)
    for stock_id in stock_ids:
        result = await db.execute(
            select(Price.high, Price.low)
            .where(Price.stock_id == stock_id)
            .where(Price.trade_date >= cutoff)
        )
        price_rows = result.all()
        highs = [r.high for r in price_rows if r.high is not None]
        lows  = [r.low  for r in price_rows if r.low  is not None]
        if not highs:
            continue

        latest_result = await db.execute(
            select(Price.id)
            .where(Price.stock_id == stock_id)
            .order_by(Price.trade_date.desc())
            .limit(1)
        )
        latest_id = latest_result.scalar_one_or_none()
        if latest_id:
            await db.execute(
                update(Price)
                .where(Price.id == latest_id)
                .values(week52_high=max(highs), week52_low=min(lows))
            )


# ---------------------------------------------------------------------------
# Job 2: Weekly dividend refresh
# ---------------------------------------------------------------------------

async def weekly_dividend_job():
    """
    Re-fetch dividend history from EODHD for all active stocks and insert
    any new records. Runs Saturday morning so it catches the prior week's
    ex-dividend announcements.
    """
    logger.info("weekly_dividend_job: starting")

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Stock.id, Stock.ticker).where(Stock.is_active.is_(True))
        )
        stock_map = {r.ticker: r.id for r in result}

    inserted_total = 0
    paying: set[str] = set()

    for code, stock_id in stock_map.items():
        records = fetch_dividends(code)
        if not records:
            time.sleep(0.1)
            continue

        paying.add(code)
        rows = [
            dict(
                stock_id=stock_id,
                maya_filing_id=f"eodhd_{code}_{r.ex_date}",
                declared_date=r.declared_date,
                ex_date=r.ex_date,
                payment_date=r.payment_date,
                record_date=r.record_date,
                amount_ils=r.amount_ils,
                frequency=None,
            )
            for r in records
        ]

        async with AsyncSessionLocal() as db:
            for i in range(0, len(rows), 500):
                chunk = rows[i: i + 500]
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
            inserted_total += len(rows)

        time.sleep(0.1)

    # Sync pays_dividend flag
    async with AsyncSessionLocal() as db:
        for code in paying:
            await db.execute(
                update(Stock).where(Stock.ticker == code).values(pays_dividend=True)
            )
        await db.commit()

    logger.info("weekly_dividend_job: done — %d records processed, %d paying stocks",
                inserted_total, len(paying))


# ---------------------------------------------------------------------------
# Job 3: Weekly fundamentals refresh (yfinance, ~57 known tickers)
# ---------------------------------------------------------------------------

async def weekly_fund_job():
    """
    Refresh fundamental data (PE, payout ratio, EPS, FCF, D/E) from yfinance
    for the validated TASE ticker subset (~57 stocks).
    """
    logger.info("weekly_fund_job: starting")

    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed — skipping fundamentals")
        return

    from app.scrapers.yfinance_loader import TASE_STOCKS

    updated = 0
    async with AsyncSessionLocal() as db:
        for yahoo_ticker, display_ticker, _ in TASE_STOCKS:
            result = await db.execute(select(Stock).where(Stock.ticker == display_ticker))
            stock = result.scalar_one_or_none()
            if not stock:
                continue

            try:
                info = yf.Ticker(yahoo_ticker).info
                if not info or info.get("quoteType") == "NONE":
                    continue

                def sf(k):
                    v = info.get(k)
                    try:
                        f = float(v)
                        return f if f == f else None
                    except (TypeError, ValueError):
                        return None

                stmt = pg_insert(Fundamental).values(
                    stock_id=stock.id,
                    fiscal_year=date.today().year,
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
                await db.execute(stmt)
                updated += 1
            except Exception as exc:
                logger.error("Fundamentals failed for %s: %s", display_ticker, exc)

        await db.commit()

    logger.info("weekly_fund_job: done — %d stocks updated", updated)


# ---------------------------------------------------------------------------
# Scheduler setup
# ---------------------------------------------------------------------------

def start_scheduler():
    """Register all jobs and start the scheduler. Called on app startup."""

    # Daily price update — Sun–Thu at 18:30 Israel time (after TASE close)
    scheduler.add_job(
        daily_price_job,
        CronTrigger(day_of_week="sun,mon,tue,wed,thu", hour=18, minute=30,
                    timezone="Asia/Jerusalem"),
        id="daily_price_job",
        replace_existing=True,
    )

    # Weekly dividend refresh — Saturday at 06:00 Israel time
    scheduler.add_job(
        weekly_dividend_job,
        CronTrigger(day_of_week="sat", hour=6, minute=0, timezone="Asia/Jerusalem"),
        id="weekly_dividend_job",
        replace_existing=True,
    )

    # Weekly fundamentals — Saturday at 07:00 Israel time
    scheduler.add_job(
        weekly_fund_job,
        CronTrigger(day_of_week="sat", hour=7, minute=0, timezone="Asia/Jerusalem"),
        id="weekly_fund_job",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))
