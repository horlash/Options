"""Additional scan tests"""
import requests
import json

BASE = "http://localhost:5001"
s = requests.Session()
s.post(f"{BASE}/login", json={"username": "dev", "password": "password123"})

# SPY LEAP SCAN
print("=== SPY LEAP SCAN ===")
r = s.post(f"{BASE}/api/scan/SPY", json={"direction": "CALL"}, timeout=120)
print(f"Status: {r.status_code}")
d = r.json()
success = d.get("success")
print(f"Success: {success}")
if d.get("result"):
    res = d["result"]
    tech = res.get("technical_score")
    sent = res.get("sentiment_score")
    print(f"Tech: {tech}, Sent: {sent}")
    opps = res.get("opportunities", [])
    print(f"Opportunities: {len(opps)}")
    if opps:
        top = opps[0]
        print(f"Top: {top.get('option_type')} Strike={top.get('strike_price')} Score={top.get('opportunity_score')}")
        bd = top.get("score_breakdown", {})
        w = bd.get("weights", {})
        total = sum(w.values())
        print(f"Weight sum: {total}")
    ts = res.get("trading_systems", {})
    vix = ts.get("vix_regime", {})
    print(f"VIX: level={vix.get('level')}, regime={vix.get('regime')}")
    pc = ts.get("put_call", {})
    print(f"P/C: ratio={pc.get('ratio')}, signal={pc.get('signal')}")
elif d.get("error"):
    err = d["error"]
    print(f"Error: {err}")

# MARKET STATUS
print()
print("=== MARKET STATUS ===")
r = s.get(f"{BASE}/api/paper/market-status")
print(f"Status: {r.status_code}")
body = r.text[:300]
print(f"Body: {body}")

# TICKERS
print()
print("=== TICKERS ===")
r = s.get(f"{BASE}/api/tickers")
print(f"Status: {r.status_code}")
d = r.json()
success = d.get("success")
tickers = d.get("tickers", [])
print(f"Success: {success}, Count: {len(tickers)}")
if tickers:
    sample = [t.get("symbol") for t in tickers[:5]]
    print(f"Sample: {sample}")

# HISTORY
print()
print("=== SEARCH HISTORY ===")
r = s.get(f"{BASE}/api/history")
print(f"Status: {r.status_code}")
print(f"Body: {r.text[:200]}")

# Try MSFT (often in uptrend)
print()
print("=== MSFT LEAP SCAN ===")
r = s.post(f"{BASE}/api/scan/MSFT", json={"direction": "CALL"}, timeout=120)
print(f"Status: {r.status_code}")
d = r.json()
success = d.get("success")
print(f"Success: {success}")
if d.get("result"):
    res = d["result"]
    tech = res.get("technical_score")
    sent = res.get("sentiment_score")
    opps = res.get("opportunities", [])
    print(f"Tech: {tech}, Sent: {sent}, Opps: {len(opps)}")
    if opps:
        top = opps[0]
        print(f"Top: {top.get('option_type')} ${top.get('strike_price')} Score={top.get('opportunity_score')}")
elif d.get("error"):
    print(f"Error: {d['error']}")
