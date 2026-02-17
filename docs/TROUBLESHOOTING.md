# Troubleshooting Guide
**Last Updated:** 2026-02-16
**Version:** NewScanner v3.0 (Strict ORATS Mode)

## Common Errors & Fixes

### 1. Docker: "Failed to scan [Ticker]" or "Connection Refused"
**Symptom:** The container is running, but scans fail instantly.
**Cause:** Usually a network issue or missing API key in the container.
**Fix:**
```bash
# 1. Check logs
docker logs leap-scanner-container

# 2. Rebuild if you changed .env
docker-compose build --no-cache
docker-compose up -d
```

### 2. ORATS: "Ticker not in ORATS universe. Skipping."
**Symptom:** A specific ticker is skipped during scanning.
**Cause:** The ticker is not in the ORATS coverage cache (`orats_universe.json`).
**Fix:**
-   **Check coverage:** ORATS covers ~11,102 tickers (~42% of FMP's list). Many small/micro-caps and foreign-listed ADRs are not supported.
-   **Refresh cache:** If the ticker was recently listed:
    ```bash
    python backend/scripts/refresh_tickers_v3.py
    ```
-   **Verify directly:** Check if ORATS supports the ticker at [orats.io](https://orats.io/).

### 3. ORATS: "⚠️ ORATS universe cache is X days old"
**Symptom:** Warning message on scanner startup.
**Cause:** The `orats_universe.json` cache hasn't been refreshed in over 7 days.
**Fix:**
```bash
python backend/scripts/refresh_tickers_v3.py
```

### 4. ORATS: get_history() Returns None
**Symptom:** Historical price data unavailable for a ticker.
**Possible Causes:**
-   Ticker not in ORATS universe (see Issue #2).
-   ORATS API key invalid or expired — check `ORATS_API_KEY` in `.env`.
-   Network/connectivity issue.
**Note:** ORATS `/hist/dailies` does NOT accept `startDate`/`endDate` params. All data is fetched and filtered client-side.

### 5. ORATS: 404 on Index Tickers
**Symptom:** Index tickers like `$SPX` return 404 errors.
**Cause:** ORATS uses **plain** ticker format. `$SPX.X` returns 404.
**Fix:** The system handles this automatically via `_clean_ticker()`. If you're calling the API directly, use `SPX` (not `$SPX` or `$SPX.X`).
**Aliases:** `DJI` → `DJX` (ORATS uses `DJX` for Dow Jones).

### 6. Finnhub: "Limit Reached" vs "Sentiment Unavailable"
**Symptom:** You see "⚠️ Finnhub Limit Reached" in logs.
**Clarification:**
-   **"Limit Reached":** You hit the 60 calls/minute cap. Wait a minute.
-   **"Sentiment Unavailable":** This is NORMAL for Indices (VIX/SPX) or small caps. The scanner will fallback to analyzing headlines automatically.

### 7. FMP: "Stock Screener Failed"
**Symptom:** Sector Scan returns 0 results.
**Cause:** Free Tier limit reached or API key invalid.
**Fix:**
-   Check `FMP_API_KEY` in `.env`.
-   Run `python backend/scripts/enrich_tickers.py` to rebuild the local cache.

### 8. Sector Scan: "Skipped X tickers not in ORATS universe"
**Symptom:** Scanner reports skipping tickers during sector scan.
**Cause:** FMP returns candidates that ORATS doesn't cover. The ORATS pre-filter removes them before batch API calls.
**Assessment:** This is **by design** — it saves API calls and prevents 404 errors. Only ORATS-covered tickers are scanned.

## Data Logic Issues

### "Why did scan fail for SPY?"
-   **Check:** Did it have >15% profit potential? `options_analyzer` enforces this for ETFs.
-   **Fix:** Lower `MIN_PROFIT_POTENTIAL` in `.env` if you want to see thinner trades.

### "Why did VIX show 0 results?"
-   **Check:** VIX options are often short-term. Ensure you aren't filtering for LEAPS (`min_days=150`) if you want near-term VIX plays.

### "Why did MSFT return None?"
-   **Check:** MTA (Multi-Timeframe Analysis) downtrend rejection. If the stock price is below SMA-200, LEAP scans are blocked.
-   **Assessment:** By design — prevents LEAP entries on downtrending stocks.
