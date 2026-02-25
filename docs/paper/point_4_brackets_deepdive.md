# Point 4: SL/TP Bracket Enforcement — FINALIZED ✅

> **Status:** Approved | **Date:** Feb 18, 2026  
> **Depends On:** Point 2 ✅

---

## Final Decisions

| Decision | Choice |
|----------|--------|
| **Execution** | **Tradier OCO** (Server-side brackets) |
| **Manual Close** | **Immediate Cleanup** (Backend fires cancel commands instantly) |
| **Confirm Modal** | **Mandatory** ("Are you sure you want to close NVDA?") |
| **Sound Effects** | **Yes** (Profit = Cha-ching 💰, Loss = Downer 📉) |
| **Undo Button** | **No** (Impossible once filled) |

---

## 🛡️ Orphan Guard Strategy

**The Risk:** User manually closes a position (sells to open market), but the OCO bracket orders (SL/TP) remain open. If price drops, Tradier might "sell short" or error out.

**The Fix:**
1. **Immediate:** When `POST /api/trades/<id>/close` is called:
   - Server places Market Sell order.
   - Server *immediately* sends `cancel_order(sl_id)` and `cancel_order(tp_id)`.
2. **Cron Backup:** Every 60s, `MonitorService` checks:
   - "Is position closed (`qty=0`) but SL/TP orders are `open`?"
   - If yes → Cancel them.

---

## 🔊 Sound Effects

| Event | Sound | Status |
|-------|-------|--------|
| **Trade Filled** | `pop.mp3` | 🟢 OPEN |
| **TP Hit** | `cash_register.mp3` | 🎯 WIN |
| **SL Hit** | `downer.mp3` | 🛑 LOSS |
| **Manual Close** | `click.mp3` | 🔵 CLOSED |

---

## The 4 Scenarios

### Scenario A: Clean Bracket Hit (The Happy Path)
- **Action:** Price hits TP ($6.30).
- **Tradier:** Fills TP order, cancels SL order automatically (OCO).
- **System:** Cron detects fill, updates DB to `TP_HIT`, plays "Cha-ching" sound.

### Scenario B: User Manual Override (The "Panic Close")
- **Action:** User clicks "Close" in UI.
- **Risk:** The SL/TP bracket orders might remain open at Tradier.
- **Solution:**
  1. Backend places Market Sell order.
  2. Backend **IMMEDIATELY** sends `cancel_order` for the orphaned SL/TP legs.
  3. **Orphan Guard:** Cron double-checks every 60s for any missed orphans.

### Scenario C: "Adjust SL" (Modify Stop Loss)
*   **Context:** You own the option (Entry Price: $5.00). You want to move your SL up to $5.50 to lock in profit.
*   **Action:** User changes SL to $5.50.
*   **Logic:**
    1.  **Cancel** the existing OCO group (Cancels the old SL at $4.00 and old TP at $8.00).
    2.  **Place New** OCO group (Sell to Close):
        *   **Stop:** New price $5.50.
        *   **Limit:** Original price $8.00.
*   **Result:** You still own the same option at the same original entry price. Only your *exit instructions* have changed.

### Scenario D: "Adjust TP" (Modify Take Profit)
*   **Context:** You own the option. You want to aim higher (move TP from $8.00 to $10.00).
*   **Action:** User changes TP to $10.00.
*   **Logic:**
    1.  **Cancel** the existing OCO group.
    2.  **Place New** OCO group (Sell to Close):
        *   **Stop:** Original price $4.00.
        *   **Limit:** New price $10.00.
*   **Result:** Seamless update of exit target.

---

## Detailed Implementation Steps

### Step 4.1: Update `MonitorService`
- **File:** `backend/services/monitor_service.py`
- **Task:** Implement `manual_close_position(trade_id)`:
  ```python
  def manual_close_position(self, trade_id):
      trade = self.db.query(PaperTrade).get(trade_id)
      
      # 1. Place Market Sell
      fill = self.tradier.place_order(..., side='sell', type='market')
      
      # 2. IMMEDIATE CLEANUP
      if trade.tradier_sl_order_id:
          self.tradier.cancel_order(trade.tradier_sl_order_id)
      if trade.tradier_tp_order_id:
          self.tradier.cancel_order(trade.tradier_tp_order_id)
          
      # 3. Update DB
      trade.status = 'MANUAL_CLOSE'
      trade.close_price = fill['price']
      return trade
  ```
- **Task:** Add **Orphan Guard** to `sync_tradier_orders` (60s cron):
  - Check for closed positions with open bracket orders → Cancel them.

### Step 4.2: Frontend Confirmation & Sounds
- **Assets:** Add `pop.mp3`, `cash_register.mp3`, `downer.mp3` to `frontend/assets/sounds/`.
- **File:** `frontend/js/utils/sound.js` — Create helper to play sounds.
- **File:** `frontend/js/components/portfolio.js` — Add `confirm()` check to "Close Position" button:
  ```javascript
  function closePosition(ticker, id) {
      if (!confirm(`Are you sure you want to close ${ticker} at market price?`)) {
          return;
      }
      api.closeTrade(id).then(() => {
          playSound('click');
          showToast(`Closed ${ticker}`);
          refreshPortfolio();
      });
  }
  ```

### Step 4.3: Backend "Adjust SL/TP" Endpoint
- **File:** `backend/app.py`
- **Task:** Add `POST /api/trades/<id>/adjust` endpoint:
  - Accepts `new_sl` OR `new_tp`.
  - Cancels existing OCO group.
  - Places new OCO group with updated values.
  - Updates DB with new order IDs.
  - **IMPORTANT:** Logic must ensure `side='sell'` and `class='oto'` (or equivalent) so it acts on the *existing* position, not opening a new one.

---

## Code Structure Changes

| File | Change |
|------|--------|
| `backend/services/monitor_service.py` | Add `manual_close_position()`, orphan guard in cron |
| `frontend/assets/sounds/` | Add `pop.mp3`, `cash_register.mp3`, `downer.mp3` |
| `frontend/js/utils/sound.js` | Helper to play sounds |
| `frontend/js/components/portfolio.js` | Add confirm modal logic |
| `backend/api/routes.py` | Add `/adjust` endpoint for Scenario C & D |
