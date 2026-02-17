# Expert Trader Recommendations 🧠

**Date:** January 29, 2026
**Context:** Strategic review of LEAP Options Scanner Algorithm.

---

## 1. The Profit Balance Dilemma
**Question:** Keep current High-Risk weighting (20% Profit) or move to Safer Spec (5%)?

### Expert Verdict: **Move to Safer Spec (5-10% Max)**

#### Analysis
The current 20% weight creates a **"Lottery Ticket Bias"**.
*   **The Math:** To get a "Profit Potential" > 500% (which scores high currently), the option usually needs to be **Deep OTM** or have very short expiry.
*   **The Risk:** Deep OTM LEAPS have a low **Delta** (probability of expiring ITM). You might win big once, but you will bleed premium on the other 9 trades.
*   **The Pro's Way:** Professionals trade **Delta** and **Trend**. If a stock moves 20%, a slightly ITM or ATM LEAP makes excellent returns with 80%+ probability. It doesn't need to yield 1000% to be a "good trade".

#### Pros & Cons
| Option | Pros | Cons |
| :--- | :--- | :--- |
| **Current (20% Weight)** | Surfaces "Home Run" trades that can make a year's profit in one go. Good for tiny accounts looking to gamble. | **High Mortality Rate.** The scanner will constantly recommend low-probability OTM options. Misses steady "base hits". |
| **Spec (5% Weight)** | Prioritizes **Trend Quality** and **Safety**. Surfaces trades you can sleep on. | Results look "boring" (e.g., "Only 80% potential return"). |

**Recommendation:** Shift to **5% Weight**. Let the "High Conviction" badge handle the excitement, but let the *Core Score* reflect **Safety**.

---

## 2. AI Provider Selection
**Question:** Use Perplexity (as in Spec) or OpenAI/Claude?
**Status:** Perplexity Key Provided (`pplx...`).

### Expert Verdict: **Stick with Perplexity (Critical)**

#### Analysis
For a **Trading Scanner**, the primary role of AI is **Risk Management**, not "Essay Writing".
*   **Perplexity (Sonar-Reasoning):** Is essentially a "Search Engine with a Brain". It excels at: *"Are there FDA rulings for PFE this week?"* or *"Did NVDA CEO sell shares today?"*
*   **OpenAI/Claude:** Are "Thinking Engines". They are better at formatting and deep logic, but their "Live Web Search" is often slower or less exhaustive for niche financial news.

#### Pros & Cons
| Provider | Pros | Cons |
| :--- | :--- | :--- |
| **Perplexity** | **Real-Time Truth.** Best at finding "News Bombs" that kill trades. Low latency. | Less capable of complex "Thesis Generation" (writing long reports) compared to Claude 3.5. |
| **OpenAI/Claude** | Superior reasoning and formatting. Can write beautiful reports. | **Latency & Cutoff.** Web search is an add-on, not the core. Risk of hallucinations on dates/events is higher. |

**Recommendation:** Use **Perplexity**. In trading, *Information Freshness* > *Writing Style*.

---

## 3. MTA Strictness
**Question:** Strictly Reject misalignment (Current) or Score it lower (Spec)?

### Expert Verdict: **Hybrid Approach (Strict for "Top Picks", Scored for "Watchlist")**

#### Analysis
*   **Strict Mode (Reject):** The "Safe" approach. It prevents you from fighting the trend. E.g., If Monthly is Down, *never* buy a Daily bounce.
    *   *Problem:* You miss the "Bottom Fishing" or "Reversal" trades (which are the most profitable).
*   **Scored Mode (Soft):** Allows you to see Reversals, but gives them a lower score (e.g., 60/100 instead of 90/100).

#### Pros & Cons
| Logic | Pros | Cons |
| :--- | :--- | :--- |
| **Strict (Current)** | **Discipline.** Prevents "catching falling knives." High win rate. | **Late Entry.** You only buy when the trend is already obvious (and expensive). Misses early reversals. |
| **Scored (Spec)** | **Oppurtunity.** Catch trend changes early. | **False Positives.** Will recommend "traps" (dead cat bounces). |

**Recommendation:**
1.  **For the "High Conviction" Badge:** Keep it **Strict**. A "High Conviction" trade MUST have full alignment.
2.  **For the General Score:** Use **Scoring**. A lower score (60-70) correctly indicates "Risky Reversal", allowing the trader to decide. **Don't hide the data**, just label the risk.

---

## 4. Implementation Plan (Spec Compliance)

Since we have the **Perplexity Key**, we are ready for **Phase 3**.

### Roadmap Adjustment
1.  **API Key:** Store `pplx-bxbv...` in `.env` as `PERPLEXITY_API_KEY`.
2.  **MTA Upgrade:** Modify `hybrid_scanner_service.py` to stop returning `None` on MTA failure, and instead apply a `-20` point penalty.
3.  **Profit Tune:** In `options_analyzer.py`, lower Profit Weight to `0.05` and raise Technical Weight to `0.40`.

*Note: No changes made to system files yet, as requested.*
