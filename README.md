# TASE Dividend Screener

A web platform for Israeli investors to screen and track dividend-paying stocks listed on the Tel Aviv Stock Exchange (TASE).

Inspired by Simply Safe Dividends, built exclusively for the Israeli market — featuring a stock screener, a custom Dividend Safety Score, and a portfolio tracker with income projections and a dividend calendar.

---

## Current Status

### What's working
- **Frontend** — React + TypeScript + Vite, Israel blue (#0038B8) theme, Inter font
  - Screener table with 26 columns, filter chips, more-filters modal, columns drawer
  - Live data from backend API
  - Running at `http://localhost:5173`
- **Backend** — FastAPI + SQLAlchemy (async) + PostgreSQL
  - Running at `http://localhost:8000`
  - Full TASE stock universe loaded: **539 stocks, 370 dividend-paying**
  - **649,695 price bars** (5 years history per stock)
  - **26,135 dividend records**
  - Fundamentals (PE, payout ratio, FCF) loaded via yfinance for ~57 known tickers

### Data sources
- **EODHD** (`EODHD_API_KEY` in `backend/.env`) — primary source for all TASE stocks, prices, dividends
  - Exchange code: `TA`, ticker format: `CODE.TA`, prices/dividends in ILA (÷100 = ILS)
- **yfinance** — fallback for fundamentals only (~57 validated `.TA` tickers)

### Scheduled jobs (APScheduler, runs inside FastAPI)
| Job | Schedule | What it does | Time |
|-----|----------|-------------|------|
| `daily_price_job` | Sun–Thu 18:30 IL | Bulk price update for all 537 stocks | ~29s |
| `weekly_dividend_job` | Saturday 06:00 IL | Check EODHD for new dividends | ~23 min |
| `weekly_fund_job` | Saturday 07:00 IL | Refresh fundamentals via yfinance | ~29s |

---

## How to run locally

```bash
# Backend
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload

# Frontend
cd frontend
npm run dev
```

### Re-seed the database (one-time or after wipe)
```bash
cd backend
source .venv/bin/activate
python init_data.py                   # full load (~8h — 537 stocks × prices + dividends)
python init_data.py --stocks-only     # just upsert stock master (~5s)
python init_data.py --prices-only     # price history only
python init_data.py --dividends-only  # dividend history only
python init_data.py --fundamentals-only  # yfinance fundamentals for known tickers
```

---

## Stack
- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS
- **Backend:** FastAPI, SQLAlchemy (async), Alembic, APScheduler
- **Database:** PostgreSQL (local), asyncpg driver
- **Data:** EODHD All World plan + yfinance

---

## Next steps (suggested)
1. **Portfolio tracker** — let users add holdings and track dividend income
2. **Dividend calendar** — show upcoming ex-dates and payment dates
3. **Safety score improvement** — incorporate more fundamentals data (currently limited to ~57 stocks)
4. **Sector enrichment** — auto-classify the ~480 stocks without a sector tag
5. **Deploy** — containerize and deploy to cloud (backend + frontend + PostgreSQL)
