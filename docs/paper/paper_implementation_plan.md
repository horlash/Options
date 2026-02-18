# Paper Trade Monitoring — Implementation Plan

> **Branch:** `feature/paper-trading` (off `feature/automated-trading`)  
> **Status:** Planning — Point-by-Point Review  
> **Last Updated:** Feb 18, 2026

---

## Overview

Build a production-grade paper trade monitoring system using **Tradier** for order execution (sandbox for paper, production for live), **Neon PostgreSQL** for persistence, and **ORATS** for price snapshots.

---

# Point 1: Database Persistence ✅ FINALIZED

**Deep Dive:** [point_1_database_deepdive.md](./point_1_database_deepdive.md)

| Decision | Choice |
|----------|--------|
| Database | Neon PostgreSQL (prod) + SQLite (dev) |
| Toggle | `DATABASE_URL` env variable |

---

# Point 2: Polling & Price Cache ✅ FINALIZED

**Deep Dive:** [point_2_polling_deepdive.md](./point_2_polling_deepdive.md)

| Decision | Choice |
|----------|--------|
| Architecture | Tradier-first (tick-level SL/TP) |
| Polling | 60s cron (Tradier) + 40s (ORATS) + 15s (Frontend) |

---

# Point 3: UI Upgrade — Portfolio Tab ✅ FINALIZED

**Deep Dive:** [point_3_ui_deepdive.md](./point_3_ui_deepdive.md)

| Decision | Choice |
|----------|--------|
| Location | **Upgrade Existing Portfolio Tab** |
| Sub-Tabs | **Open Positions**, **Trade History**, **Performance** |
| Expansion | **Inline** (slide-down details) |
| Export | **JSON + CSV** |
| **Mandate** | **Visual Verification (Mockups) Required First** |

### Implementation Steps

**Step 3.1: Visual Verification (MOCKUPS FIRST)**
- [ ] Generate numbered UI mockups
- [ ] Present to user for review
- [ ] HOLD until approved

**Step 3.2: Code Structure Updates**
- Update `frontend/index.html` triggers, `frontend/css/index.css` styles

**Step 3.3: Refactor `portfolio.js`**
- Sub-tab logic, fetch real data, inline expansion, auto-refresh

**Step 3.4: Backend Support**
- `/api/trades/history` endpoint
- `/api/trades/export` endpoint

---

# Points 4-12: PENDING

## Point 4: SL/TP Bracket Enforcement 🔲
Simplified by Tradier. Sync and display results. Alert queue.

## Point 5: Market Hours & Bookend Snapshots 🔲
9:30-4:00 ET polling. Pre-market 9:25 AM, post-close 4:05 PM.

## Point 6: Backtesting Data Model 🔲
Full context at entry + outcome at close. Schema in Point 1.

## Point 7: Multi-User Data Isolation 🔲
`username` on every table, `@require_user` decorator.

## Point 8: Multi-Device Sync 🔲
Optimistic locking (`version` column), Tradier as source of truth.

## Point 9: Tradier Integration Architecture 🔲
`BrokerInterface` abstraction. Sandbox ↔ live URL swap.

## Point 10: Concurrency & Race Conditions 🔲
Idempotency keys, transactions, optimistic locking.

## Point 11: Position Lifecycle Management 🔲
OPEN → SL_HIT/TP_HIT/MANUAL_CLOSE/EXPIRED_OTM/EXPIRED_ITM.

## Point 12: Analytics & Performance Reporting 🔲
Win rate, profit factor, AI accuracy, segmented analysis.

---

## Implementation Phases

| Phase | What | Status |
|-------|------|--------|
| Phase 1 | DB Models + Trade Placement + Tradier Client | 🔲 |
| Phase 2 | Portfolio UI (Mockups → Code) | 🔲 |
| Phase 3 | Price Monitoring (APScheduler cron) | 🔲 |
| Phase 4 | Bracket Sync (Tradier order status) | 🔲 |
| Phase 5 | Analytics Dashboard | 🔲 |
| Phase 6 | Tradier Live Toggle | 🔲 |
| Phase 7 | MCP Knowledge Server | 🔲 |
