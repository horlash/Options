# Technical Indicators Explained

This document explains the technical indicators used by the LEAP Options Scanner and how they contribute to opportunity scoring.

## Overview

The scanner uses five primary technical indicators to assess stock momentum, trend, and volatility:

1. **RSI** - Relative Strength Index
2. **MACD** - Moving Average Convergence Divergence
3. **Bollinger Bands**
4. **Moving Averages**
5. **Volume Analysis**

Each indicator generates a signal (bullish, bearish, or neutral) that contributes to the overall technical score.

---

## 1. RSI (Relative Strength Index)

### What It Is
RSI measures the speed and magnitude of price changes on a scale of 0-100.

### How It Works
- **Formula**: RSI = 100 - (100 / (1 + RS))
  - RS = Average Gain / Average Loss over 14 periods
- **Range**: 0 to 100

### Interpretation

| RSI Value | Condition | Signal | Meaning |
|-----------|-----------|--------|---------|
| < 30 | Oversold | 🟢 Bullish | Stock may be undervalued, potential buy |
| 30-70 | Neutral | ⚪ Neutral | Normal trading range |
| > 70 | Overbought | 🔴 Bearish | Stock may be overvalued, potential sell |

### For LEAP Options
- **Oversold (RSI < 30)**: Good for buying CALL options
- **Overbought (RSI > 70)**: Good for buying PUT options

### Example
If AAPL has RSI of 25:
- Stock is oversold
- Bullish signal generated
- Scanner favors CALL options
- Contributes positively to technical score

---

## 2. MACD (Moving Average Convergence Divergence)

### What It Is
MACD is a trend-following momentum indicator that shows the relationship between two moving averages.

### Components
- **MACD Line**: 12-day EMA - 26-day EMA
- **Signal Line**: 9-day EMA of MACD Line
- **Histogram**: MACD Line - Signal Line

### Interpretation

| Condition | Signal | Meaning |
|-----------|--------|---------|
| MACD > Signal & Histogram > 0 | 🟢 Bullish | Upward momentum |
| MACD < Signal & Histogram < 0 | 🔴 Bearish | Downward momentum |
| Crossover occurring | ⚪ Neutral | Trend changing |

### Key Signals
- **Bullish Crossover**: MACD crosses above signal line
- **Bearish Crossover**: MACD crosses below signal line
- **Divergence**: Price and MACD moving in opposite directions

### For LEAP Options
- Bullish MACD → Favor CALL options
- Bearish MACD → Favor PUT options
- Strong histogram → Higher confidence in signal

### Example
If TSLA shows:
- MACD: 5.2
- Signal: 3.8
- Histogram: 1.4 (positive)

Result: Bullish signal, good for CALL LEAPs

---

## 3. Bollinger Bands

### What It Is
Bollinger Bands measure volatility and identify overbought/oversold conditions using standard deviations.

### Components
- **Middle Band**: 20-day Simple Moving Average
- **Upper Band**: Middle Band + (2 × Standard Deviation)
- **Lower Band**: Middle Band - (2 × Standard Deviation)

### Interpretation

| Price Position | Signal | Meaning |
|----------------|--------|---------|
| At/Below Lower Band | 🟢 Bullish | Oversold, potential bounce |
| Between Bands | ⚪ Neutral | Normal range |
| At/Above Upper Band | 🔴 Bearish | Overbought, potential pullback |

### Additional Signals
- **Band Squeeze**: Bands narrow → Low volatility, breakout coming
- **Band Expansion**: Bands widen → High volatility, strong trend

### For LEAP Options
- Price at lower band → Buy CALL options
- Price at upper band → Buy PUT options
- Tight bands → Wait for breakout direction

### Example
If NVDA is trading at:
- Current Price: $450
- Lower Band: $455
- Middle Band: $475
- Upper Band: $495

Result: Near lower band, bullish signal for CALLs

---

## 4. Moving Averages

### What They Are
Moving averages smooth price data to identify trends.

### Types Used
- **50-day SMA**: Short-to-medium term trend
- **200-day SMA**: Long-term trend

### Interpretation

| Condition | Signal | Meaning |
|-----------|--------|---------|
| Price > 50 SMA > 200 SMA | 🟢 Bullish | Strong uptrend |
| Price < 50 SMA < 200 SMA | 🔴 Bearish | Strong downtrend |
| 50 SMA crosses 200 SMA | ⚪ Transitioning | Trend change |

### Key Patterns
- **Golden Cross**: 50 SMA crosses above 200 SMA (bullish)
- **Death Cross**: 50 SMA crosses below 200 SMA (bearish)

### For LEAP Options
- Golden Cross → Strong signal for CALL LEAPs
- Death Cross → Strong signal for PUT LEAPs
- Price above both MAs → Bullish trend confirmed

### Example
If MSFT shows:
- Current Price: $380
- 50-day SMA: $375
- 200-day SMA: $360

Result: Price above both MAs, bullish signal

---

## 5. Volume Analysis

### What It Is
Volume measures the number of shares traded and confirms price movements.

### How It Works
- Compare current volume to 20-day average
- High volume confirms trends
- Low volume suggests weak movements

### Interpretation

| Condition | Signal | Meaning |
|-----------|--------|---------|
| Volume > 1.5× Average | 🟢 Strong | Movement confirmed |
| Volume < 1.5× Average | 🔴 Weak | Movement questionable |

### Volume Patterns
- **Volume Spike + Price Up**: Strong bullish confirmation
- **Volume Spike + Price Down**: Strong bearish confirmation
- **Price Up + Low Volume**: Weak rally, may reverse
- **Price Down + Low Volume**: Weak selloff, may bounce

### For LEAP Options
- High volume strengthens all other signals
- Low volume reduces confidence in opportunity
- Volume acts as a multiplier (±10%) on technical score

### Example
If AMD shows:
- Current Volume: 75M shares
- 20-day Average: 45M shares
- Volume Ratio: 1.67× (above 1.5× threshold)

Result: Strong signal, boosts overall score by 10%

---

## Support and Resistance Levels

### What They Are
Price levels where stocks tend to stop and reverse.

### How Calculated
- **Support**: Recent lows, pivot points
- **Resistance**: Recent highs, pivot points
- **Pivot Point**: (High + Low + Close) / 3

### Usage in Scanner
- Identifies optimal strike prices for options
- Helps set profit targets
- Indicates potential reversal zones

### Example
If GOOGL shows:
- Support: $140
- Current Price: $145
- Resistance: $155

For CALLs: Strike near $150-155 (at resistance)
For PUTs: Strike near $140-145 (at support)

---

## How Indicators Combine

### Technical Score Calculation

The scanner calculates a weighted technical score:

```
Technical Score = (RSI × 20%) + (MACD × 25%) + (Bollinger × 20%) + (MA × 25%) + (Volume × 10%)
```

### Weighting Rationale
- **MACD (25%)**: Most reliable trend indicator
- **Moving Averages (25%)**: Strong long-term signal
- **RSI (20%)**: Good momentum indicator
- **Bollinger Bands (20%)**: Volatility context
- **Volume (10%)**: Confirmation factor

### Signal Conversion
Each indicator's signal is converted to a score:
- Bullish: +100
- Neutral: 0
- Bearish: -100

Then normalized to 0-100 scale.

### Volume Boost
If volume signal is "strong", the final score is multiplied by 1.1 (10% boost).

### Example Calculation

For a stock with:
- RSI: Bullish (+100)
- MACD: Bullish (+100)
- Bollinger: Neutral (0)
- MA: Bullish (+100)
- Volume: Strong (multiplier)

```
Score = (100×0.2) + (100×0.25) + (0×0.2) + (100×0.25) + (0×0.1)
      = 20 + 25 + 0 + 25 + 0
      = 70

With volume boost: 70 × 1.1 = 77/100
```

Result: **77/100** - High-quality technical setup

---

## Practical Application

### For Bullish CALL LEAPs

Look for:
- ✅ RSI < 30 (oversold)
- ✅ MACD bullish crossover
- ✅ Price at lower Bollinger Band
- ✅ Price above 50-day MA
- ✅ Golden Cross (50 > 200 MA)
- ✅ High volume on up days

### For Bearish PUT LEAPs

Look for:
- ✅ RSI > 70 (overbought)
- ✅ MACD bearish crossover
- ✅ Price at upper Bollinger Band
- ✅ Price below 50-day MA
- ✅ Death Cross (50 < 200 MA)
- ✅ High volume on down days

### Avoiding False Signals

❌ **Don't trade when:**
- Indicators conflict (some bullish, some bearish)
- Volume is very low
- Technical score < 40
- Stock has upcoming earnings (high uncertainty)

✅ **Best setups:**
- All indicators aligned
- High volume confirmation
- Technical score > 60
- Clear trend direction

---

## Limitations

### What Technical Analysis Can't Predict
- Unexpected news events
- Regulatory changes
- Management decisions
- Black swan events
- Market crashes

### Best Used With
- Fundamental analysis
- News sentiment (included in scanner)
- Sector trends
- Macro economic data
- Risk management

---

## Further Learning

### Recommended Resources
- **Books**:
  - "Technical Analysis of the Financial Markets" by John Murphy
  - "A Beginner's Guide to Technical Analysis" by Investopedia
  
- **Websites**:
  - Investopedia.com (technical analysis section)
  - StockCharts.com (chart school)
  - TradingView.com (charting platform)

### Practice
- Use the scanner on paper trading first
- Compare scanner signals with actual outcomes
- Keep a trading journal
- Backtest strategies

---

## Summary

The LEAP Options Scanner uses proven technical indicators to:
1. Identify trend direction (MACD, Moving Averages)
2. Find entry points (RSI, Bollinger Bands)
3. Confirm signals (Volume)
4. Calculate optimal strikes (Support/Resistance)

By combining multiple indicators with sentiment analysis and options-specific metrics, the scanner provides a comprehensive view of LEAP opportunities.

Remember: **Technical analysis is a tool, not a crystal ball.** Always use proper risk management and never invest more than you can afford to lose.
