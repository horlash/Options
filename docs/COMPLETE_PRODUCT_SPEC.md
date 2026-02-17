COMPLETE PRODUCT SPECIFICATION



### Step 2: Deep Analysis (Backend Algo)
**System Process**:
1. Fetches data from multiple APIs (ORATS, Finnhub, FMP)
2. Runs multi-phase scoring algorithm (see Phase Logic below)
3. Identifies **PUT** and **CALL** opportunities
4. Applies badges: 🔥 High Conviction | ⚡ Smart Money | 📈 Momentum | 🛡️ Stock Replacement



---



#### ⚠️ Trading Concerns


**Problem 2: No Volatility Context**
```python
# Current: Sentiment score without volatility awareness
sentiment_score = 75  # "Bullish"

# Trader needs: Is this bullish sentiment already priced in?
if IV_percentile > 80:
    # High IV = market already expects big move
    # Bullish sentiment may not matter
```

**Problem 3: Missing Earnings Context**
- Earnings announcements cause 20-40% IV spikes
- Current implementation doesn't flag upcoming earnings
- **Critical for theta decay** and **gamma risk**

#### 💡 Recommended Improvements

1. **Add Earnings Awareness**
2. **Sentiment-IV Divergence Detection**
3. **Options-Specific NLP Keywords**

### 2. Quality Moat (Finnhub) - Fundamental Filtering

#### Current Implementation ✅
- ROE > 15%
- Gross Margin > 40%
- Binary pass/fail

#### ⚠️ Trading Concerns

**Problem 1: Static Thresholds**
- Same threshold for all sectors
- Tech companies: ROE = 25% (typical)
- Utility companies: ROE = 8% (typical)

**Problem 2: Missing Cash Flow**
- Free Cash Flow (FCF) - Can company sustain growth?
- Debt-to-Equity - Bankruptcy risk affects option value
- Current Ratio - Liquidity crisis = stock crash

**Problem 3: No Growth Rate**
- High ROE with **declining growth** = value trap
- Low ROE with **accelerating growth** = opportunity

#### 💡 Recommended Improvements

1. **Sector-Adjusted Thresholds**
2. **Add Cash Flow Metrics**
3. **Growth Momentum Score**

### 3. Missing: Liquidity Analysis ⚠️ CRITICAL

#### Current Gap
No bid-ask spread or open interest checks

#### Trader Impact
- Wide spreads = **slippage** on entry/exit
- Low open interest = **hard to exit** position
- No volume = **stuck** in losing trade

#### 💡 Recommended Addition
```python
class LiquidityAnalyzer:
    def check_option_liquidity(self, option_chain, strike, expiry):
        bid = option['bid']
        ask = option['ask']
        oi = option['openInterest']
        volume = option['volume']
        
        # Bid-Ask Spread Check
        spread_pct = (ask - bid) / ((ask + bid) / 2)
        
        if spread_pct > 0.10:
            return 'ILLIQUID'  # >10% spread = expensive
        
        if oi < 100:
            return 'LOW_LIQUIDITY'  # Hard to exit
        
        if volume < 20:
            return 'INACTIVE'  # No market interest
        
        return 'LIQUID'  # Safe to trade
```

**Recommended Thresholds**:
- **Bid-Ask Spread**: < 5% (ideal), < 10% (acceptable)
- **Open Interest**: > 500 (great), > 100 (minimum)
- **Daily Volume**: > 100 (active), > 20 (minimum)



### 5. Missing: Risk/Reward Ratio

#### Current Gap
- Shows "Profit Potential: 45%"
- But doesn't show **maximum loss**

#### 💡 Recommended Addition
Professional risk/reward analysis with 3:1, 2:1, 1:1 ratio classification

---


---

## 🧠 **PHASE 2: Expert Analysis - Multi-Timeframe & Advanced Indicators**

### 1. Multi-Timeframe Analysis (MTA)

**Purpose**: Analyze trend alignment across Daily/Weekly/Monthly timeframes

**Logic**:
1. **Resample** daily data to weekly (W-FRI) and monthly (ME) candles
2. **Analyze** each timeframe independently using EMA20/50 + Ichimoku Cloud
3. **Score** alignment:
   - Perfect Bullish Alignment (D+W+M): +30 points
   - Pullback Opportunity (Daily dip in Weekly uptrend): +10 points
   - Caution (Daily bounce in Monthly downtrend): -10 points
   - Bullish Continuation (D+W bullish): +20 points

**Cure**: Eliminates false signals from single-timeframe analysis

### 2. ADX Slope Analysis

**Purpose**: Detect trend acceleration vs. exhaustion

**Logic**:
1. Calculate ADX (14-period)
2. Measure slope: `current_ADX - previous_ADX`
3. Classify:
   - ADX > 25 + Slope > 0.5: "Strong trend accelerating" (+15 points)
   - ADX > 25 + Slope < -0.5: "Strong trend weakening" (-10 points)
   - ADX < 25: "Choppy market" (0 points)

**Cure**: Prevents buying into exhausted trends

### 3. Ichimoku Cloud with Future Twist

**Purpose**: Predictive cloud analysis

**Logic**:
1. Calculate standard Ichimoku (Conversion, Base, Span A/B)
2. **Simulate future cloud** 26 periods ahead
3. Detect "twist" (cloud color change)
4. Classify:
   - Above green cloud: "Bullish" (+10 points)
   - Below red cloud: "Bearish" (-10 points)
   - Inside cloud: "Turbulence" (0 points)
   - Twist detected: Warning flag

**Cure**: Provides early warning of trend reversals

---

## 🤖 **PHASE 3: AI Plan - Perplexity Reasoning Engine**

### Goal
Transform the scanner from a "Data Aggregator" into an "Intelligent Assistant"

### Core Components

#### 1. The Reasoning Engine
**Service**: `backend/app/services/reasoning_engine.py`
- **Input**: Complete JSON object from `scanner.py` (Tech Score, MTA, Greeks, etc.)
- **Provider**: **Perplexity API** (Model: `sonar-reasoning-pro`)
- **Function**:
  - Ingests scanner data + Performs *live web verification*
  - Example: "Scanner says Earnings in 3 days. Perplexity verifies exact date/time from web"
  - Generates "Trade Thesis" citing both internal data and external context

#### 2. The Logic (Prompt Engineering)
**Component**: `backend/app/core/prompts.py`
- **System Prompt**: "You are a Hedge Fund Options Strategist using a Bloomberg Terminal..."
- **Task**:
  - **Synthesize**: Combine MTA (Weekly Trend) with Liquidity (Open Interest)
  - **Verify**: Use online capabilities to check for "Black Swan" news
  - **Recommend**: Actionable advice with confidence score

#### 3. Scanner Integration
**Component**: `backend/app/services/scanner.py`
- Call `ReasoningEngine.analyze_opportunity(scan_result)` for top-tier setups
- **Fail-Safe**: If Perplexity times out, return standard "Algo Analysis"

### Why Perplexity?
Acts as a **Fact-Checker**:
> "The Algo detected a Bullish Trend, and Perplexity confirms no major negative headlines in the last hour disrupting this view."

---


---

## 🎨 **PHASE 5: Frontend Restoration**

### UI Components

#### 1. Ticker Search Component
**File**: `TickerSearch.tsx`
- Autocomplete dropdown with **z-index: 1000**
- Debounced search (400ms)
- Shows: Symbol | Company Name | Exchange

#### 2. Scan Mode Selector
**Modes**:
- `WEEKLY_THIS` (Default)
- `WEEKLY_NEXT`
- `WEEKLY_2W`
- `LEAP`

#### 3. Score Cards
- Type (CALL/PUT)
- Real-time quote
- Strike
- Expiration
- Premium (Entry Cost)
- ROI %
- Score
- Badges
4. **Add to Watchlist** button

#### 4. AI Thesis Display
**Content**: Perplexity-generated analysis
**Sections**:
- Why this trade makes sense
- Key risk factors
- Technical setup
- Suggested action


---

## 📊 **PHASE 2: Expert Analysis - Multi-Timeframe & Advanced Indicators**

### Comprehensive System Review (Check 3/3)

#### 1. Integration with Phase 1 Features
- **Liquidity Filter**: Remains the "Gatekeeper". Even if MTA is perfect, if liquidity < rating, Trade = REJECTED
- **Earnings Flag**: Remains "Yellow/Red Card". MTA Bullish + Earnings < 3 days = REJECT/WARNING
- **Result**: Phase 2 enhances logic without bypassing Phase 1 safety guards ✅


---


#### Scenario 3: AI "Hallucination" Check
- [x] **Risk**: AI says "Buy" when Earnings is tomorrow
- [x] **Mitigation**: System Prompt explicitly instructs: "VERIFY: efficient market hypothesis... Search for upcoming earnings"
- [x] **Safety**: Phase 1 `EarningsCalendar` *already* flagged urgency. The AI is a *second* pair of eyes, not the only pair
- [x] **Verdict**: ✅ **Redundant Safety**



---

## 💾 **PHASE 4: Expert Analysis - Database & Persistence**

### Comprehensive System Review (Check 3/3)

#### 1. The "Platform" Feel
- **Statefulness**: By saving scans + AI Theses, the user builds a *library* of trade ideas
- **Efficiency**: JSON storage keeps the DB fast and simple
- **Accountability**: Outcome tracking turns the tool into a learning machine ("Why did my AI picks fail last week?")

#### 2. Integration
- **Scanner**: Need to add `save_scan(scan_result)` call at end of scan (optional) or expose an API endpoint `POST /scan/save`
- **Recommendation**: Expose `POST /scan/save` so the *Frontend* decides what to save (don't auto-save every junk scan). Auto-save `History` (ephemeral), Manual save `Journal` (permanent)

### Final Verdict
**3 Consecutive Checks Passed**


---


### Pass 2/3: Logic & Performance

#### 1. The "Fat Payload" Strategy
**Design**: Storing the massive Phase 3 result structure (AI Thesis + Greeks + MTA) in one JSON column
**Logic**:
- Relational (Traditional): 10+ tables. Slow Write. Complex Read
- JSON (Phase 4): 1 table. Fast Write (1 row). Fast Read (Get Blob)
- **Verdict**: ✅ **OPTIMIZED** for this specific use case (Analytical Read-Heavy)

#### 2. Failure Isolation
**Refinement**: `try...except` block added around `save_scan_history` in `scanner.py`
**Result**: If DB fails (lock), the user *still* gets their scan result in the UI
**Verdict**: ✅ **SAFE** (Persistence failure does not crash the Scanner)


---

## 🎨 **PHASE 5: Expert Analysis - Frontend Restoration & Enhancement**

### 1. Gap Analysis (The "Mock" Problem)

#### Critical Findings from Code Review:
1. **Fake Trades**: The Options Chain table is Hardcoded HTML. It does not render real data
2. **Missing AI Brain**: There is Zero UI for `scanResult.ai_thesis`. The detailed Perplexity report is invisible
3. **Fake Watchlist**: The sidebar shows hardcoded "NVDA/TSLA" placeholders


---

---

## 🐛 **Cons & Cures** (8 Documented)

### Con 1: Single Timeframe Bias
**Problem**: Daily chart looks bullish but monthly is bearish
**Cure**: Multi-Timeframe Analysis (MTA) - checks D/W/M alignment

### Con 2: Stale Technical Signals
**Problem**: RSI shows "oversold" but trend is dead
**Cure**: ADX Slope - only trust signals when ADX > 25 and rising

### Con 3: Missing Fundamental Context
**Problem**: Algorithm recommends LEAPS on failing company
**Cure**: Quality Moat Filter - requires ROE > 15%, Margin > 40%

### Con 4: No News Awareness
**Problem**: Buys calls day before FDA rejection
**Cure**: Perplexity AI - searches real-time news for black swans

### Con 5: Ignoring Institutional Flow
**Problem**: Retail buying calls while institutions hedge
**Cure**: Volatility Skew + Smart Money Flag

### Con 6: Earnings Surprise
**Problem**: IV crush destroys option value post-earnings
**Cure**: Earnings Calendar Integration - warns 7-14 days out

### Con 7: Illiquid Options
**Problem**: Can't exit position due to wide spreads
**Cure**: Liquidity Scoring - requires OI > 10, Spread < 25%

### Con 8: Trend Exhaustion
**Problem**: Buys at top of parabolic move
**Cure**: Ichimoku Future Twist - detects cloud color changes ahead

---

## 📊 **Complete Scoring Algorithm**

### Global Score Calculation
```python
global_score = (
    technical_score * 0.35 +
    mta_score * 0.20 +
    sentiment_score * 0.15 +
    skew_score * 0.15 +
    liquidity_score * 0.10 +
    profit_potential * 0.05
)

# Apply bonuses/penalties
if smart_money_flag:
    global_score += 10
    
if earnings_within_7_days:
    global_score -= 20
    
if quality_moat_failed (LEAP mode):
    global_score = 0  # Disqualify
```

### Badge Assignment
- 🔥 **High Conviction**: Score > 85 + MTA alignment
- ⚡ **Smart Money**: Volume > Open Interest
- 📈 **Momentum**: ADX slope > 0.5
- 🛡️ **Stock Replacement**: Delta > 0.80 (LEAP mode)
- ⚠️ **Earnings Risk**: Earnings within 14 days

---