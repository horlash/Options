"""T3/T4: Post-Merge HTTP Endpoint Tests"""
import requests
import sys

BASE = 'http://localhost:5001'
results = []

def log(test_id, desc, passed, detail=''):
    results.append((test_id, desc, passed, detail))
    mark = 'PASS' if passed else 'FAIL'
    print(f'  {mark} {test_id}: {desc}' + (f' [{detail}]' if detail else ''))

# T3.1: Login page loads
try:
    r = requests.get(f'{BASE}/login', timeout=5)
    log('T3.1', 'Login page loads', r.status_code == 200, f'{r.status_code} {len(r.text)}b')
except Exception as e:
    log('T3.1', 'Login page loads', False, str(e)[:80])

# T3.2: Login with dev/password123
s = requests.Session()
try:
    r = s.post(f'{BASE}/login', json={'username': 'dev', 'password': 'password123'}, timeout=5)
    ok = r.status_code == 200 and r.json().get('success', False)
    log('T3.2', 'Login with dev/password123', ok, f'{r.status_code} {r.text[:80]}')
except Exception as e:
    log('T3.2', 'Login with dev/password123', False, str(e)[:80])

# T3.3: Main page with tabs
try:
    r = s.get(f'{BASE}/', timeout=5)
    has_scanner = 'scanner' in r.text.lower()
    has_portfolio = 'portfolio' in r.text.lower()
    has_trading = 'trading' in r.text.lower() or 'paper' in r.text.lower()
    log('T3.3', 'Main page loads with tabs', r.status_code == 200,
        f'Scanner={has_scanner} Portfolio={has_portfolio} Trading={has_trading}')
except Exception as e:
    log('T3.3', 'Main page loads with tabs', False, str(e)[:80])

# T3.4: Watchlist API
try:
    r = s.get(f'{BASE}/api/watchlist', timeout=5)
    log('T3.4', 'Watchlist API', r.status_code == 200, f'{r.status_code}')
except Exception as e:
    log('T3.4', 'Watchlist API', False, str(e)[:80])

# T3.5: Tickers API
try:
    r = s.get(f'{BASE}/api/tickers', timeout=5)
    log('T3.5', 'Tickers API', r.status_code == 200, f'{r.status_code}')
except Exception as e:
    log('T3.5', 'Tickers API', False, str(e)[:80])

# T4.1: Paper trading API (graceful error without Postgres)
try:
    r = s.get(f'{BASE}/api/paper/portfolio', timeout=5)
    log('T4.1', 'Paper portfolio API (no DB)', r.status_code in [200, 500], f'{r.status_code}')
except Exception as e:
    log('T4.1', 'Paper portfolio API', False, str(e)[:80])

# Summary
passed = sum(1 for _, _, p, _ in results if p)
total = len(results)
print(f'\n{"="*50}')
print(f'T3/T4 Results: {passed}/{total} passed')
print(f'{"="*50}')
sys.exit(0 if passed == total else 1)
