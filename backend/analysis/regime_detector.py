"""
S1: VIX Regime Detection — regime_detector.py
Fetches live VIX data, classifies into regime tiers, and provides
RegimeContext for downstream modules (position_sizer, exit_manager,
options_analyzer, reasoning_engine).

Evidence: VIX %B 2-sigma strategy: 84.5% win rate, 64% annual return
(1990-2024, 130 trades). ORATS 180M backtest confirms VIX is top entry filter.

18-Persona Verdict: 16/18 APPROVED
"""

import logging
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

log = logging.getLogger(__name__)


class VIXRegime(Enum):
    """Five-tier VIX regime classification.
    
    Thresholds derived from CBOE VIX historical percentiles:
      CALM:     VIX < 15  (bottom 25th percentile, low vol)
      NORMAL:   15 <= VIX < 20  (median range)
      ELEVATED: 20 <= VIX < 25  (above-average vol)
      FEAR:     25 <= VIX < 35  (high vol, caution)
      CRISIS:   VIX >= 35  (extreme vol, defensive only)
    """
    CALM = 'CALM'
    NORMAL = 'NORMAL'
    ELEVATED = 'ELEVATED'
    FEAR = 'FEAR'
    CRISIS = 'CRISIS'


# Default regime when VIX data is unavailable — conservative per Security Auditor
FALLBACK_REGIME = VIXRegime.ELEVATED


@dataclass
class RegimeContext:
    """Immutable context object passed to all downstream modules."""
    regime: VIXRegime = VIXRegime.NORMAL
    vix_level: Optional[float] = None
    vix_change_1d: Optional[float] = None  # 1-day VIX change (for spike detection)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    is_fallback: bool = False  # True if using fallback due to data failure

    @property
    def regime_str(self) -> str:
        """Legacy compatibility — returns string like 'NORMAL', 'ELEVATED', 'CRISIS'."""
        # Map 5-tier to 3-tier for backward compat with existing code
        if self.regime in (VIXRegime.CALM, VIXRegime.NORMAL):
            return 'NORMAL'
        elif self.regime in (VIXRegime.ELEVATED, VIXRegime.FEAR):
            return 'ELEVATED'
        else:
            return 'CRISIS'

    @property
    def position_size_multiplier(self) -> float:
        """Kelly fraction multiplier per regime.
        CALM=full, NORMAL=90%, ELEVATED=60%, FEAR=35%, CRISIS=15%
        """
        return {
            VIXRegime.CALM: 1.0,
            VIXRegime.NORMAL: 0.9,
            VIXRegime.ELEVATED: 0.6,
            VIXRegime.FEAR: 0.35,
            VIXRegime.CRISIS: 0.15,
        }[self.regime]

    @property
    def universe_reduction_pct(self) -> float:
        """Percentage to reduce scan universe in high-vol regimes."""
        return {
            VIXRegime.CALM: 0,
            VIXRegime.NORMAL: 0,
            VIXRegime.ELEVATED: 10,
            VIXRegime.FEAR: 30,
            VIXRegime.CRISIS: 50,
        }[self.regime]

    @property
    def score_penalty(self) -> int:
        """Points to subtract from opportunity scores in elevated regimes."""
        return {
            VIXRegime.CALM: 0,
            VIXRegime.NORMAL: 0,
            VIXRegime.ELEVATED: -3,
            VIXRegime.FEAR: -8,
            VIXRegime.CRISIS: -15,
        }[self.regime]


class RegimeDetector:
    """Detects and caches VIX regime for the current scan session.
    
    Usage:
        detector = RegimeDetector(orats_api)
        ctx = detector.detect()
        # ctx.regime, ctx.vix_level, ctx.position_size_multiplier, etc.
    """

    # Minimum time between VIX fetches (prevents hammering API during rapid scans)
    MIN_REFRESH_SECONDS = 120

    # VIX thresholds (configurable via env in future)
    CALM_CEILING = 15.0
    NORMAL_CEILING = 20.0
    ELEVATED_CEILING = 25.0
    FEAR_CEILING = 35.0

    # 2-day minimum regime duration to prevent whipsaw (per Risk Manager resolution)
    # Note: enforced at scan level — if regime just changed, we use the MORE conservative one

    def __init__(self, orats_api=None, fmp_api=None):
        """Accept either ORATS or FMP for VIX data (ORATS preferred)."""
        self._orats = orats_api
        self._fmp = fmp_api
        self._cached_context: Optional[RegimeContext] = None
        self._last_fetch: Optional[datetime] = None
        self._last_regime: Optional[VIXRegime] = None
        # S1-FIX: Initialize to utcnow() so the first regime change also
        # respects the 48-hour anti-whipsaw stickiness window.
        # Previously None caused the `_regime_changed_at is not None` guard
        # to bypass the stickiness check on the very first detected change.
        self._regime_changed_at: datetime = datetime.utcnow()

    def detect(self, force_refresh: bool = False) -> RegimeContext:
        """Detect current VIX regime. Returns cached result if fresh enough."""
        now = datetime.utcnow()

        # Return cache if fresh
        if (not force_refresh
                and self._cached_context is not None
                and self._last_fetch is not None
                and (now - self._last_fetch).total_seconds() < self.MIN_REFRESH_SECONDS):
            return self._cached_context

        # Fetch VIX level
        vix_level = self._fetch_vix_level()

        if vix_level is None:
            log.warning("VIX data unavailable — using fallback regime: %s", FALLBACK_REGIME.value)
            ctx = RegimeContext(
                regime=FALLBACK_REGIME,
                vix_level=None,
                is_fallback=True,
                timestamp=now
            )
            self._cached_context = ctx
            self._last_fetch = now
            return ctx

        # Classify
        regime = self._classify(vix_level)

        # Anti-whipsaw: if regime just changed in last scan, use the more conservative one
        if (self._last_regime is not None
                and regime != self._last_regime):
            hours_since_change = (now - self._regime_changed_at).total_seconds() / 3600
            if hours_since_change < 48:  # 2-day stickiness
                conservative = max(regime, self._last_regime,
                                   key=lambda r: list(VIXRegime).index(r))
                if conservative != regime:
                    log.info("Anti-whipsaw: regime %s -> %s within 48h, using %s",
                             self._last_regime.value, regime.value, conservative.value)
                    regime = conservative

        # Track regime changes
        if regime != self._last_regime:
            self._regime_changed_at = now
            self._last_regime = regime

        ctx = RegimeContext(
            regime=regime,
            vix_level=vix_level,
            timestamp=now,
            is_fallback=False
        )
        self._cached_context = ctx
        self._last_fetch = now

        log.info("VIX Regime: %.1f → %s (size_mult=%.2f, score_penalty=%d)",
                 vix_level, regime.value, ctx.position_size_multiplier, ctx.score_penalty)

        return ctx

    def _fetch_vix_level(self) -> Optional[float]:
        """Try ORATS → CBOE dedicated endpoint → FMP (3 sources for redundancy)."""
        # Source 1: ORATS
        if self._orats:
            try:
                quote = self._orats.get_quote('VIX')
                price = quote.get('price') if quote else None
                if price is not None and float(price) > 0:
                    return float(price)
                else:
                    log.debug("ORATS VIX returned price=%s — skipping (0 or null)", price)
            except Exception as e:
                log.debug("ORATS VIX fetch failed: %s", e)

        # Source 2: CBOE dedicated free endpoint (no API key required)
        vix_cboe = self._fetch_vix_cboe()
        if vix_cboe is not None:
            return vix_cboe

        # Source 3: FMP fallback
        if self._fmp:
            try:
                quote = self._fmp.get_quote('^VIX')
                price = quote.get('price') if quote else None
                if price is not None and float(price) > 0:
                    return float(price)
                else:
                    log.debug("FMP VIX returned price=%s — skipping (0 or null)", price)
            except Exception as e:
                log.debug("FMP VIX fetch failed: %s", e)

        return None

    def _fetch_vix_cboe(self) -> Optional[float]:
        """Fetch the latest VIX close from CBOE's free public CSV feed.

        Endpoint: https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv
        This is maintained by CBOE, requires no API key, and returns the
        full VIX daily price history.  We parse only the last row to get
        the most recent closing value.

        Falls back to Yahoo Finance's free chart endpoint if the CBOE CSV
        is unavailable, giving two independent free sources before we touch
        the paid ORATS / FMP APIs.
        """
        import requests

        # ── Attempt 1: CBOE VIX History CSV ──────────────────────────────────
        try:
            cboe_url = (
                "https://cdn.cboe.com/api/global/us_indices/"
                "daily_prices/VIX_History.csv"
            )
            resp = requests.get(cboe_url, timeout=10)
            if resp.status_code == 200:
                lines = resp.text.strip().splitlines()
                # Format: DATE,OPEN,HIGH,LOW,CLOSE  (header on first line)
                # Last line is the most recent trading day.
                for line in reversed(lines):
                    parts = line.split(',')
                    if len(parts) >= 5 and parts[4].replace('.', '', 1).isdigit():
                        close_val = float(parts[4])
                        if close_val > 0:
                            log.info("VIX from CBOE CSV: %.2f (date=%s)",
                                     close_val, parts[0])
                            return close_val
            else:
                log.debug("CBOE VIX CSV HTTP %s", resp.status_code)
        except Exception as e:
            log.debug("CBOE VIX CSV fetch failed: %s", e)

        # ── Attempt 2: Yahoo Finance free chart API ───────────────────────────
        try:
            yf_url = (
                "https://query1.finance.yahoo.com/v8/finance/chart/"
                "%5EVIX?range=1d&interval=1d"
            )
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(yf_url, timeout=10, headers=headers)
            if resp.status_code == 200:
                payload = resp.json()
                closes = (
                    payload
                    .get('chart', {})
                    .get('result', [{}])[0]
                    .get('indicators', {})
                    .get('quote', [{}])[0]
                    .get('close', [])
                )
                # Filter out None values and take the last valid close
                valid = [c for c in closes if c is not None and c > 0]
                if valid:
                    log.info("VIX from Yahoo Finance: %.2f", valid[-1])
                    return float(valid[-1])
            else:
                log.debug("Yahoo Finance VIX HTTP %s", resp.status_code)
        except Exception as e:
            log.debug("Yahoo Finance VIX fetch failed: %s", e)

        return None

    def _classify(self, vix_level: float) -> VIXRegime:
        """Classify VIX level into regime tier."""
        if vix_level < self.CALM_CEILING:
            return VIXRegime.CALM
        elif vix_level < self.NORMAL_CEILING:
            return VIXRegime.NORMAL
        elif vix_level < self.ELEVATED_CEILING:
            return VIXRegime.ELEVATED
        elif vix_level < self.FEAR_CEILING:
            return VIXRegime.FEAR
        else:
            return VIXRegime.CRISIS
