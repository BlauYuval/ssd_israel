"""
APScheduler-based job scheduler.

Jobs:
  1. daily_price_job       — runs after TASE market close (Sun–Thu 18:00 IL time)
  2. maya_dividend_job     — runs daily, checks for new Maya announcements
  3. fundamental_job       — runs weekly (Saturday morning), refreshes fundamentals

All jobs write directly to the database via SQLAlchemy.
"""
import asyncio
import logging
from datetime import date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import AsyncSessionLocal
from app.models import Stock, Price, Dividend, Fundamental
from app.scrapers import tase_prices, maya_dividends, bizportal

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="Asia/Jerusalem")


# ---------------------------------------------------------------------------
# Job: daily prices
# ---------------------------------------------------------------------------

async def daily_price_job():
    """Fetch yesterday's closing prices for all TASE stocks and upsert to DB."""
    target_date = date.today() - timedelta(days=1)
    logger.info("Starting daily price job for %s", target_date)
    inserted = 0

    async with AsyncSessionLocal() as db:
        # Build tase_id → stock_id map
        result = await db.execute(select(Stock.tase_id, Stock.id).where(Stock.is_active.is_(True)))
        tase_to_db = {row.tase_id: row.id for row in result}

        async for bar in tase_prices.scrape_daily_prices(target_date):
            stock_id = tase_to_db.get(bar.tase_id)
            if not stock_id:
                continue

            stmt = pg_insert(Price).values(
                stock_id=stock_id,
                trade_date=bar.trade_date,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                market_cap=bar.market_cap,
            ).on_conflict_do_update(
                constraint="uq_price_stock_date",
                set_={
                    "close": bar.close,
                    "volume": bar.volume,
                    "market_cap": bar.market_cap,
                }
            )
            await db.execute(stmt)
            inserted += 1

        # Update 52-week high/low for touched stocks
        await _update_52w(db, list(tase_to_db.values()))
        await db.commit()

    logger.info("Daily price job done — %d bars upserted", inserted)


async def _update_52w(db, stock_ids: list[int]):
    """Recompute 52-week high/low and write to the latest price row."""
    cutoff = date.today() - timedelta(days=365)
    for stock_id in stock_ids:
        result = await db.execute(
            select(
                Price.high.label("max_high"),
                Price.low.label("min_low"),
            )
            .where(Price.stock_id == stock_id)
            .where(Price.trade_date >= cutoff)
        )
        # Simplified: update the most recent row
        # A production version would use a window function / materialised column
        rows = result.all()
        if not rows:
            continue
        highs = [r.max_high for r in rows if r.max_high is not None]
        lows = [r.min_low for r in rows if r.min_low is not None]
        if not highs:
            continue

        latest = await db.execute(
            select(Price)
            .where(Price.stock_id == stock_id)
            .order_by(Price.trade_date.desc())
            .limit(1)
        )
        latest_price = latest.scalar_one_or_none()
        if latest_price:
            latest_price.week52_high = max(highs)
            latest_price.week52_low = min(lows)
            db.add(latest_price)


# ---------------------------------------------------------------------------
# Job: Maya dividend watcher
# ---------------------------------------------------------------------------

async def maya_dividend_job():
    """Check Maya for new dividend announcements (last 7 days) and upsert."""
    logger.info("Starting Maya dividend job")
    inserted = 0

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Stock.tase_id, Stock.id, Stock.price))
        # Note: Stock has no price column; fetch latest price separately
        result = await db.execute(select(Stock.tase_id, Stock.id))
        tase_to_db = {row.tase_id: row.id for row in result}

        async for event in maya_dividends.scrape_recent_dividends(days_back=7):
            stock_id = tase_to_db.get(event.tase_id)
            if not stock_id:
                # New company — add to stocks table first
                stock_id = await _ensure_stock(db, event.tase_id)

            # Mark stock as dividend-paying
            await db.execute(
                select(Stock).where(Stock.id == stock_id)
            )

            stmt = pg_insert(Dividend).values(
                stock_id=stock_id,
                ex_date=event.ex_date,
                payment_date=event.payment_date,
                record_date=event.record_date,
                declared_date=event.declared_date,
                amount_ils=event.amount_ils,
                maya_filing_id=event.maya_filing_id or None,
            ).on_conflict_do_update(
                constraint="uq_dividend_stock_exdate",
                set_={
                    "payment_date": event.payment_date,
                    "amount_ils": event.amount_ils,
                }
            )
            await db.execute(stmt)

            # Mark stock as dividend paying
            result = await db.execute(select(Stock).where(Stock.id == stock_id))
            stock = result.scalar_one_or_none()
            if stock and not stock.pays_dividend:
                stock.pays_dividend = True
                db.add(stock)

            inserted += 1

        await db.commit()

    logger.info("Maya dividend job done — %d events upserted", inserted)


async def _ensure_stock(db, tase_id: str) -> int:
    """Insert a minimal stock record if it doesn't exist. Returns the DB id."""
    result = await db.execute(select(Stock).where(Stock.tase_id == tase_id))
    existing = result.scalar_one_or_none()
    if existing:
        return existing.id
    new_stock = Stock(tase_id=tase_id, ticker=tase_id)
    db.add(new_stock)
    await db.flush()
    return new_stock.id


# ---------------------------------------------------------------------------
# Job: weekly fundamentals refresh
# ---------------------------------------------------------------------------

async def fundamental_job():
    """Weekly refresh of fundamental data from bizportal."""
    logger.info("Starting weekly fundamental job")
    updated = 0

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Stock.id, Stock.tase_id, Stock.name_he)
            .where(Stock.pays_dividend.is_(True))
            .where(Stock.is_active.is_(True))
        )
        stocks = result.all()

        for stock_row in stocks:
            # Resolve bizportal ID (best-effort)
            biz_id = await bizportal.fetch_bizportal_id(stock_row.name_he or stock_row.tase_id)
            if not biz_id:
                logger.warning("No bizportal ID for tase_id=%s", stock_row.tase_id)
                continue

            async for rec in bizportal.scrape_fundamentals_for_company(stock_row.tase_id, biz_id):
                stmt = pg_insert(Fundamental).values(
                    stock_id=stock_row.id,
                    fiscal_year=rec.fiscal_year,
                    revenue=rec.revenue,
                    gross_profit=rec.gross_profit,
                    operating_income=rec.operating_income,
                    net_income=rec.net_income,
                    eps=rec.eps,
                    operating_cash_flow=rec.operating_cash_flow,
                    capex=rec.capex,
                    free_cash_flow=rec.free_cash_flow,
                    dividends_paid=rec.dividends_paid,
                    total_assets=rec.total_assets,
                    total_liabilities=rec.total_liabilities,
                    shareholders_equity=rec.shareholders_equity,
                    total_debt=rec.total_debt,
                    payout_ratio=rec.payout_ratio,
                    fcf_payout_ratio=rec.fcf_payout_ratio,
                    debt_to_equity=rec.debt_to_equity,
                    data_source=rec.data_source,
                ).on_conflict_do_update(
                    constraint="uq_fundamental_stock_year",
                    set_={
                        "revenue": rec.revenue,
                        "net_income": rec.net_income,
                        "free_cash_flow": rec.free_cash_flow,
                        "dividends_paid": rec.dividends_paid,
                        "payout_ratio": rec.payout_ratio,
                        "fcf_payout_ratio": rec.fcf_payout_ratio,
                        "debt_to_equity": rec.debt_to_equity,
                        "data_source": rec.data_source,
                    }
                )
                await db.execute(stmt)
                updated += 1

        await db.commit()

    logger.info("Fundamental job done — %d records upserted", updated)


# ---------------------------------------------------------------------------
# Scheduler setup
# ---------------------------------------------------------------------------

def start_scheduler():
    """Register all jobs and start the scheduler. Called on app startup."""
    # Daily price fetch — Sunday–Thursday at 18:30 IL time (after TASE close)
    scheduler.add_job(
        daily_price_job,
        CronTrigger(day_of_week="sun,mon,tue,wed,thu", hour=18, minute=30, timezone="Asia/Jerusalem"),
        id="daily_price_job",
        replace_existing=True,
    )

    # Maya dividend watcher — daily at 20:00 IL time
    scheduler.add_job(
        maya_dividend_job,
        CronTrigger(hour=20, minute=0, timezone="Asia/Jerusalem"),
        id="maya_dividend_job",
        replace_existing=True,
    )

    # Weekly fundamentals — Saturday at 06:00 IL time
    scheduler.add_job(
        fundamental_job,
        CronTrigger(day_of_week="sat", hour=6, minute=0, timezone="Asia/Jerusalem"),
        id="fundamental_job",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))
