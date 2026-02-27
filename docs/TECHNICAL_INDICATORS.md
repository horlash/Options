# Technical Indicators Explained

This document explains the technical indicators used by the Options Scanner and how they contribute to opportunity scoring.

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
RSI measures the speed and magnitude of price changes. We use a **5-Zone System** for precision.

### Zones & Signals
| RSI Value | Zone | Signal | Meaning |
|-----------|------|--------|---------|
| < 30 | Extreme Oversold | 🟢 **Oversold** | Strong Buy signal |
| 30-40 | Weakness | 🟢 **Near Oversold** | Potential bottom forming |
| 40-60 | Neutral | ⚪ **Neutral** | Normal range |
| 60-70 | Strength | 🔴 **Near Overbought** | Potential top forming |
| > 70 | Extreme Overbought | 🔴 **Overbought** | Strong Sell signal |

---

## 2. MACD (Moving Average Convergence Divergence)

### What It Is
MACD tracks momentum. We use **Histogram Momentum** to detect shifts *before* the crossover.

### Interpretation
| Condition | Signal | Meaning |
|-----------|--------|---------|
| MACD > Signal & Hist > 0 | 🟢 **Bullish** | Strong uptrend |
| MACD > Signal but Hist shrinking | 🟡 **Weakening Bullish** | Momentum fading |
| MACD < Signal & Hist < 0 | 🔴 **Bearish** | Strong downtrend |
| MACD < Signal but Hist rising | 🟡 **Weakening Bearish** | Selling pressure fading |

---

## 3. Bollinger Bands

### What It Is
Measures volatility. We look for **Squeezes** (volatility compression) which often precede big moves.

### Signals
| Condition | Signal | Meaning |
|-----------|--------|---------|
| Bandwidth < 20th Percentile | 🟠 **Squeeze** | Energy building (Big move coming) |
| Price <= Lower Band | 🟢 **Oversold** | Potential bounce |
| Price >= Upper Band | 🔴 **Overbought** | Potential pullback |
| %B < 25 | 🟢 **Near Oversold** | Approaching support |
| %B > 75 | 🔴 **Near Overbought** | Approaching resistance |

---

## 4. Moving Averages

### What They Are
Trend confirmation using SMA 50 and SMA 200.

### Signals
| Condition | Signal | Meaning |
|-----------|--------|---------|
| Price > 50 > 200 | 🟢 **Bullish** | Strong uptrend |
| Price > 200 but < 50 | 🟢 **Pullback Bullish** | Buy the dip opportunity |
| Price < 50 but > 200 | 🔴 **Breakdown** | Warning: Uptrend failing |
| Price < 50 < 200 | 🔴 **Bearish** | Strong downtrend |
| Price < 200 but > 50 | 🔴 **Rally Bearish** | Dead cat bounce |

---

## 5. Volume Analysis

### What It Is
We use **Z-Score Analysis** to detect unusual institutional activity relative to the stock's own history.

### Z-Score Tiers
| Z-Score | Signal | Meaning |
|---------|--------|---------|
| > 2.0 | 🟣 **Surging** | Massive institutional buying/selling |
| > 0.5 | 🟢 **Strong** | Above average volume |
| -0.5 to 0.5 | ⚪ **Normal** | Average volume |
| < -0.5 | 🔴 **Weak** | Low conviction move |

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

The Options Scanner uses proven technical indicators to:
1. Identify trend direction (MACD, Moving Averages)
2. Find entry points (RSI, Bollinger Bands)
3. Confirm signals (Volume)
4. Calculate optimal strikes (Support/Resistance)

By combining multiple indicators with sentiment analysis and options-specific metrics, the scanner provides a comprehensive view of LEAP opportunities.

Remember: **Technical analysis is a tool, not a crystal ball.** Always use proper risk management and never invest more than you can afford to lose.
