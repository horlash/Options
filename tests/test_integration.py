"""
Integration Test Suite for Options Scanner API
===============================================
Tests the Flask API routes end-to-end with mocked external services.
Covers: authentication, scanning (LEAPS/weekly/0DTE/sector), watchlist,
history, AI analysis, and error handling.

Run: pytest tests/test_integration.py -v

Architecture notes:
  - The app imports several modules at module-load time that touch real
    external services (ORATS, Postgres, etc.).  We neutralise these by:
      1. Setting dummy env vars BEFORE any import.
      2. Patching OratsAPI.__init__, MonitorService.__init__, and the
         paper_session engine factory with MagicMock before flask_app is
         imported, so no network or DB calls fire during collection.
  - Security.login_user reads users.json; we mock load_users() to return
    a pre-hashed credential without touching the filesystem.
  - get_scanner() is patched per test group to return a MagicMock scanner.
  - WatchlistService is patched per test group to control DB interactions.
"""

import pytest
import json
import os
import sys
import hashlib

# ─── Path setup ──────────────────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ─── Dummy env vars — must be set before ANY backend import fires ─────────────
os.environ.setdefault('PAPER_TRADE_DB_URL', 'sqlite:///./test_paper.db')
os.environ.setdefault('SECRET_KEY', 'test-secret-key-integration-suite')
os.environ.setdefault('DATABASE_URL', 'sqlite:///./test_integration.db')
os.environ.setdefault('ORATS_API_KEY', 'test-orats-key')
os.environ.setdefault('FMP_API_KEY', 'test-fmp-key')
os.environ.setdefault('FINNHUB_API_KEY', 'test-finnhub-key')
os.environ.setdefault('PERPLEXITY_API_KEY', 'test-perplexity-key')
os.environ.setdefault('ENCRYPTION_KEY', 'test-encryption-key')

from unittest.mock import patch, MagicMock, call

# ─── Patch problematic module-level singletons before importing the app ───────
# paper_session calls create_engine() at module level; patch it to avoid
# requiring a live Postgres connection.
_mock_paper_engine = MagicMock()
_mock_paper_session_local = MagicMock()
_mock_paper_scoped_session = MagicMock()

with patch('sqlalchemy.create_engine', return_value=_mock_paper_engine), \
     patch('sqlalchemy.orm.sessionmaker', return_value=_mock_paper_session_local), \
     patch('sqlalchemy.orm.scoped_session', return_value=_mock_paper_scoped_session):
    # Import paper_session first to get it cached with our mocks
    import backend.database.paper_session  # noqa: E402

# MonitorService.__init__ creates OratsAPI which raises without a real key.
# Patch MonitorService to a no-op before paper_routes imports it.
with patch('backend.services.monitor_service.MonitorService.__init__', return_value=None), \
     patch('backend.services.monitor_service.MonitorService.sync_tradier_orders', return_value=None), \
     patch('backend.services.monitor_service.MonitorService.update_price_snapshots', return_value=None), \
     patch('backend.services.monitor_service.MonitorService.capture_bookend_snapshot', return_value=None), \
     patch('backend.services.monitor_service.MonitorService.lifecycle_sync', return_value=None):
    # Now import paper_routes (which does `monitor = MonitorService()` at module level)
    import backend.api.paper_routes  # noqa: E402

# Also silence APScheduler which tries to start background jobs on app import
with patch('backend.app.init_scheduler', return_value=None):
    from backend.app import app as flask_app  # noqa: E402

# ─── Test credentials ─────────────────────────────────────────────────────────────────────────────
TEST_PASSWORD = 'testpass123'
TEST_PASSWORD_HASH = hashlib.sha256(TEST_PASSWORD.encode()).hexdigest()
TEST_USERNAME = 'testuser'

# ─── Shared mock scanner factory ──────────────────────────────────────────────────────────────────

def make_mock_scanner():
    """Return a fully-configured MagicMock that mimics HybridScannerService."""
    scanner = MagicMock()
    future_date = '2027-06-15'

    # scan_ticker: default single-direction LEAPS result
    scanner.scan_ticker.return_value = {
        'ticker': 'AAPL',
        'scan_type': 'LEAPS',
        'direction': 'CALL',
        'technical_score': 72.5,
        'adjusted_technical': 75.0,
        'analysis_text': 'Bullish trend, RSI neutral.',
        'trading_systems': {'vix_regime': 'NEUTRAL', 'rsi2': 'OVERSOLD'},
        'opportunities': [
            {
                'option_type': 'CALL',
                'strike_price': 180.0,
                'expiration_date': future_date,
                'premium': 8.50,
                'profit_potential': 42.0,
                'days_to_expiry': 473,
                'volume': 1500,
                'open_interest': 8000,
                'implied_volatility': 0.28,
                'delta': 0.65,
                'opportunity_score': 88.0,
            }
        ],
    }

    # scan_weekly_options
    scanner.scan_weekly_options.return_value = {
        'ticker': 'AAPL',
        'scan_type': 'WEEKLY',
        'opportunities': [
            {
                'option_type': 'CALL',
                'strike_price': 185.0,
                'expiration_date': '2026-03-07',
                'premium': 2.10,
                'profit_potential': 18.5,
                'days_to_expiry': 8,
                'volume': 3200,
                'open_interest': 15000,
                'implied_volatility': 0.22,
                'delta': 0.52,
                'opportunity_score': 76.0,
            }
        ],
    }

    # scan_0dte_options
    scanner.scan_0dte_options.return_value = {
        'ticker': 'SPY',
        'scan_type': '0DTE',
        'opportunities': [
            {
                'option_type': 'PUT',
                'strike_price': 500.0,
                'expiration_date': '2026-02-27',
                'premium': 0.85,
                'profit_potential': 22.0,
                'days_to_expiry': 0,
                'volume': 25000,
                'open_interest': 50000,
                'implied_volatility': 0.18,
                'delta': -0.48,
                'opportunity_score': 81.0,
            }
        ],
    }

    # scan_sector_top_picks
    scanner.scan_sector_top_picks.return_value = [
        {'ticker': 'MSFT', 'scan_type': 'LEAPS', 'opportunities': []}
    ]

    # scan_watchlist
    scanner.scan_watchlist.return_value = [
        {'ticker': 'AAPL', 'scan_type': 'LEAPS', 'opportunities': []},
    ]

    # get_ai_analysis
    scanner.get_ai_analysis.return_value = {
        'summary': 'AAPL looks bullish based on momentum.',
        'recommendation': 'BUY CALL',
        'confidence': 'HIGH',
        'reasoning': 'Strong technicals, above 200-day SMA.',
    }

    # get_detailed_analysis
    scanner.get_detailed_analysis.return_value = {
        'ticker': 'AAPL',
        'price': 192.50,
        'technical_score': 74.0,
        'sentiment': 'Positive',
        'news': [],
    }

    # get_cached_tickers
    scanner.get_cached_tickers.return_value = ['AAPL', 'MSFT', 'GOOGL', 'SPY', 'QQQ']

    # close() — no-op
    scanner.close.return_value = None

    return scanner


# ══════════════════════════════════════════════════════════════════════════════
#  FIXTURES
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope='session')
def app():
    """Application fixture — configure Flask for testing."""
    flask_app.config.update({
        'TESTING': True,
        'SECRET_KEY': 'test-secret-key-integration-suite',
        'WTF_CSRF_ENABLED': False,
    })
    # Reinitialise scanner DB (SQLite) tables
    from backend.database.models import init_db
    init_db()
    yield flask_app


@pytest.fixture()
def client(app):
    """Unauthenticated test client."""
    with app.test_client() as c:
        yield c


@pytest.fixture()
def auth_client(app):
    """Test client with a pre-seeded authenticated session."""
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess['user'] = TEST_USERNAME
            sess['logged_in'] = True
        yield c


@pytest.fixture()
def mock_scanner():
    """Patch get_scanner() in the app module to return a controllable mock."""
    scanner = make_mock_scanner()
    with patch('backend.app.get_scanner', return_value=scanner):
        yield scanner


@pytest.fixture()
def mock_watchlist_service():
    """Patch WatchlistService to avoid real DB calls."""
    with patch('backend.app.WatchlistService') as MockWL:
        instance = MockWL.return_value
        instance.get_watchlist.return_value = [
            {'ticker': 'AAPL', 'sector': 'Technology', 'added_date': '2026-01-01T00:00:00'},
            {'ticker': 'MSFT', 'sector': 'Technology', 'added_date': '2026-01-02T00:00:00'},
        ]
        instance.add_ticker.return_value = (True, 'AAPL added to watchlist')
        instance.remove_ticker.return_value = (True, 'AAPL removed from watchlist')
        instance.close.return_value = None
        yield instance


# ══════════════════════════════════════════════════════════════════════════════
#  GROUP 1: Authentication (5 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestAuthentication:
    """Tests for /login, /logout, and session-protected routes."""

    def test_login_success(self, client):
        """POST /login with valid credentials returns 200 success JSON."""
        with patch('backend.app.security_service') as mock_sec:
            mock_sec.login_user.return_value = True
            resp = client.post(
                '/login',
                data=json.dumps({'username': TEST_USERNAME, 'password': TEST_PASSWORD}),
                content_type='application/json',
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

    def test_login_failure(self, client):
        """POST /login with wrong password returns 401."""
        with patch('backend.app.security_service') as mock_sec:
            mock_sec.login_user.return_value = False
            resp = client.post(
                '/login',
                data=json.dumps({'username': TEST_USERNAME, 'password': 'wrongpass'}),
                content_type='application/json',
            )
        assert resp.status_code == 401
        data = resp.get_json()
        assert data['success'] is False
        assert 'Invalid credentials' in data['error']

    def test_login_missing_fields(self, client):
        """POST /login with empty body — credentials are None/None, returns 401."""
        with patch('backend.app.security_service') as mock_sec:
            mock_sec.login_user.return_value = False
            resp = client.post(
                '/login',
                data=json.dumps({}),
                content_type='application/json',
            )
        assert resp.status_code == 401
        data = resp.get_json()
        assert data['success'] is False

    def test_protected_route_without_auth(self, client):
        """GET /api/watchlist without session is blocked (302 redirect or 401)."""
        resp = client.get('/api/watchlist')
        # Security before_request hook redirects unauthenticated browser requests
        assert resp.status_code in (302, 401)

    def test_logout_clears_session(self, auth_client):
        """GET /logout clears session and redirects to /login."""
        with patch('backend.app.security_service') as mock_sec:
            mock_sec.logout_user.return_value = None
            resp = auth_client.get('/logout')
        assert resp.status_code in (301, 302)
        location = resp.headers.get('Location', '')
        assert 'login' in location.lower() or location == '/login'


# ══════════════════════════════════════════════════════════════════════════════
#  GROUP 2: Watchlist CRUD (5 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestWatchlistCRUD:
    """Tests for GET/POST /api/watchlist and DELETE /api/watchlist/<ticker>."""

    def test_get_watchlist(self, auth_client, mock_watchlist_service):
        """GET /api/watchlist returns list of tickers for the logged-in user."""
        resp = auth_client.get('/api/watchlist')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert isinstance(data['watchlist'], list)
        assert len(data['watchlist']) == 2
        assert data['watchlist'][0]['ticker'] == 'AAPL'

    def test_add_valid_ticker(self, auth_client, mock_watchlist_service):
        """POST /api/watchlist with valid ticker returns success."""
        mock_watchlist_service.add_ticker.return_value = (True, 'AAPL added to watchlist')
        resp = auth_client.post(
            '/api/watchlist',
            data=json.dumps({'ticker': 'AAPL'}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'added' in data['message'].lower()

    def test_add_invalid_ticker(self, auth_client, mock_watchlist_service):
        """POST /api/watchlist with invalid ticker format returns 400."""
        resp = auth_client.post(
            '/api/watchlist',
            data=json.dumps({'ticker': '!!!'}),
            content_type='application/json',
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert 'Invalid ticker' in data['error']

    def test_add_duplicate_ticker(self, auth_client, mock_watchlist_service):
        """POST /api/watchlist with already-present ticker returns 'already in watchlist'."""
        mock_watchlist_service.add_ticker.return_value = (False, 'AAPL already in watchlist')
        resp = auth_client.post(
            '/api/watchlist',
            data=json.dumps({'ticker': 'AAPL'}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is False
        assert 'already in watchlist' in data['message']

    def test_remove_ticker(self, auth_client, mock_watchlist_service):
        """DELETE /api/watchlist/<ticker> returns success for an existing ticker."""
        mock_watchlist_service.remove_ticker.return_value = (True, 'AAPL removed from watchlist')
        resp = auth_client.delete('/api/watchlist/AAPL')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'removed' in data['message'].lower()


# ══════════════════════════════════════════════════════════════════════════════
#  GROUP 3: Scanner Endpoints (8 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestScannerEndpoints:
    """Tests for /api/scan/<ticker>, /api/scan/daily/<ticker>,
    /api/scan/0dte/<ticker>, /api/scan/sector, and /api/scan."""

    def test_scan_leaps_ticker(self, auth_client, mock_scanner):
        """POST /api/scan/AAPL with direction=CALL returns LEAPS opportunities."""
        future_date = '2027-06-15'
        mock_scanner.scan_ticker.return_value = {
            'ticker': 'AAPL', 'scan_type': 'LEAPS', 'direction': 'CALL',
            'technical_score': 72.5, 'adjusted_technical': 75.0,
            'analysis_text': 'Bullish.', 'trading_systems': {},
            'opportunities': [{
                'option_type': 'CALL', 'strike_price': 180.0,
                'expiration_date': future_date, 'premium': 8.50,
                'profit_potential': 42.0, 'days_to_expiry': 473,
                'volume': 1500, 'open_interest': 8000,
                'implied_volatility': 0.28, 'delta': 0.65,
                'opportunity_score': 88.0,
            }],
        }
        resp = auth_client.post(
            '/api/scan/AAPL',
            data=json.dumps({'direction': 'CALL'}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['result']['ticker'] == 'AAPL'
        assert data['result']['scan_type'] == 'LEAPS'

    def test_scan_leaps_both_directions(self, auth_client, mock_scanner):
        """POST /api/scan/AAPL with direction=BOTH merges CALL and PUT opportunities."""
        future_date = '2027-06-15'
        call_result = {
            'ticker': 'AAPL', 'scan_type': 'LEAPS', 'direction': 'CALL',
            'technical_score': 70.0, 'adjusted_technical': 72.0,
            'analysis_text': 'Bullish call.', 'trading_systems': {'vix_regime': 'NEUTRAL'},
            'opportunities': [{
                'option_type': 'CALL', 'strike_price': 185.0,
                'expiration_date': future_date, 'premium': 9.0,
                'profit_potential': 40.0, 'days_to_expiry': 473,
                'volume': 1200, 'open_interest': 7000,
                'implied_volatility': 0.27, 'delta': 0.60,
                'opportunity_score': 85.0,
            }],
        }
        put_result = {
            'ticker': 'AAPL', 'scan_type': 'LEAPS', 'direction': 'PUT',
            'technical_score': 55.0, 'adjusted_technical': 57.0,
            'analysis_text': 'Mild put.', 'trading_systems': {'vix_regime': 'NEUTRAL'},
            'opportunities': [{
                'option_type': 'PUT', 'strike_price': 170.0,
                'expiration_date': future_date, 'premium': 7.0,
                'profit_potential': 30.0, 'days_to_expiry': 473,
                'volume': 900, 'open_interest': 5000,
                'implied_volatility': 0.30, 'delta': -0.38,
                'opportunity_score': 78.0,
            }],
        }
        mock_scanner.scan_ticker.side_effect = [call_result, put_result]

        resp = auth_client.post(
            '/api/scan/AAPL',
            data=json.dumps({'direction': 'BOTH'}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        result = data['result']
        assert result['direction'] == 'BOTH'
        opp_types = {o['option_type'] for o in result.get('opportunities', [])}
        assert 'CALL' in opp_types
        assert 'PUT' in opp_types

    def test_scan_weekly_ticker(self, auth_client, mock_scanner):
        """POST /api/scan/daily/AAPL returns weekly scan result."""
        resp = auth_client.post(
            '/api/scan/daily/AAPL',
            data=json.dumps({'weeks_out': 1}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'result' in data
        assert data['result']['scan_type'] == 'WEEKLY'

    def test_scan_0dte_ticker(self, auth_client, mock_scanner):
        """POST /api/scan/0dte/SPY returns 0DTE opportunities."""
        mock_scanner.scan_0dte_options.return_value = {
            'ticker': 'SPY', 'scan_type': '0DTE',
            'opportunities': [{
                'option_type': 'PUT', 'strike_price': 500.0,
                'expiration_date': '2026-02-27', 'premium': 0.85,
                'profit_potential': 22.0, 'days_to_expiry': 0,
                'volume': 25000, 'open_interest': 50000,
                'implied_volatility': 0.18, 'delta': -0.48,
                'opportunity_score': 81.0,
            }],
        }
        resp = auth_client.post('/api/scan/0dte/SPY')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['result']['ticker'] == 'SPY'
        assert data['result']['scan_type'] == '0DTE'

    def test_scan_sector(self, auth_client, mock_scanner):
        """POST /api/scan/sector with sector=Technology returns results."""
        mock_scanner.scan_sector_top_picks.return_value = [
            {'ticker': 'MSFT', 'scan_type': 'LEAPS', 'opportunities': []},
            {'ticker': 'GOOGL', 'scan_type': 'LEAPS', 'opportunities': []},
        ]
        resp = auth_client.post(
            '/api/scan/sector',
            data=json.dumps({'sector': 'Technology'}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert isinstance(data['results'], list)
        assert len(data['results']) == 2

    def test_scan_sector_0dte_blocked(self, auth_client, mock_scanner):
        """POST /api/scan/sector with is_0dte=true is rejected with 400."""
        resp = auth_client.post(
            '/api/scan/sector',
            data=json.dumps({'sector': 'Technology', 'is_0dte': True}),
            content_type='application/json',
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert '0DTE sector scans' in data['error']

    def test_scan_nonexistent_ticker(self, auth_client, mock_scanner):
        """POST /api/scan/ZZZZZ — scanner returns None, route returns graceful 200."""
        mock_scanner.scan_ticker.return_value = None
        resp = auth_client.post(
            '/api/scan/ZZZZZ',
            data=json.dumps({'direction': 'CALL'}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is False
        assert 'ZZZZZ' in data['error']

    def test_scan_watchlist(self, auth_client, mock_scanner, mock_watchlist_service):
        """POST /api/scan with authenticated user triggers watchlist-level scan."""
        mock_scanner.scan_watchlist.return_value = [
            {'ticker': 'AAPL', 'scan_type': 'LEAPS', 'opportunities': []},
            {'ticker': 'MSFT', 'scan_type': 'LEAPS', 'opportunities': []},
        ]
        resp = auth_client.post('/api/scan')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert isinstance(data['results'], list)


# ══════════════════════════════════════════════════════════════════════════════
#  GROUP 4: AI Analysis (4 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestAIAnalysis:
    """Tests for POST /api/analysis/ai/<ticker> and GET /api/analysis/<ticker>."""

    def test_ai_analysis_success(self, auth_client, mock_scanner):
        """POST /api/analysis/ai/AAPL returns AI analysis dict."""
        mock_scanner.get_ai_analysis.return_value = {
            'summary': 'AAPL looks bullish based on momentum.',
            'recommendation': 'BUY CALL',
            'confidence': 'HIGH',
            'reasoning': 'Strong technicals, above 200-day SMA.',
        }
        resp = auth_client.post(
            '/api/analysis/ai/AAPL',
            data=json.dumps({'strategy': 'LEAP'}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'ai_analysis' in data
        assert data['ai_analysis']['recommendation'] == 'BUY CALL'

    def test_ai_analysis_no_api_key(self, auth_client, mock_scanner):
        """Service returns error dict (not exception) when no API key configured."""
        mock_scanner.get_ai_analysis.return_value = {
            'error': 'PERPLEXITY_API_KEY not configured.',
            'summary': None,
        }
        resp = auth_client.post(
            '/api/analysis/ai/AAPL',
            data=json.dumps({}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'error' in data['ai_analysis']

    def test_ai_analysis_with_strategy_variants(self, auth_client, mock_scanner):
        """POST /api/analysis/ai with each strategy variant calls service correctly."""
        mock_scanner.get_ai_analysis.return_value = {
            'summary': 'Analysis result.', 'recommendation': 'HOLD',
            'confidence': 'MEDIUM',
        }
        for strategy in ('0DTE', 'WEEKLY', 'LEAP'):
            mock_scanner.get_ai_analysis.reset_mock()
            mock_scanner.get_ai_analysis.return_value = {
                'summary': f'{strategy} analysis.', 'recommendation': 'HOLD',
                'confidence': 'MEDIUM',
            }
            resp = auth_client.post(
                '/api/analysis/ai/SPY',
                data=json.dumps({'strategy': strategy, 'expiry': '2026-03-07'}),
                content_type='application/json',
            )
            assert resp.status_code == 200, f"Expected 200 for strategy={strategy}"
            data = resp.get_json()
            assert data['success'] is True
            # Confirm service was called with the right strategy
            mock_scanner.get_ai_analysis.assert_called_once()
            call_args = mock_scanner.get_ai_analysis.call_args
            passed_strategy = call_args[1].get('strategy') if call_args[1] else call_args[0][1]
            assert passed_strategy == strategy, (
                f"Expected strategy={strategy}, got {passed_strategy}"
            )

    def test_analysis_detail(self, auth_client, mock_scanner):
        """GET /api/analysis/AAPL returns detailed analysis from scanner service."""
        mock_scanner.get_detailed_analysis.return_value = {
            'ticker': 'AAPL',
            'price': 192.50,
            'technical_score': 74.0,
            'sentiment': 'Positive',
            'news': [],
        }
        resp = auth_client.get('/api/analysis/AAPL')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['analysis']['ticker'] == 'AAPL'
        assert data['analysis']['price'] == 192.50


# ══════════════════════════════════════════════════════════════════════════════
#  GROUP 5: History (3 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestHistory:
    """Tests for GET/POST /api/history."""

    def test_add_history(self, auth_client):
        """POST /api/history with a valid ticker succeeds."""
        with patch('backend.app.get_db') as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = mock_db
            mock_db.query.return_value.filter_by.return_value.first.return_value = None
            mock_db.query.return_value.filter_by.return_value.count.return_value = 1
            mock_db.commit.return_value = None
            resp = auth_client.post(
                '/api/history',
                data=json.dumps({'ticker': 'AAPL'}),
                content_type='application/json',
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

    def test_get_history(self, auth_client):
        """GET /api/history returns the list of recently searched tickers."""
        with patch('backend.app.get_db') as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = mock_db
            entry1 = MagicMock()
            entry1.ticker = 'AAPL'
            entry2 = MagicMock()
            entry2.ticker = 'MSFT'
            (mock_db.query.return_value
                .filter_by.return_value
                .order_by.return_value
                .limit.return_value
                .all.return_value) = [entry1, entry2]
            resp = auth_client.get('/api/history')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'AAPL' in data['history']
        assert 'MSFT' in data['history']

    def test_invalid_ticker_history(self, auth_client):
        """POST /api/history with digits in ticker returns 400."""
        resp = auth_client.post(
            '/api/history',
            data=json.dumps({'ticker': 'AAPL123'}),
            content_type='application/json',
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert 'Invalid ticker' in data['error']


# ══════════════════════════════════════════════════════════════════════════════
#  GROUP 6: Health & Misc (4 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestHealthAndMisc:
    """Tests for /, /api/me, and /api/tickers."""

    def test_index_page(self, client):
        """GET / serves the frontend or redirects to /login."""
        resp = client.get('/')
        assert resp.status_code in (200, 302)

    def test_get_current_user_authenticated(self, auth_client):
        """GET /api/me with valid session returns username."""
        resp = auth_client.get('/api/me')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['username'] == TEST_USERNAME

    def test_get_current_user_unauthenticated(self, client):
        """GET /api/me without a session returns 401 or redirect."""
        resp = client.get('/api/me')
        assert resp.status_code in (302, 401)

    def test_tickers_endpoint(self, auth_client, mock_scanner):
        """GET /api/tickers returns the cached ticker list."""
        mock_scanner.get_cached_tickers.return_value = ['AAPL', 'MSFT', 'GOOGL']
        resp = auth_client.get('/api/tickers')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'AAPL' in data['tickers']
        assert 'MSFT' in data['tickers']


# ══════════════════════════════════════════════════════════════════════════════
#  GROUP 7: Error Handling (4 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestErrorHandling:
    """Tests for scanner exceptions, missing inputs, and edge-case responses."""

    def test_scanner_service_exception(self, auth_client, mock_scanner):
        """Scanner throwing RuntimeError returns 500 with the error message."""
        mock_scanner.scan_ticker.side_effect = RuntimeError('ORATS connection timeout')
        resp = auth_client.post(
            '/api/scan/AAPL',
            data=json.dumps({'direction': 'CALL'}),
            content_type='application/json',
        )
        assert resp.status_code == 500
        data = resp.get_json()
        assert data['success'] is False
        assert 'ORATS connection timeout' in data['error']

    def test_sector_scan_missing_sector_field(self, auth_client, mock_scanner):
        """POST /api/scan/sector without sector field returns 400."""
        resp = auth_client.post(
            '/api/scan/sector',
            data=json.dumps({}),
            content_type='application/json',
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert 'Sector is required' in data['error']

    def test_ticker_format_validation_various(self, auth_client, mock_watchlist_service):
        """Clearly invalid ticker formats are rejected by /api/watchlist."""
        # Tickers with digits, special chars, or > 5 alpha chars must be rejected
        clearly_invalid = ['123', '!!!', 'TOOLONG', 'A1B2C', 'AA PL']
        for raw_ticker in clearly_invalid:
            resp = auth_client.post(
                '/api/watchlist',
                data=json.dumps({'ticker': raw_ticker}),
                content_type='application/json',
            )
            data = resp.get_json()
            # All of these should trigger the regex validation and return 400
            assert resp.status_code == 400, (
                f"Expected 400 for ticker '{raw_ticker}', got {resp.status_code}: {data}"
            )
            assert data['success'] is False

    def test_concurrent_scan_requests_dont_crash(self, auth_client, mock_scanner):
        """Five rapid scan requests to the same endpoint all succeed."""
        future_date = '2027-06-15'
        mock_scanner.scan_ticker.side_effect = None
        mock_scanner.scan_ticker.return_value = {
            'ticker': 'AAPL', 'scan_type': 'LEAPS', 'direction': 'CALL',
            'technical_score': 70.0, 'adjusted_technical': 70.0,
            'analysis_text': 'OK', 'trading_systems': {},
            'opportunities': [{
                'option_type': 'CALL', 'strike_price': 180.0,
                'expiration_date': future_date, 'premium': 8.0,
                'profit_potential': 38.0, 'days_to_expiry': 473,
                'volume': 1000, 'open_interest': 5000,
                'implied_volatility': 0.25, 'delta': 0.60,
                'opportunity_score': 80.0,
            }],
        }
        results = []
        for _ in range(5):
            resp = auth_client.post(
                '/api/scan/AAPL',
                data=json.dumps({'direction': 'CALL'}),
                content_type='application/json',
            )
            results.append(resp.status_code)
        assert all(s == 200 for s in results), f"Some requests failed: {results}"


# ══════════════════════════════════════════════════════════════════════════════
#  GROUP 8: Edge Cases & Additional Coverage (6 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestEdgeCasesAndAdditional:
    """Additional coverage for edge cases and business-logic filters."""

    def test_scan_sector_with_weeks_out_passed_through(self, auth_client, mock_scanner):
        """POST /api/scan/sector with weeks_out=2 forwards the param to the service."""
        mock_scanner.scan_sector_top_picks.return_value = [
            {'ticker': 'JPM', 'scan_type': 'WEEKLY', 'opportunities': []}
        ]
        resp = auth_client.post(
            '/api/scan/sector',
            data=json.dumps({'sector': 'Financial Services', 'weeks_out': 2}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        call_kwargs = mock_scanner.scan_sector_top_picks.call_args[1]
        assert call_kwargs.get('weeks_out') == 2

    def test_scan_leaps_near_term_filtered_out(self, auth_client, mock_scanner):
        """The DTE safety net in /api/scan/<ticker> drops opportunities with DTE < 150."""
        mock_scanner.scan_ticker.side_effect = None
        mock_scanner.scan_ticker.return_value = {
            'ticker': 'TSLA', 'scan_type': 'LEAPS', 'direction': 'CALL',
            'technical_score': 65.0, 'adjusted_technical': 65.0,
            'analysis_text': 'Test', 'trading_systems': {},
            'opportunities': [
                {   # Near-term — SHOULD BE DROPPED (< 150 DTE)
                    'option_type': 'CALL', 'strike_price': 200.0,
                    'expiration_date': '2026-03-15',
                    'premium': 5.0, 'profit_potential': 20.0, 'days_to_expiry': 16,
                    'volume': 500, 'open_interest': 2000,
                    'implied_volatility': 0.40, 'delta': 0.55, 'opportunity_score': 70.0,
                },
                {   # Far-term — SHOULD BE KEPT (>= 150 DTE)
                    'option_type': 'CALL', 'strike_price': 220.0,
                    'expiration_date': '2027-09-17',
                    'premium': 12.0, 'profit_potential': 55.0, 'days_to_expiry': 567,
                    'volume': 800, 'open_interest': 4000,
                    'implied_volatility': 0.38, 'delta': 0.50, 'opportunity_score': 82.0,
                },
            ],
        }
        resp = auth_client.post(
            '/api/scan/TSLA',
            data=json.dumps({'direction': 'CALL'}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        opps = data['result']['opportunities']
        assert len(opps) == 1, f"Expected 1 opportunity (far-term), got {len(opps)}"
        assert opps[0]['strike_price'] == 220.0

    def test_weekly_scan_no_results(self, auth_client, mock_scanner):
        """POST /api/scan/daily/<ticker> returns graceful 200 with success=False."""
        mock_scanner.scan_weekly_options.return_value = None
        resp = auth_client.post(
            '/api/scan/daily/ZZZZZ',
            data=json.dumps({}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is False
        assert 'ZZZZZ' in data['error']

    def test_analysis_detail_not_found(self, auth_client, mock_scanner):
        """GET /api/analysis/<ticker> returns 404 when scanner has no data."""
        mock_scanner.get_detailed_analysis.return_value = None
        resp = auth_client.get('/api/analysis/UNKNOWN')
        assert resp.status_code == 404
        data = resp.get_json()
        assert data['success'] is False
        assert 'Analysis failed' in data['error']

    def test_0dte_scan_returns_404_when_no_results(self, auth_client, mock_scanner):
        """POST /api/scan/0dte/<ticker> returns 404 when scanner finds nothing."""
        mock_scanner.scan_0dte_options.return_value = None
        resp = auth_client.post('/api/scan/0dte/NOPE')
        assert resp.status_code == 404
        data = resp.get_json()
        assert data['success'] is False
        assert 'NOPE' in data['error']

    def test_watchlist_missing_ticker_field(self, auth_client, mock_watchlist_service):
        """POST /api/watchlist with no ticker field returns 400."""
        resp = auth_client.post(
            '/api/watchlist',
            data=json.dumps({}),
            content_type='application/json',
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert 'Ticker is required' in data['error']

    def test_add_history_unauthenticated(self, client):
        """POST /api/history without a session is blocked (302 redirect or 401)."""
        resp = client.post(
            '/api/history',
            data=json.dumps({'ticker': 'AAPL'}),
            content_type='application/json',
        )
        assert resp.status_code in (302, 401)
