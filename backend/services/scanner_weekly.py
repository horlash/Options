import logging
import math
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def scan_weekly(scanner, ticker, weeks_out=0, strategy_tag="WEEKLY", pre_fetched_data=None):
    """
    Perform 'Weekly' or '0DTE' analysis.
    Incorporating Advanced Prop Trading Logic.
    pre_fetched_data: Optional injected option chain (for Batch Mode)
    """
    ticker = scanner._normalize_ticker(ticker)
    logger.info(f"\n{'='*50}")
    logger.info(f"Scanning {ticker} (WEEKLY + {weeks_out}) [Advanced Mode]...")
    # 0. Date Setup
    today = datetime.now().date()
    target_friday = today + timedelta((4-today.weekday()) % 7) # P0-12: Friday=4 (was 3=Thursday)
    target_friday += timedelta(weeks=weeks_out)
    target_friday_str = target_friday.strftime('%Y-%m-%d')
    logger.info(f"📅 Target Expiry: {target_friday_str} (Friday)")
    logger.info(f"{'='*50}")

    try:
        # 1. Fetch Price & Technical History (1 Year)
        # Using ORATS Priority -> Yahoo Fallback
        logger.info(f"[1/6] Fetching History & Technicals...")
        price_history = None

        # ORATS Primary
        if scanner.use_orats:
            try:
                price_history = scanner.batch_manager.orats_api.get_history(ticker)
                if price_history:
                    logger.info(f"   ℹ️  History fetched from ORATS ({len(price_history.get('candles', []))} candles)")
            except Exception as e:
                logger.warning(f"   ⚠️ ORATS History Error: {e}")

        # (Yahoo History Fallback Removed - Strict Mode)



        if not price_history:
            logger.error("❌ Failed to get price history")
            return None

        # Calculate Indicators
        indicators = scanner.technical_analyzer.get_all_indicators(price_history)
        df = scanner.technical_analyzer.prepare_dataframe(price_history)

        # [FIX] Fetch LIVE Quote to ensure we have the real-time price, not yesterday's close
        # [FIX] Fetch LIVE Quote (ORATS)
        try:
            real_time_price = 0
            if scanner.use_orats:
                q = scanner.batch_manager.orats_api.get_quote(ticker)
                if q:
                    real_time_price = q.get('price', 0)


            # (Yahoo Quote Fallback Removed - Strict Mode)

            if real_time_price:
                logger.info(f"⚡ Live Price Fetched: ${real_time_price:.2f} (Updating History)")
                df.iloc[-1, df.columns.get_loc('Close')] = real_time_price
        except Exception as e:
            logger.warning(f"⚠️ Live Quote Error: {e}, using history close.")

        current_price = df['Close'].iloc[-1]
        current_date = df.index[-1].date()
        logger.info(f"Current Price: ${current_price:.2f}")

        # Advanced Metrics
        atr = scanner.technical_analyzer.calculate_atr(df)
        hv_rank = scanner.technical_analyzer.calculate_hv_rank(df)

        # Relative Strength vs SPY
        rs_score = 0
        # F11 FIX: Use class-level cache to avoid re-fetching SPY per instance
        if type(scanner)._spy_history is None:
            logger.info("Fetching SPY History for Relative Strength (ORATS)...")
            if scanner.use_orats:
                try:
                    type(scanner)._spy_history = scanner.batch_manager.orats_api.get_history('SPY')
                except Exception as e:
                    logger.warning(f"⚠️ SPY History Failed: {e}")
                    type(scanner)._spy_history = None

        if type(scanner)._spy_history:
            df_spy = scanner.technical_analyzer.prepare_dataframe(type(scanner)._spy_history)
            rs_score = scanner.technical_analyzer.calculate_relative_strength(df, df_spy)
            logger.info(f"✓ Relative Strength vs SPY: {rs_score:.2f}%")

        # Inject RS score into Minervini criterion 8 if available
        if indicators.get('minervini') and rs_score is not None:
            # RS score > 0 means outperforming SPY; use as proxy for RS Rating >= 70
            indicators['minervini']['criteria']['8_rs_rating'] = rs_score > 0
            # Recalculate minervini score with criterion 8
            criteria = indicators['minervini']['criteria']
            new_score = sum(1 for k, v in criteria.items() if v is True)
            indicators['minervini']['score'] = new_score
            indicators['minervini']['is_stage2'] = new_score >= 7
            if new_score >= 7:
                indicators['minervini']['stage'] = 'STAGE_2'
            logger.info(f"   S5 Minervini Criterion 8 (RS): {rs_score:.2f}% → {'PASS' if rs_score > 0 else 'FAIL'} (score now {new_score}/8)")

        technical_score = scanner.technical_analyzer.calculate_technical_score(indicators)
        logger.info(f"✓ Technical Score: {technical_score:.1f} | ATR: {atr:.2f} | HV Rank: {hv_rank:.1f}")

        # 2. Sentiment Check (FINNHUB)
        logger.info(f"[2/6] Analyzing Sentiment (Finnhub)...")
        sentiment_score = 50
        sentiment_analysis = {'summary': 'Neutral', 'sentiment_breakdown': []}

        try:
            # 1. Try Premium "News Sentiment" endpoint first
            premium_sentiment = scanner.finnhub_api.get_news_sentiment(ticker.replace('$',''))

            if premium_sentiment and premium_sentiment != "FORBIDDEN" and 'sentiment' in premium_sentiment: # Check structure
                # Finnhub returns score 0.0 - 1.0 (Bearish < 0.5 < Bullish)
                # We map this to 0-100
                s_score = premium_sentiment.get('sentiment', {}).get('bullishPercent', 0.5) * 100
                # Alternatively, use their 'companyNewsScore' (0-1)
                if 'companyNewsScore' in premium_sentiment:
                    s_score = premium_sentiment['companyNewsScore'] * 100

                sentiment_score = s_score
                logger.info(f"✓ Finnhub Premium Score: {sentiment_score:.1f}")
                sentiment_analysis['summary'] = "Finnhub Institutional Sentiment Score"

            else:
                # 2. Fallback to Free "Company News" + Local Analysis
                logger.info("ℹ️ Using Free Tier: Analyzing Headlines...")
                news = scanner.finnhub_api.get_company_news(ticker.replace('$',''))
                if news:
                    news_articles = []
                    for n in news[:10]: # Analyze top 10
                        news_articles.append({
                            'headline': n.get('headline'),
                            'summary': n.get('summary'),
                            'url': n.get('url'),
                            'source': n.get('source'),
                            'published_date': datetime.fromtimestamp(n.get('datetime')).isoformat() if n.get('datetime') else ""
                        })

                    sentiment_analysis = scanner.sentiment_analyzer.analyze_articles(news_articles)
                    sentiment_score = scanner.sentiment_analyzer.calculate_sentiment_score(sentiment_analysis)
                    logger.info(f"✓ Finnhub Headline Analysis Score: {sentiment_score:.1f}")
                else:
                    logger.warning("⚠️ No Finnhub news found.")

        except Exception as e:
            logger.warning(f"⚠️ Sentiment Error: {e}")
            # Keep default 50


        # 3. Target Date & Earnings
        today = datetime.now().date()

        # [FIX] 0DTE vs Weekly Scan Differentiation
        # weeks_out=0 has TWO meanings:
        # 1. 0DTE Scans (strategy_tag=="0DTE"): Same-day expiry, Mon-Fri only
        # 2. Weekly Scans (strategy_tag=="WEEKLY"): "This Week" = next Friday, works any day

        if weeks_out == 0 and strategy_tag == "0DTE":
            # TRUE 0DTE: Same-day expiry for indices (Mon-Fri only)
            if today.weekday() in [5, 6]:  # Saturday=5, Sunday=6
                raise ValueError("⛔ 0DTE scans only available Monday-Friday during market hours")

            # Same-day expiry for true 0DTE
            target_friday = today
            target_friday_str = target_friday.strftime('%Y-%m-%d')
            logger.info(f"🎯 Target Expiry (0DTE - Same Day): {target_friday_str}")

        elif weeks_out == 0:
            # WEEKLY "This Week": Next Friday (or Friday+7 if today IS Friday)
            days_ahead = (4 - today.weekday() + 7) % 7

            # Special case: If today IS Friday and we want "this week",
            # use today for same-week expiry, not next Friday
            if days_ahead == 0:
                # Today is Friday
                if strategy_tag == "WEEKLY":
                    # For weekly scans on Friday, target is THIS Friday (today)
                    target_friday = today
                else:
                    # For 0DTE on Friday, same day
                    target_friday = today
            else:
                # Normal case: Next Friday
                target_friday = today + timedelta(days=days_ahead)

            target_friday_str = target_friday.strftime('%Y-%m-%d')
            logger.info(f"🎯 Target Expiry (This Week): {target_friday_str}")

        else:
            # WEEKLY "Next Week" / "2 Weeks Out": Calculate future Fridays
            days_ahead = (4 - today.weekday() + 7) % 7
            target_friday = today + timedelta(days=days_ahead + (weeks_out * 7))
            target_friday_str = target_friday.strftime('%Y-%m-%d')
            logger.info(f"🎯 Target Expiry (+{weeks_out} week(s)): {target_friday_str}")

        earnings_date = None
        has_earnings_risk = False
        earnings_move = None

        # P0-3: Re-enable earnings risk check via Finnhub (was stripped during Strict Mode migration)
        try:
            from datetime import date, timedelta as td
            today_str = date.today().isoformat()
            future_str = (date.today() + td(days=7)).isoformat()

            earnings = scanner.finnhub_api.get_earnings_calendar(
                symbol=ticker,
                from_date=today_str,
                to_date=future_str
            )
            if earnings:
                nearest = earnings[0]
                earnings_date = nearest.get('date')
                has_earnings_risk = True
                # Try to get implied move from ORATS hist/cores
                if scanner.use_orats:
                    try:
                        cores = scanner.batch_manager.orats_api.get_hist_cores(ticker)
                        if cores:
                            earnings_move = cores.get('impliedEarningsMove')
                    except Exception:
                        pass
                logger.warning(f"   ⚠️ EARNINGS in {earnings_date} (EPS est: {nearest.get('epsEstimate', 'N/A')}, "
                      f"implied move: {earnings_move or 'N/A'})")
        except Exception as e:
            logger.warning(f"   ⚠️ Earnings check failed (non-fatal): {e}")

        # 4. Fetch Options & GEX
        logger.info(f"[3/6] Fetching Options Chain...")
        opts = None

        # [PHASE 3] ORATS / BATCH LOGIC
        if pre_fetched_data:
            opts = pre_fetched_data
        elif scanner.use_orats:
            try:
                opts = scanner.batch_manager.orats_api.get_option_chain(ticker)
            except Exception: opts = None

        # ORATS Post-Processing: Filtering for Target Expiry (Weekly/0DTE)
        # ORATS returns full chain. Schwab returns filtered chain.
        # We must filter opts to ONLY contain target_friday keys to mimic Schwab behavior for GEX/Analysis.
        if opts and (scanner.use_orats or pre_fetched_data):
            # print(f"   ℹ️  Filtering ORATS chain to target: {target_friday_str}")
            filtered_opts = {'symbol': ticker, 'callExpDateMap': {}, 'putExpDateMap': {}}
            found_expiry = False

            for map_name in ['callExpDateMap', 'putExpDateMap']:
                if map_name in opts:
                    for key, val in opts[map_name].items():
                        # key format "YYYY-MM-DD:Days"
                        if key.startswith(target_friday_str):
                            filtered_opts[map_name][key] = val
                            found_expiry = True

            if found_expiry:
                opts = filtered_opts
            else:
                # Fallback: find nearest available expiry
                all_expiries = set()
                for map_name in ['callExpDateMap', 'putExpDateMap']:
                    if map_name in opts:
                        for key in opts[map_name].keys():
                            all_expiries.add(key.split(':')[0])

                if all_expiries:
                    from datetime import datetime as dt_parse
                    target_dt = dt_parse.strptime(target_friday_str, "%Y-%m-%d")
                    nearest = min(all_expiries, key=lambda e: abs((dt_parse.strptime(e, "%Y-%m-%d") - target_dt).days))
                    logger.warning(f"   ⚠️ Target expiry {target_friday_str} not found. Falling back to nearest: {nearest}")

                    fallback_opts = {'symbol': ticker, 'callExpDateMap': {}, 'putExpDateMap': {}}
                    for map_name in ['callExpDateMap', 'putExpDateMap']:
                        if map_name in opts:
                            for key, val in opts[map_name].items():
                                if key.startswith(nearest):
                                    fallback_opts[map_name][key] = val
                    opts = fallback_opts
                else:
                    logger.warning(f"   ⚠️ Target expiry {target_friday_str} not found in ORATS chain (no expiries available)")
                    opts = None

        # (Schwab Fallback Removed - Strict Mode)

        if not opts:
            logger.error("❌ No options found")
            return None

        # Calculate GEX Walls
        gex_data = scanner.options_analyzer.calculate_gex_walls(opts)
        if gex_data:
            logger.info(f"✓ Gamma Walls: Call ${gex_data['call_wall']} | Put ${gex_data['put_wall']}")

        # 5. Filter & Analyze Opportunities
        logger.info(f"[4/6] Filtering Opportunities...")

        # DEBUG DATA AVAILABILITY
        logger.debug(f"DEBUG: Target Friday: {target_friday_str}")
        logger.debug(f"DEBUG: Call Keys: {list(opts.get('callExpDateMap', {}).keys())}")
        logger.debug(f"DEBUG: Put Keys: {list(opts.get('putExpDateMap', {}).keys())}")

        weekly_options = []
        def collect_typed(exp_map, o_type):
            out = []
            if not exp_map: return []
            for date_key, strikes in exp_map.items():
                exp_date = date_key.split(':')[0]
                if exp_date != target_friday_str: continue
                for strike, opt_list in strikes.items():
                    for o in opt_list:
                        o['type'] = o_type
                        out.append(o)
            return out

        weekly_options = collect_typed(opts.get('callExpDateMap', {}), 'Call') + \
                         collect_typed(opts.get('putExpDateMap', {}), 'Put')

        opportunities = []
        # Use the new MA signal system for trend detection
        ma_signal = indicators['moving_averages']['signal']
        # Calls allowed when: bullish or pullback_bullish (dip in uptrend)
        # Puts allowed when: bearish, rally_bearish, or breakdown
        is_uptrend = ma_signal in ('bullish', 'pullback bullish')
        is_downtrend = ma_signal in ('bearish', 'rally bearish', 'breakdown')

        rsi_val = indicators['rsi']['value']

        for opt in weekly_options:
            otype = opt['type']
            strike = float(opt.get('strikePrice'))
            bid = opt.get('bid', 0)
            ask = opt.get('ask', 0)
            last = opt.get('last', 0)
            mark = opt.get('mark', 0)

            start_price = (bid + ask) / 2 if (bid > 0 and ask > 0) else last
            if start_price == 0:
                # Only log skips for near-the-money options (±30%) — deep OTM bid=0 is expected
                if current_price and current_price > 0:
                    proximity = abs(strike - current_price) / current_price
                    if proximity < 0.30:
                        logger.info(f"  SKIPPED {ticker} {strike} {otype}: bid={bid} ask={ask} last={last} mark={mark}")
                continue

            # --- ADVANCED FILTERING LOGIC ---

            # --- TACTICAL OVERRIDE (0DTE/Weekly Scalps) ---
            # Initialize play_type default
            play_type = 'value'

            is_tactical = False
            # [EXPERT CHANGE] Expand Tactical Window to 2 weeks for Momentum Plays
            if weeks_out <= 2:
                # 1. Sentiment Trigger (News Driven)
                # Bullish: Score > 60 | Bearish: Score < 40

                # Correction: For Next Week, we relax sentiment slightly if Volume is huge
                is_bullish_news = sentiment_score > 60
                is_bearish_news = sentiment_score < 40

                # 2. Price Action Trigger (5-Day SMA)
                # We want Price aligning with short-term momentum
                sma_5 = indicators['moving_averages']['values'].get('sma_5', 0)
                is_short_term_uptrend = current_price > sma_5
                is_short_term_downtrend = current_price < sma_5

                # 3. Volume Confirmation (Pro Rule)
                # Volume Ratio > 1.0 (Current Volume > Average)
                # Note: Pre-market/Early volume might be low, be careful.
                # Ideally > 1.2, but > 1.0 is a safer start.
                vol_data = indicators['volume']['values']
                vol_ratio = vol_data.get('volume_ratio', 0)
                is_high_volume = vol_ratio > 1.0

                # [EXPERT CHANGE] Strictness relaxer for Tactical
                if otype == 'Call':
                    # NEWS: Bullish + PRICE: Rising + VOLUME: High
                    if is_bullish_news and is_short_term_uptrend and is_high_volume:
                        is_tactical = True
                        play_type = 'tactical'

                elif otype == 'Put':
                    # NEWS: Bearish + PRICE: Falling + VOLUME: High
                    if is_bearish_news and is_short_term_downtrend and is_high_volume:
                        is_tactical = True
                        play_type = 'tactical'

                if weeks_out <= 2:
                    pass
            # -------------------------------------

            if not is_tactical:
                # Standard Trend Logic
                if otype == 'Call' and not is_uptrend:
                    if current_price and abs(strike - current_price)/current_price < 0.15:
                        logger.info(f"  FILTERED {ticker} {strike} {otype}: TREND (not uptrend, ma_signal={ma_signal})")
                    continue
                if otype == 'Put' and is_uptrend:
                    if current_price and abs(strike - current_price)/current_price < 0.15:
                        logger.info(f"  FILTERED {ticker} {strike} {otype}: TREND (uptrend blocks puts, ma_signal={ma_signal})")
                    continue

                # Standard RSI/RS Logic (Skip for Tactical/Scalp)
                # 2. RSI Check (Avoid Exhaustion)
                if otype == 'Call' and rsi_val > 70:
                    if current_price and abs(strike - current_price)/current_price < 0.15:
                        logger.info(f"  FILTERED {ticker} {strike} {otype}: RSI too high ({rsi_val})")
                    continue
                if otype == 'Put' and rsi_val < 30:
                    if current_price and abs(strike - current_price)/current_price < 0.15:
                        logger.info(f"  FILTERED {ticker} {strike} {otype}: RSI too low ({rsi_val})")
                    continue

                # 3. Relative Strength (RS) Check
                if otype == 'Call' and rs_score < -2.0:
                    if current_price and abs(strike - current_price)/current_price < 0.15:
                        logger.info(f"  FILTERED {ticker} {strike} {otype}: RS too low ({rs_score})")
                    continue
                if otype == 'Put' and rs_score > 2.0:
                    if current_price and abs(strike - current_price)/current_price < 0.15:
                        logger.info(f"  FILTERED {ticker} {strike} {otype}: RS too high ({rs_score})")
                    continue

            # 4. Bid/Ask Spread (Liquidity) - Keep for all
            if ask > 0:
                spread_pct = (ask - bid) / ask
                if spread_pct > 0.25 and not is_tactical:
                    if current_price and abs(strike - current_price)/current_price < 0.15:
                        logger.info(f"  FILTERED {ticker} {strike} {otype}: SPREAD too wide ({spread_pct:.0%}, bid={bid} ask={ask})")
                    continue # Relax for tactical?

            # 5. Delta (Probability)
            delta = abs(opt.get('delta', 0))
            min_delta = 0.15
            if ticker.startswith('$') or ticker in ['SPX', 'NDX', 'RUT']: min_delta = 0.05
            if delta < min_delta and not is_tactical:
                if current_price and abs(strike - current_price)/current_price < 0.15:
                    logger.info(f"  FILTERED {ticker} {strike} {otype}: DELTA too low ({delta:.3f} < {min_delta})")
                continue # Allow lower delta for lottos?

            # 6. Smart Money / Activity
            oi = opt.get('openInterest', 0)
            vol = opt.get('totalVolume', 0)

            is_smart_money = (vol > oi and vol > 50) or (vol > 100)
            if (oi < 100) and (vol < 20) and (not is_smart_money):
                if current_price and abs(strike - current_price)/current_price < 0.15:
                    logger.info(f"  FILTERED {ticker} {strike} {otype}: LOW ACTIVITY (oi={oi} vol={vol})")
                continue

            # 7. Gamma Wall Avoidance
            if gex_data:
                dist_to_wall = gex_data['call_wall'] - current_price
                if otype == 'Call' and 0 < dist_to_wall < (current_price * 0.01):
                    pass

            # --- SCORING & PROFIT ---

            # [EXPERT CHANGE] ATR Based Target with Time Scaling
            # Old: atr * 1.5 (Fixed)
            # New: atr * sqrt(days_out) (Dynamic)
            days_out_for_calc = max(1, (target_friday - today).days)
            trading_days = days_out_for_calc * 0.7 # Approx trading days
            scale_factor = math.sqrt(trading_days) if trading_days > 1 else 1.0

            # Cap scaling to avoid unrealistic expectations for long expiry weeklies
            scale_factor = min(scale_factor, 4.0)

            atr_target_move = atr * scale_factor

            if otype == 'Call':
                target_price_calc = current_price + atr_target_move
            else:
                target_price_calc = current_price - atr_target_move

            cost = start_price * 100
            gross_profit = 0

            if otype == 'Call':
                if target_price_calc > strike:
                    gross_profit = (target_price_calc - strike) * 100 - cost
            else:
                if target_price_calc < strike:
                    gross_profit = (strike - target_price_calc) * 100 - cost

            pct_return = (gross_profit / cost) * 100 if cost > 0 else 0

            if otype == 'Put':
                pass

            # [IMPROVEMENT] Momentum Override
            # Only apply if NOT already tactical
            min_return_threshold = 15

            if play_type != 'tactical':
                if sentiment_score > 75 or is_smart_money:
                    min_return_threshold = 10 # User Requested Floor (was 0)
                    play_type = 'momentum'
            else:
                # [EXPERT CHANGE] Relax ROI for Tactical (Speed > Value)
                min_return_threshold = 10 # Was 0, set to 10 ensuring at least some meat on bone

            # For Tactical, we IGNORE the ATR-based profit calculation
            # because news moves can exceed ATR significantly.
            if play_type != 'tactical' and pct_return < min_return_threshold:
                continue

            # Prepare for Ranker
            # We need to reshape slightly to match what rank_opportunities expects
            # It expects a dict, not an object.
            opp_dict = {
                'ticker': ticker,
                'option_type': otype,
                'strike_price': strike,
                'expiration_date': target_friday, # datetime
                'days_to_expiry': (target_friday - today).days,
                'premium': start_price,
                'bid': bid,
                'volume': vol,
                'open_interest': oi,
                'implied_volatility': opt.get('volatility', 0),
                'delta': delta,
                'gamma': opt.get('gamma', 0),
                'theta': opt.get('theta', 0),
                'profit_potential': pct_return,
                'contract_cost': cost,
                'has_earnings_risk': has_earnings_risk,
                'earnings_date': str(earnings_date) if earnings_date else None,
                'smart_money': is_smart_money,
                'hv_rank': float(hv_rank),
                'play_type': play_type,
                'strategy': strategy_tag
            }

            opportunities.append(opp_dict)

        # --- G8/G9/G14: Enriched context for Weekly/0DTE (S1: Enhanced) ---
        vix_regime_weekly = 'NORMAL'
        iv_percentile_weekly = 50
        days_to_earnings_weekly = None
        implied_earnings_move_weekly = None
        try:
            if scanner.regime_detector and Config.ENABLE_VIX_REGIME:
                weekly_regime = scanner.regime_detector.detect()
                vix_regime_weekly = weekly_regime.regime_str
            elif scanner.use_orats:
                vix_q_w = scanner.batch_manager.orats_api.get_quote('VIX')
                if vix_q_w and vix_q_w.get('price'):
                    vl_w = vix_q_w['price']
                    if vl_w > 30: vix_regime_weekly = 'CRISIS'
                    elif vl_w > 20: vix_regime_weekly = 'ELEVATED'

            if scanner.use_orats:
                cores_w = scanner.batch_manager.orats_api.get_hist_cores(ticker.replace('$', ''))
                if cores_w:
                    iv_percentile_weekly = cores_w.get('ivPctile1y', 50) or 50
                    days_to_earnings_weekly = cores_w.get('daysToNextErn')
                    implied_earnings_move_weekly = cores_w.get('impliedEarningsMove')
        except Exception as e:
            logger.warning(f"   ⚠️ Weekly enrichment fetch failed: {e}")

        # Use Centralized Ranker with Strategy Logic (WEEKLY/0DTE)
        ranked_opps_dicts = scanner.options_analyzer.rank_opportunities(
            opportunities,
            technical_score,
            sentiment_score,
            skew_score=50,
            strategy=strategy_tag,
            current_price=current_price,
            vix_regime=vix_regime_weekly,
            iv_percentile=iv_percentile_weekly,
            days_to_earnings=days_to_earnings_weekly,
            implied_earnings_move=implied_earnings_move_weekly,
        )

        # Convert back to Objects for existing API compatibility (lines 1000+)
        # Or just use the dicts? The code below (lines 1018+) expects objects access like o.ticker
        # Let's wrap them back or adjust 1018+.
        # Actually, lines 1018+ use dict access in my previous view?
        # No, line 1020: 'ticker': o.ticker. It expects attributes.
        # I will convert the ranked dicts back to Opportunity objects.

        final_opp_objects = []
        for d in ranked_opps_dicts:
            # Create Object
            obj = Opportunity(
                ticker=d['ticker'],
                option_type=d['option_type'],
                strike_price=d['strike_price'],
                expiration_date=d['expiration_date'],
                days_to_expiry=d['days_to_expiry'],
                premium=d['premium'],
                volume=d['volume'],
                open_interest=d['open_interest'],
                implied_volatility=d['implied_volatility'],
                profit_potential=d['profit_potential'],
                opportunity_score=d['opportunity_score']
            )
            # Attach extras
            obj.contract_cost = d['contract_cost']
            obj.has_earnings_risk = d['has_earnings_risk']
            obj.earnings_date = d['earnings_date']
            obj.smart_money = d['smart_money']
            obj.hv_rank = d['hv_rank']
            obj.play_type = d['play_type']
            obj.strategy = d['strategy']
            obj.skew_score = d['skew_score']
            obj.delta = d.get('delta', 0)
            obj.gamma = d.get('gamma', 0)
            obj.theta = d.get('theta', 0)

            final_opp_objects.append(obj)

        opportunities = final_opp_objects[:100]

        logger.info(f"✓ Found {len(opportunities)} Valid Opportunities")

        # Calculate Scanner Score (Top Opp Score)
        top_score = opportunities[0].opportunity_score if opportunities else 0

        result = {
            'ticker': ticker,
            'current_price': current_price,
            'technical_score': technical_score,
            'sentiment_score': sentiment_score,
            'opportunity_score': top_score,
            'indicators': {
                'rsi': rsi_val,
                'atr': atr,
                'hv_rank': hv_rank,
                'rs_score': rs_score,
                'moving_averages': indicators['moving_averages'], # Expose for Tactical Verification
                'volume': indicators['volume'], # Expose for Tactical Verification
                'trend': 'Bullish' if is_uptrend else 'Bearish'
            },
            'gex_data': gex_data,
            'opportunities': [
                {
                    'ticker': o.ticker,
                    'current_price': current_price,
                    'option_type': o.option_type,
                    'strike_price': o.strike_price,
                    'expiration_date': o.expiration_date.strftime('%Y-%m-%d') if o.expiration_date else target_friday_str,
                    'days_to_expiry': o.days_to_expiry,
                    'last_price': o.premium,
                    'premium': o.premium,
                    'profit_potential': o.profit_potential,
                    'opportunity_score': o.opportunity_score,
                    'contract_cost': getattr(o, 'contract_cost', o.premium * 100),
                    'open_interest': o.open_interest,
                    'volume': getattr(o, 'volume', 0),
                    'implied_volatility': o.implied_volatility,
                    'has_earnings_risk': getattr(o, 'has_earnings_risk', False),
                    'earnings_date': getattr(o, 'earnings_date', None),
                    'is_smart_money': getattr(o, 'smart_money', False),
                    'hv_rank': getattr(o, 'hv_rank', 0),
                    # Expert Strategy Fields
                    'strategy': getattr(o, 'strategy', 'standard_leap'),
                    'leverage_ratio': getattr(o, 'leverage_ratio', 0),
                    'break_even': getattr(o, 'break_even', 0),
                    'skew_score': getattr(o, 'skew_score', 50),
                    'play_type': getattr(o, 'play_type', 'value'),
                    'delta': getattr(o, 'delta', 0),
                    'gamma': getattr(o, 'gamma', 0),
                    'theta': getattr(o, 'theta', 0)
                }
                for o in opportunities
            ],
            'timestamp': datetime.now().isoformat(),
            'data_source': 'ORATS+Finnhub' if scanner.use_orats else 'Schwab+Finnhub'
        }
        return scanner._sanitize_for_json(result)

    except Exception as e:
        logger.error(f"❌ Error in advanced weekly scan: {e}")
        import traceback
        traceback.print_exc()
        return None


def scan_0dte(scanner, ticker):
    """
    Specialized 0DTE Scan (Intraday).
    Focus: Gamma Walls, VWAP (if avail), Momentum.
    RESTRICTED: Only Indices/Major ETFs (SPX, NDX, etc).
    """
    allowed_indices = ['$SPX', '$NDX', '$RUT', '$DJX', 'SPY', 'QQQ', 'IWM', 'SPX', 'NDX', 'RUT', 'DJX']
    normalized = ticker.upper().strip()  # Simple normalization

    if normalized not in allowed_indices:
        logger.error(f"⛔ 0DTE Scan BLOCKED for {normalized} (Indices Only)")
        raise ValueError(f"0DTE for Ticker {normalized} Not Supported")

    return scan_weekly(scanner, ticker, weeks_out=0, strategy_tag="0DTE")
