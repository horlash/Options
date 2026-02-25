# Point 8: Multi-Device Session Synchronization — Deep Dive

> **Status:** FINALIZED ✅
> **Date:** Feb 19, 2026  
> **Depends On:** Point 1 (Database) & Point 7 (Multi-User)

---

## 📱 The Problem: The "Zombie Trade"
**Scenario:**
1.  **Laptop:** You close a trade. Profit secured. 💰
2.  **Phone:** You are walking to lunch. The screen still shows the trade as `OPEN` (because it hasn't refreshed yet).
3.  **Panic:** You see it "open" and hit **Close** on your iPhone.

---

## 🔒 The Solution: Optimistic Locking

### How it works (The Technical Part)
1.  **The Ticket:** Every trade has a `version` number (e.g., v1).
2.  **The Laptop:** Closes the trade. DB updates `version` to **v2**.
3.  **The Phone:** Tries to close it, saying *"I am closing v1"*.
4.  **The DB:** Rejects it. *"v1 is old news. Current is v2."*
5.  **The Backend:** Returns `409 Conflict` to the phone app.

---

## 👁️ The User Experience (What You See)

**Q: "What does the user see?"**
**A: They do NOT see a crash or a "409" error.**

Here is the exact UI flow on the Phone:

1.  **Action:** You tap **[CLOSE POSITION]**.
2.  **Feedback:** The button turns into a **Spinner** ⏳.
3.  **Behind the Scenes:** The API sends the request. The Server returns `409 Conflict`.
4.  **The Intercept:** The JavaScript `api.js` layer catches the 409.
5.  **The Notification:**
    *   The Spinner stops.
    *   A **Toast Notification** (Yellow/Orange) slides down:
    *   ⚠️ *"Sync Alert: This trade was updated on another device."*
6.  **The Auto-Fix:**
    *   The app **automatically refreshes** the list 1 second later.
    *   The "OPEN" trade vanishes from the list.
    *   You see it in "HISTORY" as closed (by your laptop).

**Result:** The user realizes, "Oh, I already closed it," instead of "Why is the system broken?"

---

## 🏗️ Implementation Strategy

### Layer 1: Database Schema
**File:** `backend/database/models.py`
```python
class PaperTrade(Base):
    # ...
    version = Column(Integer, default=1, nullable=False)
```

### Layer 2: Backend Logic
**File:** `backend/services/trade_service.py`
```python
def close_trade(self, trade_id, user_version):
    # Atomic Update: Only works if version matches
    rows = db.query(PaperTrade).filter(
        id=trade_id, 
        version=user_version
    ).update({...})
    
    if rows == 0:
        # Check if trade even exists
        if db.query(PaperTrade).get(trade_id):
            # It exists, so it must be a version mismatch
            abort(409) 
```

### Layer 3: Frontend Handling
**File:** `frontend/js/api.js`
```javascript
async function closeTrade(id, currentVersion) {
    const res = await fetch(`/api/trades/${id}/close`, { ... });

    if (res.status === 409) {
        showToast("⚠️ State changed on another device. Refreshing...", "warning");
        await refreshPortfolio(); // <--- The Magic Fix
        return;
    }
}
```

---

## Final Decision
*   **Strategy:** Optimistic Locking.
*   **UX:** seamless Auto-Refresh on conflict.
*   **Complexity:** Low (Standard HTTP pattern).
