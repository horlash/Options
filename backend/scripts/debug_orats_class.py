import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from backend.api.orats import OratsAPI

def test_class():
    print("Testing OratsAPI Class...")
    api = OratsAPI()
    if not api.is_configured():
        print("API Key missing")
        return

    print("Fetching History for AAPL via Class...")
    candles = api.get_history("AAPL", days=10)
    
    if candles:
        print(f"Success! {len(candles)} candles returned.")
        print(f"First: {candles[0]}")
        print(f"Last: {candles[-1]}")
    else:
        print("Failed to fetch history.")

if __name__ == "__main__":
    test_class()
