"""Phase 5: End-to-end verification against Pi deployment"""
import requests
import sys

BASE = 'http://192.168.1.244:5000'
results = []

def log(test_id, desc, passed, detail=''):
    results.append((test_id, desc, passed, detail))
    mark = 'PASS' if passed else 'FAIL'
    print(f'  {mark} {test_id}: {desc}' + (f' [{detail}]' if detail else ''))

# V1: Login page loads
try:
    r = requests.get(f'{BASE}/login', timeout=10)
    log('V1', 'Login page loads', r.status_code == 200, f'{r.status_code} {len(r.text)}b')
except Exception as e:
    log('V1', 'Login page loads', False, str(e)[:80])

# V2: Login with dev/password123
s = requests.Session()
try:
    r = s.post(f'{BASE}/login', json={'username': 'dev', 'password': 'password123'}, timeout=10)
    ok = r.status_code == 200 and r.json().get('success', False)
    log('V2', 'Login dev/password123', ok, f'{r.status_code} {r.text[:80]}')
except Exception as e:
    log('V2', 'Login dev/password123', False, str(e)[:80])

# V3: Main page with tabs
try:
    r = s.get(f'{BASE}/', timeout=10)
    has_scanner = 'scanner' in r.text.lower()
    has_portfolio = 'portfolio' in r.text.lower()
    has_trading = 'trading' in r.text.lower() or 'paper' in r.text.lower()
    log('V3', 'Main page + tabs', r.status_code == 200,
        f'Scanner={has_scanner} Portfolio={has_portfolio} Trading={has_trading}')
except Exception as e:
    log('V3', 'Main page + tabs', False, str(e)[:80])

# V4: Paper health check (no auth)
try:
    r = requests.get(f'{BASE}/api/paper/health', timeout=10)
    log('V4', 'Paper health check', r.status_code == 200, f'{r.status_code} {r.text[:80]}')
except Exception as e:
    log('V4', 'Paper health check', False, str(e)[:80])

# V5: Paper trades API (needs Postgres)
try:
    r = s.get(f'{BASE}/api/paper/trades', timeout=10)
    log('V5', 'Paper trades API', r.status_code == 200, f'{r.status_code} {r.text[:100]}')
except Exception as e:
    log('V5', 'Paper trades API', False, str(e)[:80])

# V6: Paper stats API
try:
    r = s.get(f'{BASE}/api/paper/stats', timeout=10)
    log('V6', 'Paper stats API', r.status_code == 200, f'{r.status_code} {r.text[:100]}')
except Exception as e:
    log('V6', 'Paper stats API', False, str(e)[:80])

# V7: Market status
try:
    r = s.get(f'{BASE}/api/paper/market-status', timeout=10)
    log('V7', 'Market status API', r.status_code == 200, f'{r.status_code} {r.text[:80]}')
except Exception as e:
    log('V7', 'Market status API', False, str(e)[:80])

# V8: Watchlist API
try:
    r = s.get(f'{BASE}/api/watchlist', timeout=10)
    log('V8', 'Watchlist API', r.status_code == 200, f'{r.status_code}')
except Exception as e:
    log('V8', 'Watchlist API', False, str(e)[:80])

# V9: Login with tester1/tester1pass (multi-user)
s2 = requests.Session()
try:
    r = s2.post(f'{BASE}/login', json={'username': 'tester1', 'password': 'tester1pass'}, timeout=10)
    ok = r.status_code == 200 and r.json().get('success', False)
    log('V9', 'Login tester1/tester1pass', ok, f'{r.status_code} {r.text[:80]}')
except Exception as e:
    log('V9', 'Login tester1/tester1pass', False, str(e)[:80])

# Summary
passed = sum(1 for _, _, p, _ in results if p)
total = len(results)
print(f'\n{"="*50}')
print(f'Phase 5 Verification: {passed}/{total} passed')
print(f'{"="*50}')
