import logging
from datetime import datetime

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
        logger.info(f"🚀 Batch Fetching Options for {len(tickers)} tickers (ORATS)...")
        try:
            batch_data = scanner.batch_manager.fetch_option_chains(tickers)
        except Exception as e:
            logger.warning(f"⚠️ Batch Fetch Failed: {e}")
    
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


def scan_sector_top_picks(scanner, sector, min_volume, min_market_cap, limit=15, weeks_out=None, industry=None):
    """
    Run a 'Smart Scan' on a sector.
    1. Query FMP Screener for top candidates.
    2. Run deep LEAP scan OR Weekly scan (based on weeks_out) on them.
    3. [NEW] Run AI Analysis on Top 3 Global Picks.
    4. Return combined opportunities.
    """
    mode_label = "LEAPS" if weeks_out is None else f"WEEKLY (+{weeks_out})"
    ind_label = f" | {industry}" if industry else ""
    logger.info(f"🚀 Starting Sector Scan: {sector}{ind_label} [{mode_label}] [Cap > {min_market_cap}, Vol > {min_volume}]")
    
    # 1. Pre-filter (FMP)
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
         logger.warning(f"⚠️ FMP Screener API Failed: {e}")
         # Fallback logic omitted for brevity in this block update, assumed handled in full file if needed
         pass

    if not candidates:
        # Quick local cache fallback (simplified for edit)
        cached = scanner.get_cached_tickers()
        # Handle case where marketCap/volume exists as key but value is None (from partial enrichment)
        matches = [
            t for t in cached 
            if t.get('sector') == sector 
            and (t.get('marketCap') or 0) >= int(min_market_cap or 0)
        ]
        matches.sort(key=lambda x: (x.get('marketCap') or 0), reverse=True)
        candidates = matches[:15]
        
    if not candidates:
        logger.error("❌ No candidates found in sector screener")
        return []
        
    logger.info(f"📋 Found {len(candidates)} candidates. Starting deep scan...")
    
    # [ORATS COVERAGE PRE-FILTER] Skip tickers not in ORATS universe
    tickers = [c['symbol'] for c in candidates]
    if scanner._orats_universe:
        original_count = len(tickers)
        tickers = [t for t in tickers if scanner._is_orats_covered(t)]
        skipped = original_count - len(tickers)
        if skipped > 0:
            logger.info(f"⏭️ Skipped {skipped} tickers not in ORATS universe ({len(tickers)} remaining)")
        # Also filter candidates list to stay in sync
        candidates = [c for c in candidates if c['symbol'] in tickers]
    
    # [PHASE 3] Batch Fetching
    batch_data = {}
    if scanner.use_orats:
        logger.info(f"🚀 Batch Fetching Options for {len(tickers)} tickers (ORATS)...")
        try:
            batch_data = scanner.batch_manager.fetch_option_chains(tickers)
        except Exception as e:
            logger.warning(f"⚠️ Batch Fetch Failed: {e}")

    # 2. Deep Scan
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
        ticker = cand['symbol']
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
            all_results.append(res)

    # 3. Global Filter & AI Integration
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
    logger.info(f"🎯 Filtered down to Top {len(top_100)} Global Opportunities")

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
        if 'tactical' in play_type and "⚡ Tactical" not in grouped_results[t]['badges']:
            grouped_results[t]['badges'].append("⚡ Tactical")
        if 'momentum' in play_type and "🔥 Momentum" not in grouped_results[t]['badges']:
             grouped_results[t]['badges'].append("🔥 Momentum")
        
    # Convert to list & Sort by Best Opp
    final_results = list(grouped_results.values())
    final_results.sort(
        key=lambda x: x['opportunities'][0]['opportunity_score'] if x['opportunities'] else 0, 
        reverse=True
    )

    # [NEW] AI Analysis for Top 3
    # We process the top 3 tickers in the final list
    top_3_tickers = final_results[:3]
    logger.info(f"🤖 Running AI Analysis on Top {len(top_3_tickers)} Picks...")
    
    for res in top_3_tickers:
        t = res['ticker']
        strat = "LEAP" if weeks_out is None else "WEEKLY"
        
        # We already have context in 'res', let's re-use it if possible or just call the engine
        # The 'get_ai_analysis' helper re-fetches data which is slow.
        # Let's call reasoning_engine directly using the data we JUST fetched to save time!
        
        # Construct Context from existing result
        # P0-13: Populate full technicals + sentiment for AI reasoning engine
        indicators = res.get('indicators', {})
        context = {
            'current_price': res.get('current_price'),
            'headlines': res.get('sentiment_analysis', {}).get('headlines', []),
            'technicals': {
                'score': res.get('technical_score', 50),
                'rsi': f"{indicators.get('rsi', 0):.1f}",
                'rsi_signal': indicators.get('rsi_signal', 'neutral'),
                'macd_signal': indicators.get('macd_signal', 'neutral'),
                'bb_signal': indicators.get('bb_signal', 'neutral'),
                'bb_bandwidth_pct': indicators.get('bb_bandwidth_pct', 'N/A'),
                'bb_squeeze': indicators.get('bb_squeeze', False),
                'ma_signal': indicators.get('ma_signal', 'neutral'),
                'sma_5': indicators.get('sma_5', 'N/A'),
                'sma_50': indicators.get('sma_50', 'N/A'),
                'sma_200': indicators.get('sma_200', 'N/A'),
                'trend': indicators.get('trend', 'Neutral'),
                'atr': f"{indicators.get('atr', 0):.2f}",
                'hv_rank': f"{indicators.get('hv_rank', 0):.1f}",
                'volume_signal': indicators.get('volume_signal', 'normal'),
                'volume_ratio': indicators.get('volume_ratio', 'N/A'),
                'volume_zscore': indicators.get('volume_zscore', 0),
            },
            'sentiment': {
                'score': res.get('sentiment_score', 50),
            },
            'gex': {
                'call_wall': res.get('gex_data', {}).get('call_wall', 'N/A'),
                'put_wall': res.get('gex_data', {}).get('put_wall', 'N/A')
            },
            # XC-1: VIX regime context for AI reasoning
            'vix': {
                'level': vix_level,
                'regime': vix_regime,
            }
        }
        
        try:
            logger.info(f"   > Analyzing {t}...")
            ai_output = scanner.reasoning_engine.analyze_ticker(t, strat, None, context=context)
            res['ai_analysis'] = ai_output # Attach to result
        except Exception as e:
            logger.warning(f"   ⚠️ AI Failed for {t}: {e}")
            res['ai_analysis'] = {'thesis': "AI Analysis Failed", 'risk_assessment': "N/A"}

    return final_results
