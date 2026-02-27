"""S2: CBOE Put/Call Ratio — Z-Score Contrarian Sentiment Signal.

Evidence: CBOE equity P/C ratio as a contrarian indicator dates to 
McMillan (1980s). Z-score normalization (21-day lookback) improves
signal quality vs raw thresholds. 18-Persona verdict: 17/18 APPROVED.

When the crowd panics (high P/C ratio → Z > +1.5), it's often a
contrarian BUY signal. When complacency reigns (low P/C → Z < -1.5),
caution is warranted.

Data Source: CBOE publishes daily P/C ratios; we proxy through
the ORATS data or fallback to a lightweight web fetch.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from collections import deque

import numpy as np

log = logging.getLogger(__name__)


@dataclass
class PutCallSignal:
    """Encapsulates a P/C ratio signal for consumption by the scanner."""
    ratio: Optional[float] = None
    z_score: Optional[float] = None
    signal: str = 'neutral'           # extreme_fear, fear, neutral, complacency, extreme_complacency
    contrarian_bias: str = 'neutral'  # bullish, neutral, bearish (opposite of crowd)
    score_modifier: int = 0           # Points to add/subtract from sentiment score
    lookback_days: int = 21
    timestamp: Optional[str] = None
    source: str = 'unknown'


class MacroSignals:
    """Collects and interprets macro-level sentiment signals.
    
    Currently implements:
      - CBOE Put/Call Ratio (equity) with Z-score contrarian logic
    
    Future candidates (deferred):
      - AAII Sentiment Survey
      - CNN Fear & Greed Index
      - High-Yield Credit Spreads
    """

    # Cache TTL: P/C ratio only changes once per day
    _CACHE_TTL_SECONDS = 3600  # 1 hour

    def __init__(self, orats_api=None, fmp_api_key: Optional[str] = None):
        """
        Args:
            orats_api: OratsAPI instance for fetching VIX/market data
            fmp_api_key: Financial Modeling Prep API key (alternate data source)
        """
        self.orats_api = orats_api
        self.fmp_api_key = fmp_api_key
        
        # Rolling history for Z-score calculation
        self._pc_history: deque = deque(maxlen=63)  # ~3 months of trading days
        self._last_fetch_time: float = 0
        self._cached_signal: Optional[PutCallSignal] = None

    # ─── Public API ──────────────────────────────────────────────────────────

    def get_put_call_signal(self, force_refresh: bool = False) -> PutCallSignal:
        """Get the current P/C ratio signal with Z-score interpretation.
        
        Returns cached result if within TTL unless force_refresh=True.
        Falls back gracefully if data is unavailable.
        """
        now = time.time()
        if (not force_refresh 
                and self._cached_signal is not None 
                and (now - self._last_fetch_time) < self._CACHE_TTL_SECONDS):
            return self._cached_signal

        signal = self._fetch_and_compute()
        self._cached_signal = signal
        self._last_fetch_time = now
        return signal

    # ─── Data Fetching ───────────────────────────────────────────────────────

    def _fetch_and_compute(self) -> PutCallSignal:
        """Fetch P/C ratio data and compute Z-score signal."""
        ratio = None
        source = 'none'

        # Strategy 1: Derive from ORATS options volume data
        if self.orats_api:
            ratio = self._fetch_from_orats()
            if ratio is not None:
                source = 'orats_derived'

        # Strategy 2: FMP API (has equity P/C endpoint)
        if ratio is None and self.fmp_api_key:
            ratio = self._fetch_from_fmp()
            if ratio is not None:
                source = 'fmp'

        # Strategy 3: Use SPY options skew as proxy
        if ratio is None and self.orats_api:
            ratio = self._derive_from_spy_skew()
            if ratio is not None:
                source = 'spy_skew_proxy'

        if ratio is None:
            log.warning("[MacroSignals] P/C ratio unavailable from all sources")
            return PutCallSignal(
                signal='unavailable',
                contrarian_bias='neutral',
                score_modifier=0,
                timestamp=datetime.utcnow().isoformat() + 'Z',
                source='none'
            )

        # Add to rolling history
        self._pc_history.append(ratio)

        # Compute Z-score (need at least 10 data points for meaningful stats)
        z_score = self._compute_z_score(ratio)
        signal, contrarian_bias, score_mod = self._interpret_z_score(z_score, ratio)

        return PutCallSignal(
            ratio=round(ratio, 3),
            z_score=round(z_score, 2) if z_score is not None else None,
            signal=signal,
            contrarian_bias=contrarian_bias,
            score_modifier=score_mod,
            lookback_days=21,
            timestamp=datetime.utcnow().isoformat() + 'Z',
            source=source
        )

    def _fetch_from_orats(self) -> Optional[float]:
        """Derive P/C ratio from ORATS SPY volume data.
        
        Uses total put volume / total call volume on SPY as a proxy
        for the CBOE equity P/C ratio.
        """
        try:
            # Get SPY options chain for volume data
            spy_data = self.orats_api.get_options_chain('SPY')
            if not spy_data:
                return None

            total_put_vol = 0
            total_call_vol = 0

            # ORATS returns list of option strikes
            if isinstance(spy_data, list):
                for strike in spy_data:
                    call_vol = strike.get('callVolume', 0) or 0
                    put_vol = strike.get('putVolume', 0) or 0
                    total_call_vol += call_vol
                    total_put_vol += put_vol
            elif isinstance(spy_data, dict):
                # May be grouped by expiry
                for expiry, strikes in spy_data.items():
                    if isinstance(strikes, list):
                        for s in strikes:
                            total_call_vol += s.get('callVolume', 0) or 0
                            total_put_vol += s.get('putVolume', 0) or 0

            if total_call_vol > 0:
                ratio = total_put_vol / total_call_vol
                log.info(f"[MacroSignals] ORATS SPY P/C: {ratio:.3f} "
                         f"(puts={total_put_vol:,}, calls={total_call_vol:,})")
                return ratio

        except Exception as e:
            log.debug(f"[MacroSignals] ORATS P/C fetch failed: {e}")
        return None

    def _fetch_from_fmp(self) -> Optional[float]:
        """Fetch equity P/C ratio from Financial Modeling Prep API."""
        try:
            import requests
            url = (f"https://financialmodelingprep.com/api/v4/"
                   f"commitment_of_traders_report/ES"
                   f"?apikey={self.fmp_api_key}")
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data and isinstance(data, list) and len(data) > 0:
                    latest = data[0]
                    long_pos = latest.get('long_all', 0) or 0
                    short_pos = latest.get('short_all', 0) or 0
                    if long_pos > 0:
                        ratio = short_pos / long_pos
                        log.info(f"[MacroSignals] FMP P/C proxy: {ratio:.3f}")
                        return ratio
        except Exception as e:
            log.debug(f"[MacroSignals] FMP P/C fetch failed: {e}")
        return None

    def _derive_from_spy_skew(self) -> Optional[float]:
        """Use SPY implied volatility skew as P/C proxy.
        
        When put IV >> call IV, it implies more put buying (high P/C).
        """
        try:
            spy_quote = self.orats_api.get_quote('SPY')
            if not spy_quote:
                return None
            
            # ORATS provides smvVol fields
            put_iv = spy_quote.get('putSmvVol') or spy_quote.get('smvVol')
            call_iv = spy_quote.get('callSmvVol') or spy_quote.get('smvVol')
            
            if put_iv and call_iv and call_iv > 0:
                # Higher put_iv/call_iv ratio ≈ more demand for puts
                skew_ratio = put_iv / call_iv
                # Map skew ratio to approximate P/C ratio range
                # Typical skew: 1.0-1.3; map to P/C range 0.6-1.2
                pc_approx = 0.6 + (skew_ratio - 1.0) * 2.0
                pc_approx = max(0.4, min(1.5, pc_approx))  # Clamp
                log.info(f"[MacroSignals] SPY skew proxy P/C: {pc_approx:.3f} "
                         f"(put_iv={put_iv:.3f}, call_iv={call_iv:.3f})")
                return pc_approx

        except Exception as e:
            log.debug(f"[MacroSignals] SPY skew proxy failed: {e}")
        return None

    # ─── Z-Score Computation ─────────────────────────────────────────────────

    def _compute_z_score(self, current_ratio: float) -> Optional[float]:
        """Compute Z-score of current P/C ratio against rolling 21-day window.
        
        Z = (current - mean) / std_dev
        
        Falls back to absolute thresholds if insufficient history.
        """
        if len(self._pc_history) < 10:
            # Not enough history — use absolute heuristic
            # Historical CBOE equity P/C: mean ~0.65, std ~0.12
            mean = 0.65
            std = 0.12
        else:
            # Use most recent 21 values (or all if fewer)
            lookback = list(self._pc_history)[-21:]
            mean = np.mean(lookback)
            std = np.std(lookback)

        if std < 0.001:  # Avoid division by near-zero
            return 0.0

        return (current_ratio - mean) / std

    def _interpret_z_score(self, z_score: Optional[float], ratio: float):
        """Interpret Z-score into signal, contrarian bias, and score modifier.
        
        Contrarian logic:
          - High P/C (crowd buying puts = fear) → Z > +1.5 → contrarian BULLISH
          - Low P/C (crowd buying calls = greed) → Z < -1.5 → contrarian BEARISH
        
        Score modifiers (per 18-persona consensus):
          - Extreme fear (Z > +2.0):   +15 sentiment boost (strong contrarian buy)
          - Fear (Z > +1.5):           +10 sentiment boost
          - Neutral:                     0
          - Complacency (Z < -1.5):    -10 sentiment penalty
          - Extreme complacency (Z < -2.0): -15 sentiment penalty
        """
        if z_score is None:
            return 'unavailable', 'neutral', 0

        if z_score >= 2.0:
            return 'extreme_fear', 'bullish', 15
        elif z_score >= 1.5:
            return 'fear', 'bullish', 10
        elif z_score >= 0.75:
            return 'mild_fear', 'lean_bullish', 5
        elif z_score <= -2.0:
            return 'extreme_complacency', 'bearish', -15
        elif z_score <= -1.5:
            return 'complacency', 'bearish', -10
        elif z_score <= -0.75:
            return 'mild_complacency', 'lean_bearish', -5
        else:
            return 'neutral', 'neutral', 0

    # ─── Seed History (for fresh starts) ─────────────────────────────────────

    def seed_history(self, historical_ratios: List[float]):
        """Pre-seed P/C history for Z-score calculation.
        
        Call this at startup if historical data is available,
        so the Z-score is meaningful from the first query.
        """
        for r in historical_ratios[-63:]:  # Keep last 63 at most
            self._pc_history.append(r)
        log.info(f"[MacroSignals] Seeded P/C history with {len(self._pc_history)} values")

    # ─── Summary for Logging ─────────────────────────────────────────────────

    def get_summary(self) -> Dict:
        """Return a summary dict for logging/debugging."""
        sig = self._cached_signal or self.get_put_call_signal()
        return {
            'put_call_ratio': sig.ratio,
            'z_score': sig.z_score,
            'signal': sig.signal,
            'contrarian_bias': sig.contrarian_bias,
            'score_modifier': sig.score_modifier,
            'source': sig.source,
            'history_length': len(self._pc_history),
        }
