# Point 5: Market Hours & Bookend Snapshots — FINALIZED ✅

> **Status:** Approved | **Date:** Feb 19, 2026  
> **Depends On:** Point 2 ✅

---

## Final Decisions

| Decision | Choice |
|----------|--------|
| **Polling Window** | **9:30 AM – 4:00 PM ET** (Strict US/Eastern time) |
| **Pre-Market Snapshot** | **9:25 AM ET** (Capture gap-ups/downs) |
| **Post-Market Snapshot** | **4:05 PM ET** (Official mark-to-market close) |
| **Holidays** | **Ignored for V1** (Polling on holidays is harmless) |
| **Extended Hours** | **Ignored** (Standard equity options only) |

---

## The Strategy

### 1. The Polling Window (9:30 AM – 4:00 PM ET)
*   **Logic:** The `sync_tradier_orders` (60s) and `update_price_snapshots` (40s) jobs only run during this window.
*   **Manual Override:** `FORCE_MARKET_OPEN=true` env var allows testing at night.

### 2. "Bookend" Snapshots
Crucial for data integrity and AI training.

*   **🌅 Pre-Market Snapshot (9:25 AM):**
    *   **Why:** To capture the "Gap." If a stock closed at $100 and opens at $110, the 9:25 AM snapshot establishes the day's baseline.
    *   **Action:** Single fetch of all watched tickers.

*   **dup Post-Market Snapshot (4:05 PM):**
    *   **Why:** To capture the "Official Close." Option settlement prices often finalize a few minutes after the bell.
    *   **Action:** Final update of `close_price` for open positions to mark-to-market for the day.

---

## Detailed Implementation Steps

### Step 5.1: Timezone Utility
- **File:** `backend/utils/market_hours.py`
- **Task:** Implement `is_market_open()` helper:
  ```python
  from datetime import datetime, time
  import pytz
  
  EASTERN = pytz.timezone('US/Eastern')
  
  def is_market_open():
      now = datetime.now(EASTERN)
      if now.weekday() > 4: return False  # Weekend
      # 9:30 AM to 4:00 PM
      return time(9, 30) <= now.time() <= time(16, 0)
  ```

### Step 5.2: Configure Scheduler Triggers
- **File:** `backend/app.py`
- **Task:** Use `CronTrigger` with explicit timezone:
  ```python
  from apscheduler.triggers.cron import CronTrigger
  
  # 1. Main Polling (9:30 - 4:00)
  scheduler.add_job(
      monitor.sync_tradier_orders,
      CronTrigger(day_of_week='mon-fri', hour='9-15', minute='*', timezone=EASTERN)
  )
  
  # 2. Pre-Market Bookend (9:25 AM)
  scheduler.add_job(
      monitor.capture_bookend_snapshot,
      CronTrigger(day_of_week='mon-fri', hour=9, minute=25, timezone=EASTERN),
      args=['PRE_MARKET']
  )
  
  # 3. Post-Market Bookend (4:05 PM)
  scheduler.add_job(
      monitor.capture_bookend_snapshot,
      CronTrigger(day_of_week='mon-fri', hour=16, minute=5, timezone=EASTERN),
      args=['POST_MARKET']
  )
  ```

### Step 5.3: Manual Override
- **task:** Add logic to `is_market_open()` to return `True` if `os.getenv('FORCE_MARKET_OPEN')` is set.
