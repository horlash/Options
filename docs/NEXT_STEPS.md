# Future Roadmap & Next Steps

> **Status**: Backlog / On Hold
> **Last Updated**: 2026-02-16

---

## 1. Project "NewScanner" (Architecture Refactor)

**Objective**: Break the monolithic `HybridScannerService` into modular components.

**Proposed Structure**:
```
backend/
  scanner/
    universe_manager.py  # Loads tickers (ORATS, FMP)
    market_data.py       # Fetches prices/Greeks (Tradier, ORATS)
    strategy_engine.py   # Filters candidates (Technical + Fundamental)
    ranking_engine.py    # Scores opportunities
```

**Benefits**:
- Easier to add new strategies (e.g. Iron Condor).
- Cleaner testing (test just the ranking logic without mocking the whole world).

## 2. UI Polish & Mobile Experience

**Objective**: Make the frontend "Pro Trader" quality.

**Ideas**:
- **Mobile First**: CSS grid adjustments for phone screens.
- **TradingView Charts**: Integrate lightweight-charts for real interactive candles.
- **Dark Mode 2.0**: Higher contrast, better data density.
- **Live Connection Status**: Visual indicator if backend is polling.

## 3. Strategy Expansion

**Objective**: Move beyond simple Long Calls/Puts.

**Ideas**:
- **The Wheel**: Cash-Secured Puts → Covered Calls.
- **Credit Spreads**: Bull Put Spreads for high probabilities.
- **0DTE Snipering**: Specialized momentum logic for same-day expiries.
