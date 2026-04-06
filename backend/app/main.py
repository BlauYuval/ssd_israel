"""
TASE Dividend Screener — FastAPI application entry point.
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import screener, stock, portfolio
from app.jobs.scheduler import start_scheduler, scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="TASE Dividend Screener API",
    description="Dividend screening and portfolio tracking for Tel Aviv Stock Exchange (TASE) listed stocks.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(screener.router)
app.include_router(stock.router)
app.include_router(portfolio.router)


@app.on_event("startup")
async def on_startup():
    logger.info("Starting TASE Dividend Screener API")
    start_scheduler()


@app.on_event("shutdown")
async def on_shutdown():
    if scheduler.running:
        scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped")


@app.get("/health")
async def health():
    return {"status": "ok"}
