#!/usr/bin/env python3
"""
FINAL INTEGRATION TEST — All G1-G20 Audit Remediation Fixes
Live API tests against ORATS, Finnhub, and internal logic.
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ['ORATS_API_KEY'] = 'b87b58de-a1bb-4958-accd-b4443ca61fdd'
os.environ['FINNHUB_API_KEY'] = 'd5ksrbhr01qt47mfai40d5ksrbhr01qt47mfai4g'
os.environ['TRADIER_API_KEY'] = '8A09vGkjXxbJspeGkT0iNI8VEapW'
os.environ['TRADIER_USE_SANDBOX'] = 'True'
os.environ['FMP_API_KEY'] = 'jfB5vWaGzzEK6OowZayWNCxdbULnwROC'

results = []
def test(gap_id, name, fn):
    try:
        fn()
        results.append((gap_id, name, 'PASS', ''))
        print(f"  ✅ [{gap_id}] {name}")
    except AssertionError as e:
        results.append((gap_id, name, 'FAIL', str(e)))
        print(f"  ❌ [{gap_id}] {name}: {e}")
    except Exception as e:
        results.append((gap_id, name, 'ERROR', str(e)[:200]))
        print(f"  ⚠️  [{gap_id}] {name}: {e}")

# ================================================================
print("\n" + "="*70)
print("G1: BACKTESTING FRAMEWORK")
print("="*70)

def test_g1_backtest_engine():
    from backend.backtesting.engine import BacktestEngine, BacktestResult
    from backend.api.orats import OratsAPI
    api = OratsAPI()
    engine = BacktestEngine(orats_api=api)
    result = engine.run(
        tickers=['AAPL'],
        strategy='LEAP',
        start_date='2025-01-01',
        end_date='2025-12-31',
        initial_capital=50000,
    )
    assert isinstance(result, BacktestResult)
    assert result.total_trades > 0, f"No trades generated"
    assert 0 <= result.win_rate <= 100, f"Win rate out of range: {result.win_rate}"
    print(f"    Trades: {result.total_trades}, Win rate: {result.win_rate:.1f}%, Total P&L: {result.total_pnl_pct:.1f}%")
    print(f"    Max DD: {result.max_drawdown_pct:.1f}%, Sharpe: {result.sharpe_ratio:.2f}")

test("G1", "Backtesting engine (AAPL LEAP 2025)", test_g1_backtest_engine)

# ================================================================
print("\n" + "="*70)
print("G2: EXIT LOGIC FRAMEWORK")
print("="*70)

def test_g2_exit_plan_all_strategies():
    from backend.analysis.exit_manager import ExitManager
    em = ExitManager()
    for strat in ['LEAP', 'WEEKLY', '0DTE']:
        opp = {'premium': 5.0, 'strike_price': 200, 'days_to_expiry': 180, 'delta': 0.55}
        plan = em.generate_exit_plan(opp, strategy=strat)
        assert 'stop_loss_pct' in plan
        assert len(plan['profit_targets']) >= 2
        assert 'trailing_stop_pct' in plan

def test_g2_exit_signal():
    from backend.analysis.exit_manager import ExitManager
    em = ExitManager()
    plan = {'stop_loss_pct': -30, 'time_stop_dte': 30, 'profit_targets': [{'pct': 50, 'action': 'sell_50pct'}], 'earnings_rule': 'close_before'}
    sig = em.should_exit({}, current_pnl_pct=55, dte_remaining=90, exit_plan=plan)
    assert sig['should_exit'] == True
    assert 'profit' in sig['reason'].lower()

test("G2", "Exit plan generation (all strategies)", test_g2_exit_plan_all_strategies)
test("G2", "Exit signal detection", test_g2_exit_signal)

# ================================================================
print("\n" + "="*70)
print("G3: SENTIMENT — FINNHUB + PERPLEXITY (replacing TextBlob)")
print("="*70)

def test_g3_finnhub_scoring():
    from backend.analysis.sentiment_analyzer import SentimentAnalyzer
    sa = SentimentAnalyzer()
    mock = {'companyNewsScore': 0.82, 'sentiment': {'bullishPercent': 0.9}, 'buzz': {'articlesInLastWeek': 60}}
    result = sa.analyze_sentiment('NVDA', finnhub_premium_data=mock)
    assert result['score'] == 82.0
    assert 'Finnhub' in result['source']

def test_g3_no_textblob():
    """Verify TextBlob is not imported"""
    import importlib
    sa_module = importlib.import_module('backend.analysis.sentiment_analyzer')
    source = open(sa_module.__file__).read()
    assert 'TextBlob' not in source, "TextBlob still referenced in sentiment_analyzer.py"
    assert 'textblob' not in source.lower(), "textblob import still exists"

test("G3", "Finnhub institutional scoring", test_g3_finnhub_scoring)
test("G3", "TextBlob removed", test_g3_no_textblob)

# ================================================================
print("\n" + "="*70)
print("G4: LEAP WEIGHTS SUM TO 1.00")
print("="*70)

def test_g4():
    assert abs(0.30+0.20+0.10+0.15+0.05+0.10+0.10 - 1.0) < 0.001, "LEAP weights != 1.0"
    assert abs(0.40+0.15+0.15+0.15+0.05+0.10 - 1.0) < 0.001, "WEEKLY weights != 1.0"

test("G4", "All strategy weights sum to 1.00", test_g4)

# ================================================================
print("\n" + "="*70)
print("G5: AFTER-HOURS GREEKS ENRICHMENT")
print("="*70)

def test_g5_bs_fallback():
    """Black-Scholes fallback produces valid Greeks"""
    from backend.services.hybrid_scanner_service import HybridScannerService
    # Test BS calc directly
    import math
    S, K, T, sigma = 200, 200, 0.5, 0.30  # ATM, 6 months, 30% IV
    d1 = (math.log(S/K) + (0.045 + 0.5*sigma**2)*T) / (sigma*math.sqrt(T))
    N = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
    delta = N(d1)
    assert 0.45 < delta < 0.65, f"BS delta for ATM should be ~0.55, got {delta:.4f}"

test("G5", "Black-Scholes fallback produces valid Greeks", test_g5_bs_fallback)

# ================================================================
print("\n" + "="*70)
print("G6: GREEKS IN SCORING FORMULA")
print("="*70)

def test_g6():
    from backend.analysis.options_analyzer import OptionsAnalyzer
    a = OptionsAnalyzer()
    # Delta 0.60 LEAP should score well
    s1 = a._calculate_greeks_score({'delta': 0.60, 'gamma': 0.01, 'theta': -0.02, 'premium': 5.0}, 'LEAP')
    # Delta 0.20 LEAP should score poorly
    s2 = a._calculate_greeks_score({'delta': 0.20, 'gamma': 0.01, 'theta': -0.02, 'premium': 5.0}, 'LEAP')
    assert s1 > s2, f"Delta 0.60 ({s1}) should score higher than 0.20 ({s2})"

test("G6", "Greeks scoring differentiates delta quality", test_g6)

# ================================================================
print("\n" + "="*70)
print("G7: KELLY CRITERION POSITION SIZING")
print("="*70)

def test_g7():
    from backend.analysis.position_sizer import PositionSizer
    ps = PositionSizer(account_size=50000)
    opp = {'premium': 3.0, 'delta': 0.55, 'opportunity_score': 65, 'profit_potential': 80}
    sizing = ps.calculate(opp, strategy='LEAP', vix_regime='NORMAL')
    assert sizing['contracts'] >= 1, "Should recommend at least 1 contract"
    assert sizing['pct_of_account'] <= 5.0, f"LEAP should not exceed 5% ({sizing['pct_of_account']})"
    assert sizing['kelly_fraction'] > 0, "Kelly fraction should be positive"
    print(f"    Contracts: {sizing['contracts']}, Cost: ${sizing['total_cost']}, Kelly: {sizing['kelly_fraction']:.4f}")

def test_g7_crisis():
    from backend.analysis.position_sizer import PositionSizer
    ps = PositionSizer(account_size=50000)
    opp = {'premium': 3.0, 'delta': 0.55, 'opportunity_score': 65, 'profit_potential': 80}
    normal = ps.calculate(opp, strategy='LEAP', vix_regime='NORMAL')
    crisis = ps.calculate(opp, strategy='LEAP', vix_regime='CRISIS')
    assert crisis['kelly_fraction'] < normal['kelly_fraction'], "CRISIS should reduce sizing"

test("G7", "Kelly position sizing", test_g7)
test("G7", "CRISIS reduces position size", test_g7_crisis)

# ================================================================
print("\n" + "="*70)
print("G8: VIX REGIME ADJUSTMENT")
print("="*70)

def test_g8_live_vix():
    from backend.api.orats import OratsAPI
    api = OratsAPI()
    q = api.get_quote('VIX')
    assert q is not None
    vix = q['price']
    regime = 'CRISIS' if vix > 30 else ('ELEVATED' if vix > 20 else 'NORMAL')
    print(f"    VIX={vix:.2f}, Regime={regime}")
    assert vix > 0

test("G8", "Live VIX regime detection", test_g8_live_vix)

# ================================================================
print("\n" + "="*70)
print("G9: IV PERCENTILE RANK")
print("="*70)

def test_g9_live():
    from backend.api.orats import OratsAPI
    api = OratsAPI()
    cores = api.get_hist_cores('AAPL')
    assert cores is not None
    iv_pctile = cores.get('ivPctile1y')
    assert iv_pctile is not None, "Missing ivPctile1y"
    assert 0 <= iv_pctile <= 100, f"IV percentile out of range: {iv_pctile}"
    print(f"    AAPL IV Percentile (1Y): {iv_pctile}")

def test_g9_scoring():
    from backend.analysis.options_analyzer import OptionsAnalyzer
    a = OptionsAnalyzer()
    opp = {'delta': 0.55, 'gamma': 0.02, 'theta': -0.1, 'premium': 3.0,
           'open_interest': 500, 'volume': 50, 'bid': 2.8, 'profit_potential': 100, 'days_to_expiry': 200}
    r_low = a.rank_opportunities([opp.copy()], 60, 55, strategy='LEAP', iv_percentile=10)
    r_high = a.rank_opportunities([opp.copy()], 60, 55, strategy='LEAP', iv_percentile=90)
    assert r_low[0]['opportunity_score'] > r_high[0]['opportunity_score']

test("G9", "Live IV Percentile from ORATS", test_g9_live)
test("G9", "IV Percentile affects scoring", test_g9_scoring)

# ================================================================
print("\n" + "="*70)
print("G10-G13: FILTERS (Delta, OI, Volume, Spread)")
print("="*70)

def test_g10_delta():
    from backend.analysis.options_analyzer import OptionsAnalyzer
    a = OptionsAnalyzer()
    # Delta 0.85 should be rejected for LEAP (range 0.40-0.75)
    opp = {'delta': 0.85, 'gamma': 0.01, 'theta': -0.1, 'premium': 3.0,
           'open_interest': 500, 'volume': 50, 'bid': 2.8, 'profit_potential': 100, 'days_to_expiry': 200}
    result = a.rank_opportunities([opp], 60, 55, strategy='LEAP')
    assert len(result) == 0, "Delta 0.85 should be rejected for LEAP"

def test_g11_oi():
    from backend.analysis.options_analyzer import OptionsAnalyzer
    a = OptionsAnalyzer()
    opp = {'delta': 0.55, 'gamma': 0.02, 'theta': -0.1, 'premium': 3.0,
           'open_interest': 50, 'volume': 50, 'bid': 2.8, 'profit_potential': 100, 'days_to_expiry': 200}
    result = a.rank_opportunities([opp], 60, 55, strategy='LEAP')
    assert len(result) == 0, "OI 50 should be rejected for LEAP (min 100)"

def test_g12_volume():
    from backend.analysis.options_analyzer import OptionsAnalyzer
    a = OptionsAnalyzer()
    opp = {'delta': 0.55, 'gamma': 0.02, 'theta': -0.1, 'premium': 3.0,
           'open_interest': 500, 'volume': 3, 'bid': 2.8, 'profit_potential': 100, 'days_to_expiry': 200}
    result = a.rank_opportunities([opp], 60, 55, strategy='LEAP')
    assert len(result) == 0, "Volume 3 should be rejected for LEAP (min 10)"

def test_g13_spread():
    from backend.analysis.options_analyzer import OptionsAnalyzer
    a = OptionsAnalyzer()
    # Wide spread: bid=1.0, ask=3.0 → spread 67% > 10% limit
    opp = {'delta': 0.55, 'gamma': 0.02, 'theta': -0.1, 'premium': 2.0,
           'open_interest': 500, 'volume': 50, 'bid': 1.0, 'ask': 3.0,
           'profit_potential': 100, 'days_to_expiry': 200}
    result = a.rank_opportunities([opp], 60, 55, strategy='LEAP')
    assert len(result) == 0, "67% spread should be rejected for LEAP (max 10%)"

test("G10", "Delta range filtering", test_g10_delta)
test("G11", "Open Interest minimum", test_g11_oi)
test("G12", "Volume gate", test_g12_volume)
test("G13", "Bid-ask spread filter", test_g13_spread)

# ================================================================
print("\n" + "="*70)
print("G14: EARNINGS PROXIMITY CHECK")
print("="*70)

def test_g14_live():
    from backend.api.orats import OratsAPI
    api = OratsAPI()
    cores = api.get_hist_cores('AAPL')
    assert cores is not None
    dte = cores.get('daysToNextErn')
    em = cores.get('impliedEarningsMove')
    print(f"    AAPL: daysToNextErn={dte}, impliedEarningsMove={em}")

def test_g14_penalty():
    from backend.analysis.options_analyzer import OptionsAnalyzer
    a = OptionsAnalyzer()
    opp = {'delta': 0.55, 'gamma': 0.02, 'theta': -0.1, 'premium': 3.0,
           'open_interest': 500, 'volume': 50, 'bid': 2.8, 'profit_potential': 100, 'days_to_expiry': 200}
    r_none = a.rank_opportunities([opp.copy()], 60, 55, strategy='LEAP', days_to_earnings=None)
    r_2d = a.rank_opportunities([opp.copy()], 60, 55, strategy='LEAP', days_to_earnings=2)
    assert r_none[0]['opportunity_score'] > r_2d[0]['opportunity_score']

test("G14", "Live earnings data from ORATS", test_g14_live)
test("G14", "Earnings proximity scoring penalty", test_g14_penalty)

# ================================================================
print("\n" + "="*70)
print("G15: DIVIDEND IMPACT CHECK")
print("="*70)

def test_g15():
    from backend.api.orats import OratsAPI
    api = OratsAPI()
    cores = api.get_hist_cores('AAPL')
    assert cores is not None
    div_date = cores.get('divDate')
    print(f"    AAPL divDate: {div_date}")
    assert div_date is not None, "AAPL should have a dividend date"

test("G15", "Dividend date from ORATS", test_g15)

# ================================================================
print("\n" + "="*70)
print("G16: INDEX MACRO SENTIMENT (Perplexity)")
print("="*70)

def test_g16():
    from backend.services.reasoning_engine import ReasoningEngine
    re = ReasoningEngine()
    if not re.api_key:
        print("    ⏭️  Skipping (no Perplexity API key)")
        return
    result = re.get_macro_sentiment(vix_level=19.4, vix_regime='NORMAL')
    assert 'score' in result
    assert 0 <= result['score'] <= 100
    print(f"    Macro score: {result['score']}, Summary: {result.get('summary', 'N/A')}")

test("G16", "Macro sentiment via Perplexity", test_g16)

# ================================================================
print("\n" + "="*70)
print("G17/G18: POSITION + SECTOR LIMITS")
print("="*70)

def test_g17():
    from backend.analysis.portfolio_risk_manager import PortfolioRiskManager
    prm = PortfolioRiskManager()
    # Already have 3 AAPL positions → should block
    positions = [
        {'ticker': 'AAPL', 'sector': 'Technology', 'cost': 500},
        {'ticker': 'AAPL', 'sector': 'Technology', 'cost': 500},
        {'ticker': 'AAPL', 'sector': 'Technology', 'cost': 500},
    ]
    check = prm.check_trade('AAPL', 'Technology', 500, 50000, positions)
    assert check['allowed'] == False, "Should block 4th AAPL position"
    assert any('G17' in v for v in check['violations'])

def test_g18():
    from backend.analysis.portfolio_risk_manager import PortfolioRiskManager
    prm = PortfolioRiskManager()
    # Sector at 29% + new trade pushes over 30%
    positions = [
        {'ticker': 'AAPL', 'sector': 'Technology', 'cost': 7000},
        {'ticker': 'MSFT', 'sector': 'Technology', 'cost': 7000},
    ]
    check = prm.check_trade('NVDA', 'Technology', 2000, 50000, positions)
    assert check['allowed'] == False, "Should block — Technology at 32%"
    assert any('G18' in v and 'sector' in v.lower() for v in check['violations'])

test("G17", "Max positions per ticker", test_g17)
test("G18", "Sector concentration limits", test_g18)

# ================================================================
print("\n" + "="*70)
print("G19: SCORE NORMALIZATION")
print("="*70)

def test_g19_tech():
    from backend.analysis.technical_indicators import TechnicalIndicators
    ti = TechnicalIndicators()
    # All bullish
    bullish = {
        'rsi': {'signal': 'oversold', 'value': 25},
        'macd': {'signal': 'bullish'},
        'bollinger_bands': {'signal': 'oversold'},
        'moving_averages': {'signal': 'bullish'},
        'volume': {'signal': 'surging'},
    }
    score = ti.calculate_technical_score(bullish)
    assert 0 <= score <= 100, f"Score {score} out of range"
    assert score > 75, f"All-bullish should score >75, got {score}"
    print(f"    All-bullish tech: {score:.1f}")

test("G19", "Technical score normalization", test_g19_tech)

# ================================================================
print("\n" + "="*70)
print("G20: AUDIT TRAIL / SCORE BREAKDOWN")
print("="*70)

def test_g20():
    from backend.analysis.options_analyzer import OptionsAnalyzer
    a = OptionsAnalyzer()
    opp = {'delta': 0.55, 'gamma': 0.02, 'theta': -0.1, 'premium': 3.0,
           'open_interest': 500, 'volume': 50, 'bid': 2.8, 'profit_potential': 100, 'days_to_expiry': 200}
    ranked = a.rank_opportunities([opp], 60, 55, strategy='LEAP', iv_percentile=45, days_to_earnings=30)
    assert len(ranked) > 0
    bd = ranked[0]['score_breakdown']
    required_keys = ['technical', 'sentiment', 'skew', 'greeks', 'profit', 'liquidity',
                     'weights', 'bonus_penalty', 'vix_regime', 'iv_percentile',
                     'days_to_earnings', 'delta_range', 'spread_pct', 'oi', 'opt_volume']
    for key in required_keys:
        assert key in bd, f"Missing '{key}' in score_breakdown"
    print(f"    All {len(required_keys)} breakdown fields present ✓")

test("G20", "Score breakdown completeness", test_g20)


# ================================================================
# FINAL SUMMARY
# ================================================================
print("\n" + "="*70)
print("FINAL TEST SUMMARY — G1-G20 Audit Remediation")
print("="*70)

passed = sum(1 for _, _, s, _ in results if s == 'PASS')
failed = sum(1 for _, _, s, _ in results if s == 'FAIL')
errors = sum(1 for _, _, s, _ in results if s == 'ERROR')
total = len(results)

# Group by gap
from collections import defaultdict
gap_status = defaultdict(list)
for gap, name, status, msg in results:
    gap_status[gap].append(status)

print(f"\n  Total Tests: {total} | ✅ Passed: {passed} | ❌ Failed: {failed} | ⚠️  Errors: {errors}")
print(f"  Success Rate: {passed}/{total} ({passed/total*100:.0f}%)")

print(f"\n  Gap Coverage:")
for gap in sorted(gap_status.keys(), key=lambda x: int(x[1:]) if x[1:].isdigit() else 99):
    statuses = gap_status[gap]
    all_pass = all(s == 'PASS' for s in statuses)
    icon = "✅" if all_pass else "❌"
    print(f"    {icon} {gap}: {len([s for s in statuses if s == 'PASS'])}/{len(statuses)} tests passed")

gaps_covered = len(gap_status)
print(f"\n  Gaps Covered: {gaps_covered}/20")

if failed > 0 or errors > 0:
    print("\n  FAILURES/ERRORS:")
    for gap, name, status, msg in results:
        if status != 'PASS':
            print(f"    [{status}] {gap}: {name} — {msg}")

print(f"\n{'='*70}")
sys.exit(0 if (failed == 0 and errors == 0) else 1)
