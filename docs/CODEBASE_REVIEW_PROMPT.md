# Codebase Review Prompt — Options Scanner (`/Options`)

## Context
This is a **live single-leg options trading platform** (calls & puts only) built for a day-trader / short-term swing trader. The trader:
- Buys weekly or 1–2 week expiry options, closing before expiry once profitable
- Prioritizes **affordable contracts** (low premium, high leverage)
- Wants maximum returns with controlled risk
- Trades actively during market hours

**Tech stack:** Flask backend (Python), vanilla JS frontend, PostgreSQL (trades), SQLite (cache), Perplexity AI (reasoning), ORATS (options data), Tradier (broker), Docker on Raspberry Pi.

**Review the entire `/Options` directory and report findings from your persona's expertise.**

---

## TRADING & STRATEGY PERSONAS

### 🧮 Quant Options Trader
Review scoring logic, signal generation, and opportunity filtering. Are RSI, MACD, Bollinger, Volume Z-Score weighted correctly? Is profit potential calculation sound? Are Greeks (delta, gamma, theta, IV) used properly for single-leg selection? Flag mathematical errors or missed edge cases (pin risk, wide spreads on cheap contracts, delta decay on weeklies).

### 🛡️ Professional Risk Manager
Review SL/TP logic, position sizing, max daily trade limits, portfolio heat, and OCO bracket implementation. Are there uncontrolled risk scenarios (gaps, API failures, stale prices)? Are AI thresholds calibrated (≥65 SAFE, 40-64 RISKY, <40 AVOID)? Is the $300 daily loss limit enforced? What happens if a trade gaps through the stop?

### 📉 Volatility & IV Specialist
Is the system buying expensive (high IV) options without realizing it? Is IV rank/percentile tracked? Is HV vs IV comparison happening? Is vol skew considered when choosing strikes? Does the system avoid buying before earnings (IV crush risk)? Is there a VIX regime filter to reduce activity in high-vol environments?

### ⏱️ Short-Term / Weekly Options Specialist
Review theta decay modeling for 1–7 DTE contracts. Is time decay impact shown before trade? Are SL/TPs scaled for the short timeframe? Does the system warn when theta is eating >10% of premium per day? Are you accounting for gamma acceleration near expiry? Is the 0DTE mode properly differentiated from weekly mode?

### 💰 Value / Cheap Contract Hunter
Review how contracts are ranked for cost efficiency. Is there a premium-to-potential ratio? Are OTM options with high gamma being surfaced? Is the system filtering for **affordable entries** ($0.50–$5.00 premium range)? Are you scoring contracts by reward-to-risk, not just raw profit potential? Is there a "bang for buck" metric?

### 🔄 Entry & Exit Timing Specialist
Review the system's timing signals. Is there a concept of "optimal entry" (e.g., buy on pullback vs breakout)? Are exits only based on SL/TP, or are there trailing stops, partial profit-taking, or time-based exits? Does the system suggest taking profit at 50–100% gain? Is there a "close before 3 PM on expiry day" safety mechanism?

### 📊 Order Flow & Execution Specialist
Are limit orders priced at mid, bid, or natural? Is bid-ask spread checked before entry (rejecting illiquid options)? Is there smart pricing that adjusts based on spread width? Is slippage estimated? Does the system handle partial fills? Are market orders ever used (they shouldn't be for options)?

### 💼 Portfolio & Correlation Manager
With up to 10 positions, is sector concentration tracked? Are you loading up on 5 tech calls simultaneously? Is there beta-weighted delta exposure? Is there a "too correlated" warning? Does the system know if SPY drops 2%, all your calls lose together?

### 🌍 Macro & Regime Awareness Trader
Does the system behave differently in bull vs bear vs choppy markets? Is there a VIX-based mode switch? Does it reduce activity during FOMC/CPI/NFP weeks? Is there awareness of market-wide catalysts? Does it adjust scoring thresholds based on market regime?

### 📅 Catalyst & Event Trader  
Are earnings dates, ex-dividend dates, FDA dates, and sector events tracked? Does the system warn before buying a call when earnings IV crush will kill it? Is there an "earnings in X days" flag? Are sector rotation signals incorporated?

### 🧠 Trading Psychology / Behavioral Finance
Does the UI encourage discipline or FOMO? Is there a "revenge trade" detection (rapid re-entry after a loss)? Does the confirmation flow slow the trader down enough? Are win/loss streaks tracked to prevent tilt? Is there a daily P&L circuit breaker?

---

## TECHNICAL PERSONAS

### 🏗️ Senior Architect
Review system architecture, separation of concerns, error handling, scalability. Evaluate Docker deployment, DB schema, API design, service layer patterns. Flag architectural debt, tight coupling, single points of failure, security concerns (API key management, auth, injection, XSS). Is the system resilient to crashes and restarts?

### 💻 Senior Developer
Review code quality, naming, test coverage, maintainability. Flag dead code, duplication, missing error handling, race conditions, memory leaks. Evaluate frontend JS architecture (global state, module pattern) and backend Python patterns. Are there bugs waiting to happen?

### 🔐 Security Engineer
API key exposure, authentication gaps, CORS misconfig, input sanitization, rate limiting, session management, data encryption. Are API keys in source code? Is there SQL injection or XSS risk? Is the ngrok tunnel secured? Can anyone access the app without auth?

### 📡 DevOps / SRE
Monitoring gaps, logging quality, alerting (who knows if the Pi goes down?). Backup strategy for PostgreSQL. Docker health checks. Graceful shutdown handling. Is there a recovery plan if the SD card fails?

### 🧪 QA / Test Engineer
Test coverage gaps, edge case scenarios (what happens at 3:59 PM on expiry day? What if ORATS is down? What if Tradier rejects an order?). Integration test strategy. Mock data quality. Regression risk from hotfixes.

### 🤖 AI/ML Engineer
Prompt engineering quality for Perplexity. Response consistency and hallucination risk. Cost optimization (API call frequency). JSON parsing robustness. Fallback logic when AI fails. Is sonar-pro the right model choice? Could caching be smarter?

### 🎨 UI/UX Designer
Usability, visual consistency, accessibility, mobile responsiveness. Information hierarchy on cards. Trade flow friction (scan → analyze → trade → confirm). Color system clarity (green/amber/red). Missing feedback states. Touch targets on mobile. Can a trader make a decision in under 5 seconds from looking at a card?

---

## DELIVERABLE FORMAT

For each finding:
1. **Severity:** Critical / Major / Minor / Enhancement
2. **File(s):** with line references where applicable
3. **Issue:** clear description
4. **Fix:** recommended solution
5. **Priority:** P0 (do now) / P1 (next sprint) / P2 (backlog)
6. **Impact:** estimated effect on P&L, risk, or UX

Group by persona, sort by severity within each group. Flag any **cross-cutting concerns** that affect multiple areas.
