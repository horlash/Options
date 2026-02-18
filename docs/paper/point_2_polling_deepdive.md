# Point 2: Polling Frequency & Shared Price Cache — FINALIZED ✅

> **Status:** Approved | **Date:** Feb 18, 2026  
> **Depends On:** Point 1 (Neon PostgreSQL) ✅

---

## Final Decisions

| Decision | Choice |
|----------|--------|
| Trade execution | **Tradier** (sandbox for paper, live for real) — SL/TP at tick level |
| Server cron interval | 60 seconds — syncs Tradier order status + ORATS snapshots |
| Frontend poll interval | 15 seconds — reads cached DB data (no API calls) |
| Snapshot frequency | 40 seconds — ORATS price snapshots for P&L curves |
| Auto-refresh | On by default, user can toggle off |
| Scheduler | APScheduler |

---

## Architecture

- Tradier handles SL/TP execution at tick-level
- Our cron syncs Tradier order status every 60s
- ORATS price snapshots captured every 40s for backtesting
- Frontend polls DB every 15s (no API calls)
- Walk-away fully handled by Tradier + cron sync

---

## API Budget

| Source | Calls/day | Rate limit | Usage |
|--------|-----------|------------|-------|
| ORATS | ~4,680 | 1,000/min | 1.2% |
| Tradier | ~390 | Generous | Minimal |
| Frontend | 0 API calls | N/A | N/A |

---

## Optimizations

- Ticker dedup: 1 ORATS call per unique ticker
- Expired skip, weekend/holiday skip
- 30-second chain cache
