"""
HybridScannerService — Orchestrator
====================================
Refactored from a 2,250-line monolith into a slim orchestrator that delegates
scanning logic to focused sub-modules:

  - scanner_leaps.py   → scan_ticker_leaps()       (LEAPS scanning)
  - scanner_weekly.py  → scan_weekly(), scan_0dte() (Weekly/0DTE scanning)
  - scanner_sector.py  → scan_sector_top_picks(), scan_watchlist()
  - scanner_utils.py   → Greeks, caching, AI analysis, sentiment, helpers

The public API contract is unchanged — all existing callers (app.py routes,
batch_manager, etc.) continue to call the same method names on this class.
"""

import os
import json
import logging
import time
from datetime import datetime, timedelta

from backend.api.tradier import TradierAPI
from backend.api.fmp import FMPAPI
from backend.api.free_news import FreeNewsAPIs
from backend.api.finnhub import FinnhubAPI
from backend.analysis.technical_indicators import TechnicalIndicators
from backend.analysis.sentiment_analyzer import SentimentAnalyzer
from backend.analysis.options_analyzer import OptionsAnalyzer
from backend.analysis.exit_manager import ExitManager
from backend.services.watchlist_service import WatchlistService
from backend.services.batch_manager import BatchManager
from backend.database.models import ScanResult, Opportunity, NewsCache, SessionLocal
from backend.services.reasoning_engine import ReasoningEngine
from backend.analysis.regime_detector import RegimeDetector, VIXRegime
from backend.analysis.macro_signals import MacroSignals
from backend.analysis.sector_analysis import SectorAnalysis
from backend.config import Config

# Sub-module imports (refactored from this file)
from backend.services.scanner_leaps import scan_ticker_leaps
from backend.services.scanner_weekly import scan_weekly, scan_0dte
from backend.services.scanner_sector import scan_sector_top_picks as _scan_sector_top_picks
from backend.services.scanner_sector import scan_watchlist as _scan_watchlist
from backend.services.scanner_utils import (
    calculate_greeks_black_scholes,
    enrich_greeks,
    cache_news,
    save_scan_results,
    get_latest_results as _get_latest_results,
    get_ai_analysis as _get_ai_analysis,
    sanitize_for_json,
    get_sentiment_score as _get_sentiment_score,
    get_detailed_analysis as _get_detailed_analysis,
    close as _close,
)

logger = logging.getLogger(__name__)


class HybridScannerService:
    """Scanner service using ORATS + Finnhub for options analysis.

    Orchestrator that delegates scanning logic to sub-modules while
    maintaining the same public API contract for all callers.
    """

    _ticker_cache = []
    _orats_universe = None      # Loaded from orats_universe.json
    _spy_history = None         # F11 FIX: class-level cache (shared across instances)

    # SMART SECTOR SCAN: Session cache for ORATS /cores data
    # Data is T-1 (prior trading day) so caching for 1 hour is safe.
    # Multiple sector scans in the same session reuse one API call.
    _cores_cache = None
    _cores_cache_time = 0
    CORES_CACHE_TTL = 3600      # 1 hour in seconds

    # ═══════════════════════════════════════════════════════════════════════
    #  INITIALIZATION
    # ═══════════════════════════════════════════════════════════════════════

    def __init__(self):
        self.yahoo_api = None  # REMOVED (Strict Mode)
        self.tradier_api = TradierAPI()
        self.fmp_api = FMPAPI()
        self.finnhub_api = FinnhubAPI()
        self.news_api = FreeNewsAPIs()
        self.technical_analyzer = TechnicalIndicators()
        self.sentiment_analyzer = SentimentAnalyzer()
        self.options_analyzer = OptionsAnalyzer()
        self.exit_manager = ExitManager()
        self.reasoning_engine = ReasoningEngine()
        self.watchlist_service = WatchlistService()
        self.batch_manager = BatchManager()
        self.db = SessionLocal()

        # --- Trading System Enhancements (S1-S7A) ---
        orats_ref = self.batch_manager.orats_api if hasattr(self.batch_manager, 'orats_api') else None
        self.regime_detector = RegimeDetector(orats_api=orats_ref) if Config.ENABLE_VIX_REGIME else None
        self.macro_signals = MacroSignals(
            orats_api=orats_ref,
            fmp_api_key=Config.FMP_API_KEY
        ) if Config.ENABLE_PUT_CALL_RATIO else None
        self.sector_analysis = SectorAnalysis(orats_api=orats_ref) if Config.ENABLE_SECTOR_MOMENTUM else None

        # Check configuration
        self.use_tradier = self.tradier_api.is_configured()
        self.use_schwab = False  # DISABLED
        self.use_orats = self.batch_manager.orats_api.is_configured() if hasattr(self.batch_manager, 'orats_api') else False

        # Initialize Ticker Cache if empty
        if not HybridScannerService._ticker_cache:
            self._refresh_ticker_cache()

        # Load ORATS universe for coverage checks
        if HybridScannerService._orats_universe is None:
            self._load_orats_universe()

        if self.use_orats:
            logger.info("ORATS API configured - Primary Source (History + Options)")
        else:
            logger.warning("ORATS API NOT configured - Critical Error for Full Switch")

    # ═══════════════════════════════════════════════════════════════════════
    #  TICKER CACHE & UNIVERSE
    # ═══════════════════════════════════════════════════════════════════════

    def _refresh_ticker_cache(self):
        """Load tickers from local JSON file (backend/data/tickers.json)"""
        logger.info("Loading Ticker Cache...")

        local_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'tickers.json')

        try:
            with open(local_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Check age
            last_updated_str = data.get('last_updated')
            if last_updated_str:
                last_updated = datetime.fromisoformat(last_updated_str)
                age_days = (datetime.now() - last_updated).days

                if age_days > 90:
                    logger.warning(f"Ticker list is {age_days} days old (>90 days)")
                    logger.warning("Run 'python backend/scripts/refresh_tickers.py' to update")
                else:
                    logger.info(f"Ticker list age: {age_days} days (updated {last_updated.strftime('%Y-%m-%d')})")

            tickers = data.get('tickers', [])

            # Normalize format
            filtered = []
            for t in tickers:
                filtered.append({
                    'symbol': t.get('symbol', '').upper(),
                    'name': t.get('name', ''),
                    'exchange': t.get('exchange', 'US'),
                    'sector': t.get('sector'),
                    'marketCap': t.get('marketCap', 0),
                    'volume': t.get('volume', 0)
                })

            HybridScannerService._ticker_cache = filtered
            logger.info(f"Loaded {len(filtered)} tickers from local cache")

        except FileNotFoundError:
            logger.error(f"Ticker file not found: {local_path}")
            logger.warning("Run 'python backend/scripts/refresh_tickers.py' to create it")
            HybridScannerService._ticker_cache = []
        except Exception as e:
            logger.error(f"Error loading tickers: {e}")
            HybridScannerService._ticker_cache = []

    def get_cached_tickers(self):
        return HybridScannerService._ticker_cache

    def _load_orats_universe(self):
        """Load ORATS ticker universe from local cache for O(1) coverage lookups."""
        orats_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'orats_universe.json')
        try:
            with open(orats_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            universe = set(data.get('tickers', {}).keys())
            HybridScannerService._orats_universe = universe

            # Check age
            last_updated = data.get('last_updated', '')
            if last_updated:
                updated_dt = datetime.fromisoformat(last_updated)
                age_days = (datetime.now() - updated_dt).days
                if age_days > 7:
                    logger.warning(f"ORATS universe cache is {age_days} days old. Run 'python backend/scripts/refresh_tickers_v3.py'")
                else:
                    logger.info(f"ORATS universe: {len(universe)} tickers (cache age: {age_days} days)")
            else:
                logger.info(f"ORATS universe: {len(universe)} tickers loaded")
        except FileNotFoundError:
            logger.warning("ORATS universe cache not found. Run 'python backend/scripts/refresh_tickers_v3.py'")
            HybridScannerService._orats_universe = set()
        except Exception as e:
            logger.warning(f"Error loading ORATS universe: {e}")
            HybridScannerService._orats_universe = set()

    def _is_orats_covered(self, ticker):
        """Check if a ticker is in the ORATS universe (O(1) lookup)."""
        if not HybridScannerService._orats_universe:
            return True  # If no universe loaded, don't block
        clean = ticker.replace('$', '').strip().upper()
        return clean in HybridScannerService._orats_universe

    def _normalize_ticker(self, ticker):
        """Normalize ticker symbol (uppercase, strip whitespace)."""
        ticker = ticker.upper().strip()
        return ticker

    # ═══════════════════════════════════════════════════════════════════════
    #  SCANNING — delegated to sub-modules
    # ═══════════════════════════════════════════════════════════════════════

    def scan_ticker(self, ticker, strict_mode=True, pre_fetched_data=None, direction='CALL', pre_fetched_history=None):
        """Scan a single ticker for LEAP opportunities. Delegates to scanner_leaps.
        
        Args:
            pre_fetched_history: Optional pre-fetched price history dict from
                                batch get_history_batch(). If provided, skips
                                the per-ticker ORATS history API call.
        """
        return scan_ticker_leaps(self, ticker, strict_mode, pre_fetched_data, direction, pre_fetched_history)

    def scan_weekly_options(self, ticker, weeks_out=0, strategy_tag="WEEKLY", pre_fetched_data=None):
        """Scan a ticker for weekly options opportunities. Delegates to scanner_weekly."""
        return scan_weekly(self, ticker, weeks_out, strategy_tag, pre_fetched_data)

    def scan_0dte_options(self, ticker):
        """Scan a ticker for 0DTE options. Delegates to scanner_weekly."""
        return scan_0dte(self, ticker)

    def scan_sector_top_picks(self, sector, min_volume, min_market_cap, limit=30, weeks_out=None, industry=None):
        """Scan top picks in a sector. Delegates to scanner_sector.
        
        SMART SECTOR SCAN (v2): Default limit raised from 15 to 30.
        Uses ORATS /cores for options-aware pre-filtering instead of FMP market-cap sort.
        """
        return _scan_sector_top_picks(self, sector, min_volume, min_market_cap, limit, weeks_out, industry)

    def _get_cores_cached(self, sector=None):
        """Return cached ORATS /cores data, refreshing if stale.

        SMART SECTOR SCAN: Caches the full /cores universe response so
        multiple sector scans in one session only make ONE API call.
        Data is T-1 (prior trading day close) so hourly caching is safe.

        Args:
            sector: Optional sector/industry name to filter.

        Returns:
            list[dict]: ORATS core records filtered by sector.
        """
        now = time.time()
        orats_api = self.batch_manager.orats_api if hasattr(self.batch_manager, 'orats_api') else None

        if not orats_api:
            return []

        # Check if cache needs refresh
        if (HybridScannerService._cores_cache is None or
                now - HybridScannerService._cores_cache_time > self.CORES_CACHE_TTL):
            try:
                # Fetch entire universe (no sector filter) — filter client-side
                HybridScannerService._cores_cache = orats_api.get_cores_bulk(sector=None)
                HybridScannerService._cores_cache_time = now
                logger.info(
                    f"\U0001f504 Refreshed ORATS /cores cache: "
                    f"{len(HybridScannerService._cores_cache)} tickers"
                )
            except Exception as e:
                logger.warning(f"\u26a0\ufe0f ORATS /cores cache refresh failed: {e}")
                if HybridScannerService._cores_cache:
                    logger.info("Using stale /cores cache")
                else:
                    return []

        # Client-side sector filter on cached data
        if sector and HybridScannerService._cores_cache:
            sector_lower = sector.lower().strip()
            etf_codes = orats_api.SECTOR_NAME_MAP.get(sector_lower, [])

            filtered = []
            for r in HybridScannerService._cores_cache:
                best_etf = (r.get("bestEtf") or "").upper()
                sector_name = (r.get("sectorName") or "").lower()

                if best_etf in etf_codes:
                    filtered.append(r)
                elif sector_lower in sector_name:
                    filtered.append(r)

            logger.info(f"\U0001f4e6 /cores cache hit: {len(filtered)} tickers in '{sector}'")
            return filtered

        return HybridScannerService._cores_cache or []

    def scan_watchlist(self, username=None):
        """Scan user's watchlist. Delegates to scanner_sector."""
        return _scan_watchlist(self, username)

    # ═══════════════════════════════════════════════════════════════════════
    #  UTILITIES — delegated to scanner_utils
    # ═══════════════════════════════════════════════════════════════════════

    def _calculate_greeks_black_scholes(self, S, K, T, sigma, r=0.045, opt_type='call'):
        return calculate_greeks_black_scholes(self, S, K, T, sigma, r, opt_type)

    def _enrich_greeks(self, ticker, strike, expiry_date_str, opt_type, current_price, iv, context_greeks=None):
        return enrich_greeks(self, ticker, strike, expiry_date_str, opt_type, current_price, iv, context_greeks)

    def _cache_news(self, ticker, articles, sentiment_analysis):
        return cache_news(self, ticker, articles, sentiment_analysis)

    def _save_scan_results(self, ticker, technical_score, sentiment_score, opportunities):
        return save_scan_results(self, ticker, technical_score, sentiment_score, opportunities)

    def get_latest_results(self):
        return _get_latest_results(self)

    def get_ai_analysis(self, ticker, strategy="LEAP", expiry_date=None, **kwargs):
        return _get_ai_analysis(self, ticker, strategy, expiry_date, **kwargs)

    def _sanitize_for_json(self, obj):
        return sanitize_for_json(obj)

    def get_sentiment_score(self, ticker):
        return _get_sentiment_score(self, ticker)

    def get_detailed_analysis(self, ticker, expiry_date=None):
        return _get_detailed_analysis(self, ticker, expiry_date)

    def close(self):
        return _close(self)
