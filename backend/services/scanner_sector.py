import logging
from datetime import datetime
from backend.config import Config

logger = logging.getLogger(__name__)


def scan_watchlist(scanner, username=None):
    """Scan all tickers in watchlist.
    
    F42 FIX: Accept username param so app.py can pass current_user.
    Previously crashed with TypeError when called from /api/scan route.
    """
    watchlist = scanner.watchlist_service.get_watchlist(username)
    if not watchlist:
        return []
    
    tickers = [item['ticker'] for item in watchlist]
    
    # [PHASE 3] Batch Fetching
    batch_data = {}
    if scanner.use_orats:
        logger.info(f"\U0001f680 Batch Fetching Options for {len(tickers)} tickers (ORATS)...")
        try:
            batch_data = scanner.batch_manager.fetch_option_chains(tickers)
        except Exception as e:
            logger.warning(f"\u26a0\ufe0f Batch Fetch Failed: {e}")
    
    results = []
    for item in watchlist:
        t = item['ticker']
        # Pass pre-fetched data if available
        opts = batch_data.get(t)
        
        result = scanner.scan_ticker(t, pre_fetched_data=opts)
        if result:
            results.append(result)
    
    # Sort
    results.sort(key=lambda x: x['opportunities'][0]['opportunity_score'] if x['opportunities'] else 0, reverse=True)
    return results


# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
# SMART SECTOR SCAN \u2014 Industrial-grade ticker selection
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
#
# Architecture (v2 \u2014 replaces FMP-only screener):
#   1. ORATS /cores (single API call) \u2192 full sector universe with options metrics
#   2. Smart rank by IV percentile, liquidity, momentum, mispricing
#   3. No ORATS coverage filter needed (source IS ORATS)
#   4. Batch option chain fetch (concurrent via BatchManager)
#   5. Deep scan per ticker (sequential)
#   6. Global filter \u2192 top 100 opportunities
#
# Why this is better than v1 (FMP screener):
#   - FMP sorted by market cap only \u2192 missed mid-cap gems
#   - ORATS /cores provides IV percentile, options volume, market width
#   - Tickers are pre-qualified for options tradability
#   - Single API call replaces FMP screener + ORATS coverage check
#
# Scoring rationale (industry-validated):
#   - IV Percentile extremes (25%): High OR low IV = opportunity
#   - Options Liquidity (25%): avgOptVolu20d \u2014 must be tradeable
#   - Market Tightness (15%): mktWidthVol \u2014 tight = better fills
#   - Price Momentum (15%): 1-month stock price change
#   - IV/HV Divergence (10%): Volatility mispricing signal
#   - Open Interest Buildup (10%): Institutional conviction signal
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550


def _rank_options_candidates(candidates, min_market_cap=0, min_volume=0, limit=30):
    """Rank sector tickers by options-worthiness using ORATS core data.

    Uses a composite scoring model validated against professional options
    screening methodology (tastylive, Market Chameleon, ORATS, Barchart).

    Args:
        candidates: list of ORATS /cores records for a sector
        min_market_cap: Minimum market cap filter (user param, in thousands \u2014 ORATS mktCap unit)
        min_volume: Minimum stock volume filter (user param)
        limit: How many top candidates to return

    Returns:
        list[dict]: Top N candidates sorted by composite score,
                    each dict augmented with 'scan_score' and 'symbol' fields
    """
    # \u2500\u2500 Step 1: Hard filters (eliminate unworthy) \u2500\u2500
    filtered = []
    for c in candidates:
        ticker = c.get("ticker", "")

        # Skip empty or obviously bad records
        if not ticker:
            continue

        avg_opt_vol = c.get("avgOptVolu20d") or 0
        mkt_cap = c.get("mktCap") or 0
        stk_vol = c.get("stkVolu") or 0

        # Options liquidity floor: skip tickers with < 100 avg daily options volume
        # A ticker with no options trading is useless for an options scanner
        if avg_opt_vol < 100:
            continue

        # User's minimum thresholds
        # Note: ORATS mktCap is in thousands, FMP sends raw. We handle both.
        if min_market_cap and mkt_cap < int(min_market_cap):
            continue
        if min_volume and stk_vol < int(min_volume):
            continue

        # Market width sanity: skip extremely wide markets (illiquid options)
        # mktWidthVol > 15 vol points means terrible bid-ask spreads
        mkt_width = c.get("mktWidthVol")
        if mkt_width is not None and mkt_width > 15:
            continue

        filtered.append(c)

    if not filtered:
        logger.warning("\u26a0\ufe0f Smart Rank: No candidates passed hard filters")
        return []

    logger.info(f"\U0001f4ca Smart Rank: {len(filtered)} passed hard filters (from {len(candidates)} raw)")

    # \u2500\u2500 Step 2: Normalize metrics using percentile rank \u2500\u2500
    def percentile_rank(values, value):
        """Rank a value within a list as 0-100 percentile."""
        if not values or value is None:
            return 50.0  # neutral default
        sorted_vals = sorted(v for v in values if v is not None)
        if not sorted_vals:
            return 50.0
        rank = sum(1 for v in sorted_vals if v <= value)
        return (rank / len(sorted_vals)) * 100

    # Collect metric arrays for normalization
    iv_pcts = [c.get("ivPctile1y") or 50 for c in filtered]
    opt_vols = [c.get("avgOptVolu20d") or 0 for c in filtered]
    mkt_widths = [c.get("mktWidthVol") or 10 for c in filtered]
    momentums = [c.get("stkPxChng1m") or 0 for c in filtered]

    # Total open interest per ticker (calls + puts)
    total_ois = [(c.get("cOi") or 0) + (c.get("pOi") or 0) for c in filtered]

    # IV vs HV divergence: abs(iv30d - orHv20d) / orHv20d
    divergences = []
    for c in filtered:
        iv = c.get("iv30d") or 0
        hv = c.get("orHv20d") or 0
        div = abs((iv - hv) / hv * 100) if hv > 0 else 0
        divergences.append(div)

    # \u2500\u2500 Step 3: Score each candidate \u2500\u2500
    scored = []
    for i, c in enumerate(filtered):
        # --- IV Percentile (25%) \u2014 reward EXTREMES (high OR low) ---
        # High IV (>75) = premium selling opportunity
        # Low IV (<25) = cheap LEAP entry opportunity
        # Both are interesting; middle is boring
        raw_iv_pct = iv_pcts[i]
        # Transform: distance from 50 (center) \u2192 0-100 scale
        # ivPctile=5 \u2192 score=90, ivPctile=50 \u2192 score=0, ivPctile=95 \u2192 score=90
        iv_extremeness = abs(raw_iv_pct - 50) * 2  # 0-100 scale
        iv_score = min(iv_extremeness, 100)

        # --- Options Liquidity (25%) ---
        liq_score = percentile_rank(opt_vols, opt_vols[i])

        # --- Market Tightness (15%) \u2014 lower width = higher score ---
        width_score = 100 - percentile_rank(mkt_widths, mkt_widths[i])

        # --- Price Momentum (15%) ---
        mom_score = percentile_rank(momentums, momentums[i])

        # --- IV/HV Divergence (10%) ---
        div_score = percentile_rank(divergences, divergences[i])

        # --- Open Interest Buildup (10%) ---
        oi_score = percentile_rank(total_ois, total_ois[i])

        # Weighted composite
        composite = (
            iv_score    * 0.25 +   # IV extremes
            liq_score   * 0.25 +   # Options liquidity
            width_score * 0.15 +   # Market tightness
            mom_score   * 0.15 +   # Price momentum
            div_score   * 0.10 +   # IV/HV divergence
            oi_score    * 0.10     # OI buildup
        )

        # Augment record with scoring metadata
        c["scan_score"] = round(composite, 2)
        c["symbol"] = c.get("ticker", "")  # Normalize for downstream compatibility
        scored.append(c)

    # \u2500\u2500 Step 4: Sort and return top N \u2500\u2500
    scored.sort(key=lambda x: x["scan_score"], reverse=True)

    top_n = scored[:limit]
    if top_n:
        logger.info(
            f"\U0001f3af Smart Rank: Top {len(top_n)} selected "
            f"(scores: {top_n[0]['scan_score']:.1f} \u2192 {top_n[-1]['scan_score']:.1f})"
        )
        # Log top 5 for debugging
        for rank, t in enumerate(top_n[:5], 1):
            logger.info(
                f"   #{rank} {t['ticker']}: score={t['scan_score']:.1f} "
                f"ivPct={t.get('ivPctile1y', 'N/A')} "
                f"optVol={t.get('avgOptVolu20d', 0):.0f} "
                f"mktWidth={t.get('mktWidthVol', 'N/A')}"
            )

    return top_n


def scan_sector_top_picks(scanner, sector, min_volume, min_market_cap, limit=30, weeks_out=None, industry=None):
    """
    Smart Sector Scan \u2014 Industrial-grade ticker selection (v2).

    Architecture:
      1. ORATS /cores (single API call) \u2192 full sector with options metrics
      2. Smart rank by IV percentile, liquidity, momentum, mispricing
      3. Batch option chain fetch (concurrent via BatchManager)
      4. Deep scan per ticker (sequential)
      5. Global filter \u2192 top 100 opportunities

    Key change from v1:
      - Replaced FMP screener (market-cap only) with ORATS /cores ranking
      - Tickers are pre-qualified for options tradability
      - Default limit raised from 15 to 30
      - AI Analysis on Top 3 removed (user-approved)
    """
    mode_label = "LEAPS" if weeks_out is None else f"WEEKLY (+{weeks_out})"
    ind_label = f" | {industry}" if industry else ""
    logger.info(f"\U0001f680 Starting Smart Sector Scan: {sector}{ind_label} [{mode_label}] [Cap > {min_market_cap}, Vol > {min_volume}]")

    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    # Step 1: ORATS /cores \u2014 single API call for sector universe
    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    all_sector_tickers = []
    orats_api = scanner.batch_manager.orats_api if hasattr(scanner.batch_manager, 'orats_api') else None

    # Use session cache if available (set by HybridScannerService)
    if hasattr(scanner, '_get_cores_cached') and callable(scanner._get_cores_cached):
        try:
            # Determine filter: use industry if provided, else broad sector
            filter_term = industry if industry else sector
            all_sector_tickers = scanner._get_cores_cached(sector=filter_term)
        except Exception as e:
            logger.warning(f"\u26a0\ufe0f Cached /cores failed: {e}")

    # Direct call if cache miss or not available
    if not all_sector_tickers and orats_api:
        try:
            filter_term = industry if industry else sector
            all_sector_tickers = orats_api.get_cores_bulk(sector=filter_term)
        except Exception as e:
            logger.warning(f"\u26a0\ufe0f ORATS /cores failed: {e}")

    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    # Fallback: FMP screener (backward compatible)
    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    if not all_sector_tickers:
        logger.warning("\u26a0\ufe0f ORATS /cores unavailable \u2014 falling back to FMP screener")
        candidates = []
        try:
            candidates = scanner.fmp_api.get_stock_screener(
                sector=sector,
                industry=industry,
                min_market_cap=min_market_cap,
                min_volume=min_volume,
                limit=limit
            )
        except Exception as e:
            logger.warning(f"\u26a0\ufe0f FMP Screener API Failed: {e}")

        if not candidates:
            # Quick local cache fallback
            cached = scanner.get_cached_tickers()
            matches = [
                t for t in cached
                if t.get('sector') == sector
                and (t.get('marketCap') or 0) >= int(min_market_cap or 0)
            ]
            matches.sort(key=lambda x: (x.get('marketCap') or 0), reverse=True)
            candidates = matches[:limit]

        if not candidates:
            logger.error("\u274c No candidates found (ORATS, FMP, and local cache all failed)")
            return []

        logger.info(f"\U0001f4cb FMP fallback: {len(candidates)} candidates. Starting deep scan...")

        # FMP path: still need ORATS coverage filter
        tickers = [c['symbol'] for c in candidates]
        if type(scanner)._orats_universe:
            original_count = len(tickers)
            tickers = [t for t in tickers if scanner._is_orats_covered(t)]
            skipped = original_count - len(tickers)
            if skipped > 0:
                logger.info(f"\u23ed\ufe0f Skipped {skipped} tickers not in ORATS universe ({len(tickers)} remaining)")
            candidates = [c for c in candidates if c['symbol'] in tickers]

    else:
        # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
        # Step 2: Smart Rank (ORATS path)
        # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
        candidates = _rank_options_candidates(
            all_sector_tickers,
            min_market_cap=min_market_cap,
            min_volume=min_volume,
            limit=limit
        )

        if not candidates:
            logger.error("\u274c No qualified candidates after smart ranking")
            return []

        logger.info(
            f"\U0001f4cb Smart-ranked {len(candidates)} candidates "
            f"(from {len(all_sector_tickers)} in sector). Starting deep scan..."
        )

        # No ORATS coverage filter needed \u2014 source IS ORATS
        tickers = [c["ticker"] for c in candidates]

    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    # Step 3: Batch Fetch Option Chains (concurrent)
    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    batch_data = {}
    if scanner.use_orats:
        logger.info(f"\U0001f680 Batch Fetching Options for {len(tickers)} tickers (ORATS)...")
        try:
            batch_data = scanner.batch_manager.fetch_option_chains(tickers)
        except Exception as e:
            logger.warning(f"\u26a0\ufe0f Batch Fetch Failed: {e}")

    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    # Step 4: Deep Scan (sequential per ticker)
    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    # XC-1: VIX Regime Filter (S1: Enhanced RegimeDetector)
    vix_level = None
    vix_regime = 'NORMAL'
    try:
        if scanner.regime_detector and Config.ENABLE_VIX_REGIME:
            sector_regime = scanner.regime_detector.detect()
            vix_level = sector_regime.vix_level
            vix_regime = sector_regime.regime_str  # Legacy 3-tier
            logger.info(f"\U0001f30a S1 VIX Regime: {vix_level} \u2192 {sector_regime.regime.value} (mapped: {vix_regime})")
            if vix_regime == 'CRISIS':
                logger.warning(f"\u26a0\ufe0f CRISIS mode: tightening filters, reducing position sizes recommended")
        elif scanner.use_orats:
            vix_quote = scanner.batch_manager.orats_api.get_quote('VIX')
            if vix_quote and vix_quote.get('price'):
                vix_level = vix_quote['price']
                if vix_level > 30:
                    vix_regime = 'CRISIS'
                elif vix_level > 20:
                    vix_regime = 'ELEVATED'
                logger.info(f"\U0001f30a VIX Regime: {vix_level:.1f} ({vix_regime})")
                if vix_regime == 'CRISIS':
                    logger.warning(f"\u26a0\ufe0f CRISIS mode: tightening filters, reducing position sizes recommended")
            else:
                logger.warning(f"\u26a0\ufe0f VIX quote unavailable, proceeding with NORMAL regime")
    except Exception as e:
        logger.warning(f"\u26a0\ufe0f VIX regime detection failed: {e} (proceeding with NORMAL regime)")

    all_results = []
    for cand in candidates:
        ticker = cand.get('symbol') or cand.get('ticker', '')
        if not ticker:
            continue

        opts = batch_data.get(ticker)

        # Choose Scan Mode
        if weeks_out is not None:
            res = scanner.scan_weekly_options(ticker, weeks_out=weeks_out, pre_fetched_data=opts)
        else:
            res = scanner.scan_ticker(ticker, pre_fetched_data=opts, direction='CALL') # LEAP (calls)
            # P0-17: Also scan for put LEAPs (bearish)
            res_put = scanner.scan_ticker(ticker, pre_fetched_data=opts, direction='PUT')
            if res_put and res_put.get('opportunities'):
                if res and res.get('opportunities'):
                    # Merge put opportunities into the call result
                    res['opportunities'].extend(res_put['opportunities'])
                else:
                    res = res_put

        if res and res.get('opportunities'):
            # Carry forward scan_score from smart ranking (if available)
            if 'scan_score' in cand:
                res['scan_score'] = cand['scan_score']
            all_results.append(res)

    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    # Step 5: Global Filter & Regroup
    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    # Flatten all opportunities to find absolute best
    all_opps = []
    results_map = {} # Ticker -> Result Object

    for res in all_results:
        t = res['ticker']
        results_map[t] = res
        for opp in res['opportunities']:
            opp['ticker'] = t
            all_opps.append(opp)

    # Sort by Score
    all_opps.sort(key=lambda x: x.get('opportunity_score', 0), reverse=True)
    top_100 = all_opps[:100]
    logger.info(f"\U0001f3af Filtered down to Top {len(top_100)} Global Opportunities")

    # Regroup
    grouped_results = {}
    for opp in top_100:
        t = opp['ticker']
        if t not in grouped_results:
            orig = results_map[t]
            grouped_results[t] = orig.copy()
            grouped_results[t]['opportunities'] = []

            # [NEW] Initialize Badges for Frontend
            grouped_results[t]['badges'] = []

        # Add opp
        grouped_results[t]['opportunities'].append(opp)

        # [NEW] Aggregate Badges from Opportunities
        # If any opp is "tactical", tag the ticker result
        play_type = str(opp.get('play_type', '')).lower()
        if 'tactical' in play_type and "\u26a1 Tactical" not in grouped_results[t]['badges']:
            grouped_results[t]['badges'].append("\u26a1 Tactical")
        if 'momentum' in play_type and "\U0001f525 Momentum" not in grouped_results[t]['badges']:
             grouped_results[t]['badges'].append("\U0001f525 Momentum")

    # Convert to list & Sort by Best Opp
    final_results = list(grouped_results.values())
    final_results.sort(
        key=lambda x: x['opportunities'][0]['opportunity_score'] if x['opportunities'] else 0,
        reverse=True
    )

    # NOTE: AI Analysis on Top 3 has been REMOVED (user-approved).
    # Users will trigger AI analysis manually via the Analyze button
    # on individual tickers they're interested in.

    return final_results
