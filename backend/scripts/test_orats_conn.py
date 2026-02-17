import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from backend.api.orats import OratsAPI

def test_connection():
    try:
        print("Initializing ORATS API...")
        orats = OratsAPI()
        
        ticker = "AAPL"
        print(f"Fetching Option Chain for {ticker}...")
        data = orats.get_option_chain(ticker)
        
        if data:
            print(f"SUCCESS! Fetched {ticker} data.")
            print(f"Symbol: {data.get('symbol')}")
            
            calls = data.get('callExpDateMap', {})
            puts = data.get('putExpDateMap', {})
            
            print(f"Call Expirations Found: {len(calls)}")
            print(f"Put Expirations Found: {len(puts)}")
            
            # Print sample
            if calls:
                first_exp = list(calls.keys())[0]
                first_strike = list(calls[first_exp].keys())[0]
                sample = calls[first_exp][first_strike][0]
                print(f"\nSample Option: {sample['description']}")
                print(f"Mark: {sample['mark']}, Delta: {sample['delta']}, IV: {sample['volatility']}")
        else:
            print("FAILURE: No data returned.")
            
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")

if __name__ == "__main__":
    test_connection()
