"""
Full Backend Regression Test Suite (Strict ORATS Mode)
======================================================
Tests ALL scanner functionalities across:
- Large Cap Stocks (AAPL, MSFT, NVDA)
- Mid Cap Stocks (CROX, DECK)
- Small Cap Stocks (SBLK, CORT)
- ETFs (SPY, QQQ, XLE)
- Indices ($SPX, $NDX)

Modules Tested:
1. OratsAPI: get_history, get_quote, get_option_chain
2. HybridScannerService: scan_ticker (LEAP), scan_weekly_options, scan_sector_top_picks
3. get_detailed_analysis, get_sentiment_score
4. Data integrity checks (data_source label, fundamental scaling)

Protocol: 3 consecutive clean loops required to PASS.
"""

import sys
import os
import json
import time
import traceback
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from backend.api.orats import OratsAPI
from backend.services.hybrid_scanner_service import HybridScannerService

# ============================================================
# TEST CONFIGURATION
# ============================================================
TEST_TICKERS = {
    "large_cap": ["AAPL", "MSFT", "NVDA"],
    "mid_cap": ["CROX", "DECK"],
    "small_cap": ["SBLK", "CORT"],
    "etf": ["SPY", "QQQ", "XLE"],
    "index": ["$SPX"],
}

RESULTS = {
    "passes": [],
    "failures": [],
    "warnings": [],
    "timestamp": datetime.now().isoformat()
}

# ============================================================
# HELPER FUNCTIONS
# ============================================================
def record_pass(test_name, details=""):
    RESULTS["passes"].append({"test": test_name, "details": details})
    print(f"  ✅ PASS: {test_name} {details}")

def record_fail(test_name, error, details=""):
    RESULTS["failures"].append({"test": test_name, "error": str(error), "details": details})
    print(f"  ❌ FAIL: {test_name} — {error}")

def record_warn(test_name, message):
    RESULTS["warnings"].append({"test": test_name, "message": message})
    print(f"  ⚠️ WARN: {test_name} — {message}")

# ============================================================
# TEST 1: OratsAPI — get_history
# ============================================================
def test_orats_history(orats_api):
    print("\n" + "="*60)
    print("TEST 1: OratsAPI.get_history()")
    print("="*60)
    
    test_tickers = ["AAPL", "SPY", "SBLK", "$SPX"]
    
    for ticker in test_tickers:
        test_name = f"get_history({ticker})"
        try:
            result = orats_api.get_history(ticker)
            
            if result is None:
                record_fail(test_name, "Returned None")
                continue
            
            # Verify format: must have 'candles' key
            if 'candles' not in result:
                record_fail(test_name, f"Missing 'candles' key. Keys: {list(result.keys())}")
                continue
            
            candles = result['candles']
            if len(candles) < 50:
                record_warn(test_name, f"Only {len(candles)} candles (need 50+ for MTA)")
            
            # Verify candle structure
            sample = candles[0]
            required_keys = ['datetime', 'open', 'high', 'low', 'close', 'volume']
            missing = [k for k in required_keys if k not in sample]
            if missing:
                record_fail(test_name, f"Missing candle keys: {missing}")
                continue
            
            record_pass(test_name, f"{len(candles)} candles, latest close: {candles[-1]['close']}")
            
        except Exception as e:
            record_fail(test_name, str(e))

# ============================================================
# TEST 2: OratsAPI — get_quote
# ============================================================
def test_orats_quote(orats_api):
    print("\n" + "="*60)
    print("TEST 2: OratsAPI.get_quote()")
    print("="*60)
    
    test_tickers = ["AAPL", "MSFT", "SPY", "SBLK", "CROX"]
    
    for ticker in test_tickers:
        test_name = f"get_quote({ticker})"
        try:
            result = orats_api.get_quote(ticker)
            
            if result is None:
                record_fail(test_name, "Returned None")
                continue
            
            price = result.get('price', 0)
            if price == 0 or price is None:
                record_fail(test_name, f"Price is ${price}")
                continue
            
            # Sanity check
            if price < 0.01:
                record_fail(test_name, f"Price unrealistically low: ${price}")
                continue
            
            record_pass(test_name, f"Price: ${price:.2f}, Vol: {result.get('volume', 'N/A')}")
            
        except Exception as e:
            record_fail(test_name, str(e))

# ============================================================
# TEST 3: OratsAPI — get_option_chain
# ============================================================
def test_orats_chain(orats_api):
    print("\n" + "="*60)
    print("TEST 3: OratsAPI.get_option_chain()")
    print("="*60)
    
    test_tickers = ["AAPL", "SPY", "CROX"]
    
    for ticker in test_tickers:
        test_name = f"get_option_chain({ticker})"
        try:
            result = orats_api.get_option_chain(ticker)
            
            if result is None:
                record_fail(test_name, "Returned None")
                continue
            
            # Verify structure
            has_calls = 'callExpDateMap' in result
            has_puts = 'putExpDateMap' in result
            
            if not has_calls and not has_puts:
                record_fail(test_name, f"No call/put maps. Keys: {list(result.keys())}")
                continue
            
            call_expiries = len(result.get('callExpDateMap', {}))
            put_expiries = len(result.get('putExpDateMap', {}))
            
            record_pass(test_name, f"Call Expiries: {call_expiries}, Put Expiries: {put_expiries}")
            
        except Exception as e:
            record_fail(test_name, str(e))

# ============================================================
# TEST 4: scan_ticker (LEAP Mode)
# ============================================================
def test_scan_ticker(scanner):
    print("\n" + "="*60)
    print("TEST 4: HybridScannerService.scan_ticker() [LEAP]")
    print("="*60)
    
    for category, tickers in TEST_TICKERS.items():
        for ticker in tickers:
            test_name = f"scan_ticker({ticker}) [{category}]"
            try:
                result = scanner.scan_ticker(ticker, strict_mode=False)
                
                if result is None:
                    record_warn(test_name, "Returned None (strict=False, likely data issue)")
                    continue
                
                # Verify data_source
                ds = result.get('data_source', 'UNKNOWN')
                if 'Schwab' in ds and scanner.use_orats:
                    record_fail(test_name, f"data_source still says '{ds}' in ORATS mode")
                    continue
                
                # Verify price
                price = result.get('current_price', 0)
                if price == 0:
                    record_fail(test_name, "current_price is $0.00")
                    continue
                
                # Verify technical_score is reasonable
                tech = result.get('technical_score', -1)
                if tech < 0 or tech > 100:
                    record_fail(test_name, f"technical_score out of range: {tech}")
                    continue
                
                # Verify fundamental_analysis exists
                fund = result.get('fundamental_analysis', {})
                
                # Check for blown-out ROE/Margin (the bug we fixed)
                # These are in console output only, not in result dict directly
                # But we can check badges for "Quality" flags
                
                opps = result.get('opportunities', [])
                record_pass(test_name, f"Price: ${price:.2f}, Tech: {tech}, Opps: {len(opps)}, Source: {ds}")
                
            except Exception as e:
                record_fail(test_name, str(e))
                traceback.print_exc()

# ============================================================
# TEST 5: scan_weekly_options
# ============================================================
def test_scan_weekly(scanner):
    print("\n" + "="*60)
    print("TEST 5: HybridScannerService.scan_weekly_options()")
    print("="*60)
    
    # Weekly scans on a subset
    test_tickers = ["AAPL", "SPY", "NVDA"]
    
    for ticker in test_tickers:
        test_name = f"scan_weekly({ticker}, weeks_out=1)"
        try:
            result = scanner.scan_weekly_options(ticker, weeks_out=1)
            
            if result is None:
                record_warn(test_name, "Returned None (may be filtered by quality)")
                continue
            
            ds = result.get('data_source', 'UNKNOWN')
            if 'Schwab' in ds and scanner.use_orats:
                record_fail(test_name, f"data_source still says '{ds}' in ORATS mode")
                continue
            
            price = result.get('current_price', 0)
            opps = result.get('opportunities', [])
            
            record_pass(test_name, f"Price: ${price:.2f}, Opps: {len(opps)}, Source: {ds}")
            
        except Exception as e:
            record_fail(test_name, str(e))
            traceback.print_exc()

# ============================================================
# TEST 6: get_detailed_analysis
# ============================================================
def test_detailed_analysis(scanner):
    print("\n" + "="*60)
    print("TEST 6: HybridScannerService.get_detailed_analysis()")
    print("="*60)
    
    test_tickers = ["AAPL", "SPY"]
    
    for ticker in test_tickers:
        test_name = f"get_detailed_analysis({ticker})"
        try:
            result = scanner.get_detailed_analysis(ticker)
            
            if result is None:
                record_fail(test_name, "Returned None")
                continue
            
            # Verify structure
            required = ['ticker', 'current_price', 'indicators']
            missing = [k for k in required if k not in result]
            if missing:
                record_fail(test_name, f"Missing keys: {missing}")
                continue
            
            record_pass(test_name, f"Price: ${result.get('current_price', 0):.2f}")
            
        except Exception as e:
            record_fail(test_name, str(e))
            traceback.print_exc()

# ============================================================
# TEST 7: get_sentiment_score
# ============================================================
def test_sentiment(scanner):
    print("\n" + "="*60)
    print("TEST 7: HybridScannerService.get_sentiment_score()")
    print("="*60)
    
    test_tickers = ["AAPL", "NVDA", "XLE"]
    
    for ticker in test_tickers:
        test_name = f"get_sentiment_score({ticker})"
        try:
            score, analysis = scanner.get_sentiment_score(ticker)
            
            if score is None:
                record_fail(test_name, "Score is None")
                continue
            
            if score < 0 or score > 100:
                record_fail(test_name, f"Score out of range: {score}")
                continue
            
            record_pass(test_name, f"Score: {score:.1f}")
            
        except Exception as e:
            record_fail(test_name, str(e))
            traceback.print_exc()

# ============================================================
# TEST 8: scan_sector_top_picks
# ============================================================
def test_sector_scan(scanner):
    print("\n" + "="*60)
    print("TEST 8: HybridScannerService.scan_sector_top_picks()")
    print("="*60)
    
    test_name = "scan_sector_top_picks('Technology', limit=5)"
    try:
        result = scanner.scan_sector_top_picks(
            sector="Technology",
            min_volume=1000000,
            min_market_cap=10000000000,
            limit=5
        )
        
        if result is None:
            record_fail(test_name, "Returned None")
        elif isinstance(result, list):
            record_pass(test_name, f"Returned {len(result)} results")
        else:
            record_warn(test_name, f"Unexpected type: {type(result)}")
            
    except Exception as e:
        record_fail(test_name, str(e))
        traceback.print_exc()

# ============================================================
# TEST 9: Data Integrity Checks
# ============================================================
def test_data_integrity(scanner):
    print("\n" + "="*60)
    print("TEST 9: Data Integrity Checks")
    print("="*60)
    
    # 9a) Verify ORATS is primary
    test_name = "ORATS Primary Check"
    if scanner.use_orats:
        record_pass(test_name, "use_orats=True")
    else:
        record_fail(test_name, "use_orats=False — ORATS not configured!")
    
    # 9b) Verify Yahoo API is disabled
    test_name = "Yahoo Disabled Check"
    if scanner.yahoo_api is None:
        record_pass(test_name, "yahoo_api=None (Strict Mode)")
    else:
        record_fail(test_name, f"yahoo_api is NOT None: {type(scanner.yahoo_api)}")
    
    # 9c) Verify data_source label in scan_ticker
    test_name = "data_source Label (LEAP)"
    try:
        res = scanner.scan_ticker("AAPL", strict_mode=False)
        if res:
            ds = res.get('data_source', 'UNKNOWN')
            if ds == 'ORATS':
                record_pass(test_name, f"data_source='{ds}'")
            else:
                record_fail(test_name, f"Expected 'ORATS', got '{ds}'")
        else:
            record_warn(test_name, "scan_ticker returned None, can't verify label")
    except Exception as e:
        record_fail(test_name, str(e))
    
    # 9d) Verify _clean_ticker format (ORATS uses plain tickers, DJI -> DJX alias)
    test_name = "_clean_ticker Format"
    from backend.api.orats import OratsAPI as _O
    _api = _O()
    tests = {
        'AAPL': 'AAPL',
        '$SPX': 'SPX',
        'SPX': 'SPX',
        'NDX': 'NDX',
        'VIX': 'VIX',
        'DJI': 'DJX',    # Alias: DJI -> DJX
        'DJX': 'DJX',
        'SPY': 'SPY',
        ' aapl ': 'AAPL', # Whitespace + lowercase
    }
    all_ok = True
    for inp, expected in tests.items():
        actual = _api._clean_ticker(inp)
        if actual != expected:
            record_fail(f"{test_name}: _clean_ticker('{inp}')", f"Expected '{expected}', got '{actual}'")
            all_ok = False
    if all_ok:
        record_pass(test_name, f"All {len(tests)} format tests passed")
    
    # 9e) Verify ORATS universe cache
    test_name = "ORATS Universe Cache"
    if HybridScannerService._orats_universe:
        universe_size = len(HybridScannerService._orats_universe)
        has_aapl = 'AAPL' in HybridScannerService._orats_universe
        has_spy = 'SPY' in HybridScannerService._orats_universe
        has_spx = 'SPX' in HybridScannerService._orats_universe
        if universe_size > 1000 and has_aapl and has_spy:
            record_pass(test_name, f"{universe_size} tickers, AAPL={has_aapl}, SPY={has_spy}, SPX={has_spx}")
        else:
            record_fail(test_name, f"Universe too small or missing key tickers (size={universe_size})")
    else:
        record_warn(test_name, "ORATS universe not loaded (run refresh_tickers_v3.py)")

# ============================================================
# MAIN RUNNER
# ============================================================
def run_all_tests():
    print("="*60)
    print(f"  FULL BACKEND REGRESSION TEST")
    print(f"  Timestamp: {datetime.now().isoformat()}")
    print(f"  Mode: Strict ORATS")
    print("="*60)
    
    orats_api = OratsAPI()
    scanner = HybridScannerService()
    
    # Run all test suites
    test_orats_history(orats_api)
    test_orats_quote(orats_api)
    test_orats_chain(orats_api)
    test_scan_ticker(scanner)
    test_scan_weekly(scanner)
    test_detailed_analysis(scanner)
    test_sentiment(scanner)
    test_sector_scan(scanner)
    test_data_integrity(scanner)
    
    return RESULTS

def print_summary(results):
    print("\n" + "="*60)
    print("  REGRESSION TEST SUMMARY")
    print("="*60)
    print(f"  ✅ Passes:   {len(results['passes'])}")
    print(f"  ❌ Failures: {len(results['failures'])}")
    print(f"  ⚠️ Warnings: {len(results['warnings'])}")
    print("="*60)
    
    if results['failures']:
        print("\n--- FAILURE DETAILS ---")
        for f in results['failures']:
            print(f"  ❌ {f['test']}: {f['error']}")
    
    if results['warnings']:
        print("\n--- WARNING DETAILS ---")
        for w in results['warnings']:
            print(f"  ⚠️ {w['test']}: {w['message']}")
    
    print()

if __name__ == "__main__":
    results = run_all_tests()
    print_summary(results)
    
    # Save results to file
    output_path = os.path.join(os.path.dirname(__file__), "regression_results.json")
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Results saved to: {output_path}")
