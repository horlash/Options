"""Live API Audit Tests for Options Scanner"""
import requests
import json
import sys

BASE = "http://localhost:5001"
s = requests.Session()

def hr(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

# === 1. LOGIN ===
hr("1. LOGIN")
r = s.post(f"{BASE}/login", json={"username": "dev", "password": "password123"})
print(f"Status: {r.status_code}")
print(f"Body: {r.text[:200]}")

# === 2. HEALTH ===
hr("2. HEALTH CHECK")
r = s.get(f"{BASE}/api/paper/health")
print(f"Status: {r.status_code}")
print(f"Body: {r.text[:200]}")

# === 3. ME ===
hr("3. WHO AM I")
r = s.get(f"{BASE}/api/me")
print(f"Status: {r.status_code}")
print(f"Body: {r.text[:200]}")

# === 4. WATCHLIST GET ===
hr("4. WATCHLIST")
r = s.get(f"{BASE}/api/watchlist")
print(f"Status: {r.status_code}")
print(f"Body: {r.text[:300]}")

# === 5. PAPER TRADES ===
hr("5. PAPER TRADES (OPEN)")
r = s.get(f"{BASE}/api/paper/trades?status=OPEN")
print(f"Status: {r.status_code}")
print(f"Body: {r.text[:500]}")

# === 6. PAPER STATS ===
hr("6. PAPER STATS")
r = s.get(f"{BASE}/api/paper/stats")
print(f"Status: {r.status_code}")
print(f"Body: {r.text[:500]}")

# === 7. UNAUTHED ACCESS ===
hr("7. UNAUTHED ACCESS")
s2 = requests.Session()
tests = [
    ("GET", "/api/watchlist"),
    ("GET", "/api/me"),
    ("POST", "/api/scan/AAPL"),
    ("GET", "/api/paper/trades"),
    ("GET", "/api/paper/stats"),
    ("POST", "/api/paper/trades"),
    ("GET", "/api/history"),
    ("GET", "/api/tickers"),
]
for method, path in tests:
    if method == "GET":
        r = s2.get(f"{BASE}{path}", allow_redirects=False)
    else:
        r = s2.post(f"{BASE}{path}", json={}, allow_redirects=False)
    status_ok = "PASS" if r.status_code in (302, 401) else "FAIL"
    print(f"  [{status_ok}] {method} {path}: {r.status_code}")

# === 8. TICKER VALIDATION ===
hr("8. TICKER VALIDATION (XSS/SQLi)")
xss_tests = [
    ("<script>alert(1)</script>", "XSS"),
    ("A" * 50, "Long ticker"),
    ("OR 1=1--", "SQLi"),
    ("../../../etc/passwd", "Path traversal"),
    ("", "Empty"),
]
for payload, label in xss_tests:
    r = s.post(f"{BASE}/api/watchlist", json={"ticker": payload})
    try:
        d = r.json()
        err = d.get("error", "")[:60]
    except:
        err = r.text[:60]
    status_ok = "PASS" if r.status_code == 400 else "FAIL"
    print(f"  [{status_ok}] {label}: {r.status_code} - {err}")

# === 9. HEALTH WITHOUT AUTH ===
hr("9. HEALTH WITHOUT AUTH")
s3 = requests.Session()
r = s3.get(f"{BASE}/api/paper/health", allow_redirects=False)
print(f"Status: {r.status_code}")
print(f"Expected: 200 (whitelisted)")
status_ok = "PASS" if r.status_code == 200 else "FAIL"
print(f"Result: [{status_ok}]")

# === 10. SCAN AAPL ===
hr("10. SCAN AAPL (LEAP, BOTH)")
try:
    r = s.post(f"{BASE}/api/scan/AAPL", json={"direction": "BOTH"}, timeout=120)
    print(f"Status: {r.status_code}")
    try:
        d = r.json()
        print(f"Success: {d.get('success')}")
        if d.get("result"):
            res = d["result"]
            print(f"Ticker: {res.get('ticker')}")
            print(f"Tech Score: {res.get('technical_score')}")
            print(f"Sent Score: {res.get('sentiment_score')}")
            opps = res.get("opportunities", [])
            print(f"Opportunities: {len(opps)}")
            if opps:
                top = opps[0]
                print(f"Top: {top.get('option_type')} ${top.get('strike_price')} Score={top.get('opportunity_score')}")
                bd = top.get("score_breakdown", {})
                print(f"Breakdown: tech={bd.get('technical')}, sent={bd.get('sentiment')}, skew={bd.get('skew')}, greeks={bd.get('greeks')}, liq={bd.get('liquidity')}")
                w = bd.get("weights", {})
                total = sum(w.values())
                print(f"Weight sum: {total} (expected: 1.0)")
            ts = res.get("trading_systems", {})
            print(f"VIX: {ts.get('vix_regime', {}).get('level')} ({ts.get('vix_regime', {}).get('regime')})")
            print(f"P/C: {ts.get('put_call', {}).get('ratio')}")
        elif d.get("error"):
            print(f"Error: {d.get('error')}")
    except Exception as e:
        print(f"Parse error: {e}")
        print(f"Raw: {r.text[:300]}")
except requests.Timeout:
    print("TIMEOUT (120s)")
except Exception as e:
    print(f"Request error: {e}")

# === 11. DAILY SCAN ===
hr("11. DAILY SCAN AAPL")
try:
    r = s.post(f"{BASE}/api/scan/daily/AAPL", json={"weeks_out": 1}, timeout=120)
    print(f"Status: {r.status_code}")
    try:
        d = r.json()
        print(f"Success: {d.get('success')}")
        if d.get("result"):
            opps = d["result"].get("opportunities", [])
            print(f"Weekly opportunities: {len(opps)}")
        elif d.get("error"):
            print(f"Error: {d.get('error')}")
    except:
        print(f"Raw: {r.text[:300]}")
except requests.Timeout:
    print("TIMEOUT")

# === 12. SETTINGS ===
hr("12. USER SETTINGS")
r = s.get(f"{BASE}/api/paper/settings")
print(f"Status: {r.status_code}")
print(f"Body: {r.text[:400]}")

print("\n\nDONE")
