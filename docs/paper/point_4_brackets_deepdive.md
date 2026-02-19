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

## Implementation Detail

### Backend Logic (`MonitorService`)

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

### Frontend Logic (`portfolio.js`)

```javascript
function closePosition(ticker, id) {
    if (!confirm(`Are you sure you want to close ${ticker} at market price?`)) {
        return; // User cancelled
    }
    
    api.closeTrade(id).then(() => {
        playSound('click');
        showToast(`Closed ${ticker}`);
        refreshPortfolio();
    });
}
```

---

## Code Structure Changes

| File | Change |
|------|--------|
| `backend/services/monitor_service.py` | Add `manual_close_position()`, orphan guard in cron |
| `frontend/assets/sounds/` | Add `pop.mp3`, `cash_register.mp3`, `downer.mp3` |
| `frontend/js/utils/sound.js` | Helper to play sounds |
| `frontend/js/components/portfolio.js` | Add confirm modal logic |
