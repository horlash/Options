# Technical Indicator Upgrades — NewScanner Migration Guide

> **Source**: `Options/backend/analysis/technical_indicators.py`  
> **Target**: `Scanner/NewScanner/analysis/technical_indicators.py`  
> **Date**: 2026-02-16

---

## Overview

The Options scanner received a full upgrade to its 5 technical indicators. This document provides exact code changes to apply the same upgrades to the NewScanner codebase.

### Key Differences Between Codebases
| Feature | Options (Source) | NewScanner (Target) |
|---------|-----------------|-------------------|
| RSI | Uses `ta` library | Manual calculation |
| MACD | Uses `ta` library | Manual EWM calculation |
| Bollinger Bands | Uses `ta` library | Manual rolling mean/std |
| Volume threshold | Config-based, now z-score | Hardcoded 1.5x |
| Scoring function | `calculate_technical_score()` | **Not present** — may need to add |

> [!IMPORTANT]
> NewScanner uses manual calculations (no `ta` library dependency). The upgrade logic is the same, but the implementation must use pandas directly.

---

## Upgrade 1: RSI — 5-Zone System

### Before (NewScanner lines 42-48)
```python
if current_rsi < self.rsi_oversold:
    signal = 'bullish'
elif current_rsi > self.rsi_overbought:
    signal = 'bearish'
else:
    signal = 'neutral'
```

### After
```python
# 5-zone RSI system
if current_rsi < self.rsi_oversold:      # < 30
    signal = 'oversold'
elif current_rsi < 40:
    signal = 'near oversold'
elif current_rsi > self.rsi_overbought:  # > 70
    signal = 'overbought'
elif current_rsi > 60:
    signal = 'near overbought'
else:
    signal = 'neutral'                    # 40-60
```

---

## Upgrade 2: MACD — Histogram Momentum (2-Bar Confirmation)

### Before (NewScanner lines 64-66)
```python
if m > s and h > 0: signal_type = 'bullish'
elif m < s and h < 0: signal_type = 'bearish'
else: signal_type = 'neutral'
```

### After
```python
# Get last 3 histogram values for momentum detection
hist_series = (macd_line - signal_line).tail(3).tolist()

if m > s and h > 0:
    # 2-bar confirmation: histogram shrinking for 2+ consecutive bars
    if (len(hist_series) >= 3 and 
        hist_series[-1] < hist_series[-2] < hist_series[-3]):
        signal_type = 'weakening bullish'
    else:
        signal_type = 'bullish'
elif m < s and h < 0:
    if (len(hist_series) >= 3 and 
        hist_series[-1] > hist_series[-2] > hist_series[-3]):
        signal_type = 'weakening bearish'
    else:
        signal_type = 'bearish'
else:
    signal_type = 'neutral'
```

---

## Upgrade 3: Bollinger Bands — Squeeze Detection

### Before (NewScanner lines 84-86)
```python
if c <= l: signal = 'bullish'
elif c >= u: signal = 'bearish'
else: signal = 'neutral'
```

### After
```python
# Calculate bandwidth and percentile for squeeze detection
bandwidth = (u - l) / m if m > 0 else 0
bb_width_series = (upper - lower) / sma
bb_width_history = bb_width_series.dropna().tail(100)
bandwidth_percentile = (bb_width_history < bandwidth).sum() / len(bb_width_history) * 100 if len(bb_width_history) > 0 else 50

# Price position within bands (0 = lower, 100 = upper)
band_range = u - l
band_position = ((c - l) / band_range * 100) if band_range > 0 else 50

# Squeeze-aware 5-zone system
is_squeeze = bandwidth_percentile < 20

if is_squeeze:
    signal = 'squeeze'
elif c >= u:
    signal = 'overbought'
elif band_position > 75:
    signal = 'near overbought'
elif c <= l:
    signal = 'oversold'
elif band_position < 25:
    signal = 'near oversold'
else:
    signal = 'neutral'

# Return additional data
return {
    'upper': u, 'middle': m, 'lower': l, 'current_price': c,
    'bandwidth': bandwidth,
    'bandwidth_percentile': bandwidth_percentile,
    'band_position': band_position,
    'is_squeeze': is_squeeze
}, signal
```

---

## Upgrade 4: Moving Averages — Pullback/Breakdown Zones

### Before (NewScanner lines 100-102)
```python
if sma_50 > sma_200 and current > sma_50: signal = 'bullish'
elif sma_50 < sma_200 and current < sma_50: signal = 'bearish'
else: signal = 'neutral'
```

### After
```python
# 5-zone trend with SMA200 safety net
if sma_50 > sma_200 and current > sma_50:
    signal = 'bullish'              # Full uptrend
elif sma_50 > sma_200 and current > sma_200:
    signal = 'pullback bullish'     # Dip in uptrend (buy-the-dip)
elif sma_50 > sma_200 and current < sma_200:
    signal = 'breakdown'            # Uptrend failing — danger
elif sma_50 < sma_200 and current < sma_50:
    signal = 'bearish'              # Full downtrend
elif sma_50 < sma_200 and current > sma_200:
    signal = 'rally bearish'        # Dead cat bounce
else:
    signal = 'neutral'
```

> [!WARNING]
> NewScanner only requires `len(df) >= 50` for MAs. If `sma_200` is 0 (not enough data), all conditions comparing to `sma_200` will behave incorrectly.  
> **Fix**: Change the guard to `if df is None or len(df) < 200: return None, 'neutral'`

---

## Upgrade 5: Volume — Z-Score Tiers

### Before (NewScanner lines 115-116)
```python
if ratio > 1.5: signal = 'strong'
else: signal = 'weak'
```

### After
```python
# Z-score based volume (ticker-adaptive)
vol_series = df['Volume'].tail(50)
vol_mean = vol_series.mean()
vol_std = vol_series.std()

if vol_mean > 0 and vol_std > 0:
    z_score = (cur_vol - vol_mean) / vol_std
    if z_score > 2.0:     signal = 'surging'   # Institutional
    elif z_score > 0.5:   signal = 'strong'
    elif z_score > -0.5:  signal = 'normal'
    else:                 signal = 'weak'
else:
    signal = 'normal'

return {
    'current_volume': cur_vol, 'avg_volume': avg_vol,
    'volume_ratio': ratio, 'z_score': z_score if vol_mean > 0 and vol_std > 0 else 0
}, signal
```

---

## Upgrade 6: Scoring Function (NEW — Add to NewScanner)

NewScanner does not have `calculate_technical_score()`. Add this method:

```python
def calculate_technical_score(self, indicators):
    if not indicators:
        return 0
    
    score = 0
    weights = {
        'rsi': 20, 'macd': 20, 'bollinger_bands': 25,
        'moving_averages': 20, 'volume': 15
    }
    
    # RSI
    rsi_sig = indicators['rsi']['signal']
    if rsi_sig == 'oversold':           score += weights['rsi']
    elif rsi_sig == 'near oversold':    score += weights['rsi'] * 0.5
    elif rsi_sig == 'overbought':       score -= weights['rsi']
    elif rsi_sig == 'near overbought':  score -= weights['rsi'] * 0.5
    
    # MACD
    macd_sig = indicators['macd']['signal']
    if macd_sig == 'bullish':             score += weights['macd']
    elif macd_sig == 'weakening bullish': score += weights['macd'] * 0.5
    elif macd_sig == 'bearish':           score -= weights['macd']
    elif macd_sig == 'weakening bearish': score -= weights['macd'] * 0.5
    
    # Bollinger Bands
    bb_sig = indicators['bollinger_bands']['signal']
    if bb_sig == 'oversold':          score += weights['bollinger_bands']
    elif bb_sig == 'near oversold':   score += weights['bollinger_bands'] * 0.5
    elif bb_sig == 'overbought':      score -= weights['bollinger_bands']
    elif bb_sig == 'near overbought': score -= weights['bollinger_bands'] * 0.5
    # squeeze = 0 pts (directional-neutral)
    
    # Moving Averages
    ma_sig = indicators['moving_averages']['signal']
    if ma_sig == 'bullish':           score += weights['moving_averages']
    elif ma_sig == 'pullback bullish': score += weights['moving_averages'] * 0.5
    elif ma_sig == 'breakdown':       score -= weights['moving_averages'] * 0.75
    elif ma_sig == 'bearish':          score -= weights['moving_averages']
    elif ma_sig == 'rally bearish':   score -= weights['moving_averages'] * 0.5
    
    # Volume
    vol_sig = indicators['volume']['signal']
    if vol_sig == 'surging':   score *= 1.2
    elif vol_sig == 'strong':  score *= 1.1
    elif vol_sig == 'weak':    score *= 0.95
    
    normalized = ((score + 100) / 200) * 100
    return max(0, min(100, normalized))
```

---

## Frontend Signal Color Mapping

If NewScanner has a frontend, update the signal-to-color mapping:

```javascript
getSignalColor(signal) {
    // Green (bullish)
    if (['bullish','oversold','near oversold','pullback bullish','weakening bearish'].includes(signal))
        return 'green';
    // Red (bearish)
    if (['bearish','overbought','near overbought','breakdown','rally bearish','weakening bullish'].includes(signal))
        return 'red';
    // Amber (special attention)
    if (signal === 'squeeze' || signal === 'surging')
        return '#f59e0b';
    if (signal === 'strong') return 'green';
    if (signal === 'weak') return 'red';
    return 'gray'; // neutral, normal
}
```

---

## Checklist for Migration

- [ ] Update `calculate_rsi()` → 5-zone
- [ ] Update `calculate_macd()` → histogram momentum
- [ ] Update `calculate_bollinger_bands()` → squeeze + band position
- [ ] Fix `calculate_moving_averages()` guard: `len(df) < 200`
- [ ] Update `calculate_moving_averages()` → pullback/breakdown zones
- [ ] Update `analyze_volume()` → z-score tiers
- [ ] Add `calculate_technical_score()` method
- [ ] Update frontend signal colors (if applicable)
- [ ] Test with live data
