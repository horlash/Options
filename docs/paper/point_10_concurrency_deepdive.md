# Point 10: Concurrency & Race Conditions — Deep Dive (Double Deep)

> **Status:** FINALIZED ✅  
> **Date:** Feb 19, 2026  
> **Depends On:** Point 1 (Database), Point 8 (Optimistic Locking), Point 9 (Tradier)

---

## 🎯 The Goal: "No Double Spends, No Ghost Trades"
In a multi-user, multi-device system with background cron jobs, things can go wrong fast.
This point defines every race condition scenario and the exact fix for each.

---

## 🏁 Race Condition #1: The "Double Click" (Idempotency)

### The Problem
User clicks **"Place Trade"** on NVDA. Network is slow. They click again.
Without protection, the system places **two identical trades**.

### The Danger
- 2x position size (double the risk)
- 2x bracket orders at Tradier
- Confused P&L calculations

### The Fix: Idempotency Keys

Every trade placement request gets a **unique key** generated on the frontend.
The backend uses a `UNIQUE` constraint to reject duplicates.

#### Frontend: Generate the Key
```javascript
// frontend/js/api.js
async function placeTrade(signal) {
    const idempotencyKey = crypto.randomUUID(); // e.g., "a1b2c3d4-..."
    
    const res = await fetch('/api/trades', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            ...signal,
            idempotency_key: idempotencyKey
        })
    });
    
    if (res.status === 409) {
        // Duplicate detected — the first request already went through
        showToast("Trade already placed.", "info");
        return;
    }
    
    return res.json();
}
```

#### Backend: Enforce Uniqueness
```python
# backend/services/trade_service.py
def place_trade(self, signal, idempotency_key):
    # 1. Check if this key already exists
    existing = self.db.query(PaperTrade).filter_by(
        idempotency_key=idempotency_key
    ).first()
    
    if existing:
        # Return the existing trade (idempotent response)
        return existing
    
    # 2. Create the trade
    trade = PaperTrade(
        idempotency_key=idempotency_key,
        ticker=signal['ticker'],
        # ... all other fields ...
    )
    
    try:
        self.db.add(trade)
        self.db.commit()
    except IntegrityError:
        # Race condition: another request snuck in between check and insert
        self.db.rollback()
        return self.db.query(PaperTrade).filter_by(
            idempotency_key=idempotency_key
        ).first()
    
    return trade
```

#### Database: The Safety Net
```python
# backend/database/models.py
class PaperTrade(Base):
    # ...
    idempotency_key = Column(String(100), unique=True, nullable=True)
    #                                       ^^^^^^ THIS IS THE GUARD
```

**Flow:**
1. Click 1 → Key `abc123` → INSERT succeeds → Trade placed ✅
2. Click 2 → Key `abc123` → UNIQUE violation → Return existing trade ✅

---

## 🏁 Race Condition #2: Cron Job Overlap (Scheduler Locking)

### The Problem
The `sync_tradier_orders` cron runs every 60 seconds.
If one run takes 65 seconds (slow API), the next run starts while the first is still going.
Both runs try to update the same trade → **data corruption**.

### The Danger
- Trade gets closed twice
- Bracket orders get double-canceled
- P&L calculated on stale data

### The Fix: PostgreSQL Advisory Locks

Advisory Locks are lightweight, application-level locks provided by Postgres.
They don't lock rows — they lock a **concept** (identified by a number).

```python
# backend/services/monitor_service.py
LOCK_ID_SYNC_ORDERS = 100001
LOCK_ID_PRICE_SNAPSHOTS = 100002

def sync_tradier_orders(self):
    """Cron job: Sync order statuses from Tradier."""
    conn = self.db.connection()
    
    # Try to acquire lock (non-blocking)
    acquired = conn.execute(
        "SELECT pg_try_advisory_lock(%s)", [LOCK_ID_SYNC_ORDERS]
    ).scalar()
    
    if not acquired:
        # Another instance is already running — skip this cycle
        logger.info("sync_tradier_orders: Skipped (lock held by another instance)")
        return
    
    try:
        # === DO THE ACTUAL WORK ===
        open_trades = self.db.query(PaperTrade).filter_by(status='OPEN').all()
        for trade in open_trades:
            self._sync_single_trade(trade)
        self.db.commit()
    finally:
        # Always release the lock
        conn.execute("SELECT pg_advisory_unlock(%s)", [LOCK_ID_SYNC_ORDERS])
```

**Flow:**
1. Cron Run A starts → Acquires lock `100001` → Processing...
2. Cron Run B starts → `pg_try_advisory_lock(100001)` → Returns `false` → **Skips** ✅
3. Cron Run A finishes → Releases lock → Next cron cycle can proceed

---

## 🏁 Race Condition #3: Simultaneous Adjust (Already Solved)

### The Problem
Phone sends "Adjust SL to $3.00". Laptop sends "Adjust SL to $3.50".
Both hit the server at the same time.

### The Fix: Optimistic Locking (Point 8)
This is already solved by the `version` column.

```python
# Both requests arrive:
# Phone:  UPDATE ... SET sl_price=3.00 WHERE id=101 AND version=3
# Laptop: UPDATE ... SET sl_price=3.50 WHERE id=101 AND version=3

# Only ONE succeeds (the first to commit).
# The other gets rows_affected=0 → 409 Conflict → Auto-refresh.
```

**No additional code needed.** Point 8's Optimistic Locking handles this.

---

## 🏁 Race Condition #4: Frontend Button Spam (Debounce)

### The Problem
Even with idempotency keys, we don't want 50 requests hitting the server.
The user is stress-clicking "Close Position" during a market crash.

### The Fix: Disable + Debounce

```javascript
// frontend/js/components/portfolio.js
async function closePosition(ticker, tradeId, version) {
    const button = document.getElementById(`close-btn-${tradeId}`);
    
    // 1. IMMEDIATELY disable the button
    button.disabled = true;
    button.textContent = "Closing...";
    
    try {
        const result = await api.closeTrade(tradeId, version);
        if (result.success) {
            playSound('click');
            showToast(`Closed ${ticker}`, 'success');
        }
    } catch (err) {
        showToast(`Error: ${err.message}`, 'error');
    } finally {
        // 2. Re-enable after response (success or failure)
        button.disabled = false;
        button.textContent = "Close";
        await refreshPortfolio();
    }
}
```

**Defense Layers:**
1. **Button Disable** → Prevents clicks during flight (instant).
2. **Idempotency Key** → Prevents duplicates even if disable fails (backend).
3. **Optimistic Lock** → Prevents stale actions (database).

---

## 🏁 Race Condition #5: Connection Pool Exhaustion

### The Problem
Under load (many users, frequent cron jobs), all database connections are in use.
New requests queue up → timeouts → 500 errors.

### The Fix: SQLAlchemy Pool Configuration

```python
# backend/database/session.py
from sqlalchemy import create_engine

engine = create_engine(
    DATABASE_URL,
    pool_size=10,           # Base number of connections
    max_overflow=5,         # Burst capacity (up to 15 total)
    pool_timeout=30,        # Wait 30s for a connection before error
    pool_recycle=1800,      # Recycle connections every 30 minutes
    pool_pre_ping=True,     # Test connections before using them
)
```

| Parameter | Value | Why |
|-----------|-------|-----|
| `pool_size` | 10 | Enough for 10 concurrent requests |
| `max_overflow` | 5 | Burst to 15 during peak (market open) |
| `pool_timeout` | 30 | Don't wait forever — fail fast |
| `pool_recycle` | 1800 | Neon closes idle connections after 5 min |
| `pool_pre_ping` | True | Avoid "connection already closed" errors |

---

## 🏁 Race Condition #6: The "Phantom Read" (Transaction Isolation)

### The Problem
Cron job reads: "Trade #101 is OPEN, current_price = $5.00".
Between the read and the write, user manually closes the trade.
Cron job writes: "Trade #101 unrealized_pnl = $50" → **Overwriting the closed status**.

### The Fix: Transaction Isolation Level

```python
# For critical operations, use SERIALIZABLE isolation
from sqlalchemy.orm import Session

with Session(engine, expire_on_commit=False) as session:
    session.connection(execution_options={
        "isolation_level": "REPEATABLE READ"
    })
    
    trade = session.query(PaperTrade).filter_by(id=101).first()
    
    if trade.status != 'OPEN':
        # Someone closed it while we were processing
        return
    
    trade.unrealized_pnl = calculate_pnl(trade)
    session.commit()  # Will fail if trade was modified by another transaction
```

| Isolation Level | Protection | Use Case |
|----------------|------------|----------|
| `READ COMMITTED` (Default) | No dirty reads | Normal queries |
| `REPEATABLE READ` | No phantom reads | Cron job updates |
| `SERIALIZABLE` | Full isolation | Financial transactions (rare) |

---

## 📋 Summary: The Defense Matrix

| Race Condition | Scenario | Fix | Layer |
|---------------|----------|-----|-------|
| Double Click | User clicks "Place Trade" twice | Idempotency Key (UUID) | Frontend + DB |
| Cron Overlap | Two cron instances run simultaneously | Advisory Locks (`pg_try_advisory_lock`) | Database |
| Simultaneous Adjust | Two devices adjust SL at same time | Optimistic Locking (`version` column) | Database |
| Button Spam | User stress-clicks during crash | Button Disable + Debounce | Frontend |
| Pool Exhaustion | Too many concurrent connections | Pool Config (`pool_size=10`) | Infrastructure |
| Phantom Read | Cron overwrites user action | Transaction Isolation (`REPEATABLE READ`) | Database |

---

## 🗂️ Files Affected

```
backend/
├── database/
│   └── session.py            # Pool config + transaction helpers
├── services/
│   ├── trade_service.py      # Idempotency check on place_trade()
│   └── monitor_service.py    # Advisory lock wrapper on cron jobs
frontend/
└── js/
    ├── api.js                # Idempotency key generation
    └── components/
        └── portfolio.js      # Button disable/debounce
```
