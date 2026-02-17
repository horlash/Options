# API Setup Guide
**Last Updated:** 2026-02-16
**Version:** NewScanner v3.0 (Strict ORATS Mode)

This guide walks you through obtaining API keys for all data sources used by the scanner.

## ORATS API (Primary — Options, Quotes, History)

### Step 1: Subscribe
1. Go to [ORATS.io](https://orats.io/) and sign up for the **$199/mo Live Data** plan.
2. This provides access to Options Chains, Real-Time Quotes, Historical Dailies, and the Ticker Universe.

### Step 2: Get API Key
1. Log in to the ORATS dashboard.
2. Navigate to **API Keys** and copy your key.
3. Add it to your `.env` file as `ORATS_API_KEY`.

### Step 3: Initialize Ticker Universe Cache
Run the ORATS universe refresh script to build the local coverage cache:
```bash
python backend/scripts/refresh_tickers_v3.py
```
This creates:
- `backend/data/orats_universe.json` — All ~11,102 ORATS-supported tickers (O(1) lookups).
- Enriches `backend/data/tickers.json` with `orats_covered` status.

> **Note:** Run this weekly to keep coverage current.

### ORATS Ticker Format
- ORATS uses **plain tickers**: `SPX`, `NDX`, `VIX`, `AAPL`, `SPY`.
- Do **NOT** use `$` prefix or `.X` suffix — `$SPX.X` returns 404.
- Only alias: `DJI` → `DJX` (ORATS lists Dow Jones as `DJX`).

---

## Financial Modeling Prep (FMP) (Sector Screening)
**Required for:** Sector, Industry, Market Cap, and Volume filtering.

### Step 1: Sign Up
1. Go to [FMP (Financial Modeling Prep)](https://site.financialmodelingprep.com/developer/docs)
2. Sign up for a **Free** account.

### Step 2: Get API Key
1. Copy your API Key from the dashboard.
2. Add it to `.env` as `FMP_API_KEY`.
3. **Note:** The Free Tier has daily limits. The scanner caches data locally (`tickers.json`) to minimize API calls.

---

## Finnhub (Sentiment & Fundamentals)
**Required for:** AI Sentiment Analysis and "Moat" (Fundamentals) checks.

### Step 1: Create Account
1. Go to [Finnhub.io](https://finnhub.io/)
2. Click "Get free API key"

### Step 2: Get API Key
1. Copy API Key to `.env` as `FINNHUB_API_KEY`.

### Free Tier Limits
- **60 calls/minute.** The scanner respects this automatically.
- **Sentiment Data:** Often unavailable for Indices (VIX) or small caps. The scanner will log "Skipping Sentiment" and proceed with Headlines only.

---

## NewsAPI (Headlines Backup)
**Required for:** Fallback news data.

### Step 1: Sign Up
1. Go to [NewsAPI.org](https://newsapi.org/)
2. Get API Key → `.env` as `NEWSAPI_KEY`.

---

## Complete .env Configuration

```env
# === PRIMARY DATA SOURCE ===
ORATS_API_KEY=your_orats_api_key

# === SCREENING & FUNDAMENTALS ===
FMP_API_KEY=your_fmp_key
FINNHUB_API_KEY=your_finnhub_key
NEWSAPI_KEY=your_newsapi_key

# === APPLICATION SETTINGS ===
MAX_INVESTMENT_PER_POSITION=2000
MIN_LEAP_DAYS=150
MIN_PROFIT_POTENTIAL=15  # 15% minimum ROI

# === TECHNICAL INDICATOR THRESHOLDS ===
RSI_OVERSOLD=30
RSI_OVERBOUGHT=70

# === DATABASE ===
DATABASE_URL=sqlite:///./leap_scanner.db

# === SERVER ===
PORT=5000
```

> **Note:** `SCHWAB_API_KEY` and `SCHWAB_API_SECRET` are no longer used. Schwab integration has been fully removed.
