import json
import os
import sys
import time
import yfinance as yf
from datetime import datetime

# Adjust path to find backend modules if needed
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

DATA_FILE = os.path.join(os.path.dirname(__file__), '../data/tickers.json')

def load_tickers():
    if not os.path.exists(DATA_FILE):
        print(f"❌ Cache file not found: {DATA_FILE}")
        return None
    with open(DATA_FILE, 'r') as f:
        return json.load(f)

def save_tickers(data):
    data['last_updated'] = datetime.now().isoformat()
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"💾 Saved progress to {DATA_FILE}")

def enrich():
    data = load_tickers()
    if not data: return

    tickers = data.get('tickers', [])
    print(f"📦 Loaded {len(tickers)} tickers.")
    
    # Statistics
    missing_sector = sum(1 for t in tickers if 'sector' not in t)
    print(f"⚠️ Tickers missing sector data: {missing_sector}")
    
    if missing_sector == 0:
        print("✅ All tickers have sector data! No action needed.")
        return

    print("🚀 Starting enrichment via Yahoo Finance...")
    print("Press CTRL+C to stop (Progress is saved every 10 tickers).")
    
    count = 0
    updated = 0
    
    # Prioritize: Maybe shuffle? Or just go sequential.
    # Sequential is fine. 
    # Optimization: Filter only those needing update
    
    try:
        for t in tickers:
            if 'sector' in t and t['sector']:
                continue
                
            symbol = t['symbol']
            try:
                # Add delay to be nice to Yahoo
                time.sleep(0.5) 
                
                tick = yf.Ticker(symbol)
                info = tick.info
                
                # Extract data
                sector = info.get('sector')
                industry = info.get('industry')
                cap = info.get('marketCap')
                vol = info.get('averageVolume')
                
                if sector:
                    t['sector'] = sector
                    t['industry'] = industry
                    t['marketCap'] = cap
                    t['volume'] = vol
                    updated += 1
                    print(f"  ✅ {symbol}: {sector} | {industry}")
                else:
                    print(f"  ⚠️ {symbol}: No data found")
                    # Mark as visited to avoid retry loop? 
                    # Maybe set sector="Unknown" to skip next time?
                    # t['sector'] = "Unknown" 
                    
            except Exception as e:
                print(f"  ❌ {symbol}: Error {e}")
            
            count += 1
            # Limit removed for full run
            # if count >= 500: ...
                
            if count % 10 == 0:
                save_tickers(data)
                
    except KeyboardInterrupt:
        print("\n🛑 Stopped by user.")
    finally:
        save_tickers(data)
        print(f"\n🎉 Session Complete. Updated {updated} tickers.")

if __name__ == "__main__":
    enrich()
