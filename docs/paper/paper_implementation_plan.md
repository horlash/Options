# Paper Trade Monitoring System — Implementation Plan

> **Branch:** `feature/paper-trading` (off `feature/automated-trading`)  
> **Status:** Planning — Point-by-Point Review  
> **Last Updated:** Feb 18, 2026

---

## Overview

Build a production-grade paper trade monitoring system that records every trade with full context, monitors live P&L via ORATS, enforces bracket orders, and generates backtesting data to measure scanner + AI accuracy. Designed for multi-user, multi-device use with future Tradier live trading integration.

---

## Point 1: Database Persistence ✅ FINALIZED

> **Deep Dive:** [point_1_database_deepdive.md](./point_1_database_deepdive.md)

| Decision | Choice |
|----------|--------|
| Dev database | SQLite (local, zero setup) |
| Production database | **Neon PostgreSQL** (always free, 500MB, no pause, no lock-in) |
| Toggle | `DATABASE_URL` env variable |
| Data protection | Auto-backup + 6-hour PITR + `is_locked` on closed trades |
| MCP server | Deferred to Phase 7 (need 50+ trades first) |

---

## Point 2: Polling Frequency & Shared Price Cache 🔲 PENDING

**Current Recommendation:** 60-sec auto-poll while Portfolio tab active + manual refresh. Server-side batch polling (1 ORATS call per unique ticker across all users).

**Deep Dive:** TBD

---

## Point 3: UI Location — Portfolio Tab Upgrade 🔲 PENDING

**Current Recommendation:** Upgrade existing Portfolio tab with DB-backed real data, responsive layout, last-updated timestamp.

**Deep Dive:** TBD

---

## Point 4: SL/TP Bracket Enforcement 🔲 PENDING

**Current Recommendation:** Auto-close + toast alert + 1-click undo (60-sec window). Server-side enforcement for when user is offline.

**Deep Dive:** TBD

---

## Point 5: Market Hours & Bookend Snapshots 🔲 PENDING

**Current Recommendation:** Poll during 9:30-4:00 ET only, plus pre-market (9:25 AM) and post-close (4:05 PM) snapshots.

**Deep Dive:** TBD

---

## Point 6: Backtesting Data Model 🔲 PENDING

**Current Recommendation:** Full context at entry (card score, AI score, Greeks, strategy) + outcome at close (realized P&L, hold duration, close reason, override count).

**Deep Dive:** TBD

---

## Point 7: Multi-User Data Isolation 🔲 PENDING

**Current Recommendation:** `username` column on every trade table, `@require_user` decorator, query-level enforcement.

**Deep Dive:** TBD

---

## Point 8: Multi-Device Sync 🔲 PENDING

**Current Recommendation:** Optimistic locking (version column) to prevent double-close race conditions.

**Deep Dive:** TBD

---

## Point 9: Tradier Integration Architecture 🔲 PENDING

**Current Recommendation:** `BrokerInterface` abstraction — `PaperBroker` (local) → `TradierBroker(sandbox)` → `TradierBroker(live)`.

**Deep Dive:** TBD

---

## Point 10: Concurrency & Race Conditions 🔲 PENDING

**Current Recommendation:** Idempotency keys for duplicate prevention, transaction wrapping, optimistic locking.

**Deep Dive:** TBD

---

## Point 11: Position Lifecycle Management 🔲 PENDING

**Current Recommendation:** Full state machine (OPEN → SL_HIT/TP_HIT/MANUAL_CLOSE/EXPIRED_OTM/EXPIRED_ITM), expiry handling, daily pre-market health check.

**Deep Dive:** TBD

---

## Point 12: Analytics & Performance Reporting 🔲 PENDING

**Current Recommendation:** Win rate, profit factor, AI accuracy, segmented analysis by strategy/score/delta. Trade History sub-tab.

**Deep Dive:** TBD

---

## Implementation Phases (After All Points Approved)

| Phase | What | Status |
|-------|------|--------|
| Phase 1 | DB + Trade Placement | 🔲 |
| Phase 2 | Portfolio Display | 🔲 |
| Phase 3 | Price Monitoring | 🔲 |
| Phase 4 | Bracket Enforcement | 🔲 |
| Phase 5 | Analytics Dashboard | 🔲 |
| Phase 6 | Tradier Abstraction | 🔲 |
| Phase 7 | MCP Knowledge Server | 🔲 |
