# Frontend Audit Report
**Last Updated:** 2026-02-16
**Version:** NewScanner v3.0 (Strict ORATS Mode)

---

## Architecture Overview

### How It Works
```
Browser → Flask (single port) → Serves both frontend files AND API routes
                              ↓
                    /              → index.html (dashboard)
                    /login         → login.html (auth page)
                    /api/*         → JSON API endpoints
                    /css/*, /js/*  → Static assets from frontend/
```

Flask serves the `frontend/` directory as static files (`static_folder`), with all API routes prefixed under `/api/`. This means **one port serves everything** — no separate frontend server needed.

**Local launch command:**
```bash
python backend/app.py
# → http://localhost:5000 (everything served here)
```

---

## File Inventory

### HTML Pages (3)
| File | Purpose | Status |
|------|---------|--------|
| `index.html` (264 lines) | Main dashboard — scan controls, watchlist, opportunities, analysis modal | ✅ Functional |
| `login.html` (5.7KB) | Login form — session-based auth via `/login` POST | ✅ Functional |
| `v2.html` (45KB) | V2 UI concept — **unused**, not linked anywhere | ⚠️ Dead file |

### JavaScript (7 files in `js/`)
| File | Purpose | Status |
|------|---------|--------|
| `js/utils/api.js` (120 lines) | API client — all backend calls via relative `/api` prefix | ✅ Clean, tunnel-safe |
| `js/utils/toast.js` | Toast notification system | ✅ Functional |
| `js/utils/charts.js` | Chart.js integration | ✅ Functional |
| `js/components/scanner.js` (379 lines) | Scan mode logic, Smart Search, Sector Scan | ✅ Functional |
| `js/components/watchlist.js` | Watchlist CRUD | ✅ Functional |
| `js/components/opportunities.js` | Opportunity card rendering | ✅ Functional |
| `js/components/analysis-detail.js` | Analysis detail modal | ✅ Functional |
| `js/app.js` (196 lines) | Entry point — init, event listeners, history | ✅ Functional |

### CSS (3 files)
| File | Status |
|------|--------|
| `css/styles.css` (14.8KB) | ✅ Exists — main styles |
| `css/components/opportunities.css` (5KB) | ✅ Exists |
| `css/components/watchlist.css` (2.6KB) | ✅ Exists |
| `css/components/scanner.css` | ❌ **MISSING** — referenced in index.html line 10, returns 404 |
| `css/components/analysis-detail.css` | ❌ **MISSING** — referenced in index.html line 12, returns 404 |

---

## Backend API Route Map

All routes served by `backend/app.py` on Flask. Frontend calls these via `api.js`.

### Page Routes
| Method | Route | Frontend File | Function |
|--------|-------|---------------|----------|
| GET | `/` | `index.html` | Main dashboard |
| GET/POST | `/login` | `login.html` | Auth page + login API |
| GET | `/logout` | redirect | Logout + redirect to login |
| GET | `/demo` | `demo.html` | ❌ **BROKEN** — `demo.html` does not exist |

### API Routes (used by `api.js`)
| Method | Route | JS Function | Purpose |
|--------|-------|-------------|---------|
| GET | `/api/watchlist` | `api.getWatchlist()` | Get user watchlist |
| POST | `/api/watchlist` | `api.addToWatchlist()` | Add ticker |
| DELETE | `/api/watchlist/<ticker>` | `api.removeFromWatchlist()` | Remove ticker |
| POST | `/api/scan` | `api.runScan()` | LEAP scan on watchlist |
| POST | `/api/scan/<ticker>` | `api.scanTicker()` | Single-ticker LEAP scan |
| POST | `/api/scan/daily` | `api.runDailyScan()` | Weekly scan on watchlist |
| POST | `/api/scan/daily/<ticker>` | `api.scanTickerDaily()` | Single-ticker weekly scan |
| POST | `/api/scan/0dte/<ticker>` | `api.scan0DTE()` | 0DTE scan |
| POST | `/api/scan/sector` | `api.runSectorScan()` | Sector scan |
| GET | `/api/tickers` | `api.getTickers()` | Autocomplete data |
| GET | `/api/analysis/<ticker>` | `api.getAnalysis()` | Detailed analysis |
| POST | `/api/analysis/ai/<ticker>` | — | AI analysis (Perplexity) |
| GET | `/api/history` | `api.getHistory()` | Search history |
| POST | `/api/history` | `api.addHistory()` | Add to history |
| GET | `/api/data/<filename>` | — | Serve data files (tickers.json) |

---

## Issues Found

### 🔴 Critical (Affects Functionality)

#### 1. Missing CSS Files — 404 Errors
`index.html` references 2 CSS files that don't exist:
```html
<link rel="stylesheet" href="css/components/scanner.css?v=17">        <!-- LINE 10 -->
<link rel="stylesheet" href="css/components/analysis-detail.css?v=17"> <!-- LINE 12 -->
```
**Impact:** Scanner controls and analysis modal may have broken/default styling.
**Fix:** Create the missing CSS files, or remove the `<link>` tags if styles are already in `styles.css`.

#### 2. Duplicate Route — `/api/scan/0dte/<ticker>`
Defined twice in `app.py`:
- Line 305: `scan_0dte_ticker()` — returns 200 on failure
- Line 467: `scan_0dte()` — returns 404 on failure
**Impact:** Flask uses the **last** definition. This is confusing and could cause bugs.
**Fix:** Remove line 305-326 (the first, older definition).

### 🟡 Minor (Cosmetic / Cleanup)

#### 3. Stale CSS Classes in `index.html`
Lines 148-161 define `.source-schwab` and `.source-yahoo` badge styles. Schwab and Yahoo are removed.
**Fix:** Remove these classes. Keep `.source-tradier` if in use, add `.source-orats`.

#### 4. Dead HTML Page — `v2.html` (45KB)
Not linked or referenced anywhere. This was a V2 UI concept from a previous conversation (Jan 21).
**Fix:** Delete or move to `docs/archive/`.

#### 5. Dead Route — `/demo`
`app.py` line 77 serves `demo.html`, but this file doesn't exist.
**Fix:** Remove the route from `app.py`.

#### 6. Debug Statements in Production Code
`app.py` lines 272-285 contain `sys.stderr.write("I AM THE DEV APP STARTUP")` and other debug prints.
**Fix:** Remove debug statements.

#### 7. Duplicate Route Decorator
`app.py` line 387-388: `@app.route('/api/history', methods=['GET'])` is declared twice.
**Fix:** Remove the duplicate.

#### 8. `frontend_dist` Fallback Reference
`app.py` lines 18-23 check for a `frontend_dist/` directory that was deleted.
**Fix:** Remove the conditional; always use `frontend/`.

---

## Frontend Features Summary

### Scan Modes (5)
| Mode | Button ID | Backend Route | Description |
|------|-----------|---------------|-------------|
| **0DTE** | `mode-0dte` | `/api/scan/0dte/<ticker>` | Same-day expiry (red button) |
| **This Week** | `mode-weekly-0` | `/api/scan/daily/<ticker>` (weeks_out=0) | Default active |
| **Next Week** | `mode-weekly-1` | `/api/scan/daily/<ticker>` (weeks_out=1) | +1 week |
| **Next 2 Weeks** | `mode-weekly-2` | `/api/scan/daily/<ticker>` (weeks_out=2) | +2 weeks |
| **LEAPs** | `mode-leaps` | `/api/scan/<ticker>` | >150 DTE |

### UI Components
- **Smart Search:** Autocomplete ticker input → calls `/api/tickers` for data
- **Sector Scan:** Sector + Industry + Cap + Volume filters → `/api/scan/sector`
- **Watchlist:** Add/remove tickers → stored per-user in SQLite DB
- **Opportunity Cards:** Score, badges, profit %, expiry, delta, premium display
- **Analysis Modal:** Detailed breakdown (Greeks, MTA, AI thesis)
- **Search History:** Recent ticker searches, clickable for re-scan
- **Profit Filters:** >15%, >25%, >35% filter buttons

### Authentication
- Session-based via Flask `session` + `Security` class
- Login page at `/login` with username/password
- User-specific watchlists and search history

---

## Tunnel Compatibility Assessment

| Concern | Status |
|---------|--------|
| API base URL | ✅ **Relative** (`/api`) — works through any tunnel/proxy |
| Static assets | ✅ **Relative paths** — no hardcoded localhost |
| CORS | ✅ `flask_cors` enabled — allows cross-origin |
| WebSocket | N/A — all HTTP REST calls |
| Session cookies | ⚠️ May need `Secure` flag and `SameSite=None` for HTTPS tunnel |
| Single port | ✅ Everything on one port — tunnel only needs to expose one port |

**Verdict:** Frontend is **tunnel-ready** with minimal config changes (cookie settings for HTTPS).
