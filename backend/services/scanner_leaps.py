import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def scan_ticker_leaps(scanner, ticker, strict_mode=True, pre_fetched_data=None, direction='CALL'):
    """
    Perform complete LEAP analysis on a single ticker.
    strict_mode: If True, blocks tickers with poor fundamentals (ROE/Margin).
                 If False, allows them but marks as "Speculative".
    pre_fetched_data: Optional injected option chain data (for batch processing)
    direction: 'CALL' (bullish LEAPs) or 'PUT' (bearish LEAPs) — P0-17
    """
    ticker = scanner._normalize_ticker(ticker)
    logger.info(f"\n{'='*50}")
    logger.info(f"Scanning {ticker} (LEAPS — {direction})...")
    logger.info(f"{'='*50}")

    # [ORATS COVERAGE CHECK] Skip tickers not in ORATS universe
    if not scanner._is_orats_covered(ticker):
        logger.warning(f"⚠️ {ticker} not in ORATS universe. Skipping.")
        return None

    # Initialize badges early for strict mode logging
    fund_badges = []
    fund_score = 0

    try:
        # [PHASE 1] EXPERT QUALITY MOAT CHECK (Finnhub)
        logger.info(f"[0/5] Checking Quality Moat (Finnhub)...")

        # [FIX] Exemption Lists
        clean_ticker = ticker.replace('$', '').upper()
        non_corporate_list = ['VIX', 'SPX', 'NDX', 'RUT', 'DJI', 'SPY', 'QQQ', 'IWM', 'DIA', 'TLT', 'GLD', 'SLV']
        is_non_corporate = clean_ticker in non_corporate_list

        if is_non_corporate:
            logger.info(f"   ℹ️  Exempt from Corporate Fundamentals (Index/ETF): {ticker}")
            # G16: Use Perplexity macro sentiment for indices/ETFs
            try:
                macro = scanner.reasoning_engine.get_macro_sentiment(
                    vix_level=vix_level_leap if 'vix_level_leap' in locals() else None,
                    vix_regime=vix_regime_leap if 'vix_regime_leap' in locals() else 'NORMAL'
                )
                if macro and macro.get('score'):
                    sentiment_score = macro['score']
                    logger.info(f"   G16 Macro Sentiment (Index): {sentiment_score}/100")
            except Exception as e:
                logger.warning(f"   ⚠️ G16 macro sentiment failed: {e}")
        elif scanner.finnhub_api:
            financials = scanner.finnhub_api.get_basic_financials(clean_ticker)

            if financials == "FORBIDDEN":
                logger.error("⚠️ Finnhub Limit Reached or Feature Blocked. Aborting Scan (Strict Quality Mode).")
                return None

            if financials:
                roe = financials.get('roe')
                gross_margin = financials.get('gross_margin')

                # FIX: Finnhub returns raw percentages (15.5 = 15.5%), DO NOT multiply by 100
                # if roe is not None:
                #     roe = roe * 100
                # if gross_margin is not None:
                #     gross_margin = gross_margin * 100

                logger.info(f"   • ROE: {roe}% (Target > 15%)")
                logger.info(f"   • Gross Margin: {gross_margin}% (Target > 40%)")

                # Strict Filtering Logic
                # We accept None as "Pass" strictly for ETFs or data gaps to avoid over-filtering,
                # UNLESS it looks like a valid stock with bad data.
                # For now, strict on values if present.

                quality_fail_reasons = []
                if roe is not None and roe < 15:
                    quality_fail_reasons.append(f"Low ROE ({roe}%)")

                if gross_margin is not None and gross_margin < 40:
                    # Sector exception? (Retail/Auto might be lower). For now, strict.
                    quality_fail_reasons.append(f"Low Margins ({gross_margin}%)")

                if quality_fail_reasons:
                    logger.error(f"❌ Quality Check Failed: {', '.join(quality_fail_reasons)}")

                    if strict_mode:
                        return None

                    # Non-strict mode: Flag as Speculative
                    logger.warning("⚠️ STRICT MODE OFF: Continuing as EXPLORATORY/SPECULATIVE scan.")
                    fund_score = 0  # Penalize heavily
                    fund_badges.append("Speculative ⚠️")
                    fund_badges.append(f"Bad Fund: {quality_fail_reasons[0]}")  # Show primary reason

                    # Ensure we don't return None, but proceed
                else:
                    logger.info("✓ Quality Check Passed (Moat Detected)")
            else:
                logger.warning("⚠️ No Finnhub Data. Skipping Quality Check (Proceeding with Caution).")

        # [PHASE 2] MULTI-TIMEFRAME ANALYSIS (MTA)
        # Strict Mode: Use ORATS Daily History for Trend Analysis
        logger.info(f"[1/5] MTA Trend Alignment (ORATS Strict)...")

        price_history = None
        if scanner.use_orats:
            try:
                price_history = scanner.batch_manager.orats_api.get_history(ticker)
            except Exception as e:
                logger.error(f"❌ ORATS History Failed: {e}")

        if not price_history:
            logger.error("❌ Strict Mode: No History Data. Aborting.")
            return None

        df = scanner.technical_analyzer.prepare_dataframe(price_history)
        if df is None or len(df) < 50:
            logger.error("❌ Insufficient Data for Analysis.")
            return None

        # P0-17 FIX: Direction-aware SMA filter.
        # Calls require price > SMA (uptrend). Puts require price < SMA (downtrend).
        # Use SMA 200 (Daily) as proxy for Long-Term Trend
        current_price = df['Close'].iloc[-1]
        sma_200 = df['Close'].rolling(window=200).mean().iloc[-1]

        # Handle cases with <200 days data (use shorter SMA)
        if str(sma_200) == 'nan':
            sma_200 = df['Close'].rolling(window=50).mean().iloc[-1]

        if str(sma_200) != 'nan':
            if direction == 'CALL' and current_price < sma_200:
                logger.error(f"\u274c Downtrend for CALL LEAPs (Price {current_price:.2f} < SMA {sma_200:.2f})")
                return None
            elif direction == 'PUT' and current_price > sma_200:
                logger.error(f"\u274c Uptrend for PUT LEAPs (Price {current_price:.2f} > SMA {sma_200:.2f})")
                return None

        trend_label = "Bullish" if current_price > sma_200 else "Bearish"
        logger.info(f"\u2713 Trend {trend_label} for {direction} LEAPs (Price vs Long-Term SMA)")

        # 1. Get Fundamental Data (Hybrid Strategy)
        logger.info(f"[1/5] Fetching Fundamentals (FMP + Yahoo)...")
        fmp_quote = None
        fmp_rating = None
        y_fundamentals = None
        try:
            # Remove $ for data providers
            clean_ticker = ticker.replace('$', '')
            if scanner.fmp_api:
                fmp_quote = scanner.fmp_api.get_quote(clean_ticker)
                fmp_rating = scanner.fmp_api.get_rating(clean_ticker)

            # (Yahoo Fundamentals Removed - Strict Mode)
        except Exception as e:
            logger.warning(f"⚠️ Fundamental fetch warning: {e}")

        # P0-11: Preserve history price as ORATS fallback
        history_price = current_price  # from df['Close'].iloc[-1] above
        current_price = 0
        pe_ratio = 0

        # 2. Get Real-Time Price (ORATS Priority)
        if scanner.use_orats:
            logger.info("[2/5] Fetching Real-Time Price (ORATS)...")
            # Use batch manager's API instance
            q = scanner.batch_manager.orats_api.get_quote(ticker)
            if q:
                current_price = q.get('price') or 0
                logger.info(f"✓ Price (ORATS): ${current_price:.2f}")

        if not current_price:
            # P0-11: Fall back to history price instead of returning None
            if history_price and history_price > 0:
                current_price = history_price
                logger.warning(f"⚠️ ORATS price failed — using history price: ${current_price:.2f} (T-1 delay)")
            else:
                logger.error("❌ Strict Mode: No price available (ORATS + history both failed)")
                return None

        # 3. Calculate Fundamental Score
        # fund_score and fund_badges already initialized at top

        # A. FMP Rating (New!)
        if fmp_rating:
            r_score = fmp_rating.get('ratingScore', 0)
            r_letter = fmp_rating.get('rating', 'N/A')
            # 5=S, 4=A, 3=B, 2=C, 1=D
            if r_score >= 4:  # S or A
                fund_score += 15
                fund_badges.append(f"FMP Rating: {r_letter} ⭐")
            elif r_score == 3:  # B
                fund_score += 10
                fund_badges.append(f"FMP Rating: {r_letter}")

        # (Yahoo Fundamentals Removed - Strict Mode)

        # 4. Technical Analysis
        logger.info(f"[3/5] Analyzing technical indicators (ORATS Data)...")

        # price_history verified in Phase 1

        indicators = scanner.technical_analyzer.get_all_indicators(price_history)

        if not indicators:
            logger.error(f"❌ Failed to calculate technical indicators")
            return None

        technical_score = scanner.technical_analyzer.calculate_technical_score(indicators)
        logger.info(f"✓ Technical score: {technical_score:.1f}/100")

        # 5. Sentiment (RESTORED FINNHUB)
        logger.info(f"[4/5] Analyzing news sentiment (Finnhub)...")
        sentiment_score = 50
        sentiment_analysis = {'summary': 'Neutral', 'sentiment_breakdown': []}

        try:
            # 1. Try Premium "News Sentiment" endpoint first
            premium_sentiment = scanner.finnhub_api.get_news_sentiment(clean_ticker)

            if premium_sentiment and premium_sentiment != "FORBIDDEN" and 'sentiment' in premium_sentiment:
                # Finnhub returns score 0.0 - 1.0 (Bearish < 0.5 < Bullish) -> Map to 0-100
                s_score = premium_sentiment.get('sentiment', {}).get('bullishPercent', 0.5) * 100
                # Alternatively, use their 'companyNewsScore' (0-1)
                if 'companyNewsScore' in premium_sentiment:
                    s_score = premium_sentiment['companyNewsScore'] * 100

                sentiment_score = s_score
                logger.info(f"✓ Finnhub Premium Score: {sentiment_score:.1f}")
                sentiment_analysis['summary'] = "Finnhub Institutional Sentiment Score"

            else:
                # 2. Fallback for Indices or Free Tier
                # If it's an Index, Finnhub often returns nothing for sentiment.
                if is_non_corporate:
                    logger.info("ℹ️ Index/ETF Detected: Skipping Sentiment Score (Data Unavailable)")
                else:
                    logger.info("ℹ️ Using Free Tier or Data Gap: Analyzing Headlines...")

                news = scanner.finnhub_api.get_company_news(clean_ticker)

                news_articles = []
                if news:
                    for n in news[:15]:  # Analyze top 15
                        news_articles.append({
                            'headline': n.get('headline'),
                            'summary': n.get('summary'),
                            'url': n.get('url'),
                            'source': n.get('source'),
                            'published_date': datetime.fromtimestamp(n.get('datetime')).isoformat() if n.get('datetime') else ""
                        })
                    logger.info(f"   • Analyzed {len(news_articles)} Finnhub articles")

                if not news_articles:
                    # 3. Ultimate Fallback to Free News APIs (Google/Yahoo)
                    logger.warning("⚠️ No Finnhub news found, falling back to Google/Yahoo...")
                    news_articles = scanner.news_api.get_all_news(clean_ticker)

                sentiment_analysis = scanner.sentiment_analyzer.analyze_articles(news_articles)
                sentiment_score = scanner.sentiment_analyzer.calculate_sentiment_score(sentiment_analysis)
                logger.info(f"✓ Sentiment score: {sentiment_score:.1f}/100")

        except Exception as e:
            logger.warning(f"⚠️ Sentiment Error: {e}")
            # Keep default 50

        # Cache news (optional, implemented in _cache_news)

        # 6. Options Chain
        logger.info(f"[5/5] Identifying LEAP opportunities...")
        opportunities = []
        options_data = None

        # [PHASE 3] ORATS / BATCH LOGIC
        if pre_fetched_data:
            logger.info(f"   ℹ️  Using Pre-Fetched Option Data (Batch Mode)")
            options_data = pre_fetched_data
        elif scanner.use_orats:
            logger.info(f"   ℹ️  Fetching from ORATS API...")
            try:
                options_data = scanner.batch_manager.orats_api.get_option_chain(ticker)
            except Exception as e:
                logger.warning(f"   ⚠️ ORATS Fetch Failed: {e}")
                options_data = None

        # Fallback to Schwab
        if not options_data and scanner.use_schwab:
            logger.info(f"   ℹ️  Fetching from Schwab API (Observed Date Calculation)...")
            options_data = scanner.schwab_api.get_leap_options_chain(ticker, min_days=150)  # 5+ months

        if options_data:
            # Enforce 30% Profit Floor for LEAPs
            parsed_opps = scanner.options_analyzer.parse_options_chain(options_data, current_price, min_profit_override=30)

            # [FIX] ORATS returns ALL expiries. Filter for LEAPs (150+ days) manually if using ORATS
            # Schwab API already filters min_days=150 internally.
            # We apply a safety filter here for all data sources.
            if parsed_opps:
                leap_opps = []
                for o in parsed_opps:
                    dte = o.get('days_to_expiry', 0)
                    # Double-check: recalculate DTE from expiration_date to prevent stale cache
                    exp = o.get('expiration_date')
                    if exp:
                        try:
                            if isinstance(exp, str):
                                exp_dt = datetime.strptime(exp.split('T')[0], '%Y-%m-%d')
                            else:
                                exp_dt = exp
                            dte = (exp_dt - datetime.now()).days
                            o['days_to_expiry'] = dte  # Ensure consistency
                        except (ValueError, TypeError):
                            pass
                    if dte >= 150:
                        leap_opps.append(o)
                logger.info(f"   • Filtered {len(parsed_opps)} options -> {len(leap_opps)} LEAPs (>150 days)")
                opportunities.extend(leap_opps)

        # [PHASE 3] VOLATILITY SKEW ANALYSIS
        # P0-2: Skew was always 50 because use_schwab=False. Now uses ORATS live/summaries
        skew_score = 50  # Default Neutral
        skew_raw = 0.0

        # Option A: Use ORATS live/summaries for pre-calculated skew (preferred)
        if scanner.use_orats:
            try:
                summary = scanner.batch_manager.orats_api.get_live_summary(ticker)
                if summary:
                    # rSlp30 = 30-day risk-neutral skew slope
                    r_slp30 = summary.get('rSlp30', 0) or 0
                    skewing = summary.get('skewing', 0) or 0

                    # Normalize rSlp30 to 0-100 score
                    # rSlp30 typically ranges from -0.10 to +0.10
                    skew_raw = r_slp30
                    skew_score = max(0, min(100, 50 + (r_slp30 * 500)))

                    skew_label = "Neutral"
                    if r_slp30 > 0.02: skew_label = "Bullish"
                    elif r_slp30 < -0.03: skew_label = "Bearish"

                    logger.info(f"   • ORATS Skew: rSlp30={r_slp30:.4f}, skewing={skewing:.2f} -> Score={skew_score:.0f} ({skew_label})")
            except Exception as e:
                logger.warning(f"   ⚠️ ORATS skew fetch failed (using default 50): {e}")

        # Option B: Fallback to chain-based calculate_skew if ORATS didn't work
        if skew_score == 50 and options_data:
            try:
                skew_raw, skew_score = scanner.options_analyzer.calculate_skew(options_data, current_price)
                skew_label = "Neutral"
                if skew_raw > 0.03: skew_label = "Bullish"
                elif skew_raw < -0.05: skew_label = "Bearish"
                logger.info(f"   • Chain Skew: {skew_raw:.1%} ({skew_label}) [Score: {skew_score:.0f}]")
            except Exception as e:
                logger.warning(f"   ⚠️ Chain skew calculation failed: {e}")

        # --- G8: VIX REGIME for LEAPs (S1: Enhanced RegimeDetector) ---
        vix_level_leap = None
        vix_regime_leap = 'NORMAL'
        regime_context = None
        try:
            if scanner.regime_detector and Config.ENABLE_VIX_REGIME:
                regime_context = scanner.regime_detector.detect()
                vix_level_leap = regime_context.vix_level
                vix_regime_leap = regime_context.regime_str  # Legacy 3-tier: NORMAL/ELEVATED/CRISIS
                logger.info(f"   S1 VIX Regime: {vix_level_leap} → {regime_context.regime.value} (mapped: {vix_regime_leap})")
                if regime_context.score_penalty:
                    logger.info(f"   S1 Score Penalty: {regime_context.score_penalty}, Size Mult: {regime_context.position_size_multiplier}")
            elif scanner.use_orats:
                # Fallback: original inline logic
                vix_q = scanner.batch_manager.orats_api.get_quote('VIX')
                if vix_q and vix_q.get('price'):
                    vix_level_leap = vix_q['price']
                    if vix_level_leap > 30:
                        vix_regime_leap = 'CRISIS'
                    elif vix_level_leap > 20:
                        vix_regime_leap = 'ELEVATED'
                    logger.info(f"   VIX Regime (LEAP): {vix_level_leap:.1f} ({vix_regime_leap})")
        except Exception as e:
            logger.warning(f"   ⚠️ VIX regime detection failed: {e}")

        # --- S2: CBOE Put/Call Ratio (Contrarian Sentiment) ---
        pc_signal = None
        pc_score_mod = 0
        try:
            if scanner.macro_signals and Config.ENABLE_PUT_CALL_RATIO:
                pc_signal = scanner.macro_signals.get_put_call_signal()
                pc_score_mod = pc_signal.score_modifier
                if pc_signal.ratio is not None:
                    logger.info(f"   S2 P/C Ratio: {pc_signal.ratio:.3f} (Z={pc_signal.z_score}) → {pc_signal.signal} ({pc_signal.contrarian_bias}, {pc_score_mod:+d} sentiment)")
        except Exception as e:
            logger.warning(f"   ⚠️ P/C ratio fetch failed: {e}")

        # --- S4: Sector Momentum Modifier ---
        sector_mod = 0
        sector_info = None
        try:
            if scanner.sector_analysis and Config.ENABLE_SECTOR_MOMENTUM:
                sector_info = scanner.sector_analysis.get_ticker_sector_modifier(clean_ticker)
                sector_mod = sector_info.get('score_modifier', 0)
                if sector_info.get('rank'):
                    logger.info(f"   S4 Sector: {sector_info['sector']} ({sector_info['etf']}) — Rank #{sector_info['rank']} ({sector_info['tier']}, {sector_mod:+d})")
        except Exception as e:
            logger.warning(f"   ⚠️ Sector momentum failed: {e}")

        # --- G9: IV Percentile Rank from ORATS ---
        iv_percentile = 50  # default neutral
        try:
            if scanner.use_orats:
                cores = scanner.batch_manager.orats_api.get_hist_cores(clean_ticker)
                if cores:
                    iv_percentile = cores.get('ivPctile1y', 50) or 50
                    logger.info(f"   IV Percentile (1Y): {iv_percentile}")
        except Exception as e:
            logger.warning(f"   ⚠️ IV Percentile fetch failed: {e}")

        # --- G14: Earnings Proximity Check for LEAPs ---
        days_to_earnings = None
        implied_earnings_move = None
        try:
            if scanner.use_orats:
                if not cores:  # re-fetch if needed
                    cores = scanner.batch_manager.orats_api.get_hist_cores(clean_ticker)
                if cores:
                    days_to_earnings = cores.get('daysToNextErn')
                    implied_earnings_move = cores.get('impliedEarningsMove')
                    if days_to_earnings is not None and days_to_earnings <= 14:
                        logger.warning(f"   ⚠️ EARNINGS in {days_to_earnings} days (implied move: {implied_earnings_move})")
        except Exception as e:
            logger.warning(f"   ⚠️ Earnings check failed: {e}")

        # --- G15: Dividend Impact Check ---
        div_date = None
        try:
            if scanner.use_orats and cores:
                div_date_str = cores.get('divDate')
                if div_date_str:
                    from datetime import datetime as dt_parse
                    div_date = dt_parse.strptime(str(div_date_str)[:10], '%Y-%m-%d').date()
                    days_to_div = (div_date - datetime.now().date()).days
                    if 0 < days_to_div <= 30:
                        logger.warning(f"   ⚠️ DIVIDEND in {days_to_div} days ({div_date})")
        except Exception as e:
            logger.warning(f"   ⚠️ Dividend check failed: {e}")

        # Rank with enriched context
        # --- S1/S2/S3/S4/S7A: Apply trading system score adjustments ---
        adjusted_sentiment = sentiment_score
        adjusted_technical = technical_score

        # S1: VIX regime score penalty (high-VIX environments penalize scores)
        if regime_context and regime_context.score_penalty != 0:
            adjusted_technical = max(0, min(100, adjusted_technical + regime_context.score_penalty))
            logger.info(f"   S1 VIX Penalty: tech {regime_context.score_penalty:+d} → {adjusted_technical:.1f} (regime: {regime_context.regime.value})")

        # S2: P/C ratio contrarian sentiment modifier
        if pc_score_mod != 0:
            adjusted_sentiment = max(0, min(100, adjusted_sentiment + pc_score_mod))
            logger.info(f"   S2 Adjusted Sentiment: {sentiment_score:.1f} → {adjusted_sentiment:.1f} ({pc_score_mod:+d} P/C)")

        # S4: Sector momentum modifier on technical score
        if sector_mod != 0:
            adjusted_technical = max(0, min(100, adjusted_technical + sector_mod))
            logger.info(f"   S4 Adjusted Technical: {technical_score:.1f} → {adjusted_technical:.1f} ({sector_mod:+d} sector)")

        # S3: RSI-2 extreme signal boost (from indicators dict)
        if Config.ENABLE_RSI2 and indicators.get('rsi2'):
            rsi2 = indicators['rsi2']
            rsi2_mod = 0
            if rsi2.get('signal') == 'extreme_oversold' and direction == 'CALL':
                rsi2_mod = 12  # Strong mean-reversion buy signal for calls
            elif rsi2.get('signal') == 'oversold' and direction == 'CALL':
                rsi2_mod = 6
            elif rsi2.get('signal') == 'extreme_overbought' and direction == 'PUT':
                rsi2_mod = 12  # Strong mean-reversion sell signal for puts
            elif rsi2.get('signal') == 'overbought' and direction == 'PUT':
                rsi2_mod = 6
            elif rsi2.get('signal') == 'extreme_overbought' and direction == 'CALL':
                rsi2_mod = -8  # Contrarian warning for calls
            elif rsi2.get('signal') == 'extreme_oversold' and direction == 'PUT':
                rsi2_mod = -8  # Contrarian warning for puts
            if rsi2_mod != 0:
                adjusted_technical = max(0, min(100, adjusted_technical + rsi2_mod))
                logger.info(f"   S3 RSI-2={rsi2.get('value')} ({rsi2.get('signal')}): tech {rsi2_mod:+d} → {adjusted_technical:.1f}")

        # S7A: VWAP institutional level boost
        if Config.ENABLE_VWAP_LEVELS and indicators.get('vwap'):
            vwap_mod = indicators['vwap'].get('score_boost', 0)
            if vwap_mod != 0:
                adjusted_technical = max(0, min(100, adjusted_technical + vwap_mod))
                logger.info(f"   S7A VWAP {indicators['vwap'].get('signal')}: tech {vwap_mod:+d} → {adjusted_technical:.1f}")

        # S5: Minervini Stage 2 pre-filter (log but don't hard-block — zero-results floor)
        if Config.ENABLE_MINERVINI_FILTER and indicators.get('minervini'):
            mstage = indicators['minervini']
            if mstage.get('stage') in ('STAGE_3_OR_4',) and not is_non_corporate:
                # Not in Stage 2 uptrend — penalize but don't block
                adjusted_technical = max(0, adjusted_technical - 10)
                logger.info(f"   S5 Minervini: {mstage.get('stage')} ({mstage.get('score')}/8) — tech -10 → {adjusted_technical:.1f}")
            elif mstage.get('is_stage2'):
                adjusted_technical = min(100, adjusted_technical + 8)
                logger.info(f"   S5 Minervini: {mstage.get('stage')} ({mstage.get('score')}/8) — tech +8 → {adjusted_technical:.1f}")

        ranked_opportunities = scanner.options_analyzer.rank_opportunities(
            opportunities,
            adjusted_technical,
            adjusted_sentiment,
            skew_score=skew_score,
            strategy="LEAP",
            current_price=current_price,
            fundamental_score=fund_score,
            vix_regime=vix_regime_leap,
            iv_percentile=iv_percentile,
            days_to_earnings=days_to_earnings,
            implied_earnings_move=implied_earnings_move,
        )

        # --- G2: Attach exit plans to ranked opportunities ---
        for opp in ranked_opportunities:
            try:
                opp['exit_plan'] = scanner.exit_manager.generate_exit_plan(
                    opp,
                    strategy='LEAP',
                    vix_regime=vix_regime_leap,
                    days_to_earnings=days_to_earnings,
                    iv_percentile=iv_percentile,
                )
            except Exception as e:
                opp['exit_plan'] = {'summary': f'Exit plan generation failed: {e}'}

        # Save Results
        scanner._save_scan_results(ticker, technical_score, sentiment_score, ranked_opportunities)

        result = {
            'ticker': ticker,
            'current_price': current_price,
            'technical_score': adjusted_technical,
            'sentiment_score': adjusted_sentiment,
            'raw_technical_score': technical_score,
            'raw_sentiment_score': sentiment_score,
            'indicators': indicators,
            'sentiment_analysis': sentiment_analysis,
            'fundamental_analysis': {
                'score': fund_score,
                'badges': fund_badges,
                'fmp_rating': fmp_rating.get('rating', 'N/A') if fmp_rating else "N/A",
                'eps_growth': f"{y_fundamentals.get('trailing_eps')} -> {y_fundamentals.get('forward_eps')}" if y_fundamentals else "N/A",
                'analyst_rating': y_fundamentals.get('analyst_rating') if y_fundamentals else "N/A",
                'pe_ratio': pe_ratio if pe_ratio else (y_fundamentals.get('pe_ratio') if y_fundamentals else "N/A")
            },
            'opportunities': ranked_opportunities,
            'data_source': 'ORATS' if scanner.use_orats else 'Schwab',
            # --- Trading System Enhancements ---
            'trading_systems': {
                'vix_regime': {
                    'level': vix_level_leap,
                    'regime': vix_regime_leap,
                    'context': {
                        'regime_5tier': regime_context.regime.value,
                        'score_penalty': regime_context.score_penalty,
                        'position_size_mult': regime_context.position_size_multiplier,
                        'is_fallback': regime_context.is_fallback,
                    } if regime_context else None,
                },
                'put_call': {
                    'ratio': pc_signal.ratio if pc_signal else None,
                    'z_score': pc_signal.z_score if pc_signal else None,
                    'signal': pc_signal.signal if pc_signal else 'disabled',
                    'contrarian_bias': pc_signal.contrarian_bias if pc_signal else None,
                    'score_modifier': pc_score_mod,
                },
                'sector_momentum': sector_info if sector_info else {'tier': 'disabled'},
                'rsi2': indicators.get('rsi2', {}),
                'minervini': indicators.get('minervini', {}),
                'vwap': indicators.get('vwap', {}),
                'score_adjustments': {
                    'technical_raw': technical_score,
                    'technical_adjusted': adjusted_technical,
                    'sentiment_raw': sentiment_score,
                    'sentiment_adjusted': adjusted_sentiment,
                },
            },
        }
        return scanner._sanitize_for_json(result)

    except Exception as e:
        logger.error(f"❌ Error scanning {ticker}: {str(e)}")
        import traceback
        traceback.print_exc()
        return None
