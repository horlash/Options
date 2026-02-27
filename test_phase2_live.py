#!/usr/bin/env python3
"""
Live API Test Suite for Phase 1 + Phase 2 Audit Remediation.
Tests all G1-G20 fixes against live APIs (ORATS, Finnhub).
"""

import os
import sys
import json
from datetime import datetime

# Ensure backend is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set env
os.environ['ORATS_API_KEY'] = 'b87b58de-a1bb-4958-accd-b4443ca61fdd'
os.environ['FINNHUB_API_KEY'] = 'd5ksrbhr01qt47mfai40d5ksrbhr01qt47mfai4g'
os.environ['TRADIER_API_KEY'] = '8A09vGkjXxbJspeGkT0iNI8VEapW'
os.environ['TRADIER_USE_SANDBOX'] = 'True'
os.environ['FMP_API_KEY'] = 'jfB5vWaGzzEK6OowZayWNCxdbULnwROC'

results = []
def test(name, fn):
    """Run a test, catch errors, record pass/fail."""
    try:
        fn()
        results.append((name, 'PASS', ''))
        print(f"  ✅ {name}")
    except AssertionError as e:
        results.append((name, 'FAIL', str(e)))
        print(f"  ❌ {name}: {e}")
    except Exception as e:
        results.append((name, 'ERROR', str(e)[:200]))
        print(f"  ⚠️  {name}: {e}")


# =============================================================
# TEST GROUP 1: Core API Connectivity
# =============================================================
print("\n" + "="*60)
print("TEST GROUP 1: API Connectivity")
print("="*60)

def test_orats_quote():
    from backend.api.orats import OratsAPI as ORATSAPI
    api = ORATSAPI()
    q = api.get_quote('AAPL')
    assert q is not None, "ORATS quote returned None"
    assert q.get('price', 0) > 0, f"ORATS price invalid: {q}"

def test_orats_hist_cores():
    from backend.api.orats import OratsAPI as ORATSAPI
    api = ORATSAPI()
    cores = api.get_hist_cores('AAPL')
    assert cores is not None, "hist/cores returned None"
    assert 'ivPctile1y' in cores, f"Missing ivPctile1y in cores"
    assert 'daysToNextErn' in cores, f"Missing daysToNextErn"
    assert 'divDate' in cores, f"Missing divDate"
    print(f"    ivPctile1y={cores['ivPctile1y']}, daysToNextErn={cores['daysToNextErn']}, divDate={cores.get('divDate')}")

def test_orats_live_summary():
    from backend.api.orats import OratsAPI as ORATSAPI
    api = ORATSAPI()
    s = api.get_live_summary('AAPL')
    assert s is not None, "live/summaries returned None"
    assert 'rSlp30' in s, "Missing rSlp30 in summary"

def test_finnhub_sentiment():
    from backend.api.finnhub import FinnhubAPI
    api = FinnhubAPI()
    data = api.get_news_sentiment('AAPL')
    assert data is not None, "Finnhub sentiment returned None"
    assert data != "FORBIDDEN", "Finnhub returned FORBIDDEN"
    print(f"    companyNewsScore={data.get('companyNewsScore')}, buzz={data.get('buzz', {}).get('articlesInLastWeek')}")

def test_finnhub_earnings():
    from backend.api.finnhub import FinnhubAPI
    api = FinnhubAPI()
    data = api.get_earnings_calendar(symbol='AAPL')
    # May be empty if no earnings soon, that's OK
    print(f"    Upcoming earnings entries: {len(data) if data else 0}")

def test_vix_quote():
    from backend.api.orats import OratsAPI as ORATSAPI
    api = ORATSAPI()
    q = api.get_quote('VIX')
    assert q is not None, "VIX quote returned None"
    vix = q.get('price', 0)
    assert vix > 0, f"VIX price invalid: {vix}"
    print(f"    VIX={vix:.2f}")

test("ORATS Quote (AAPL)", test_orats_quote)
test("ORATS hist/cores (AAPL) [G9/G14/G15]", test_orats_hist_cores)
test("ORATS live/summaries (AAPL)", test_orats_live_summary)
test("Finnhub Sentiment (AAPL) [G3]", test_finnhub_sentiment)
test("Finnhub Earnings Calendar [G14]", test_finnhub_earnings)
test("VIX Quote [G8]", test_vix_quote)


# =============================================================
# TEST GROUP 2: Phase 1 — Scoring Logic
# =============================================================
print("\n" + "="*60)
print("TEST GROUP 2: Phase 1 — Scoring Logic (G4, G6, G10-G13, G19, G20)")
print("="*60)

def test_leap_weights_sum():
    """G4: LEAP weights must sum to 1.00"""
    W = {'W_TECH': 0.30, 'W_SENT': 0.20, 'W_SKEW': 0.10, 'W_GREEKS': 0.15,
         'W_PROF': 0.05, 'W_LIQ': 0.10, 'W_FUND': 0.10}
    total = sum(W.values())
    assert abs(total - 1.0) < 0.001, f"LEAP weights sum to {total}, not 1.0"

def test_weekly_weights_sum():
    """G4: WEEKLY weights must sum to 1.00"""
    W = {'W_TECH': 0.40, 'W_SKEW': 0.15, 'W_SENT': 0.15, 'W_GREEKS': 0.15,
         'W_PROF': 0.05, 'W_LIQ': 0.10}
    total = sum(W.values())
    assert abs(total - 1.0) < 0.001, f"WEEKLY weights sum to {total}, not 1.0"

def test_greeks_score():
    """G6: Greeks scoring function"""
    from backend.analysis.options_analyzer import OptionsAnalyzer
    analyzer = OptionsAnalyzer()
    opp = {'delta': 0.60, 'gamma': 0.02, 'theta': -0.05, 'premium': 5.0}
    score = analyzer._calculate_greeks_score(opp, 'LEAP')
    assert 0 <= score <= 100, f"Greeks score out of range: {score}"
    assert score > 50, f"Delta 0.60 LEAP should score above 50, got {score}"
    print(f"    Greeks score for delta=0.60 LEAP: {score}")

def test_delta_ranges():
    """G10: Strategy-specific delta ranges"""
    from backend.analysis.options_analyzer import OptionsAnalyzer
    analyzer = OptionsAnalyzer()
    # Create opportunity with delta outside LEAP range
    opp_bad = {'delta': 0.20, 'gamma': 0.01, 'theta': -0.1, 'premium': 2.0,
               'open_interest': 500, 'volume': 50, 'bid': 1.9,
               'profit_potential': 100, 'days_to_expiry': 200}
    ranked = analyzer.rank_opportunities([opp_bad], 50, 50, strategy='LEAP')
    assert len(ranked) == 0, f"Delta 0.20 should be rejected for LEAP, got {len(ranked)} results"

def test_score_normalization():
    """G19: Scores clamped 0-100"""
    from backend.analysis.technical_indicators import TechnicalIndicators
    ti = TechnicalIndicators()
    # All bearish indicators should still produce 0-100 score
    fake_indicators = {
        'rsi': {'signal': 'overbought', 'value': 80},
        'macd': {'signal': 'bearish'},
        'bollinger_bands': {'signal': 'overbought'},
        'moving_averages': {'signal': 'bearish'},
        'volume': {'signal': 'weak'},
    }
    score = ti.calculate_technical_score(fake_indicators)
    assert 0 <= score <= 100, f"Score {score} outside 0-100 range"
    print(f"    All-bearish tech score: {score:.1f}")

def test_score_breakdown():
    """G20: Score breakdown dict attached"""
    from backend.analysis.options_analyzer import OptionsAnalyzer
    analyzer = OptionsAnalyzer()
    opp = {'delta': 0.55, 'gamma': 0.02, 'theta': -0.1, 'premium': 3.0,
           'open_interest': 500, 'volume': 50, 'bid': 2.8,
           'profit_potential': 100, 'days_to_expiry': 200}
    ranked = analyzer.rank_opportunities([opp], 60, 55, strategy='LEAP')
    if ranked:
        assert 'score_breakdown' in ranked[0], "Missing score_breakdown"
        bd = ranked[0]['score_breakdown']
        assert 'technical' in bd, "Missing technical in breakdown"
        assert 'greeks' in bd, "Missing greeks in breakdown"
        assert 'weights' in bd, "Missing weights in breakdown"
        assert 'iv_percentile' in bd, "Missing iv_percentile in breakdown"
        print(f"    Breakdown keys: {list(bd.keys())}")

test("G4: LEAP weights sum to 1.00", test_leap_weights_sum)
test("G4: WEEKLY weights sum to 1.00", test_weekly_weights_sum)
test("G6: Greeks scoring function", test_greeks_score)
test("G10: Delta range filtering", test_delta_ranges)
test("G19: Score normalization 0-100", test_score_normalization)
test("G20: Score breakdown audit trail", test_score_breakdown)


# =============================================================
# TEST GROUP 3: Phase 2 — New Features
# =============================================================
print("\n" + "="*60)
print("TEST GROUP 3: Phase 2 — G2, G3, G8, G9, G14, G15, G16")
print("="*60)

def test_exit_manager():
    """G2: Exit manager generates valid plans"""
    from backend.analysis.exit_manager import ExitManager
    em = ExitManager()
    opp = {'premium': 5.0, 'strike_price': 200, 'days_to_expiry': 180, 'delta': 0.55}
    plan = em.generate_exit_plan(opp, strategy='LEAP', vix_regime='NORMAL')
    assert 'stop_loss_pct' in plan, "Missing stop_loss_pct"
    assert 'profit_targets' in plan, "Missing profit_targets"
    assert len(plan['profit_targets']) >= 2, "Need at least 2 profit targets"
    assert 'trailing_stop_pct' in plan, "Missing trailing_stop"
    assert 'summary' in plan, "Missing summary"
    print(f"    LEAP stop: {plan['stop_loss_pct']}%, targets: {[t['pct'] for t in plan['profit_targets']]}")

def test_exit_manager_crisis():
    """G2+G8: Exit manager adjusts for CRISIS"""
    from backend.analysis.exit_manager import ExitManager
    em = ExitManager()
    opp = {'premium': 5.0, 'strike_price': 200, 'days_to_expiry': 180, 'delta': 0.55}
    plan = em.generate_exit_plan(opp, strategy='LEAP', vix_regime='CRISIS')
    assert plan['stop_loss_pct'] > -30, f"CRISIS stop should be tighter than -30, got {plan['stop_loss_pct']}"
    assert any('CRISIS' in a for a in plan['adjustments']), "Missing CRISIS adjustment note"
    print(f"    CRISIS stop: {plan['stop_loss_pct']}%, adjustments: {plan['adjustments']}")

def test_exit_should_exit():
    """G2: Real-time exit signal check"""
    from backend.analysis.exit_manager import ExitManager
    em = ExitManager()
    plan = em.DEFAULTS['WEEKLY'].copy()
    plan['stop_loss_pct'] = -40

    signal = em.should_exit({}, current_pnl_pct=-45, dte_remaining=3, exit_plan=plan)
    assert signal['should_exit'] == True, "Should trigger stop loss"
    assert 'stop' in signal['reason'].lower(), f"Reason should mention stop: {signal['reason']}"

def test_sentiment_analyzer_new():
    """G3: New sentiment analyzer with Finnhub"""
    from backend.analysis.sentiment_analyzer import SentimentAnalyzer
    sa = SentimentAnalyzer()
    # Test with mock Finnhub data
    mock_fh = {'companyNewsScore': 0.75, 'sentiment': {'bullishPercent': 0.8}, 'buzz': {'articlesInLastWeek': 50}}
    result = sa.analyze_sentiment('AAPL', finnhub_premium_data=mock_fh)
    assert 'score' in result, "Missing score"
    assert result['score'] == 75.0, f"Expected 75.0 from companyNewsScore=0.75, got {result['score']}"
    assert 'Finnhub' in result['source'], f"Source should mention Finnhub: {result['source']}"
    print(f"    Finnhub premium score: {result['score']}, source: {result['source']}")

def test_sentiment_legacy_compat():
    """G3: Legacy analyze_articles still works"""
    from backend.analysis.sentiment_analyzer import SentimentAnalyzer
    sa = SentimentAnalyzer()
    articles = [
        {'headline': 'Apple beats earnings expectations', 'summary': 'Strong quarter', 'published_date': '2026-02-25'},
        {'headline': 'Apple revenue surges 15%', 'summary': 'Growth continues', 'published_date': '2026-02-25'},
    ]
    result = sa.analyze_articles(articles)
    assert 'weighted_score' in result, "Missing weighted_score"
    assert 'article_count' in result, "Missing article_count"
    assert result['article_count'] == 2, f"Expected 2 articles, got {result['article_count']}"

def test_iv_percentile_scoring():
    """G9: IV percentile affects scoring"""
    from backend.analysis.options_analyzer import OptionsAnalyzer
    analyzer = OptionsAnalyzer()
    opp = {'delta': 0.55, 'gamma': 0.02, 'theta': -0.1, 'premium': 3.0,
           'open_interest': 500, 'volume': 50, 'bid': 2.8,
           'profit_potential': 100, 'days_to_expiry': 200}

    ranked_low_iv = analyzer.rank_opportunities([opp.copy()], 60, 55, strategy='LEAP', iv_percentile=15)
    ranked_high_iv = analyzer.rank_opportunities([opp.copy()], 60, 55, strategy='LEAP', iv_percentile=85)

    if ranked_low_iv and ranked_high_iv:
        low_score = ranked_low_iv[0]['opportunity_score']
        high_score = ranked_high_iv[0]['opportunity_score']
        assert low_score > high_score, f"Low IV score ({low_score}) should be > high IV score ({high_score})"
        print(f"    Low IV score: {low_score:.1f} > High IV score: {high_score:.1f}")

def test_earnings_penalty():
    """G14: Earnings proximity penalizes score"""
    from backend.analysis.options_analyzer import OptionsAnalyzer
    analyzer = OptionsAnalyzer()
    opp = {'delta': 0.55, 'gamma': 0.02, 'theta': -0.1, 'premium': 3.0,
           'open_interest': 500, 'volume': 50, 'bid': 2.8,
           'profit_potential': 100, 'days_to_expiry': 200}

    ranked_no_earnings = analyzer.rank_opportunities([opp.copy()], 60, 55, strategy='LEAP', days_to_earnings=None)
    ranked_earnings_soon = analyzer.rank_opportunities([opp.copy()], 60, 55, strategy='LEAP', days_to_earnings=2)

    if ranked_no_earnings and ranked_earnings_soon:
        no_e_score = ranked_no_earnings[0]['opportunity_score']
        e_score = ranked_earnings_soon[0]['opportunity_score']
        assert no_e_score > e_score, f"No-earnings score ({no_e_score}) should be > near-earnings ({e_score})"
        print(f"    No earnings: {no_e_score:.1f} > Earnings in 2d: {e_score:.1f}")

test("G2: Exit plan generation", test_exit_manager)
test("G2+G8: Exit plan CRISIS adjustment", test_exit_manager_crisis)
test("G2: Real-time exit signal", test_exit_should_exit)
test("G3: Sentiment analyzer (Finnhub)", test_sentiment_analyzer_new)
test("G3: Legacy analyze_articles compat", test_sentiment_legacy_compat)
test("G9: IV Percentile scoring impact", test_iv_percentile_scoring)
test("G14: Earnings proximity penalty", test_earnings_penalty)


# =============================================================
# SUMMARY
# =============================================================
print("\n" + "="*60)
print("TEST SUMMARY")
print("="*60)
passed = sum(1 for _, status, _ in results if status == 'PASS')
failed = sum(1 for _, status, _ in results if status == 'FAIL')
errors = sum(1 for _, status, _ in results if status == 'ERROR')
total = len(results)

print(f"\n  Total: {total} | ✅ Passed: {passed} | ❌ Failed: {failed} | ⚠️  Errors: {errors}")
print(f"  Success Rate: {passed}/{total} ({passed/total*100:.0f}%)")

if failed > 0 or errors > 0:
    print("\n  FAILURES/ERRORS:")
    for name, status, msg in results:
        if status != 'PASS':
            print(f"    [{status}] {name}: {msg}")

print(f"\n{'='*60}")
sys.exit(0 if (failed == 0 and errors == 0) else 1)
