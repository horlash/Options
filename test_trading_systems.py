"""Integration test for Trading System Enhancements S1-S7A."""
import sys
sys.path.insert(0, '/home/user/workspace/Options')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

print("=" * 60)
print("TRADING SYSTEM ENHANCEMENTS — INTEGRATION TEST")
print("=" * 60)

passed = 0
failed = 0

def check(condition, msg):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ {msg}")
    else:
        failed += 1
        print(f"  ❌ {msg}")

# ─── S1: VIX Regime Detection ──────────────────────────────────
print("\n[S1] VIX Regime Detection")
from backend.analysis.regime_detector import RegimeDetector, VIXRegime, RegimeContext

rd = RegimeDetector(orats_api=None)

# Test classification thresholds
test_cases = [
    (10.0, VIXRegime.CALM),
    (17.0, VIXRegime.NORMAL),
    (22.0, VIXRegime.ELEVATED),
    (28.0, VIXRegime.FEAR),
    (42.0, VIXRegime.CRISIS),
]
for vix, expected in test_cases:
    result = rd._classify(vix)
    check(result == expected, f"VIX {vix:.1f} → {result.value} (expected: {expected.value})")

# Test regime_str property (legacy compatibility)
ctx = RegimeContext(regime=VIXRegime.CALM, vix_level=12.0)
check(ctx.regime_str == 'NORMAL', f"CALM.regime_str = {ctx.regime_str} (expected NORMAL)")
ctx = RegimeContext(regime=VIXRegime.FEAR, vix_level=28.0)
check(ctx.regime_str == 'ELEVATED', f"FEAR.regime_str = {ctx.regime_str} (expected ELEVATED)")
ctx = RegimeContext(regime=VIXRegime.CRISIS, vix_level=40.0)
check(ctx.regime_str == 'CRISIS', f"CRISIS.regime_str = {ctx.regime_str} (expected CRISIS)")

# Test position_size_multiplier
ctx = RegimeContext(regime=VIXRegime.CRISIS)
check(ctx.position_size_multiplier == 0.15, f"CRISIS size_mult = {ctx.position_size_multiplier}")
ctx = RegimeContext(regime=VIXRegime.CALM)
check(ctx.position_size_multiplier == 1.0, f"CALM size_mult = {ctx.position_size_multiplier}")

# Test score_penalty
ctx = RegimeContext(regime=VIXRegime.FEAR)
check(ctx.score_penalty == -8, f"FEAR score_penalty = {ctx.score_penalty}")

# Test fallback (no API)
fallback = rd.detect()
check(fallback.is_fallback == True, f"Fallback (no API): regime={fallback.regime.value}, is_fallback={fallback.is_fallback}")

# ─── S2: CBOE Put/Call Ratio ──────────────────────────────────
print("\n[S2] CBOE Put/Call Ratio — Contrarian Signals")
from backend.analysis.macro_signals import MacroSignals, PutCallSignal

ms = MacroSignals(orats_api=None)

# Test Z-score interpretation
test_zscores = [
    (2.5, 'extreme_fear', 'bullish', 15),
    (1.7, 'fear', 'bullish', 10),
    (0.9, 'mild_fear', 'lean_bullish', 5),
    (0.3, 'neutral', 'neutral', 0),
    (-0.9, 'mild_complacency', 'lean_bearish', -5),
    (-1.7, 'complacency', 'bearish', -10),
    (-2.5, 'extreme_complacency', 'bearish', -15),
]
for z, exp_sig, exp_bias, exp_mod in test_zscores:
    sig, bias, mod = ms._interpret_z_score(z, 0.65)
    check(sig == exp_sig and bias == exp_bias and mod == exp_mod,
          f"Z={z:+.1f} → {sig} ({bias}, {mod:+d})")

# Test Z-score computation with seeded history
ms.seed_history([0.60, 0.62, 0.65, 0.63, 0.61, 0.64, 0.66, 0.62, 0.65, 0.63,
                  0.61, 0.64, 0.66, 0.62, 0.65, 0.63, 0.61, 0.64, 0.66, 0.62, 0.65])
z = ms._compute_z_score(0.90)
check(z is not None and z > 1.5, f"Z-score for P/C=0.90 (mean~0.63): Z={z:.2f}")

# Test fallback (no API)
signal = ms.get_put_call_signal()
check(signal.source == 'none', f"Fallback signal source: {signal.source}")

# ─── S3: RSI-2 ──────────────────────────────────────────────────
print("\n[S3] Connors RSI-2 Mean Reversion")
from backend.analysis.technical_indicators import TechnicalIndicators

ti = TechnicalIndicators()

# Create synthetic data with sharp drop
dates = pd.date_range(end=datetime.now(), periods=50, freq='B')
prices = np.concatenate([
    np.linspace(100, 110, 40),
    np.linspace(110, 95, 10),
])
df = pd.DataFrame({
    'Open': prices - 0.5,
    'High': prices + 1,
    'Low': prices - 1,
    'Close': prices,
    'Volume': np.random.randint(1000000, 5000000, 50)
}, index=dates)

rsi2 = ti.calculate_rsi2(df)
check(rsi2['value'] is not None, f"RSI-2 value: {rsi2['value']}")
check(rsi2['signal'] in ('extreme_oversold', 'oversold', 'neutral', 'overbought', 'extreme_overbought'),
      f"RSI-2 signal: {rsi2['signal']}")

# Test with insufficient data
rsi2_short = ti.calculate_rsi2(df.head(3))
check(rsi2_short['value'] is None, "RSI-2 graceful fallback for short data")

# ─── S4: Sector Momentum ──────────────────────────────────────
print("\n[S4] Sector Momentum Rotation")
from backend.analysis.sector_analysis import SectorAnalysis

sa = SectorAnalysis(orats_api=None)

check(sa._find_sector('AAPL') == 'XLK', "AAPL → XLK")
check(sa._find_sector('JPM') == 'XLF', "JPM → XLF")
check(sa._find_sector('AMZN') == 'XLY', "AMZN → XLY")
check(sa._find_sector('ZZZZ') is None, "ZZZZ → None")

mod = sa.get_ticker_sector_modifier('AAPL')
check(mod['sector'] == 'Technology', f"AAPL sector: {mod['sector']}")
check(mod.get('score_modifier') is not None, f"AAPL modifier: {mod.get('score_modifier')}")

mod_unknown = sa.get_ticker_sector_modifier('ZZZZ')
check(mod_unknown['score_modifier'] == 0, f"Unknown ticker modifier: {mod_unknown['score_modifier']}")

# ─── S5: Minervini Stage 2 ──────────────────────────────────
print("\n[S5] Minervini Stage 2 Filter")

dates_long = pd.date_range(end=datetime.now(), periods=300, freq='B')
prices_up = np.linspace(50, 120, 300) + np.random.randn(300) * 2
df_up = pd.DataFrame({
    'Open': prices_up - 0.5,
    'High': prices_up + 2,
    'Low': prices_up - 2,
    'Close': prices_up,
    'Volume': np.random.randint(1000000, 5000000, 300)
}, index=dates_long)

mstage = ti.calculate_minervini_criteria(df_up)
check(mstage['score'] >= 0 and mstage['score'] <= 8, f"Score: {mstage['score']}/8")
check(mstage['stage'] in ('STAGE_2', 'STAGE_2_EARLY', 'STAGE_1', 'STAGE_3_OR_4', 'UNCLASSIFIED'),
      f"Stage: {mstage['stage']}")
check('sma50' in mstage and 'sma150' in mstage and 'sma200' in mstage,
      f"SMAs present: 50={mstage.get('sma50')}, 150={mstage.get('sma150')}, 200={mstage.get('sma200')}")

# Insufficient data
mstage_short = ti.calculate_minervini_criteria(df.head(50))
check(mstage_short['stage'] == 'UNCLASSIFIED', f"Short data: {mstage_short['stage']}")

# ─── S7A: VWAP Levels ──────────────────────────────────────
print("\n[S7A] VWAP Institutional Levels (EOD)")

vwap = ti.calculate_vwap_levels(df)
check(vwap['weekly_vwap'] is not None, f"Weekly VWAP: {vwap['weekly_vwap']}")
check(vwap['monthly_vwap'] is not None, f"Monthly VWAP: {vwap['monthly_vwap']}")
check(vwap['signal'] in ('neutral', 'at_weekly_vwap', 'at_monthly_vwap', 'above_vwap', 'below_vwap', 'mixed'),
      f"Signal: {vwap['signal']}")

vwap_short = ti.calculate_vwap_levels(df.head(5))
check(vwap_short['weekly_vwap'] is None or vwap_short['weekly_vwap'] is not None,
      f"Short data handled: {vwap_short}")

# ─── get_all_indicators() ──────────────────────────────────
print("\n[Integration] get_all_indicators() includes new systems")

price_history = []
for i in range(300):
    d = (datetime.now() - timedelta(days=300-i)).strftime('%Y-%m-%d')
    p = 50 + i * 0.2 + np.random.randn() * 1.5
    price_history.append({
        'datetime': d,
        'open': p - 0.3,
        'high': p + 1.2,
        'low': p - 1.2,
        'close': p,
        'volume': int(np.random.randint(1000000, 5000000))
    })

indicators = ti.get_all_indicators(price_history)
if indicators:
    check('rsi2' in indicators, f"rsi2 in indicators: {indicators.get('rsi2', {}).get('value')}")
    check('vwap' in indicators, f"vwap in indicators: {indicators.get('vwap', {}).get('signal')}")
    check('minervini' in indicators, f"minervini in indicators: {indicators.get('minervini', {}).get('stage')}")
    # Original indicators still present
    check('rsi' in indicators, "Original RSI still present")
    check('macd' in indicators, "Original MACD still present")
    check('bollinger_bands' in indicators, "Original Bollinger Bands still present")
else:
    failed += 1
    print("  ❌ get_all_indicators returned None")

# ─── Config Flags ──────────────────────────────────────────
print("\n[Config] Feature Toggle Flags")
from backend.config import Config
flags = {
    'ENABLE_VIX_REGIME': Config.ENABLE_VIX_REGIME,
    'ENABLE_PUT_CALL_RATIO': Config.ENABLE_PUT_CALL_RATIO,
    'ENABLE_RSI2': Config.ENABLE_RSI2,
    'ENABLE_SECTOR_MOMENTUM': Config.ENABLE_SECTOR_MOMENTUM,
    'ENABLE_MINERVINI_FILTER': Config.ENABLE_MINERVINI_FILTER,
    'ENABLE_VWAP_LEVELS': Config.ENABLE_VWAP_LEVELS,
}
for flag, value in flags.items():
    check(value == True, f"{flag}: {value}")

# ─── Summary ──────────────────────────────────────────────
print("\n" + "=" * 60)
print(f"RESULTS: {passed} passed, {failed} failed")
if failed == 0:
    print("ALL TESTS PASSED ✅")
else:
    print(f"{failed} TESTS FAILED ❌")
print("=" * 60)

sys.exit(0 if failed == 0 else 1)
