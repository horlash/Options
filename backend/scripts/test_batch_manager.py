import sys
import os
import time

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from backend.services.batch_manager import BatchManager

def test_batch_speed():
    # Create valid tickers list (duplicated to create volume)
    base_tickers = ['AAPL', 'MSFT', 'TSLA', 'AMZN', 'GOOGL', 'NVDA', 'META', 'AMD', 'NFLX', 'INTC']
    tickers = base_tickers * 5 # 50 tickers
    
    print(f"Starting Batch Test for {len(tickers)} tickers...")
    
    manager = BatchManager(max_workers=20, rate_limit_per_min=1000)
    
    start = time.time()
    results = manager.fetch_option_chains(tickers)
    end = time.time()
    
    duration = end - start
    count = len(results)
    rate = count / duration if duration > 0 else 0
    
    print(f"\n--- Batch Test Results ---")
    print(f"Total Tickers: {len(tickers)}")
    print(f"Successful Fetches: {count}")
    print(f"Total Time: {duration:.2f} seconds")
    print(f"Rate: {rate:.2f} tickers/second")
    
    if count > 0:
        first_key = list(results.keys())[0]
        data = results[first_key]
        print(f"Sample Data ({first_key}): {data.get('symbol')} - Calls: {len(data.get('callExpDateMap', {}))}, Puts: {len(data.get('putExpDateMap', {}))}")

if __name__ == "__main__":
    test_batch_speed()
