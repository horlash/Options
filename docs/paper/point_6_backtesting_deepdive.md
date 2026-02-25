# Point 6: Backtesting Data Model & Schema — FINALIZED ✅

> **Status:** Approved | **Date:** Feb 19, 2026  
> **Depends On:** Point 1 (Database)

---

## Final Decisions

| Decision | Choice |
|----------|--------|
| **Signals** | **Multi-Timeframe** (1m, 5m, 1h, Daily) snapshots |
| **Market Context** | **Regime Aware** (SPY, VIX, Sector Correlations) |
| **Liquidity** | **Order Book State** (Bid/Ask Spread + Greeks) |
| **AI Logic** | **Full Reasoning Log** (Prompt + Output + Confidence) |
| **Targets** | **MFE/MAE/PnL** (Calculated post-trade for ML labeling) |

---

## 🎯 The Goal: "Super-Resolution" Training Data
We are not just logging trades; we are building a **Time Capsule**.
When we train our future AI Agent, it needs to be able to "replay" the exact market conditions of Feb 19, 2026, to see *why* a trade worked or failed.

## 🧱 The Data Architecture

We will implement a **"Context-Rich" Schema** using PostgreSQL `JSONB` flexibility.
This ensures we capture high-dimensional data without needing 500 columns.

### 1. `signals_snapshot` (The "Micro" View)
Captures technicals across **multiple timeframes** to detect alignment (or divergence).

```json
{
  "1m": { "rsi": 75, "macd_hist": 0.02, "ema_9_21_cross": "bullish" },
  "5m": { "rsi": 60, "macd_hist": 0.15, "ema_9_21_cross": "bullish" },
  "15m": { "rsi": 55, "squeeze": "firing" },
  "1h": { "trend": "neutral" },
  "daily": { "trend": "bullish", "dist_from_200sma": 5.2 }
}
```
*   **Why:** A "Buy" signal on the 1m chart might be a "Trap" if the Daily chart is hitting resistance. The AI needs to learn this relationship.

### 2. `market_regime` (The "Macro" View)
Captures the broader market tide. "A rising tide lifts all boats."

```json
{
  "spy": { "price": 502.50, "pct_change": -0.45, "vix": 18.2 },
  "sector": { "ticker": "XLK", "pct_change": -1.2, "correlation_30d": 0.85 },
  "market_internals": { "ad_line": "declining", "put_call_ratio": 1.15 }
}
```
*   **Why:** Buying a tech dip when `XLK` (Tech Sector) is crashing -1.2% is dangerous. The AI must learn to check the sector health.

### 3. `order_book_state` (Liquidity & Greeks)
Captures the execution environment.

```json
{
  "bid": 4.50,
  "ask": 4.60,
  "spread_pct": 2.1,
  "volume": 520,
  "open_interest": 12000,
  "greeks": {
    "delta": 0.35,
    "gamma": 0.04,
    "theta": -0.08,
    "vega": 0.12,
    "iv": 45.5
  }
}
```
*   **Why:** High spreads kill short-term strategies. High Theta kills waiting strategies. The AI needs to see these costs.

### 4. `ai_reasoning_log` (The "Black Box")
Captures the LLM's internal monologue.

```json
{
  "model": "gemini-2.0-flash",
  "prompt_version": "v4_aggressive",
  "confidence_score": 8.5/10,
  "bull_case": "Strong gap up above 200 SMA...",
  "bear_case": "Approaching resistance at $150...",
  "decision_logic": "risk_reward_ratio_favorable"
}
```

---

## 🧪 Target Variables (Labels for ML)

To act as a "Supervisor," we need to calculate **Forward-Looking Targets** after the trade closes (or during nightly cleanup).

*   `target_pnl_15m`: P&L 15 minutes after entry.
*   `target_pnl_1h`: P&L 1 hour after entry.
*   `target_mae_pct`: Maximum Adverse Excursion (Risk/Drawdown).
*   `target_mfe_pct`: Maximum Favorable Excursion (Potential Profit).

**Training Query Example:**
> "Find all trades where `signals_snapshot->5m->rsi > 70` AND `profit_1h < -10%`. What was the `market_regime->vix`?"

---

## Detailed Implementation Steps

### Step 6.1: Database Schema Overhaul
- **File:** `backend/database/models.py`
- **Task:** Add `JSONB` columns to `PaperTrade` (Postgres only).

```python
from sqlalchemy.dialects.postgresql import JSONB

class PaperTrade(Base):
    # ... existing fields ...
    
    # Context (Inputs - Captured at Entry)
    signals_snapshot = Column(JSONB)   # Multi-timeframe technicals
    market_regime    = Column(JSONB)   # SPY, VIX, Sector
    order_book_state = Column(JSONB)   # Bid/Ask, Greeks, Liquidity
    ai_reasoning_log = Column(JSONB)   # LLM Inputs/Outputs
    
    # Targets (Outputs - Calculated Post-Close)
    target_pnl_15m   = Column(Float)
    target_pnl_1h    = Column(Float)
    target_mfe_pct   = Column(Float)   # Max potential profit %
    target_mae_pct   = Column(Float)   # Max risk (pain) %
```

### Step 6.2: "Context Collector" Service
- **File:** `backend/services/context_service.py`
- **Task:** Implement service that runs *at the moment of entry*:
  1.  **get_multi_timeframe_signals(ticker):** Queries the scanner for 1m/5m/1h/D data.
  2.  **get_market_context():** Fetches SPY/VIX and the ticker's Sector ETF (e.g., NVDA -> XLK).
  3.  **get_greeks(option_symbol):** Fetches Delta/Gamma/Theta from Tradier/ORATS.

### Step 6.3: "Forensic Analyst" Job (Nightly)
- **Task:** dedicated cron job to calculate `target_` variables for closed trades.
  - Queries minute-level price history for the day.
  - Computes MFE/MAE relative to entry price.
  - Updates the `PaperTrade` record.
