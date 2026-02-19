# Point 3: UI Location — Portfolio Tab Upgrade — FINALIZED ✅

> **Status:** Approved | **Date:** Feb 18, 2026  
> **Depends On:** Point 1 ✅, Point 2 ✅

---

## Final Decisions

| Decision | Choice |
|----------|--------|
| **UI Location** | **Upgrade Existing Portfolio Tab** (maintain current nav structure) |
| **Sub-Tabs** | 1. **Open Positions** (default)<br>2. **Trade History**<br>3. **Performance** (future) |
| **Row Expansion** | **Inline Expansion** (click row → details slide down) |
| **Export Format** | **JSON + CSV** (for programmatic analysis + Excel) |
| **Visual Verification** | **Mandatory:** Create number-labeled mockups for user review *before* writing code |

---

## 🏆 Architecture: The "Hub" Approach

The Portfolio tab becomes the central hub for all trade management, split into focused sub-tabs.

```
📊 Portfolio Tab
├── Refresh Bar [🔄 Refresh All] [Prices as of 1:42 PM ET 🟢] [Auto-refresh: ON]
│
├── Sub-Tab: Open Positions (default)
│   ├── Stat Cards Row (Value, P&L, Count, Cash)
│   └── Positions Table (Live monitoring, inline expansion)
│
├── Sub-Tab: Trade History
│   ├── Filter Bar (Wins, Losses, SL/TP Hit) + [📥 Export JSON/CSV]
│   └── Closed Trades Table (Results, hold time, close reason)
│
└── Sub-Tab: Performance (Point 12 — future)
    └── Analytics Dashboard (Win metrics, charts)
```

---

## 📸 Visual Verification Step (Mandatory)

**Before writing any implementation code:**
1. Generate **numbered mockups** (e.g., Mockup #1, #2, #3)
2. Present to user for review
3. Iterate until approved
4. **Only then** proceed to code

---

## Detailed Implementation Steps

### Step 3.1: Visual Verification (MOCKUPS FIRST)
- [ ] Generate numbered UI mockups (Tab view, Mobile view, etc.)
- [ ] Present to user for review
- [ ] **HOLD** until approved

### Step 3.2: Code Structure Updates
- **File:** `frontend/index.html` — Add sub-tab pills, refresh bar, history table container.
- **File:** `frontend/css/index.css` — Add styles for pills, badges, mobile cards, inline expansion.

### Step 3.3: Refactor `portfolio.js`
- Implement sub-tab switching logic (`currentTab` state: OPEN, HISTORY, PERFORMANCE).
- Fetch real data from `/api/trades?status=OPEN` and `/api/trades?status=CLOSED`.
- Implement `renderOpenPositions()` with inline expansion (slide-down details).
- Implement `renderTradeHistory()` with filtering (Wins, Losses, Expired).
- Wire up "Refresh All" and Auto-refresh toggle.

### Step 3.4: Add Backend Support
- **File:** `backend/api/routes.py`
- Add `GET /api/trades/history` endpoint (paginated or filtered).
- Add `GET /api/trades/export` endpoint (supports `?format=csv` and `?format=json`).

---

## Code Structure Changes

| File | Change |
|------|--------|
| `frontend/index.html` | Add sub-tab pills, refresh bar container |
| `frontend/js/components/portfolio.js` | **Major Refactor:** State management, fetch logic, inline expansion, auto-refresh |
| `frontend/css/index.css` | Styles for sub-tabs, tables, expanded rows, mobile cards |
| `backend/api/routes.py` | Add `get_trades(status)`, `export_trades(format)` |
