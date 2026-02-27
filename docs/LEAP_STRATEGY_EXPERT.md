# Expert LEAP Strategy (Institutional Grade)

This document outlines the "Hedge Fund in a Box" logic used in the Expert Options Scanner.

## Core Philosophy
We do not just look for "cheap" options. We look for **High Quality Businesses** that are in an **Established Uptrend**, where **Smart Money** is already positioning for a move.

---

## Phase 1: The Quality Moat (Fundamental Filter)
*   **Goal:** Eliminate "Junk" companies that could go bankrupt or stagnate.
*   **Logic (Finnhub):**
    *   **ROE (Return on Equity):** Must be **> 15%**. (Efficiency)
    *   **Gross Margin:** Must be **> 40%**. (Pricing Power/Moat)
*   **Why:** We are holding for 1+ year. We only want to own the "House," not the "Player."
*   **Exception:** Some "Growth" stocks might fail this but pass via high-conviction overrides (manual only).

## Phase 2: Trend Alignment (Multi-Timeframe Analysis)
*   **Goal:** "Don't Fight the Tide." Ensure the long-term trend is up.
*   **Logic (ORATS Price History):**
    *   **Monthly Chart:** Price must be **> 20-Month SMA**. (The Tide)
    *   **Weekly Chart:** Price must be **> 50-Week SMA**. (The Wave)
*   **Why:** Buying LEAPS in a downtrend ("Catching a falling knife") is the #1 capital destroyer. We wait for the turn.

## Phase 3: Volatility Skew (Smart Money Sentiment)
*   **Goal:** Detect if institutions are aggressively buying Calls.
*   **Logic:**
    *   Compare Implied Volatility (IV) of OTM Calls vs OTM Puts (at same Delta).
    *   **Formula:** `Skew = (Call IV - Put IV) / ATM IV`
    *   **Signal:**
        *   **Positive (> 0%):** Bullish. Market pays more for upside.
        *   **Negative (< -10%):** Bearish. Market pays more for downside protection (Hedging).

## Phase 4: Stock Replacement (80 Delta)
*   **Goal:** Leverage without the "Binary Risk" of OTM options.
*   **Logic:**
    *   **Target:** Deep In-The-Money (ITM) Calls with **Delta >= 0.80**.
    *   **Leverage Ratio:** `Stock Price / Premium`. Target > 2x.
    *   **Safety:** Break-even price should be < 5% above current price.
*   **Why:** You control 100 shares for ~25% of the cash. If the stock goes up $10, your option goes up ~$8. If it crashes, you lose less than owning shares.

## Phase 5: The Core Engine (Foundational Logic)
Once a ticker passes the "Expert Filters" (Phases 1-3), specific options are analyzed using this core logic:

*   **1. Selection Criteria:**
    *   **Expiration:** Must be > 240 Days (8+ Months).
    *   **Delta:** Must be **> 0.15** (Avoid "Lotto Tickets").
    *   **Liquidity:**
        *   Open Interest > 10.
        *   Volume check (prefer higher volume).
        *   Liquidity Score calculated (Open Interest weighted 70%).

*   **2. Profit Calculation:**
    *   **Conservative Model:** We do NOT assume the stock goes to the moon.
    *   **Call Formula:** Target Price = `Strike + (Strike - Current) * 0.5`. (Assume it moves halfway past the strike).
    *   **Min Threshold:** Opportunity must show **> 15% ROI** based on this conservative model.

*   **3. Scoring System (The Final Rank):**
    Opportunities are ranked 0-100 based on weighted factors:
    *   **Technical Trend:** 35% (Is the chart perfect?)
    *   **Profit Potential:** 20% (Is the math good?)
    *   **Sentiment:** 20% (Is the news good?)
    *   **Skew:** 15% (Are institutions buying?)
    *   **Liquidity:** 10% (Can we exit easily?)

---

## Data Architecture
*   **Primary:** ORATS API (Price History, Real-Time Quotes, Options Chains).
*   **Quality/News:** Finnhub API (Financial Metrics, Sentiment).
*   **Screening:** FMP API (Sector, Market Cap, Volume).

## Risk Management (Hard Rules)
*   **Earnings:** Warn if Earnings Date < Expiry (though less relevant for 1yr LEAPS).
*   **Liquidity:** Spread < 25%.
*   **Capital:** "Stock Replacement" trades allow higher allocation (up to $25k) due to lower risk profile.
