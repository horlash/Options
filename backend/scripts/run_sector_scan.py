import sys
import os
import json

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from backend.services.hybrid_scanner_service import HybridScannerService
from backend.api.orats import OratsAPI

def run_energy_scan():
    print("--- Starting Energy Sector Scan (Strict ORATS) ---")
    
    scanner = HybridScannerService()
    
    if not scanner.use_orats:
        print("❌ ORATS NOT DETECTED! Scan will likely fail in strict mode.")
        return

    # Create dummy reasoning engine for compatibility if needed? 
    # scanner.scan_sector_top_picks handles prompt loop.

    print("🚀 Initiating Scan for 'Energy'...")
    try:
        # scan_sector_top_picks(sector, min_volume, min_market_cap) 
        # Hardcoded limit=15 in service
        results = scanner.scan_sector_top_picks(
            sector="Energy", 
            min_volume=1000000, # 1M Volume
            min_market_cap=5000000000 # 5B Cap
        ) 
        
        # Explicit scan of AAPL to verify Price Check & Options (since Energy failed Quality)
        # res = scanner.scan_ticker("AAPL", strict_mode=True)
        # results = [res] if res else [] 
        
        print("\n✅ Scan Complete.")
        
        # scan_sector_top_picks returns a LIST of result objects
        top_picks = results 
        
        print(f"Top Picks Count: {len(top_picks)}")
        
        if top_picks:
            print("\n--- Example Pick ---")
            print(json.dumps(top_picks[0], indent=2, default=str))
            
        # Analysis key is likely not present in the list return, needing prompt integration check
        # print("\n--- Analysis Summary ---")
        # print(results.get('analysis', 'No analysis generated'))

    except Exception as e:
        print(f"❌ Scan Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_energy_scan()
