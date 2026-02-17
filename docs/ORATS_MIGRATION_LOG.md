# ORATS Migration Log
**Date:** February 16, 2026 (Updated)
**Objective:** Fully replace Schwab API with ORATS API for Options Data, Quotes, and Price History.

## 1. Migration Overview
The migration aimed to remove the dependency on Schwab API due to reliability/access issues and switch to ORATS as the primary data source. ORATS successfully replaced Schwab for **Option Chains**, **Real-Time Quotes**, and **Historical Price Data**.

## 2. Failures & Challenges

### ✅ Failure 1: Historical Data Access (Resolved)
*   **Issue:** Requests to the ORATS `/candles` endpoint returned a `403 Forbidden` error.
*   **Diagnosis:** `/candles` is not a valid endpoint for stock history. The correct endpoint is `/hist/dailies`.
*   **Fix:** Updated `OratsAPI.get_history` to use `/hist/dailies`. This endpoint does NOT support `startDate`/`endDate` parameters — it returns all available data. Client-side filtering is applied using a `cutoff` date.
*   **Resolution:** **ORATS API** is now the SOLE Source for historical price data. Yahoo Finance fallback has been REMOVED (Strict Mode).

### ✅ Failure 2: Data Format Differences (Resolved)
*   **Issue:** ORATS returns data in a "wide" format (one row contains both Call and Put info for a strike) unlike the standard "long" format.
*   **Fix:** Implemented `_parse_wide_format` in `OratsAPI.get_option_chain` to normalize this data.

### ✅ Failure 3: Unfiltered Expirations (Resolved)
*   **Issue:** ORATS API returns *all* available options for a ticker in a single response.
*   **Fix:** Client-side filtering — LEAP scans filter for `days_to_expiry >= 150`, Weekly scans for `expiration_date == target_friday`.

### ✅ Failure 4: Index Ticker Format (Resolved)
*   **Issue:** ORATS doesn't recognize `$`-prefixed tickers (e.g., `$SPX`). Additionally, the initial fix assumed `$SPX.X` format was required, which was contradicted by live API testing.
*   **Live API Results:** `SPX` → 200 OK (13,359 results), `$SPX.X` → 404 Not Found.
*   **Fix:** `_clean_ticker()` strips `$` prefix, removes `.X` suffix, and applies a single alias: `DJI` → `DJX` (ORATS uses `DJX` for Dow Jones). RUT excluded due to inconsistent ORATS coverage.

### ✅ Failure 5: `/hist/dailies` Invalid Parameters (Resolved)
*   **Issue:** `get_history()` was sending `startDate`/`endDate` parameters, which are not supported by the `/hist/dailies` endpoint.
*   **Fix:** Removed these parameters. Now fetches all available data and applies client-side `cutoff` date filtering based on the `days` parameter.

## 3. Implementation Details (Final State)

### A. Option Chains (ORATS)
*   **Source:** ORATS API (`/datav2/strikes`)
*   **Method:** `BatchManager` fetches data for multiple tickers in parallel/batches.
*   **Status:** ✅ Fully Implemented.

### B. Real-Time Quotes (ORATS)
*   **Source:** ORATS API (`/datav2/live/strikes`)
*   **Method:** `OratsAPI.get_quote(ticker)` returns the latest snapshot price.
*   **Status:** ✅ Fully Implemented.

### C. Price History (ORATS)
*   **Source:** ORATS API (`/hist/dailies`)
*   **Method:** `OratsAPI.get_history(ticker, days=365)` — fetches all data, filters client-side.
*   **Status:** ✅ Fully Implemented (Strict Mode). No `startDate`/`endDate` params sent.

### D. ORATS Ticker Universe & Caching
*   **Source:** ORATS API (`/datav2/tickers`) — returns ~11,102 supported tickers.
*   **Cache File:** `backend/data/orats_universe.json` (773 KB, O(1) lookups)
*   **Refresh Script:** `backend/scripts/refresh_tickers_v3.py` — weekly refresh recommended.
*   **Coverage:** 4,341 of 10,345 FMP tickers are ORATS-covered (42%).
*   **Integration:**
    *   Scanner loads universe on init (`_load_orats_universe`).
    *   `scan_sector_top_picks()` pre-filters candidates before batch fetch.
    *   `scan_ticker()` early-exits for uncovered tickers.
*   **Status:** ✅ Fully Implemented.

### E. Schwab API
*   **Status:** 🗑️ **REMOVED**. `refresh_tickers_v2.py` (Schwab-based) replaced by `refresh_tickers_v3.py` (ORATS-based).

## 4. Final Validation & Fixes (Strict Mode Refinement)
*   **Resolved Fundamental Scaling Bug:** Finnhub returns raw percentage values (e.g., 159.9) for ROE/Margin, which were incorrectly multiplied by 100.
*   **Resolved Sector Scan Limit:** Updated `scan_sector_top_picks` to accept a `limit` argument.
*   **Resolved Real-Time Price Fetch:** Switched to `/datav2/live/strikes` which reliably populates `stockPrice`.
*   **Resolved Index Ticker Handling:** `_clean_ticker()` strips `$`, applies `DJI`→`DJX` alias. ORATS uses plain tickers (SPX, NDX, VIX).
*   **Resolved data_source Label:** Changed hardcoded `'Schwab'` to `'ORATS'`.
*   **Resolved _normalize_ticker:** Removed legacy Schwab `$` prefix logic.
*   **Added ORATS Universe Pre-filter:** Eliminates wasted API calls on uncovered tickers (saves ~30% scan time).
*   **Removed Dead Code:** Two unreachable duplicate `except` blocks cleaned up.
*   **Validation:** Full 9-suite regression test with `_clean_ticker` format tests and universe cache validation.

## 5. Future Action Items
1.  **Weekly Universe Refresh:** Run `python backend/scripts/refresh_tickers_v3.py` weekly to keep ORATS coverage current.
2.  **Monitor Data Gaps:** Watch for "Insufficient Data" errors in logs, as strict mode drops tickers rather than falling back.
3.  **MTA Override:** Consider adding a `force_scan` flag to bypass MTA downtrend rejection for deep-value LEAP analysis.
