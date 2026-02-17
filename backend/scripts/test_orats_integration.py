import sys
import os
import logging

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from backend.services.hybrid_scanner_service import HybridScannerService

def test_integration():
    print("--- Starting ORATS Integration Test ---")
    
    scanner = HybridScannerService()
    
    if not scanner.use_orats:
        print("❌ ORATS not detected in Scanner! Check .env")
        return
        
    print("✅ ORATS Configuration Detected.")
    
    ticker = "AAPL"
    print(f"Scanning {ticker} (Single Mode)...")
    
    # Test 1: Single Scan (should hit ORATS API directly via BatchManager internal or scan_ticker logic)
    result = scanner.scan_ticker(ticker, strict_mode=False)
    
    if result:
        print(f"✅ Scan Successful!")
        opps = result.get('opportunities', [])
        print(f"Found {len(opps)} Opportunities.")
        if opps:
            print(f"Sample: {opps[0]}")
            # Verify they are LEAPs
            not_leaps = [o for o in opps if o['days_to_expiry'] < 150]
            if not_leaps:
                print(f"⚠️  WARNING: Found {len(not_leaps)} non-LEAPs! Filter failed?")
            else:
                 print("✅ LEAP Filter Verified (>150 days).")
    else:
        print("❌ Scan returned None.")

    # Test 2: Mock Batch Mode (simulating scan_watchlist)
    print("\n--- Testing Batch Injection ---")
    # Fetch data manualy
    print("Fetching data manually via BatchManager...")
    batch_data = scanner.batch_manager.fetch_option_chains([ticker])
    data = batch_data.get(ticker)
    
    if data:
        print("✅ Batch Fetch Successful.")
        print("Injecting data into scan_ticker...")
        res2 = scanner.scan_ticker(ticker, strict_mode=False, pre_fetched_data=data)
        if res2:
             print("✅ Injected Scan Successful!")
        else:
             print("❌ Injected Scan Failed.")
    else:
        print("❌ Batch Fetch Failed.")

if __name__ == "__main__":
    test_integration()
