# Index vs. Profit Logic (The "Two-Tier" System)
**Last Updated:** 2026-02-16
**Version:** NewScanner v2.0

## The Problem
Standard stock scanning logic fails for two major asset classes:
1.  **Indices (SPX, VIX):** They have no "Corporate Fundamentals" (ROE/Margin) and are often priced on Futures (breaking "Spot Price" profit math).
2.  **ETFs (SPY, QQQ):** They have no Corporate Fundamentals but *do* trade like stocks (Spot Price is accurate).

## The Solution: Two-Tier Exemptions

To safely scan these assets without letting "Junk" through, we use two separate exemption lists in `options_analyzer.py` and `hybrid_scanner_service.py`.

### Tier 1: Non-Corporate List (Fundamentals Exemption)
*   **Applies To:** Indices (`VIX, SPX, NDX`) AND ETFs (`SPY, QQQ, IWM`).
*   **Logic:**
    *   **Skip:** ROE Check (>15%) and Gross Margin Check (>40%).
    *   **Reason:** These metrics don't exist for baskets of stocks.
    *   **Result:** Prevents false failures in the "Quality Moat" phase.

### Tier 2: Pricing Anomaly List (Profit Math Exemption)
*   **Applies To:** **Indices ONLY** (`VIX, SPX, NDX`).
*   **Logic:**
    *   **Skip:** `Profit Potential > 15%` check.
    *   **Reason:** Index options are often cash-settled or based on Futures prices, which can diverge significantly from the Spot price. A standard "(Target - Strike) / Cost" calculation often shows 0% return for valid hedges.
    *   **Risk Mitigation:** We rely on **Technical Trend** and **Implied Volatility** warnings to ensure quality.

### Vital Distinction: SPY vs SPX
*   **SPY (ETF):** Is in Tier 1 (No ROE) but **NOT Tier 2**. We **DO** enforce profit math on SPY because it tracks the spot price 1:1. If an SPY option shows 0% profit, it is a bad trade.
*   **SPX (Index):** Is in **Both Tiers**. We trust the market pricing more than our calculator.
