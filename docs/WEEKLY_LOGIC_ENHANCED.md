# Enhanced Weekly Strategy (Prop Trading Logic)

This document outlines the "Prop Desk" logic used in the Weekly Options Scanner.
Unlike LEAPS (which are slow), Weekly options are fast-moving. We prioritize **Momentum**, **Technical Strength**, and **Profit Potential**.

## Core Philosophy
We do not just gamble. We enter when **Technical Trend**, **Sentiment**, and **Money Flow** align to create a high-probability "Sniper Entry" (0-30 Days).

---

## Phase 1: Technical Trend (The Setup)
*   **Goal:** Only trade in the direction of the immediate momentum.
*   **Logic:**
    *   **Trend:**
        *   **Calls:** Price must be **> 50-Day SMA** (and ideally 20-Day).
        *   **Puts:** Price must be **< 50-Day SMA**.
    *   **RSI (Momentum):**
        *   **Calls:** RSI must be **< 70** (Avoid Overbought).
        *   **Puts:** RSI must be **> 30** (Avoid Oversold).
    *   **Relative Strength (RS):**
        *   Stock should outperform SPY (RS Score > -2.0) for Calls.

## Phase 2: Sentiment (The Catalyst)
*   **Goal:** Ensure news flow supports the trade.
*   **Logic (Finnhub):**
    *   **News Score:** Analyzes recent headlines and institutional sentiment.
    *   **Confirmation:** A high technical score can be invalidated by terrible news.

## Phase 3: Options Flow (The "Smart Money")
*   **Goal:** Follow the whales and avoid traps.
*   **Gamma Walls (GEX):**
    *   Avoid buying Calls right below a "Gamma Wall" (huge Open Interest strike), as price often pins there.
*   **Smart Money Flag:**
    *   **Volume > Open Interest:** Indicates aggressive *new* positioning (not just closing trades).
    *   **Bonus:** Awards **+10 Points** to the Opportunity Score.

## Phase 4: Selection & Scoring (The Engine)
Once a ticker passes Phases 1-3, we analyze specific options:

*   **1. Selection Criteria:**
    *   **Expiration:** 0 to 4 Weeks (Front Month).
    *   **Liquidity:** Open Interest > 10, Spread < 25%.
    *   **Delta:** > 0.15 (No far OTM lottos).

*   **2. Profit Calculation (ATR Model):**
    *   We use **Average True Range (ATR)** to project a realistic move.
    *   *Target Price* = `Current + (ATR * 1.5)`.
    *   **Threshold:** Must have **> 15% ROI** potential to be listed.
    *   **Momentum Override:** If Stocks have **High Sentiment (>75)** or **Smart Money**, this threshold drops to **0%** (Break-Even) to allow chasing news-driven breakouts.

*   **3. Scoring System (The Rank):**
    Opportunities are ranked 0-100 based on momentum-heavy weights:
    *   **Profit Potential:** 40% (Can we make money?)
    *   **Technical Score:** 30% (Is the chart good?)
    *   **Sentiment:** 20% (Is the news good?)
    *   **Smart Money:** +10 Points Bonus.
    *   **Earnings Risk:** -20 Points Penalty.

---

## Data Architecture
*   **Primary:** ORATS API (Price History, Real-Time Quotes, Options Chains).
*   **Sentiment:** Finnhub API.
*   **Screening:** FMP API (Sector, Volume).
