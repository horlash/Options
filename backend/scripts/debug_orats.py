import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import requests
from backend.config import Config

API_KEY = Config.ORATS_API_KEY
BASE_URL = "https://api.orats.io/datav2"

def test_dailies_range():
    endpoint = "hist/dailies"
    url = f"{BASE_URL}/{endpoint}"
    print(f"\nTesting: {url} (Range)")
    
    # Try startDate/endDate (Common ORATS pattern)
    params = {
        "token": API_KEY, 
        "ticker": "AAPL", 
        "startDate": "2024-01-01", 
        "endDate": "2024-01-10"
    }
    
    try:
        resp = requests.get(url, params=params)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
             data = resp.json()
             print(f"Data Keys: {data.keys() if isinstance(data, dict) else 'List'}")
             if isinstance(data, dict) and 'data' in data:
                 print(f"Rows Returned: {len(data['data'])}")
                 if len(data['data']) > 0:
                      print(f"Sample: {data['data'][0]}")
             else:
                 print(f"Body: {resp.text[:300]}")
        else:
             print(f"Error Body: {resp.text[:300]}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_dailies_range()
