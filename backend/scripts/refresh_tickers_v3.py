#!/usr/bin/env python3
"""
ORATS-Based Ticker Refresh Script (v3)

Replaces Schwab-based refresh_tickers_v2.py.
1. Fetches ORATS ticker universe (~5,000+ symbols with date ranges)
2. Cross-references with existing FMP-based tickers.json
3. Tags each ticker with orats_covered + date range
4. Saves orats_universe.json (fast O(1) lookup cache)
5. Saves enriched tickers.json

Usage:
    python backend/scripts/refresh_tickers_v3.py
"""

import os
import sys
import json
import requests
from datetime import datetime
from pathlib import Path

# Auto-detect project root
script_dir = Path(__file__).parent
project_root = script_dir.parent.parent
sys.path.insert(0, str(project_root))

# File paths
ORATS_UNIVERSE_FILE = project_root / 'backend' / 'data' / 'orats_universe.json'
TICKERS_FILE = project_root / 'backend' / 'data' / 'tickers.json'

# Load ORATS API key
from dotenv import load_dotenv
load_dotenv(project_root / '.env')
ORATS_API_KEY = os.getenv("ORATS_API_KEY")
ORATS_BASE_URL = "https://api.orats.io/datav2"


def fetch_orats_universe():
    """Fetch complete ORATS ticker universe from /datav2/tickers."""
    print("=" * 70)
    print("ORATS TICKER UNIVERSE REFRESH (v3)")
    print("=" * 70)
    
    if not ORATS_API_KEY:
        print("❌ ORATS_API_KEY not found in environment variables.")
        return None
    
    print(f"\n[1/4] Fetching ORATS ticker universe...")
    url = f"{ORATS_BASE_URL}/tickers"
    params = {"token": ORATS_API_KEY}
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        raw_tickers = data.get("data", [])
        print(f"✅ Received {len(raw_tickers)} tickers from ORATS")
        
        # Build universe dict (O(1) lookup)
        universe = {}
        for t in raw_tickers:
            ticker = t.get("ticker", "")
            if ticker:
                universe[ticker] = {
                    "minDate": t.get("minDate"),
                    "maxDate": t.get("maxDate")
                }
        
        return universe
        
    except requests.exceptions.HTTPError as e:
        print(f"❌ ORATS API Error: {e}")
        return None
    except Exception as e:
        print(f"❌ Connection Error: {e}")
        return None


def save_orats_universe(universe):
    """Save ORATS universe to orats_universe.json."""
    print(f"\n[2/4] Saving ORATS universe to {ORATS_UNIVERSE_FILE.name}...")
    
    output = {
        "last_updated": datetime.now().isoformat(),
        "source": "ORATS /datav2/tickers",
        "count": len(universe),
        "tickers": universe
    }
    
    with open(ORATS_UNIVERSE_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2)
    
    # Stats
    active_count = 0
    for ticker, info in universe.items():
        max_date = info.get("maxDate", "")
        if max_date:
            try:
                md = datetime.strptime(max_date, "%Y-%m-%d")
                if (datetime.now() - md).days <= 7:
                    active_count += 1
            except:
                pass
    
    print(f"✅ Saved {len(universe)} tickers ({active_count} actively traded)")
    file_size = ORATS_UNIVERSE_FILE.stat().st_size / 1024
    print(f"   File size: {file_size:.0f} KB")


def enrich_tickers_json(universe):
    """Cross-reference FMP tickers with ORATS universe."""
    print(f"\n[3/4] Enriching {TICKERS_FILE.name} with ORATS coverage...")
    
    if not TICKERS_FILE.exists():
        print(f"⚠️ {TICKERS_FILE.name} not found. Skipping enrichment.")
        return
    
    with open(TICKERS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    tickers = data.get('tickers', [])
    original_count = len(tickers)
    covered_count = 0
    not_covered_count = 0
    
    for t in tickers:
        symbol = t.get('symbol', '').upper()
        
        if symbol in universe:
            t['orats_covered'] = True
            t['orats_min_date'] = universe[symbol].get('minDate')
            t['orats_max_date'] = universe[symbol].get('maxDate')
            covered_count += 1
        else:
            t['orats_covered'] = False
            t.pop('orats_min_date', None)
            t.pop('orats_max_date', None)
            not_covered_count += 1
    
    # Update metadata
    data['last_updated'] = datetime.now().isoformat()
    data['source'] = 'FMP + ORATS Coverage'
    data['orats_coverage_stats'] = {
        'total_fmp': original_count,
        'orats_covered': covered_count,
        'not_covered': not_covered_count,
        'coverage_pct': round(covered_count / max(original_count, 1) * 100, 1)
    }
    
    with open(TICKERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    
    print(f"✅ Enriched {original_count} tickers:")
    print(f"   ORATS covered: {covered_count} ({data['orats_coverage_stats']['coverage_pct']}%)")
    print(f"   Not covered:   {not_covered_count}")


def print_summary(universe):
    """Print summary statistics."""
    print(f"\n[4/4] Summary:")
    print(f"{'=' * 50}")
    print(f"  ORATS Universe: {len(universe)} tickers")
    
    # Show some sample tickers
    sample_indexes = ['$SPX.X', '$NDX.X', '$VIX.X', '$DJX.X']
    sample_stocks = ['AAPL', 'MSFT', 'NVDA', 'SPY', 'QQQ']
    
    print(f"\n  Index Coverage:")
    for idx in sample_indexes:
        info = universe.get(idx)
        if info:
            print(f"    ✅ {idx:10s} ({info['minDate']} to {info['maxDate']})")
        else:
            print(f"    ❌ {idx:10s} (not found)")
    
    print(f"\n  Sample Stock Coverage:")
    for stock in sample_stocks:
        info = universe.get(stock)
        if info:
            print(f"    ✅ {stock:10s} ({info['minDate']} to {info['maxDate']})")
        else:
            print(f"    ❌ {stock:10s} (not found)")
    
    # Check RUT
    rut_info = universe.get('RUT') or universe.get('$RUT.X')
    if rut_info:
        print(f"\n  ⚠️ RUT found in universe (use with caution — inconsistent coverage)")
    else:
        print(f"\n  ℹ️ RUT not in ORATS universe (expected — inconsistent coverage)")
    
    print(f"\n✅ Ticker refresh complete!")
    print(f"   ORATS universe: {ORATS_UNIVERSE_FILE}")
    print(f"   Enriched list:  {TICKERS_FILE}")


if __name__ == "__main__":
    universe = fetch_orats_universe()
    if universe:
        save_orats_universe(universe)
        enrich_tickers_json(universe)
        print_summary(universe)
    else:
        print("\n❌ Failed to fetch ORATS universe. Aborting.")
        sys.exit(1)
