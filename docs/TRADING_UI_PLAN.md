# Trading UI Plan — Frontend Design Document

> **Status**: Planning / Demo Complete
> **Demo File**: [TRADING_UI_DEMO.html](file:///c:/Users/olasu/.gemini/antigravity/Options/docs/TRADING_UI_DEMO.html)

---

## 1. Design Principles

- **Match existing UI**: Same dark mode, same glassmorphism cards, same fonts (Inter/Aptos)
- **Zero new pages**: Add tabs to the existing `index.html`, not new routes
- **3-click max**: Scan result → Review modal → Confirm trade
- **Color-coded everything**: Green = call/profit, Red = put/loss, Amber = warning

---

## 2. What's Changing in the Existing UI

### 2A. New Navigation Tabs

Currently the app has one view (scanner). We add **tabs** at the top:

| Tab | Icon | Content |
|-----|------|---------|
| **Scanner** | 🎯 | Existing scan results (unchanged) + new "Trade" button per card |
| **Portfolio** | 💼 | Open positions with live P&L + action buttons |
| **Risk** | 🛡️ | Portfolio heat, win rate, tilt status, weekly report |

### 2B. Header Stats Update

Current header shows `Watchlist` and `Opportunities` counts. Add:
- **Open Trades**: Number of active positions
- **Portfolio Heat**: Current heat % with color coding

---

## 3. Component Breakdown

### 3A. Trade Button (on each opportunity card)

Added to the **bottom of every scan result card**:

| Conviction Score | Button State | Visual |
|-----------------|-------------|--------|
| **≥ 80** | ✅ Enabled — green gradient (call) or red gradient (put) | `⚡ Trade This Setup` |
| **72 – 79** | ⚠️ Enabled with warning border | `⚡ Trade — ⚠️ Moderate Edge` |
| **< 72** | 🔒 Disabled — grey | `🔒 Watch Only — Score Below 72` |

Below the button: small text showing edge gate status.

> [!IMPORTANT]
> **Existing Features — 100% Preserved**
> - **All scan modes** work exactly as today: 0DTE, This Week, Next Week, Next 2 Weeks, LEAPS
> - **Smart Search**, **Sector Scan** (with subsector), **Watchlist**, and **Recent History** are untouched
> - **All badges** continue to display on cards: play type badges (⚡ Tactical, 🚀 Momentum, 💎 Value), earnings risk (⚠️ Earn), **and fundamental badges** (EPS Growth ↗, Analyst Buy ⭐, Smart Money 🏦, etc.)
> - The **Trade button** is the **only addition** to the existing card — appended below the badges
> - **No existing card content is removed or modified**

### 3B. Trade Setup Modal

Opens when clicking "Trade" on a scan result. Layout:

```
┌──────────────────────────────────────────┐
│  ⚡ Trade Setup                     [×]  │
├──────────────────────────────────────────┤
│  ┌──────────────────────────────────┐    │
│  │ NVDA  [BUY CALL]    Score: 82   │    │
│  └──────────────────────────────────┘    │
│                                          │
│  ENTRY                                   │
│  Strike: $150.00    Expiry: Mar 7 (18d)  │
│  Limit:  [-] $4.20 [+]   Qty: [-] 1 [+] │
│                                          │
│  BRACKET ORDERS (Auto-Attached)          │
│  SL (-25%): [-] $3.15 [+]               │
│  TP (+50%): [-] $6.30 [+]               │
│                                          │
│  ┌── RISK ANALYSIS ─────────────────┐    │
│  │ Total Cost:    $420.00            │    │
│  │ Max Loss:      -$105 (2.1%)  🟡  │    │
│  │ Target Profit: +$210 (+50%)  🟢  │    │
│  │ Risk:Reward:   1:2.0         ✅  │    │
│  │ Heat After:    5.2% → OK     ✅  │    │
│  └──────────────────────────────────┘    │
│                                          │
│  ✅ Buying power sufficient              │
│  ✅ Bid-Ask spread: 3.2% (healthy)       │
│  ✅ Open Interest: 2,450 (liquid)        │
│  ✅ No earnings within 5 days            │
│  ✅ Daily loss limit: $0 / $150          │
│  ✅ No duplicate NVDA position           │
│                                          │
│  ⚠️ YOU ARE ABOUT TO SPEND $420.00      │
│          Max Risk: $105.00               │
│                                          │
│  [  ✅ CONFIRM TRADE — BUY 1x NVDA  ]   │
│    Enter to Confirm  |  Esc to Cancel    │
└──────────────────────────────────────────┘
```

**Key UX Details**:
- `[-]` / `[+]` buttons adjust price by $0.05
- Quantity `[-]` / `[+]` adjusts by 1 contract
- Risk Analysis updates **live** as you change values
- Pre-trade checks are auto-validated (no user action)
- Big red warning text before the confirm button

### 3C. Portfolio Tab

Displays all open positions in a table:

| Column | Source | Interactive? |
|--------|--------|-------------|
| Ticker | Tradier positions API | Link to scan card |
| Type | Call/Put | Color-coded |
| Strike | From order data | — |
| Entry Price | From fill data | — |
| Current Price | Tradier quotes API | Live refresh |
| P&L | Calculated | Green/Red |
| SL / TP | From bracket orders | — |
| Status | Calculated from price vs SL/TP | 🟢🟡🔴 |
| Actions | — | Adjust SL, Adjust TP, Close |

**Portfolio Summary Cards** (top of tab):
- Account Value + All-Time %
- Today's P&L
- Open Positions (X of Y max)
- Cash Available (% in cash)

### 3D. Risk Dashboard Tab

Three metric cards + a weekly report:

| Card | Shows | Visual |
|------|-------|--------|
| **Portfolio Heat** | Current heat % + bar chart with 6% limit line | 🔥 |
| **Win Rate** | W/L ratio over last 25 trades + bar chart | 📊 |
| **Tilt Status** | Consecutive losses count + clear/warning/danger state | 🧠 |

**Weekly Report** (auto-generated Fridays):
- 8-metric grid: Trades, Win Rate, Avg Win, Avg Loss, Expectancy, Max Drawdown, Best Trade, Worst Trade

---

## 4. New Files Required

| File | Purpose |
|------|---------|
| `frontend/css/components/trading.css` | All styles for trade modal, portfolio, risk dashboard |
| `frontend/js/components/trade-modal.js` | Modal logic, risk calculations, API calls |
| `frontend/js/components/portfolio.js` | Position tracking, P&L calculation |
| `frontend/js/components/risk-dashboard.js` | Heat monitor, tilt tracker, weekly report |

---

## 5. Implementation Notes

- **No new HTML pages**: Add tab navigation to `index.html` + include new components
- **No new backend needed for demo**: First build the frontend connected to mock data, then wire to Tradier API
- **Feature branch**: All work on `feature/automated-trading`
- **CSS approach**: New component CSS file (`trading.css`), no changes to existing `styles.css`
