# Maintenance Manual
**Last Updated:** 2026-02-16
**Version:** NewScanner v3.0 (Strict ORATS Mode)

This guide explains how to maintain the NewScanner system, including updating data caches and monitoring API health.

---

## 📅 Routine Maintenance Schedule

| Frequency | Task | Script/Command | Why? |
| :--- | :--- | :--- | :--- |
| **Weekly** | Refresh ORATS Universe | `python backend/scripts/refresh_tickers_v3.py` | Updates the local cache of ~11,102 ORATS-supported tickers. |
| **Monthly** | Enrich Sector Data | `python backend/scripts/enrich_tickers.py` | Updates Market Cap/Sector info (FMP) for Sector Scans. |

---

## 🛠️ Script Reference

All scripts are located in `backend/scripts/`. Run them from the project root.

### 1. `refresh_tickers_v3.py` (Primary — Weekly)
**Purpose:** Fetches the complete ORATS ticker universe and builds a local coverage cache.
**What it does:**
-   Calls ORATS `/datav2/tickers` to get all ~11,102 supported tickers.
-   Saves to `backend/data/orats_universe.json` (773 KB, used for O(1) lookups).
-   Enriches `backend/data/tickers.json` with `orats_covered` flag and date ranges.
**When to run:**
-   Weekly (recommended).
-   If you see "⚠️ ORATS universe cache is X days old" warnings in logs.
-   If new IPOs appear to be missing from scans.
**Command:**
```bash
python backend/scripts/refresh_tickers_v3.py
```

### 2. `enrich_tickers.py` (Monthly)
**Purpose:** Adds "Sector", "Industry", and "Market Cap" data to the local ticker cache.
**When to run:**
-   If Sector Scan returns 0 results.
-   If FMP API failed during a previous run.
**Command:**
```bash
python backend/scripts/enrich_tickers.py
```

### 3. `regression_test.py` (After Changes)
**Purpose:** Full 9-suite backend regression test. Validates ORATS API, scanner logic, and data integrity.
**When to run:**
-   After any code changes to `orats.py` or `hybrid_scanner_service.py`.
-   Protocol: 3 consecutive clean loops required to PASS.
**Command:**
```bash
python backend/scripts/regression_test.py
```

---

## 🗄️ Database Maintenance

### Resetting the Database
If you want to clear all past scan results and start fresh:

1.  **Stop the App:** Ctrl+C or `docker-compose down`.
2.  **Delete the DB File:**
    ```bash
    rm leap_scanner.db
    # On Windows: del leap_scanner.db
    ```
3.  **Restart App:** The system will automatically recreate an empty DB on startup.

---

## 📂 Cache Files Reference

| File | Location | Purpose | Refresh |
|------|----------|---------|---------|
| `orats_universe.json` | `backend/data/` | ORATS supported tickers (O(1) lookups) | Weekly |
| `tickers.json` | `backend/data/` | FMP tickers enriched with ORATS coverage | Weekly |

---

## 📂 Logs & Debugging
-   **App Logs:** stdout / console.
-   **Docker Logs:** `docker logs leap-scanner-container`
-   **Debug Output:** Check `debug_output.txt` if you ran a specific debug script.
-   **ORATS Cache Age Warning:** If you see "⚠️ ORATS universe cache is X days old", run `refresh_tickers_v3.py`.

---

## 🗑️ Deprecated Scripts (Do Not Use)
-   `refresh_tickers_v2.py` — Relied on Schwab API (removed). Replaced by `refresh_tickers_v3.py`.
-   `auto_schwab_auth.py` — Schwab OAuth token renewal. No longer needed.
