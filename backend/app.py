import sys
import os

# Force UTF-8 output encoding (Windows CMD uses cp1252 by default, crashes on emoji)
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Add project root to sys.path so 'backend' module is found
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask, jsonify, request, render_template, session, redirect, send_from_directory
from flask_cors import CORS
from backend.config import Config
from backend.database.models import init_db, SearchHistory, get_db
from backend.services.hybrid_scanner_service import HybridScannerService as ScannerService
from backend.services.watchlist_service import WatchlistService
from backend.security import Security
from datetime import datetime

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
static_folder = os.path.join(project_root, 'frontend')

app = Flask(__name__, static_folder=static_folder, static_url_path='')
app.config.from_object(Config)
CORS(app)
security_service = Security(app)

# Initialize database
init_db()

# Global service instance
scanner_service = None

def get_scanner():
    global scanner_service
    if scanner_service is None:
        try:
            print("Initializing global ScannerService...", flush=True)
            scanner_service = ScannerService()
            print("ScannerService initialized.", flush=True)
        except Exception as e:
            print(f"Error initializing ScannerService: {e}", flush=True)
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

@app.route('/logout')
def logout():
    """Logout user"""
    security_service.logout_user()
    return redirect('/login')

@app.route('/')
def index():
    return app.send_static_file('index.html')



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
        
        # Override scanner logic to use THIS watchlist, not fetch all from DB inside scanner
        # We need to check if ScannerService.scan_watchlist() supports passing a list.
        # Reading models suggests it might fetch from DB internaly. 
        # Let's check HybridScannerService.scan_watchlist later. 
        # For now, let's assume we might need to update ScannerService OR 
        # manually loop if the scanner service doesn't support list.
        # But wait, looking at past `app.py`, `scanner_service.scan_watchlist()` takes no args.
        # We need to check `HybridScannerService.scan_watchlist` implementation.
        
        # ACTUALLY, strict user segregation means the scanner should ONLY scan what the user has.
        # If `scan_watchlist` pulls ALL tickers from DB, it's wrong.
        # I'll update this route to fetch tickers first, then ask scanner to scan THEM.
        
        # For this step, I will updated run_daily_scan first which explicitly iterates.
        
        scanner_service = ScannerService()
        # Modifying to pass tickers if supported, or we need to update ScannerService
        # Let's assume we will update ScannerService next if needed.
        # For now, let's look at `run_daily_scan` below which DOES iterate.
        
        results = scanner_service.scan_watchlist(username=current_user) # Proposed change to scanner
        scanner_service.close()
        
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
    """Run scan on a specific ticker"""
    try:
        # Scan specific ticker doesn't need watchlist check strictly as per plan
        scanner_service = ScannerService()
        # [MODIFIED] Use strict_mode=False for manual single-ticker scans
        # This allows users to "force" a scan on speculative/poor-quality stocks (EOSE, etc.)
        result = scanner_service.scan_ticker(ticker, strict_mode=False)
        scanner_service.close()
        
        if result:
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
    """Run Daily scan on a specific ticker"""
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
                'error': f'Failed to scan {ticker}'
            }), 500
    except Exception as e:
        print(f"ERROR in scan_ticker_daily: {e}")
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
        print(f"Error getting tickers: {e}")
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
        
        weeks_out = data.get('weeks_out') # None if not provided
        industry = data.get('industry')
        
        if not sector:
             return jsonify({'success': False, 'error': 'Sector is required'}), 400
             
        service = get_scanner()
        print(f"Starting Sector Scan: {sector} (weeks_out={weeks_out}, industry={industry})", flush=True)
        
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
        print(f"Error in sector scan: {e}")
        import traceback
        traceback.print_exc()
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
        print(f"Error adding history: {e}")
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
        print(f"Error getting analysis: {e}")
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
        print(f"Error 0DTE scan: {e}")
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
        print(f"Error getting AI analysis: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(
        debug=Config.FLASK_DEBUG,
        port=Config.PORT,
        threaded=True
    )
