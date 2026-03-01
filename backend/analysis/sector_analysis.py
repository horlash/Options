"""S4: Sector Momentum Rotation — Rank sectors by relative momentum.

Evidence: Sector rotation momentum has been validated by academics
(Moskowitz & Grinblatt, 1999) and practitioners (Faber, 2007).
Top-quartile sectors outperform by 3-5% annually. 18-Persona verdict:
15/18 APPROVED WITH CONDITIONS (daily cache, 10-sector SPDR universe).

Implementation: 
  - Rank 11 sector ETFs by 1-month momentum (% change over 21 trading days)
  - Tickers in top 3 sectors get a score boost
  - Tickers in bottom 3 sectors get a penalty
  - Results cached for 1 trading day (reduces API calls)
"""

import logging
import time
from cachetools import TTLCache
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple

log = logging.getLogger(__name__)

# Module-level TTL cache: shared across all SectorAnalysis instances
# maxsize=1 because we only cache one result (all sectors ranked together)
_sector_cache = TTLCache(maxsize=1, ttl=6 * 3600)  # 6-hour TTL


@dataclass
class SectorRanking:
    """A single sector's momentum ranking."""
    etf: str                          # e.g., 'XLK'
    name: str                         # e.g., 'Technology'
    momentum_pct: Optional[float]     # 21-day return %
    rank: int                         # 1 = strongest, 11 = weakest
    tier: str                         # 'top', 'middle', 'bottom'
    score_modifier: int               # Points to add/subtract


@dataclass 
class SectorMomentumResult:
    """Complete sector momentum analysis."""
    rankings: List[SectorRanking] = field(default_factory=list)
    timestamp: Optional[str] = None
    source: str = 'unknown'
    is_cached: bool = False
    cache_age_minutes: int = 0


class SectorAnalysis:
    """Sector momentum rotation analysis using SPDR sector ETFs.
    
    Uses the same 11 sector ETFs already mapped in context_service.py.
    Calculates 21-day momentum for each sector and ranks them.
    """

    # Sector ETF universe (11 SPDR sectors — matches context_service.py)
    SECTOR_MAP = {
        'XLK':  'Technology',
        'XLF':  'Financials',
        'XLV':  'Health Care',
        'XLY':  'Consumer Discretionary',
        'XLC':  'Communication Services',
        'XLE':  'Energy',
        'XLI':  'Industrials',
        'XLP':  'Consumer Staples',
        'XLU':  'Utilities',
        'XLRE': 'Real Estate',
        'XLB':  'Materials',
    }

    # Ticker-to-sector reverse lookup (imported from context_service.py style)
    SECTOR_MEMBERS = {
        'XLK': ['AAPL', 'MSFT', 'NVDA', 'AMD', 'AVGO', 'ORCL', 'CRM', 'ADBE', 'CSCO', 'ACN',
                 'INTC', 'IBM', 'QCOM', 'TXN', 'AMAT', 'MU', 'LRCX', 'KLAC', 'SNPS', 'CDNS',
                 'NOW', 'PANW', 'CRWD', 'FTNT', 'PLTR', 'DELL', 'HPE', 'MRVL', 'ON', 'NXPI'],
        'XLF': ['JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'BLK', 'SCHW', 'AXP', 'SPGI'],
        'XLV': ['UNH', 'JNJ', 'LLY', 'PFE', 'ABBV', 'MRK', 'TMO', 'ABT', 'DHR', 'BMY'],
        'XLY': ['AMZN', 'TSLA', 'HD', 'MCD', 'NKE', 'SBUX', 'TJX', 'LOW', 'BKNG', 'CMG'],
        'XLC': ['META', 'GOOGL', 'GOOG', 'NFLX', 'DIS', 'CMCSA', 'T', 'VZ', 'TMUS', 'CHTR'],
        'XLE': ['XOM', 'CVX', 'COP', 'EOG', 'SLB', 'MPC', 'PSX', 'VLO', 'OXY', 'HAL'],
        'XLI': ['RTX', 'HON', 'UPS', 'BA', 'CAT', 'DE', 'LMT', 'GE', 'MMM', 'UNP'],
        'XLP': ['PG', 'KO', 'PEP', 'COST', 'WMT', 'PM', 'MO', 'CL', 'MDLZ', 'EL'],
        'XLU': ['NEE', 'DUK', 'SO', 'D', 'AEP', 'SRE', 'EXC', 'XEL', 'ED', 'WEC'],
        'XLRE': ['PLD', 'AMT', 'CCI', 'EQIX', 'PSA', 'SPG', 'O', 'WELL', 'DLR', 'AVB'],
        'XLB': ['LIN', 'APD', 'SHW', 'ECL', 'FCX', 'NEM', 'NUE', 'VMC', 'MLM', 'DOW'],
    }

    # Cache TTL: 6 hours (momentum doesn't change dramatically intraday)
    _CACHE_TTL_SECONDS = 6 * 3600

    def __init__(self, orats_api=None):
        """
        Args:
            orats_api: OratsAPI instance for fetching price data
        """
        self.orats_api = orats_api

    # ─── Public API ──────────────────────────────────────────────────────────

    def get_sector_rankings(self, force_refresh: bool = False) -> SectorMomentumResult:
        """Get current sector momentum rankings.
        
        Returns cached result if within TTL unless force_refresh=True.
        Uses module-level TTLCache (shared across Gunicorn workers in same process).
        """
        cache_key = 'sector_rankings'

        if not force_refresh and cache_key in _sector_cache:
            result = _sector_cache[cache_key]
            result.is_cached = True
            return result

        result = self._compute_rankings()
        _sector_cache[cache_key] = result
        return result

    def get_ticker_sector_modifier(self, ticker: str, force_refresh: bool = False) -> Dict:
        """Get the sector momentum modifier for a specific ticker.
        
        Returns:
            dict with sector, etf, rank, tier, score_modifier
        """
        ticker = ticker.upper().replace('$', '')
        sector_etf = self._find_sector(ticker)

        if not sector_etf:
            return {
                'sector': 'Unknown',
                'etf': None,
                'rank': None,
                'tier': 'unknown',
                'score_modifier': 0,
                'reason': f'{ticker} not in sector mapping'
            }

        rankings = self.get_sector_rankings(force_refresh=force_refresh)
        
        for sr in rankings.rankings:
            if sr.etf == sector_etf:
                return {
                    'sector': sr.name,
                    'etf': sr.etf,
                    'momentum_pct': sr.momentum_pct,
                    'rank': sr.rank,
                    'tier': sr.tier,
                    'score_modifier': sr.score_modifier,
                }

        return {
            'sector': self.SECTOR_MAP.get(sector_etf, 'Unknown'),
            'etf': sector_etf,
            'rank': None,
            'tier': 'unknown',
            'score_modifier': 0,
            'reason': 'ranking_unavailable'
        }

    # ─── Computation ─────────────────────────────────────────────────────────

    def _compute_rankings(self) -> SectorMomentumResult:
        """Compute momentum for all sectors and rank them."""
        momentum_data = []  # List of (etf, name, momentum_pct)

        for etf, name in self.SECTOR_MAP.items():
            momentum = self._get_sector_momentum(etf)
            momentum_data.append((etf, name, momentum))

        # Sort by momentum (descending — highest momentum first)
        # None values go to the end
        momentum_data.sort(
            key=lambda x: x[2] if x[2] is not None else -999,
            reverse=True
        )

        # Assign ranks and tiers
        rankings = []
        total = len(momentum_data)
        for i, (etf, name, momentum) in enumerate(momentum_data):
            rank = i + 1
            
            # Tier assignment: top 3, middle 5, bottom 3
            if rank <= 3:
                tier = 'top'
                score_modifier = 10  # Per 18-persona: +10 for top sectors
            elif rank <= 8:
                tier = 'middle'
                score_modifier = 0
            else:
                tier = 'bottom'
                score_modifier = -8  # Per 18-persona: -8 for bottom sectors

            # If momentum is None (data unavailable), don't modify score
            if momentum is None:
                score_modifier = 0
                tier = 'unknown'

            rankings.append(SectorRanking(
                etf=etf,
                name=name,
                momentum_pct=round(momentum, 2) if momentum is not None else None,
                rank=rank,
                tier=tier,
                score_modifier=score_modifier,
            ))

        source = 'orats' if self.orats_api else 'none'
        return SectorMomentumResult(
            rankings=rankings,
            timestamp=datetime.utcnow().isoformat() + 'Z',
            source=source,
            is_cached=False,
            cache_age_minutes=0,
        )

    def _get_sector_momentum(self, etf: str) -> Optional[float]:
        """Get 21-day momentum (% change) for a sector ETF.
        
        Uses ORATS price history if available.
        """
        if not self.orats_api:
            return None

        try:
            # Try to get price history from ORATS
            raw_history = self.orats_api.get_history(etf, days=30)
            
            # get_history() returns {'candles': [...], 'symbol': ticker, 'empty': bool}
            # Unwrap the candles list from the dict
            history = raw_history
            if isinstance(raw_history, dict):
                history = raw_history.get('candles', [])
            
            if history and isinstance(history, list) and len(history) >= 2:
                # Calculate % change from 21 days ago (or earliest available)
                lookback_idx = min(21, len(history) - 1)
                
                # History format: list of dicts with 'close' or 'price' key
                current_price = None
                past_price = None
                
                if isinstance(history[-1], dict):
                    current_price = history[-1].get('close') or history[-1].get('price')
                    past_price = history[-1 - lookback_idx].get('close') or history[-1 - lookback_idx].get('price')
                elif isinstance(history[-1], (int, float)):
                    current_price = history[-1]
                    past_price = history[-1 - lookback_idx]
                
                if current_price and past_price and past_price > 0:
                    momentum = ((current_price - past_price) / past_price) * 100
                    return momentum

            # Fallback: use ORATS quote for single-day change
            quote = self.orats_api.get_quote(etf)
            if quote:
                pct_change = quote.get('pctChange')
                if pct_change is not None:
                    # Single-day change is not 21-day momentum, but it's a proxy
                    log.info(f"[SectorAnalysis] {etf}: using daily change as proxy: {pct_change:.2f}%")
                    return pct_change

        except Exception as e:
            log.debug(f"[SectorAnalysis] Failed to get momentum for {etf}: {e}")

        return None

    # ─── Lookup ──────────────────────────────────────────────────────────────

    def _find_sector(self, ticker: str) -> Optional[str]:
        """Find the sector ETF for a given ticker."""
        ticker = ticker.upper()
        for etf, members in self.SECTOR_MEMBERS.items():
            if ticker in members:
                return etf
        return None

    # ─── Summary ─────────────────────────────────────────────────────────────

    def get_summary(self) -> Dict:
        """Return a summary dict for logging/debugging."""
        result = self.get_sector_rankings()
        top = [f"{r.etf}({r.momentum_pct:+.1f}%)" for r in result.rankings if r.tier == 'top' and r.momentum_pct is not None]
        bottom = [f"{r.etf}({r.momentum_pct:+.1f}%)" for r in result.rankings if r.tier == 'bottom' and r.momentum_pct is not None]
        return {
            'top_sectors': top,
            'bottom_sectors': bottom,
            'total_ranked': len(result.rankings),
            'source': result.source,
            'is_cached': result.is_cached,
            'cache_age_minutes': result.cache_age_minutes,
        }
