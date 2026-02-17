# Strategic Analysis: LEAPS vs. Weeklies 📊

**Date:** January 29, 2026
**Context:** Deep dive into how the Algorithm and Recommendations apply differently to Short-Term (Weekly) vs Long-Term (LEAP) strategies.

---

## 1. The Profit Balance Dilemma (Detailed Analysis)

**The Core Conflict:**
The current algorithm normalizes scores based on a **200% Profit Target**.
*   **Formula:** `Score = (Profit Potential / 200) * 100` (Capped at 100).
*   **Result:** It treats a trade with 15% potential as "Low Quality" (Score: 7.5/100), largely ignoring the probability of success.

### 🟢 WEEKLY Options Strategy (Short Term)
**User Target:** Steady **15%** gains.

*   **Current State (20% Weight):**
    *   **The Math:** A 15% gain contributes only **1.5 points** to the total score.
    *   **The Problem:** To get a high score, the scanner forces you into OTM options that promise 100%+ gains (Gamma Plays). These are binary "Win/Loss" events.
    *   **Expert Verdict:** **CRITICAL to lower weight.** For Weeklies, *Precision* matters more than *Potential*. A 15% gain compounded weekly is massive. You want the algorithm to rank based on **Momentum (Technicals)** and **Catalysts (News)**, not Payoff.

*   **Recommendation:** Use **separate scoring logic** for Weeklies.
    *   **Normalize at 50%:** Max score reached at 50% profit.
    *   **Badge to Watch:** 📈 **Gamma Squeeze** (Price > Call Wall).

### 🔵 LEAP Options Strategy (Long Term)
**User Target:** Steady **50%** gains.

*   **Current State (20% Weight):**
    *   **The Math:** A 50% gain contributes **5 points** to the total score.
    *   **The Problem:** Deep OTM LEAPS (e.g., $1000 Strike on NVDA) show 500% potential and dominate the rankings.
    *   **Expert Verdict:** **Safety First.** A LEAP is an investment. You want **Stock Replacement** (Delta > 80). These naturally have lower ROI % (because they are expensive), but they behave like the stock.
    *   **The "Trap":** Buying OTM LEAPS is buying "Time Premium". Theta (decay) works against you every single day. Buying ITM LEAPS means theta hurts you less.

*   **Recommendation:**
    *   **Score Penalty for OTM:** If Delta < 0.60, penalize the score.
    *   **Badge to Watch:** 🛡️ **Stock Replacement** (Delta > 0.80).

### 🔴 0DTE Strategy (Indices: SPX, NDX)
**User Target:** Scalping **10-30%** gains (High Frequency).

*   **Risk Profile:** Extreme. Lives in "Gamma Land".
*   **The Math:** A 0DTE option can move 50% in 5 minutes. Traditional scoring breaks here.
*   **The Key:** You are trading **Gamma** and **Flow**, not Fundamentals.
*   **Recommendation:**
    *   **Ignore Fundamentals:** P/E Ratio does not matter for 0DTE.
    *   **Focus on GEX:** Is price approaching a "Gamma Wall"?
    *   **Focus on VWAP:** Is price above Intraday VWAP?
    *   **Badges to Watch:** 🌊 **Gamma Wall**, ⚡ **0DTE Liquidity**.

---

## 2. Do the Other Recommendations Apply to Both?

### A. AI Reasoning (Perplexity) 🧠
*   **WEEKLIES:** **Extreme Importance.**
    *   *Why?* A Weekly trade lives or dies by *Binary Events* (Earnings, FDA, Fed, geopolitical news).
    *   *Role:* "Scan strictly for events in the next 5 days." If there is a Fed meeting tomorrow, the AI must flag "HIGH RISK".
*   **LEAPS:** **Moderate Importance.**
    *   *Why?* A LEAP can survive a bad news cycle.
    *   *Role:* "Verify the Macro Thesis." (e.g., "Is the AI sector actually crashing, or is this just noise?").

### B. MTA Strictness (Multi-Timeframe Analysis) 📉
*   **WEEKLIES:** **Must be STRICT.**
    *   *Why?* You do not have time on your side. If you buy a Weekly Call when the Daily Trend is down (hoping for a bounce), you will likely lose 50% of value in one day.
    *   *Rule:* Weekly Trade requires **Daily + Hourly** alignment.
*   **LEAPS:** **Can be LENIENT (Scored).**
    *   *Why?* You *want* to buy dips. If the Monthly Trend is Up, but Daily is Down, that is a **Discount Entry** for a LEAP.
    *   *Rule:* Strict Rejection here is bad. It blocks you from buying the dip.

### C. 0DTE Support ⚡
*   **Logic:** Requires **Intraday Data** (1-minute candles).
    *   *Backend:* Must query intraday data (if available via ORATS/Tradier).
    *   *AI Analysis:* "Check for FOMC/Fed Speakers today." (Macro is King).

---

## 3. The "Badge" Guide for Traders 🏷️

Here is how to interpret badges for each strategy to guide your decision-making.

| Badge | Strategy | Meaning | Expert Advice |
| :--- | :--- | :--- | :--- |
| 🔥 **High Conviction** | **BOTH** | The "Perfect Storm". Techs, Sentiment, and Skew all align. | **Size Up.** This is your "Base Hit" trade. 80%+ Probability. |
| 🛡️ **Stock Replacement** | **LEAPS** | Deep ITM (Delta > 0.80). | **The "Safe" Play.** Use this instead of buying shares. Low Theta decay. Perfect for your 50% target. |
| ⚡ **Smart Money** | **WEEKLIES** | Unusual Institutional Flow detection. | **Follow the Whale.** Someone knows something. Good for short-term speculative plays. |
| 📈 **Momentum / Gamma** | **WEEKLIES** | ADX High or Approaching Gamma Wall. | **Ride the Wave.** The stock is moving FAST. Enter/Exit quickly. Do not hold overnight if momentum fades. |
| ⚠️ **Earnings Risk** | **BOTH** | Earnings event imminent. | **WEEKLIES:** **AVOID** (Gambling). <br>**LEAPS:** **WAIT** (Buy after the volatility crush). |
| 📉 **Reversal** | **LEAPS** | Trend mismatch (e.g., Monthly Up, Daily Down). | **Dip Buy Opportunity.** Only for LEAPS. Dangerous for Weeklies. |
| 🌊 **Gamma Wall** | **0DTE** | Price attacking a major GEX Level. | **Magnet Effect.** Price often gravitates here. Scalp the move to the wall. |
| ⚡ **0DTE Liquidity** | **0DTE** | Tight Spreads (< $0.10) on Index Options. | **Execution is Key.** Only trade if liquidity is perfect. |

---

## 4. Summary of Adjustments (No Code Changes Yet)

To meet your goals (**15% Weekly / 50% LEAP**), the "One Size Fits All" scoring is the bottleneck.

1.  **For Weeklies:** We need to value **Momentum** over generic Profit Potential. The target is *Speed*.
2.  **For LEAPS:** We need to value **Delta (Safety)** over Profit Potential. The target is *Resilience*.

**Expert Final Word:**
*   *"Don't let the 500% potential of a 'Lotto Ticket' distract you from the 15% certainty of a 'Rent Payer'. Lower the profit weight, trust the badges."*
