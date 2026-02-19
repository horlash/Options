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

## Implementation Detail

### 1. Open Positions Table (Inline Expansion)

| Column | Source |
|--------|--------|
| **Ticker** | `paper_trades.ticker` |
| **Type** | Call/Put (Green/Red) |
| **Strike** | `strike` |
| **Expiry** | `expiry` (e.g., "Feb 27") |
| **Entry** | `entry_price` |
| **Current** | `current_price` (Live) |
| **P&L** | `(current - entry) * qty * 100` |
| **SL / TP** | `sl_price` / `tp_price` |
| **Status** | 🟢 Winning / 🟡 Dipping / 🔴 At Risk |
| **Actions** | [Adjust SL] [Close] |

**Expanded Detail (Inline):**
- **Scanner Context:** Card Score, AI Score, AI Verdict, Strategy, Technical/Sentiment Scores
- **Greeks:** Delta, IV (at entry)
- **Progress:** Visual progress bar (Entry → Current → TP)
- **Metadata:** Tradier Order ID, Open Date

### 2. Trade History Table

| Column | Source |
|--------|--------|
| **Ticker** | `ticker` |
| **Type** | `option_type` |
| **Entry → Close** | `$4.20 → $5.10` |
| **P&L** | `realized_pnl` (`+$90 (+21%)`) |
| **Hold Time** | `hold_duration_h` ("2.4d") |
| **Close Reason** | 🎯 TP Hit / 🛑 SL Hit / ⏰ Expired |
| **AI Score** | `ai_score` |

### 3. Responsive Strategy

- **Desktop:** Full table
- **Mobile:** Card layout (vertical stack)
    - Open Position Card: Ticker/Type header, P&L prominent, Action buttons
    - History Card: Ticker/Type, Result, Close Reason badge

---

## Code Structure Changes

| File | Change |
|------|--------|
| `frontend/index.html` | Add sub-tab pills, refresh bar container |
| `frontend/js/components/portfolio.js` | **Major Refactor:**<br>- State management for active tab<br>- Fetch logic for `/api/trades?status=OPEN` vs `CLOSED`<br>- Inline row expansion logic<br>- Auto-refresh wiring |
| `frontend/css/index.css` | Styles for sub-tabs, tables, expanded rows, mobile cards |
| `backend/api/routes.py` | Add `get_trades(status)`, `export_trades(format)` |
