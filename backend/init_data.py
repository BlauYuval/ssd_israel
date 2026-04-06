"""
init_data.py — One-time data backfill script.

Run this once after `docker compose up` to:
  1. Create all DB tables (via SQLAlchemy metadata)
  2. Fetch the full TASE company/securities list → populate stocks table
  3. Backfill 5 years of historical prices for each stock
  4. Backfill all historical dividend announcements from Maya
  5. Scrape annual fundamental data from bizportal for dividend-paying stocks

Usage:
    cd backend
    python init_data.py [--stocks-only] [--prices-only] [--dividends-only] [--fundamentals-only]
"""
import asyncio
import argparse
import logging
import sys
from datetime import date

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("init_data")

# ── import app modules after path is set ────────────────────────────────────
sys.path.insert(0, ".")
from app.core.config import settings
from app.database import Base
from app.models import Stock, Price, Dividend, Fundamental
from app.scrapers import tase_prices, maya_dividends, bizportal
from app.scrapers.tase_prices import _norm


# ── engine (sync-url not needed here — we use async throughout) ─────────────
engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

PRICE_HISTORY_YEARS = 5


# ── 1. Create tables ─────────────────────────────────────────────────────────

async def create_tables():
    logger.info("Creating database tables…")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Tables ready.")


# ── 2. Populate stocks ────────────────────────────────────────────────────────

async def populate_stocks():
    """
    Fetch the TASE securities list and upsert every equity into the stocks table.
    Maps: secId → tase_id, ticker symbol, name.
    """
    logger.info("Fetching TASE securities list…")
    from app.scrapers.base import build_client
    async with build_client() as client:
        securities = await tase_prices.fetch_securities_list(client)

    if not securities:
        logger.warning("No securities returned from TASE API — check connectivity.")
        return

    logger.info("Upserting %d securities into stocks table…", len(securities))
    async with Session() as db:
        for sec in securities:
            tase_id = str(_norm(sec, "secId", "SecId", "id", "Id") or "")
            ticker  = str(_norm(sec, "symbol", "Symbol", "ticker", "Ticker") or tase_id)
            name_en = _norm(sec, "nameEn", "NameEn", "name", "Name")
            name_he = _norm(sec, "nameHe", "NameHe", "nameHebrew", "NameHebrew")
            sector  = _norm(sec, "sector", "Sector", "sectorName", "SectorName")
            industry= _norm(sec, "industry", "Industry")
            isin    = _norm(sec, "isin", "ISIN")

            if not tase_id:
                continue

            stmt = pg_insert(Stock).values(
                tase_id=tase_id,
                ticker=ticker,
                name_en=name_en,
                name_he=name_he,
                sector=sector,
                industry=industry,
                isin=isin,
                is_active=True,
            ).on_conflict_do_update(
                index_elements=["tase_id"],
                set_={
                    "ticker": ticker,
                    "name_en": name_en,
                    "name_he": name_he,
                    "sector": sector,
                    "industry": industry,
                }
            )
            await db.execute(stmt)

        await db.commit()
    logger.info("Stocks table populated.")


# ── 3. Backfill historical prices ─────────────────────────────────────────────

async def backfill_prices():
    """Backfill PRICE_HISTORY_YEARS of daily OHLCV for every active stock."""
    async with Session() as db:
        result = await db.execute(
            select(Stock.id, Stock.tase_id).where(Stock.is_active.is_(True))
        )
        stocks = result.all()

    logger.info("Backfilling %d years of prices for %d stocks…", PRICE_HISTORY_YEARS, len(stocks))
    total_bars = 0

    for idx, (stock_id, tase_id) in enumerate(stocks, 1):
        logger.info("[%d/%d] Fetching prices for tase_id=%s", idx, len(stocks), tase_id)
        bars = []
        async for bar in tase_prices.scrape_price_history_bulk(tase_id, years_back=PRICE_HISTORY_YEARS):
            bars.append({
                "stock_id": stock_id,
                "trade_date": bar.trade_date,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "market_cap": bar.market_cap,
            })

        if not bars:
            continue

        async with Session() as db:
            for row in bars:
                stmt = pg_insert(Price).values(**row).on_conflict_do_update(
                    constraint="uq_price_stock_date",
                    set_={
                        "close": row["close"],
                        "volume": row["volume"],
                        "market_cap": row["market_cap"],
                    }
                )
                await db.execute(stmt)
            await db.commit()

        total_bars += len(bars)
        logger.info("  → %d bars saved", len(bars))

    logger.info("Price backfill complete — %d total bars.", total_bars)


# ── 4. Backfill dividends ─────────────────────────────────────────────────────

async def backfill_dividends():
    """Scrape all historical dividend announcements from Maya for every stock."""
    async with Session() as db:
        result = await db.execute(
            select(Stock.id, Stock.tase_id).where(Stock.is_active.is_(True))
        )
        stocks = result.all()

    logger.info("Backfilling dividends for %d stocks from Maya…", len(stocks))
    total_events = 0

    from app.scrapers.base import build_client
    async with build_client() as client:
        for idx, (stock_id, tase_id) in enumerate(stocks, 1):
            events = []
            async for event in maya_dividends.fetch_dividends_for_company(client, tase_id, max_pages=50):
                events.append(event)

            if not events:
                continue

            logger.info("[%d/%d] tase_id=%s — %d dividend events", idx, len(stocks), tase_id, len(events))

            async with Session() as db:
                for event in events:
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
                stock_result = await db.execute(select(Stock).where(Stock.id == stock_id))
                stock = stock_result.scalar_one_or_none()
                if stock:
                    stock.pays_dividend = True
                    db.add(stock)

                await db.commit()

            total_events += len(events)

    logger.info("Dividend backfill complete — %d total events.", total_events)


# ── 5. Backfill fundamentals ──────────────────────────────────────────────────

async def backfill_fundamentals():
    """Scrape annual fundamentals from bizportal for all dividend-paying stocks."""
    async with Session() as db:
        result = await db.execute(
            select(Stock.id, Stock.tase_id, Stock.name_he, Stock.name_en)
            .where(Stock.pays_dividend.is_(True))
            .where(Stock.is_active.is_(True))
        )
        stocks = result.all()

    logger.info("Backfilling fundamentals for %d dividend-paying stocks…", len(stocks))
    total_records = 0
    skipped = 0

    for idx, row in enumerate(stocks, 1):
        name = row.name_he or row.name_en or row.tase_id
        biz_id = await bizportal.fetch_bizportal_id(name)
        if not biz_id:
            logger.warning("[%d/%d] No bizportal ID for %s — skipping", idx, len(stocks), name)
            skipped += 1
            continue

        recs = []
        async for rec in bizportal.scrape_fundamentals_for_company(row.tase_id, biz_id):
            recs.append(rec)

        if not recs:
            continue

        logger.info("[%d/%d] %s — %d annual records", idx, len(stocks), name, len(recs))

        async with Session() as db:
            for rec in recs:
                stmt = pg_insert(Fundamental).values(
                    stock_id=row.id,
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
            await db.commit()

        total_records += len(recs)

    logger.info(
        "Fundamental backfill complete — %d records saved, %d skipped (no bizportal ID).",
        total_records, skipped,
    )


# ── main ─────────────────────────────────────────────────────────────────────

async def main(args):
    run_all = not any([args.stocks_only, args.prices_only, args.dividends_only, args.fundamentals_only])

    await create_tables()

    if run_all or args.stocks_only:
        await populate_stocks()

    if run_all or args.prices_only:
        await backfill_prices()

    if run_all or args.dividends_only:
        await backfill_dividends()

    if run_all or args.fundamentals_only:
        await backfill_fundamentals()

    await engine.dispose()
    logger.info("Init complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TASE Dividend Screener — initial data backfill")
    parser.add_argument("--stocks-only",       action="store_true", help="Only populate stocks table")
    parser.add_argument("--prices-only",       action="store_true", help="Only backfill prices")
    parser.add_argument("--dividends-only",    action="store_true", help="Only backfill dividends")
    parser.add_argument("--fundamentals-only", action="store_true", help="Only backfill fundamentals")
    args = parser.parse_args()
    asyncio.run(main(args))
