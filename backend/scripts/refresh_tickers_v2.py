#!/usr/bin/env python3
"""
Enhanced Ticker List Refresh Script (Schwab-based)

Fetches and validates tickers from multiple sources with Schwab as primary validator.
Implements batch processing, rate limiting, and progress checkpointing.

Usage:
    python backend/scripts/refresh_tickers_v2.py
"""

import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path

# Auto-detect project root
script_dir = Path(__file__).parent
project_root = script_dir.parent.parent
sys.path.insert(0, str(project_root))

from backend.api.schwab import SchwabAPI

# Configuration
BATCH_SIZE = 100
RATE_LIMIT_DELAY = 1.0  # seconds between batches
CHECKPOINT_INTERVAL = 1000  # Save progress every N tickers
OUTPUT_FILE = project_root / 'backend' / 'data' / 'tickers.json'
CHECKPOINT_FILE = project_root / 'backend' / 'data' / 'tickers_checkpoint.json'

# High-Priority Manual Tickers (Always Include)
PRIORITY_TICKERS = {
    # Major Indices
    'SPX': {'name': 'S&P 500 Index', 'exchange': 'INDEX', 'sector': 'Index'},
    'NDX': {'name': 'Nasdaq 100 Index', 'exchange': 'INDEX', 'sector': 'Index'},
    'DJI': {'name': 'Dow Jones Industrial Average', 'exchange': 'INDEX', 'sector': 'Index'},
    'RUT': {'name': 'Russell 2000 Index', 'exchange': 'INDEX', 'sector': 'Index'},
    'VIX': {'name': 'CBOE Volatility Index', 'exchange': 'INDEX', 'sector': 'Index'},
    
    # Popular ETFs
    'SPY': {'name': 'SPDR S&P 500 ETF Trust', 'exchange': 'NYSE', 'sector': 'Index'},
    'QQQ': {'name': 'Invesco QQQ Trust', 'exchange': 'NASDAQ', 'sector': 'Technology'},
    'IWM': {'name': 'iShares Russell 2000 ETF', 'exchange': 'NYSE', 'sector': 'Index'},
    'DIA': {'name': 'SPDR Dow Jones Industrial Average ETF', 'exchange': 'NYSE', 'sector': 'Index'},
    'TLT': {'name': 'iShares 20+ Year Treasury Bond ETF', 'exchange': 'NASDAQ', 'sector': 'Bonds'},
    'GLD': {'name': 'SPDR Gold Trust', 'exchange': 'NYSE', 'sector': 'Commodities'},
    'SLV': {'name': 'iShares Silver Trust', 'exchange': 'NYSE', 'sector': 'Commodities'},
    'VXX': {'name': 'iPath Series B S&P 500 VIX Short-Term Futures ETN', 'exchange': 'NYSE', 'sector': 'Volatility'},
    
    # Mega-Cap Stocks
    'AAPL': {'name': 'Apple Inc', 'exchange': 'NASDAQ', 'sector': 'Technology'},
    'MSFT': {'name': 'Microsoft Corporation', 'exchange': 'NASDAQ', 'sector': 'Technology'},
    'GOOGL': {'name': 'Alphabet Inc Class A', 'exchange': 'NASDAQ', 'sector': 'Technology'},
    'AMZN': {'name': 'Amazon.com Inc', 'exchange': 'NASDAQ', 'sector': 'Consumer Cyclical'},
    'NVDA': {'name': 'NVIDIA Corporation', 'exchange': 'NASDAQ', 'sector': 'Technology'},
    'TSLA': {'name': 'Tesla Inc', 'exchange': 'NASDAQ', 'sector': 'Consumer Cyclical'},
    'META': {'name': 'Meta Platforms Inc', 'exchange': 'NASDAQ', 'sector': 'Technology'},
    'AMD': {'name': 'Advanced Micro Devices Inc', 'exchange': 'NASDAQ', 'sector': 'Technology'},
    'PLTR': {'name': 'Palantir Technologies Inc', 'exchange': 'NYSE', 'sector': 'Technology'},
    
    # Meme Stocks & High Volume
    'GME': {'name': 'GameStop Corp', 'exchange': 'NYSE', 'sector': 'Consumer Cyclical'},
    'AMC': {'name': 'AMC Entertainment Holdings Inc', 'exchange': 'NYSE', 'sector': 'Consumer Cyclical'},
    
    # Recent Additions
    'SNDK': {'name': 'SanDisk Corporation', 'exchange': 'NASDAQ', 'sector': 'Technology'},
    'WDC': {'name': 'Western Digital Corporation', 'exchange': 'NASDAQ', 'sector': 'Technology'},
}

def load_checkpoint():
    """Load progress checkpoint if exists"""
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, 'r') as f:
            return json.load(f)
    return None

def save_checkpoint(data):
    """Save progress checkpoint"""
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump(data, f)

def load_existing_tickers():
    """Load existing ticker list as base"""
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            tickers_data = data.get('tickers', {})
            
            # Handle both list and dict formats
            if isinstance(tickers_data, list):
                # Convert list to dict
                tickers = {t['symbol']: t for t in tickers_data if 'symbol' in t}
                print(f"✅ Loaded {len(tickers)} existing tickers from {OUTPUT_FILE.name} (converted from list)")
            else:
                tickers = tickers_data
                print(f"✅ Loaded {len(tickers)} existing tickers from {OUTPUT_FILE.name}")
            
            return tickers
    print("⚠️  No existing tickers.json found. Starting fresh.")
    return {}

def validate_with_schwab(symbol, schwab_api):
    """Validate and enrich ticker data via Schwab API"""
    try:
        import schwab.client
        result = schwab_api.client.get_instruments(
            symbol,
            schwab.client.Client.Instrument.Projection.FUNDAMENTAL
        )
        
        if result.status_code == 200:
            data = result.json()
            if data and symbol in data:
                instrument = data[symbol]
                return {
                    'symbol': instrument.get('symbol', symbol),
                    'name': instrument.get('description', ''),
                    'exchange': instrument.get('exchange', 'US'),
                    'sector': instrument.get('sector'),
                    'industry': instrument.get('industry'),
                    'assetType': instrument.get('assetType'),
                    'validated': True,
                    'validated_date': datetime.now().isoformat()
                }
        return None
    except Exception as e:
        # Silently skip errors to avoid overwhelming output
        return None

def refresh_tickers():
    """Main refresh function"""
    print("=" * 70)
    print("ENHANCED TICKER REFRESH (Schwab-based)")
    print("=" * 70)
    print(f"Project root: {project_root}")
    print(f"Output: {OUTPUT_FILE}\n")
    
    # Initialize Schwab API
    print("[1/6] Initializing Schwab API...")
    schwab_api = SchwabAPI()
    if not schwab_api.is_configured():
        print("❌ Schwab API not configured! Cannot proceed with validation.")
        print("Please ensure token.json exists and is valid.")
        return
    print("✅ Schwab API ready\n")
    
    # Load existing tickers as base
    print("[2/6] Loading existing ticker list...")
    all_tickers = load_existing_tickers()
    original_count = len(all_tickers)
    
    # Add priority tickers first
    print("\n[3/6] Adding priority tickers...")
    for symbol, data in PRIORITY_TICKERS.items():
        if symbol not in all_tickers:
            all_tickers[symbol] = data
            print(f"  ➕ {symbol}")
        else:
            # Update if existing
            all_tickers[symbol].update(data)
    print(f"✅ Priority tickers: {len(PRIORITY_TICKERS)}\n")
    
    # Check for checkpoint
    checkpoint = load_checkpoint()
    start_index = 0
    if checkpoint:
        print(f"📌 Found checkpoint: {checkpoint['processed']}/{checkpoint['total']} tickers processed")
        response = input("Resume from checkpoint? (y/n): ")
        if response.lower() == 'y':
            start_index = checkpoint['processed']
            all_tickers = checkpoint['tickers']
    
    # Validate existing tickers with Schwab
    print(f"\n[4/6] Validating tickers with Schwab API...")
    print(f"Total to validate: {len(all_tickers)}")
    print(f"Batch size: {BATCH_SIZE}, Rate limit: {RATE_LIMIT_DELAY}s/batch\n")
    
    ticker_list = list(all_tickers.keys())
    validated_count = 0
    failed_count = 0
    
    for i in range(start_index, len(ticker_list), BATCH_SIZE):
        batch = ticker_list[i:i+BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        total_batches = (len(ticker_list) + BATCH_SIZE - 1) // BATCH_SIZE
        
        print(f"Batch {batch_num}/{total_batches} ({len(batch)} symbols)...")
        
        for symbol in batch:
            validated_data = validate_with_schwab(symbol, schwab_api)
            if validated_data:
                all_tickers[symbol].update(validated_data)
                validated_count += 1
            else:
                failed_count += 1
        
        # Rate limiting
        if i + BATCH_SIZE < len(ticker_list):
            time.sleep(RATE_LIMIT_DELAY)
        
        # Checkpoint
        if (i + BATCH_SIZE) % CHECKPOINT_INTERVAL == 0:
            save_checkpoint({
                'processed': i + BATCH_SIZE,
                'total': len(ticker_list),
                'tickers': all_tickers,
                'timestamp': datetime.now().isoformat()
            })
            print(f"  💾 Checkpoint saved")
    
    print(f"\n✅ Validation complete!")
    print(f"  Validated: {validated_count}")
    print(f"  Failed: {failed_count}")
    print(f"  Total tickers: {len(all_tickers)}")
    
    # Save final output
    print(f"\n[5/6] Saving to {OUTPUT_FILE.name}...")
    
    # Convert dict back to list for consistency with original format
    tickers_list = list(all_tickers.values())
    
    output_data = {
        'last_updated': datetime.now().isoformat(),
        'source': 'Schwab API + Manual Priority List',
        'count': len(tickers_list),
        'validated_count': validated_count,
        'tickers': tickers_list
    }
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2)
    
    print(f"✅ Saved {len(tickers_list)} tickers\n")
    
    # Cleanup checkpoint
    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        print("🗑️  Checkpoint file deleted\n")
    
    # Summary
    print("[6/6] Summary:")
    print(f"  Original count: {original_count}")
    print(f"  Final count: {len(all_tickers)}")
    print(f"  Change: +{len(all_tickers) - original_count}")
    print("\n✅ Ticker refresh complete!")

if __name__ == "__main__":
    import schwab.client
    refresh_tickers()
