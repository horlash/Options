import sys
import os
import logging

logger = logging.getLogger(__name__)

# Force UTF-8 output encoding (Windows CMD uses cp1252 by default, crashes on emoji)
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Add project root to sys.path so 'backend' module is found
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask, jsonify, request, render_template, session, redirect, send_from_directory
from flask_cors import CORS
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    HAS_LIMITER = True
except ImportError:
    HAS_LIMITER = False
from backend.config import Config
from backend.database.models import init_db, SearchHistory, get_db
from backend.services.hybrid_scanner_service import HybridScannerService as ScannerService
from backend.services.watchlist_service import WatchlistService
from backend.security import Security
from datetime import datetime
import atexit
import re

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
static_folder = os.path.join(project_root, 'frontend')

app = Flask(__name__, static_folder=static_folder, static_url_path='')
app.config.from_object(Config)

# CORS: Restrict allowed origins (configurable via ALLOWED_ORIGINS env var)
_allowed_origins = os.getenv('ALLOWED_ORIGINS', '').split(',') if os.getenv('ALLOWED_ORIGINS') else []
if _allowed_origins:
    CORS(app, origins=_allowed_origins, supports_credentials=True)
else:
    # Development fallback: allow all origins but log warning
    CORS(app)
    logger.warning("ALLOWED_ORIGINS not set — CORS allows all origins. Set ALLOWED_ORIGINS for production.")

security_service = Security(app)

# Warn if SECRET_KEY is auto-generated (sessions won't persist)
if Config.SECRET_KEY_IS_DEFAULT:
    logger.warning("SECRET_KEY not set — using random key. Sessions will not persist across restarts.")

# XC-7: Rate limiting on login endpoint to prevent brute-force attacks
if HAS_LIMITER:
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=[],            # No global limit — only applied per-route
        storage_uri="memory://",      # In-memory; works fine for single-process Pi deploy
    )
else:
    limiter = None
    logging.getLogger(__name__).warning(
        "flask-limiter not installed — login rate limiting disabled. "
        "Run: pip install flask-limiter>=3.5.0"
    )

# Register paper trading API routes (Phase 3)
from backend.api.paper_routes import paper_bp
app.register_blueprint(paper_bp)

# Initialize database
init_db()

# P1-A12: Validate ENCRYPTION_KEY at startup (needed for Tradier token encryption)
if not Config.ENCRYPTION_KEY:
    logging.getLogger(__name__).warning(
        "ENCRYPTION_KEY not set. Tradier token encryption/decryption will fail. "
        "Set ENCRYPTION_KEY env var for paper trading with Tradier."
    )

# Global service instance
scanner_service = None

def get_scanner():
    global scanner_service
    if scanner_service is None:
        try:
            logger.info("Initializing global ScannerService...")
            scanner_service = ScannerService()
            logger.info("ScannerService initialized.")
        except Exception as e:
            logger.error(f"Error initializing ScannerService: {e}")
            raise e
    return scanner_service

# ...

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    """Login page and API"""
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        if security_service.login_user(username, password):
            return jsonify({'success': True})
            
        return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

    # GET request - serve login page
    return app.send_static_file('login.html')

# XC-7: Apply rate limit to login — 5 attempts/minute per IP
# Prevents brute-force attacks on the login endpoint
if limiter is not None:
    login_page = limiter.limit("5/minute")(login_page)

@app.route('/logout')
def logout():
    """Logout user"""
    security_service.logout_user()
    return redirect('/login')

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/v2')
def index_v2():
    return send_from_directory(os.path.join(project_root, 'frontend', 'scanner-demo'), 'index.html')

@app.route('/v2/<path:filename>')
def serve_v2_static(filename):
    return send_from_directory(os.path.join(project_root, 'frontend', 'scanner-demo'), filename)

@app.route('/api/me', methods=['GET'])
def get_current_user():
    """Return the logged-in username for frontend display"""
    username = session.get('user')
    if username:
        return jsonify({'success': True, 'username': username})
    return jsonify({'success': False, 'username': None}), 401

# Serve static data files (for tickers.json)
@app.route('/api/data/<path:filename>')
def serve_data(filename):
    data_dir = os.path.join(project_root, 'backend', 'data')
    return send_from_directory(data_dir, filename)

@app.route('/api/watchlist', methods=['GET'])
def get_watchlist():
    """Get current watchlist"""
    try:
        current_user = session.get('user')
        if not current_user:
             return jsonify({'success': False, 'error': 'Not authenticated'}), 401

        watchlist_service = WatchlistService()
        watchlist = watchlist_service.get_watchlist(current_user)
        watchlist_service.close()
        
        return jsonify({
            'success': True,
            'watchlist': watchlist
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/watchlist', methods=['POST'])
def add_to_watchlist():
    """Add ticker to watchlist"""
    try:
        current_user = session.get('user')
        if not current_user:
             return jsonify({'success': False, 'error': 'Not authenticated'}), 401

        data = request.get_json()
        ticker = data.get('ticker')
        
        if not ticker:
            return jsonify({
                'success': False,
                'error': 'Ticker is required'
            }), 400
        
        # BUG-2 FIX: Validate ticker format (1-5 uppercase letters only)
        ticker = ticker.strip().upper()
        if not re.match(r'^[A-Z]{1,5}$', ticker):
            return jsonify({
                'success': False,
                'error': f'Invalid ticker format: {ticker}. Use 1-5 letters (e.g. AAPL, MSFT).'
            }), 400
        
        watchlist_service = WatchlistService()
        success, message = watchlist_service.add_ticker(ticker, current_user)
        watchlist_service.close()
        
        return jsonify({
            'success': success,
            'message': message
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/watchlist/<ticker>', methods=['DELETE'])
def remove_from_watchlist(ticker):
    """Remove ticker from watchlist"""
    try:
        current_user = session.get('user')
        if not current_user:
             return jsonify({'success': False, 'error': 'Not authenticated'}), 401

        watchlist_service = WatchlistService()
        success, message = watchlist_service.remove_ticker(ticker, current_user)
        watchlist_service.close()
        
        return jsonify({
            'success': success,
            'message': message
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/scan', methods=['POST'])
def run_scan():
    """Run LEAP options scan on watchlist"""
    try:
        current_user = session.get('user')
        if not current_user:
             return jsonify({'success': False, 'error': 'Not authenticated'}), 401
             
        # Get user's watchlist
        watchlist_service = WatchlistService()
        watchlist = watchlist_service.get_watchlist(current_user)
        watchlist_service.close()
        
        # Use singleton scanner for watchlist scan (user-scoped)
        service = get_scanner()
        results = service.scan_watchlist(username=current_user)
        
        return jsonify({
            'success': True,
            'results': results
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/scan/<ticker>', methods=['POST'])
def scan_ticker(ticker):
    """Run scan on a specific ticker. Supports direction: CALL, PUT, or BOTH (default)."""
    try:
        scanner_service = get_scanner()
        data = request.get_json(silent=True) or {}
        direction = data.get('direction', 'BOTH').upper()
        if direction not in ('CALL', 'PUT', 'BOTH'):
            direction = 'BOTH'

        if direction == 'BOTH':
            # Scan both directions and merge opportunities
            result_call = scanner_service.scan_ticker(ticker, strict_mode=False, direction='CALL')
            result_put = scanner_service.scan_ticker(ticker, strict_mode=False, direction='PUT')

            if result_call and result_put:
                # Merge: preserve both CALL and PUT metadata independently
                # Each scan produces its own technical_score, analysis_text, etc.
                merged = {
                    'ticker': result_call.get('ticker', ticker),
                    'scan_type': result_call.get('scan_type', 'LEAPS'),
                    'direction': 'BOTH',
                    'opportunities': [],
                    'trading_systems': result_call.get('trading_systems', {}),
                    'call_summary': {
                        'technical_score': result_call.get('technical_score'),
                        'adjusted_technical': result_call.get('adjusted_technical'),
                        'analysis_text': result_call.get('analysis_text'),
                    },
                    'put_summary': {
                        'technical_score': result_put.get('technical_score'),
                        'adjusted_technical': result_put.get('adjusted_technical'),
                        'analysis_text': result_put.get('analysis_text'),
                    }
                }
                call_opps = result_call.get('opportunities', [])
                put_opps = result_put.get('opportunities', [])
                merged['opportunities'] = call_opps + put_opps
                result = merged
            elif result_call:
                result = result_call
            elif result_put:
                result = result_put
            else:
                result = None
        else:
            result = scanner_service.scan_ticker(ticker, strict_mode=False, direction=direction)

        scanner_service.close()
        
        if result:
            # Safety net: ensure LEAP opportunities have DTE >= 150
            # (prevents near-term options leaking through stale cache data)
            opps = result.get('opportunities', [])
            from datetime import datetime as dt_check
            now = dt_check.now()
            filtered_opps = []
            for o in opps:
                exp_str = o.get('expiration_date', '')
                try:
                    if isinstance(exp_str, str) and exp_str:
                        exp_dt = dt_check.strptime(exp_str[:10], '%Y-%m-%d')
                        dte = (exp_dt - now).days
                        if dte < 150:
                            continue  # Drop near-term leakers
                        o['days_to_expiry'] = dte  # Ensure consistency
                except (ValueError, TypeError, KeyError):
                    pass
                filtered_opps.append(o)
            result['opportunities'] = filtered_opps

            return jsonify({
                'success': True,
                'result': result
            })
        else:
            return jsonify({
                'success': False,
                'error': f'Ticker {ticker} rejected by filters (MTA/Moat) or data unavailable'
            }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/scan/daily', methods=['POST'])
def run_daily_scan():
    """Run Daily/Weekly options scan on watchlist"""
    try:
        current_user = session.get('user')
        if not current_user:
             return jsonify({'success': False, 'error': 'Not authenticated'}), 401
             
        data = request.get_json() or {}
        weeks_out = int(data.get('weeks_out', 0))
        
        # Get user's watchlist to iterate over
        watchlist_service = WatchlistService()
        watchlist = watchlist_service.get_watchlist(current_user)
        watchlist_service.close()
        
        # Service is global
        service = get_scanner()
        
        results = []
        for item in watchlist:
            res = service.scan_weekly_options(item['ticker'], weeks_out=weeks_out)
            if res:
                results.append(res)
        
        return jsonify({
            'success': True,
            'results': results
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/scan/daily/<ticker>', methods=['POST'])
def scan_ticker_daily(ticker):
    """Run Daily scan on a specific ticker. Already returns both CALL and PUT."""
    try:
        data = request.get_json() or {}
        weeks_out = int(data.get('weeks_out', 0))
        
        service = get_scanner()
        result = service.scan_weekly_options(ticker, weeks_out=weeks_out)
        
        if result:
            return jsonify({
                'success': True,
                'result': result
            })
        else:
            return jsonify({
                'success': False,
                'error': f'No opportunities found for {ticker}'
            }), 200
    except Exception as e:
        logger.error(f"ERROR in scan_ticker_daily: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500



@app.route('/api/tickers', methods=['GET'])
def get_tickers():
    """Get cached full ticker list for autocomplete"""
    try:
        service = get_scanner()
        tickers = service.get_cached_tickers()
        
        return jsonify({
            'success': True,
            'tickers': tickers
        })
    except Exception as e:
        logger.error(f"Error getting tickers: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/scan/sector', methods=['POST'])
def run_sector_scan():
    """Run Smart Sector Scan"""
    try:
        data = request.get_json() or {}
        sector = data.get('sector')
        
        # safely handle empty strings from frontend
        min_market_cap = int(data.get('min_market_cap') or 0)
        min_volume = int(data.get('min_volume') or 0)
        
        weeks_out = data.get('weeks_out') # None if not provided (LEAPS mode)
        industry = data.get('industry')
        is_0dte = data.get('is_0dte', False)  # Explicit 0DTE flag from frontend
        
        if not sector:
             return jsonify({'success': False, 'error': 'Sector is required'}), 400
        
        # F43: Backend validation for 0DTE sector scans (frontend blocks this, but
        # enforce server-side too). 0DTE requires same-day expiry on specific tickers,
        # not broad sector sweeps.
        # Note: weeks_out=0 means "This Week" expiry — NOT 0DTE. Only block explicit 0DTE.
        if is_0dte:
            return jsonify({
                'success': False,
                'error': '0DTE sector scans are not supported. Use single-ticker 0DTE scan instead.'
            }), 400
        
        # weeks_out: None = LEAPS mode, 0 = This Week, 1+ = weeks ahead
        # Do NOT default to 1 — let None pass through for LEAPS sector scans
        if weeks_out is not None:
            weeks_out = int(weeks_out)
        
        service = get_scanner()
        logger.info(f"Starting Sector Scan: {sector} (weeks_out={weeks_out}, industry={industry})")
        
        results = service.scan_sector_top_picks(
            sector=sector,
            min_market_cap=min_market_cap,
            min_volume=min_volume,
            weeks_out=weeks_out,
            industry=industry
        )
        
        return jsonify({
            'success': True,
            'results': results
        })
    except Exception as e:
        logger.error(f"Error in sector scan: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    """Get recent search history for current user"""
    try:
        current_user = session.get('user')
        if not current_user:
             return jsonify({'success': False, 'error': 'Not authenticated'}), 401
             
        db = get_db()
        history = db.query(SearchHistory).filter_by(username=current_user).order_by(SearchHistory.last_searched.desc()).limit(15).all()
        return jsonify({
            'success': True,
            'history': [h.ticker for h in history]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/history', methods=['POST'])
def add_history():
    """Add ticker to search history"""
    try:
        data = request.get_json()
        ticker = data.get('ticker')
        if not ticker:
            return jsonify({'success': False, 'error': 'Ticker required'}), 400
        
        # Backend safety net: reject invalid ticker formats
        ticker = ticker.strip().upper()
        if not re.match(r'^[A-Z]{1,5}$', ticker):
            return jsonify({'success': False, 'error': f'Invalid ticker format: {ticker}'}), 400
            
        db = get_db()
        current_user = session.get('user')
        
        if not current_user:
             return jsonify({'success': False, 'error': 'Not authenticated'}), 401
             
        # Check if exists for this user
        existing = db.query(SearchHistory).filter_by(username=current_user, ticker=ticker).first()
        if existing:
            existing.last_searched = datetime.utcnow()
        else:
            new_entry = SearchHistory(username=current_user, ticker=ticker)
            db.add(new_entry)
            
        db.commit()
        
        # Cleanup old entries (keep top 15 mostly recent PER USER)
        total_count = db.query(SearchHistory).filter_by(username=current_user).count()
        if total_count > 15:
            # Delete oldest for this user
            subquery = db.query(SearchHistory.id).filter_by(username=current_user).order_by(SearchHistory.last_searched.desc()).limit(15)
            db.query(SearchHistory).filter(SearchHistory.username == current_user, ~SearchHistory.id.in_(subquery)).delete(synchronize_session=False)
            db.commit()
            
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error adding history: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/analysis/<ticker>', methods=['GET'])
def get_analysis_detail(ticker):
    """Get detailed analysis for a ticker"""
    try:
        service = get_scanner()
        expiry = request.args.get('expiry')  # Optional: from card's expiration_date
        analysis = service.get_detailed_analysis(ticker, expiry_date=expiry)
        
        if analysis:
            return jsonify({
                'success': True,
                'analysis': analysis
            })
        else:
             return jsonify({
                'success': False,
                'error': 'Analysis failed or no data found'
            }), 404
    except Exception as e:
        logger.error(f"Error getting analysis: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/scan/0dte/<ticker>', methods=['POST'])
def scan_0dte(ticker):
    """Run 0DTE scan on a ticker"""
    try:
        service = get_scanner()
        result = service.scan_0dte_options(ticker)
        
        if result:
             return jsonify({'success': True, 'result': result})
        else:
             return jsonify({'success': False, 'error': f'No 0DTE opportunities found for {ticker}'}), 404
    except Exception as e:
        logger.error(f"Error 0DTE scan: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/analysis/ai/<ticker>', methods=['POST'])
def get_ai_analysis_route(ticker):
    """Get AI-Reasoned Analysis for ticker"""
    try:
        data = request.get_json() or {}
        strategy = data.get('strategy', 'LEAP')
        expiry = data.get('expiry')
        
        strike = data.get('strike')
        opt_type = data.get('type')
        
        service = get_scanner()
        # Ensure we block if no API key? Service handles it returning error dict.
        analysis = service.get_ai_analysis(ticker, strategy=strategy, expiry_date=expiry, strike=strike, type=opt_type)
        
        return jsonify({
            'success': True,
            'ai_analysis': analysis
        })
    except Exception as e:
        logger.error(f"Error getting AI analysis: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ═══════════════════════════════════════════════════════════════
# Phase 3: APScheduler — Background Engine
# ═══════════════════════════════════════════════════════════════

def init_scheduler(app):
    """Initialize APScheduler with the monitoring engine jobs.

    Jobs:
      1. sync_tradier_orders   — every 60s  (market hours only)
      2. update_price_snapshots — every 40s  (market hours only)
      3. pre_market_bookend     — Mon-Fri 9:25 AM ET
      4. post_market_bookend    — Mon-Fri 4:05 PM ET
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger
        from apscheduler.triggers.cron import CronTrigger
        from backend.services.monitor_service import MonitorService
        import pytz

        EASTERN = pytz.timezone('US/Eastern')
        monitor = MonitorService()
        scheduler = BackgroundScheduler(daemon=True)

        # Job 1: Sync order status from Tradier (every 60s)
        scheduler.add_job(
            func=monitor.sync_tradier_orders,
            trigger=IntervalTrigger(seconds=60),
            id='sync_tradier_orders',
            name='Tradier Order Sync (60s)',
            replace_existing=True,
            max_instances=1,
        )

        # Job 2: Update price snapshots via ORATS (every 40s)
        scheduler.add_job(
            func=monitor.update_price_snapshots,
            trigger=IntervalTrigger(seconds=40),
            id='update_price_snapshots',
            name='ORATS Price Snapshots (40s)',
            replace_existing=True,
            max_instances=1,
        )

        # Job 3: Pre-market bookend (9:25 AM ET, Mon-Fri)
        scheduler.add_job(
            func=monitor.capture_bookend_snapshot,
            trigger=CronTrigger(
                day_of_week='mon-fri',
                hour=9,
                minute=25,
                timezone=EASTERN,
            ),
            args=['OPEN_BOOKEND'],
            id='pre_market_bookend',
            name='Pre-Market Bookend (9:25 AM ET)',
            replace_existing=True,
            max_instances=1,  # P2-A3: prevent overlapping bookend runs
        )

        # Job 4: Post-market bookend (4:05 PM ET, Mon-Fri)
        scheduler.add_job(
            func=monitor.capture_bookend_snapshot,
            trigger=CronTrigger(
                day_of_week='mon-fri',
                hour=16,
                minute=5,
                timezone=EASTERN,
            ),
            args=['CLOSE_BOOKEND'],
            id='post_market_bookend',
            name='Post-Market Bookend (4:05 PM ET)',
            replace_existing=True,
            max_instances=1,  # P2-A3: prevent overlapping bookend runs
        )

        # P0-8: Job 5: Lifecycle sync — process stale PENDING/CLOSING trades + expire
        scheduler.add_job(
            func=monitor.lifecycle_sync,
            trigger=IntervalTrigger(seconds=120),
            id='lifecycle_sync',
            name='Lifecycle Sync (120s)',
            replace_existing=True,
            max_instances=1,
        )

        scheduler.start()
        atexit.register(lambda: scheduler.shutdown(wait=False))

        logger = logging.getLogger(__name__)
        logger.info(
            "APScheduler started — 5 jobs registered "
            "(order sync 60s, snapshots 40s, bookends 9:25/16:05 ET, lifecycle 120s)"
        )
        logger.info(
            "APScheduler started - 5 background jobs registered"
            "   • sync_tradier_orders  (every 60s)\n"
            "   • update_price_snapshots (every 40s)\n"
            "   • pre_market_bookend   (9:25 AM ET Mon-Fri)\n"
            "   • post_market_bookend  (4:05 PM ET Mon-Fri)\n"
            "   • lifecycle_sync       (every 120s)\n"
        )

    except ImportError:
        logger.warning(
            "apscheduler not installed - "
            "Run: pip install apscheduler pytz\n"
            "   Background monitoring engine will NOT run.\n"
        )
    except Exception as e:
        logger.error(f"Scheduler failed to start: {e}")


# Start scheduler unconditionally. APScheduler's replace_existing=True
# prevents duplicate jobs if the module is re-imported.
init_scheduler(app)


if __name__ == '__main__':
    app.run(
        debug=Config.FLASK_DEBUG,
        port=Config.PORT,
        threaded=True
    )
