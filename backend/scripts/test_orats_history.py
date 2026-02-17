import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from backend.config import Config
import requests
import json
from datetime import datetime, timedelta

# Mock ORATS API class for testing
class OratsProbe:
    def __init__(self):
        self.api_key = Config.ORATS_API_KEY
        self.base_url = "https://api.orats.io/datav2"
        if not self.api_key:
            print("❌ ORATS_API_KEY not found in Config")
            exit(1)

    def test_endpoint(self, endpoint, params):
        url = f"{self.base_url}/{endpoint}"
        params['token'] = self.api_key
        print(f"Testing {url} with params: {params}...")
        try:
            resp = requests.get(url, params=params)
            print(f"Status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                print(f"Success! Keys: {list(data.keys()) if isinstance(data, dict) else 'List'}")
                if isinstance(data, dict) and 'data' in data:
                    print(f"Rows: {len(data['data'])}")
                    if len(data['data']) > 0:
                        print(f"Sample: {data['data'][0]}")
                elif isinstance(data, list) and len(data) > 0:
                     print(f"Sample: {data[0]}")
                return True
            else:
                print(f"Failed: {resp.text[:200]}")
        except Exception as e:
            print(f"Error: {e}")
        return False

def main():
    probe = OratsProbe()
    ticker = "AAPL"
    
    # 1. Try /candles (Common)
    # Params often: ticker, start, end, resolution
    params = {
        "ticker": ticker,
        "start": (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
        "end": datetime.now().strftime("%Y-%m-%d"),
        "resolution": "1D" # standard
    }
    print("\n--- Probing /candles ---")
    probe.test_endpoint("candles", params)

    # 2. Try /hist/dailies (Retry with date range params)
    print("\n--- Probing /hist/dailies (Retry) ---")
    probe.test_endpoint("hist/dailies", {"ticker": ticker, "startDate": params['start'], "endDate": params['end']})

    # 3. Try /cores (Current?)
    print("\n--- Probing /cores ---")
    probe.test_endpoint("cores", {"ticker": ticker})

    # 4. Try /hist/strikes? (Maybe history of strikes?)
    print("\n--- Probing /hist/strikes ---")
    probe.test_endpoint("hist/strikes", {"ticker": ticker, "tradeDate": params['start']})
    
    # 5. Try /hist/summaries
    print("\n--- Probing /hist/summaries ---")
    probe.test_endpoint("hist/summaries", {"ticker": ticker, "startDate": params['start'], "endDate": params['end']})

if __name__ == "__main__":
    main()
