import logging
import math
import json
from datetime import datetime, timedelta
from backend.database.models import ScanResult, Opportunity, NewsCache

logger = logging.getLogger(__name__)


def calculate_greeks_black_scholes(scanner, S, K, T, sigma, r=0.045, opt_type='call'):
    """
    Estimate Greeks using Black-Scholes (Pure Python, no scipy).
    S: Spot Price
    K: Strike Price
    T: Time to Expiry (years)
    sigma: Volatility (decimal, e.g. 0.30)
    r: Risk-free rate
    """
    if T <= 0 or sigma <= 0:
        return {'delta': 0, 'gamma': 0, 'theta': 0}

    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        # Cumulative Distribution Function (CDF)
        def N(x):
            return 0.5 * (1 + math.erf(x / math.sqrt(2)))

        # Probability Density Function (PDF)
        def N_prime(x):
            return (1 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * x ** 2)

        if opt_type.lower() == 'call':
            delta = N(d1)
            theta = (- (S * N_prime(d1) * sigma) / (2 * math.sqrt(T))
                     - r * K * math.exp(-r * T) * N(d2)) / 365.0
        else:  # Put
            delta = N(d1) - 1
            theta = (- (S * N_prime(d1) * sigma) / (2 * math.sqrt(T))
                     + r * K * math.exp(-r * T) * N(-d2)) / 365.0

        gamma = N_prime(d1) / (S * sigma * math.sqrt(T))

        return {
            'delta': round(delta, 4),
            'gamma': round(gamma, 4),
            'theta': round(theta, 4),
            'source': 'Black-Scholes (Est.)'
        }
    except Exception as e:
        logger.warning(f"BS Calc Error: {e}")
        return {'delta': 0, 'gamma': 0, 'theta': 0, 'source': 'Error'}


def enrich_greeks(scanner, ticker, strike, expiry_date_str, opt_type, current_price, iv, context_greeks=None):
    """
    G5: Ensure Greeks are populated even outside market hours (weekends/after-hours).
    Strategy: ORATS (Live) -> Tradier (Live/Last) -> Black-Scholes (Est) -> Unavailable
    """
    # 1. Check if ORATS gave us good Greeks (Delta != 0)
    if abs(context_greeks.get('delta', 0)) > 0.001:
        context_greeks['source'] = 'ORATS (Live)'
        return context_greeks

    logger.warning(f"ORATS Greeks are 0. Attempting enrichment for {ticker}...")

    # 2. Try Tradier API (if configured)
    if scanner.use_tradier:
        try:
            # Tradier format: YYYY-MM-DD
            chain = scanner.tradier_api.get_option_chain(ticker, expiry_date_str)
            if chain:
                # Find matching strike
                for opt in chain:
                    if (abs(opt.get('strike', 0) - strike) < 0.01 and
                            opt.get('option_type', '').lower() == opt_type.lower()):
                        greeks = opt.get('greeks', {})
                        if greeks and greeks.get('delta'):
                            logger.info("Found Greeks via Tradier")
                            return {
                                'delta': greeks.get('delta'),
                                'gamma': greeks.get('gamma'),
                                'theta': greeks.get('theta'),
                                'iv': context_greeks.get('iv', 0),  # Keep original IV logic
                                'oi': context_greeks.get('oi', 0),
                                'volume': context_greeks.get('volume', 0),
                                'source': 'Tradier (Live)'
                            }
        except Exception as e:
            logger.warning(f"Tradier fallback failed: {e}")

    # 3. Try Black-Scholes (Calculation)
    # Needs IV > 0 and Time > 0
    try:
        exp_dt = datetime.strptime(expiry_date_str, "%Y-%m-%d")
        days_to_exp = (exp_dt - datetime.now()).days
        T = max(1, days_to_exp) / 365.0

        # Use 'iv' from ORATS (smvVol usually present even if Greeks aren't)
        # If iv is 0, we can't calc BS.
        sigma = context_greeks.get('iv', 0) / 100.0

        if sigma > 0 and current_price > 0:
            bs_greeks = calculate_greeks_black_scholes(
                scanner,
                S=current_price,
                K=strike,
                T=T,
                sigma=sigma,
                opt_type=opt_type
            )
            if bs_greeks['delta'] != 0:
                logger.info(f"Calculated Greeks via Black-Scholes (IV={sigma:.1%})")
                # Merge with original (keep IO/Vol)
                context_greeks.update(bs_greeks)
                return context_greeks
        else:
            logger.warning(f"Cannot calc BS: IV={sigma:.2f}, Price={current_price}")
    except Exception as e:
        logger.warning(f"BS Setup Error: {e}")

    # 4. Give up
    context_greeks['source'] = 'Unavailable (Market Closed)'
    return context_greeks


def cache_news(scanner, ticker, articles, sentiment_analysis):
    try:
        scanner.db.query(NewsCache).filter(NewsCache.ticker == ticker).delete()
        for i, article in enumerate(articles):
            s = sentiment_analysis['sentiment_breakdown'][i]['sentiment'] if i < len(sentiment_analysis['sentiment_breakdown']) else 0
            scanner.db.add(NewsCache(
                ticker=ticker,
                headline=article.get('headline'),
                summary=article.get('summary'),
                source=article.get('source'),
                url=article.get('url'),
                published_date=article.get('published_date'),
                sentiment_score=s
            ))
        scanner.db.commit()
    except Exception:
        scanner.db.rollback()


def save_scan_results(scanner, ticker, technical_score, sentiment_score, opportunities):
    try:
        avg_score = sum(o['opportunity_score'] for o in opportunities) / len(opportunities) if opportunities else 0
        res = ScanResult(ticker=ticker, technical_score=technical_score, sentiment_score=sentiment_score, opportunity_score=avg_score, profit_potential=opportunities[0]['profit_potential'] if opportunities else 0)
        scanner.db.add(res)
        scanner.db.commit()

        for opp in opportunities[:10]:
            scanner.db.add(Opportunity(
                scan_result_id=res.id,
                ticker=ticker,
                option_type=opp['option_type'],
                strike_price=opp['strike_price'],
                expiration_date=opp['expiration_date'],
                premium=opp['premium'],
                profit_potential=opp['profit_potential'],
                days_to_expiry=opp['days_to_expiry'],
                volume=opp['volume'],
                open_interest=opp['open_interest'],
                implied_volatility=opp.get('implied_volatility'),
                delta=opp.get('delta'),
                opportunity_score=opp['opportunity_score']
            ))
        scanner.db.commit()
    except Exception:
        scanner.db.rollback()


def get_latest_results(scanner):
    try:
        results = scanner.db.query(ScanResult).order_by(ScanResult.scan_date.desc()).limit(100).all()
        return [{'ticker': r.ticker, 'opportunity_score': r.opportunity_score} for r in results]
    except Exception:
        return []


def get_ai_analysis(scanner, ticker, strategy="LEAP", expiry_date=None, **kwargs):
    """
    Call the AI Reasoning Engine with Rich Context (News, Tech, GEX).
    """
    logger.info(f"AI Analysis Requested for {ticker} (Strategy: {strategy})...")

    # 1. Gather Context (Reuse Scan Logic)
    context = {
        'headlines': [],
        'technicals': {},
        'gex': {},
        'vix': {},  # XC-1: VIX regime context
    }

    try:
        # Derive weeks_out from the expiry_date param so we scan the correct expiry
        weeks_out = 0
        req_expiry = expiry_date or kwargs.get('expiry')
        if req_expiry:
            try:
                exp_dt = datetime.strptime(str(req_expiry), "%Y-%m-%d").date()
                today = datetime.now().date()
                days_diff = (exp_dt - today).days
                # Convert to weeks: 0-6 days = this week, 7-13 = +1 week, etc.
                weeks_out = max(0, days_diff // 7)
                logger.info(f"[AI] Scan targeting expiry {req_expiry} (weeks_out={weeks_out})")
            except Exception as e:
                logger.warning(f"[WARN] Could not parse expiry '{req_expiry}': {e}")

        scan_result = scanner.scan_weekly_options(ticker, weeks_out=weeks_out)

        if scan_result:
            # A. Price
            context['current_price'] = scan_result.get('current_price')

            # B. News
            sent_analysis = scan_result.get('sentiment_analysis', {})
            if sent_analysis and 'headlines' in sent_analysis:
                context['headlines'] = sent_analysis['headlines']

            # C. Technicals (Enriched with upgrade signals)
            inds = scan_result.get('indicators', {})
            ma_vals = inds.get('moving_averages', {}).get('values', {})
            vol_vals = inds.get('volume', {}).get('values', {})
            bb_vals = inds.get('bollinger_bands', {}).get('values', {})
            context['technicals'] = {
                'rsi': f"{inds.get('rsi', 0):.1f}",
                'rsi_signal': inds.get('rsi_signal', 'neutral'),
                'trend': inds.get('trend', 'Neutral'),
                'atr': f"{inds.get('atr', 0):.2f}",
                'hv_rank': f"{inds.get('hv_rank', 0):.1f}",
                'sma_5': f"{ma_vals.get('sma_5', 0):.2f}" if ma_vals.get('sma_5') else 'N/A',
                'sma_50': f"{ma_vals.get('sma_50', 0):.2f}" if ma_vals.get('sma_50') else 'N/A',
                'sma_200': f"{ma_vals.get('sma_200', 0):.2f}" if ma_vals.get('sma_200') else 'N/A',
                'ma_signal': inds.get('moving_averages', {}).get('signal', 'neutral'),
                'volume_ratio': f"{vol_vals.get('volume_ratio', 0):.2f}" if vol_vals.get('volume_ratio') else 'N/A',
                'volume_signal': inds.get('volume', {}).get('signal', 'normal'),
                'volume_zscore': f"{vol_vals.get('z_score', 0):.1f}" if vol_vals.get('z_score') is not None else 'N/A',
                'macd_signal': inds.get('macd', {}).get('signal', 'neutral'),
                'bb_signal': inds.get('bollinger_bands', {}).get('signal', 'neutral'),
                'bb_squeeze': bb_vals.get('is_squeeze', False),
                'bb_bandwidth_pct': f"{bb_vals.get('bandwidth_percentile', 50):.0f}" if bb_vals.get('bandwidth_percentile') is not None else 'N/A',
            }

            # Log upgraded signal summary
            logger.info(f"SIGNALS: RSI={context['technicals']['rsi']}({context['technicals']['rsi_signal']}) | "
                        f"MACD={context['technicals']['macd_signal']} | "
                        f"BB={context['technicals']['bb_signal']} (BW%={context['technicals']['bb_bandwidth_pct']}) | "
                        f"MA={context['technicals']['ma_signal']} | "
                        f"Vol={context['technicals']['volume_signal']} (z={context['technicals']['volume_zscore']})")

            # D. GEX
            gex = scan_result.get('gex_data')
            if gex:
                context['gex'] = {
                    'call_wall': gex.get('call_wall', 'N/A'),
                    'put_wall': gex.get('put_wall', 'N/A')
                }

            # XC-1: VIX regime context for AI reasoning
            try:
                if scanner.use_orats:
                    vix_q = scanner.batch_manager.orats_api.get_quote('VIX')
                    if vix_q and vix_q.get('price'):
                        vl = vix_q['price']
                        vr = 'CRISIS' if vl > 30 else ('ELEVATED' if vl > 20 else 'NORMAL')
                        context['vix'] = {'level': vl, 'regime': vr}
            except Exception:
                pass  # VIX is supplementary, don't block on failure

            # E. Option Greeks (Fix 3: Find specific option if strike+type provided)
            req_strike = kwargs.get('strike')
            req_type = kwargs.get('type')
            if req_strike and req_type:
                try:
                    strike_f = float(req_strike)
                    opps = scan_result.get('opportunities', [])
                    # Need expiry for Tradier/BS
                    expiry_date_str = scan_result.get('expiry_date')  # e.g. "2026-07-17"
                    if not expiry_date_str and opps:
                        expiry_date_str = opps[0].get('expiration_date')

                    for opp in opps:
                        if (abs(opp.get('strike_price', 0) - strike_f) < 0.01 and
                                str(opp.get('option_type', '')).lower() == str(req_type).lower()):

                            raw_greeks = {
                                'delta': round(opp.get('delta', 0), 4),
                                'gamma': round(opp.get('gamma', 0), 4),
                                'theta': round(opp.get('theta', 0), 4),
                                'iv': round(opp.get('iv', 0), 1) or round(opp.get('implied_volatility', 0), 1),
                                'oi': opp.get('open_interest', 0),
                                'volume': opp.get('volume', 0),
                            }

                            # Enrich if needed (Weekend Fix)
                            context['option_greeks'] = enrich_greeks(
                                scanner,
                                ticker=ticker,
                                strike=strike_f,
                                expiry_date_str=expiry_date_str,
                                opt_type=str(req_type).lower(),
                                current_price=context.get('current_price', 0),
                                iv=raw_greeks['iv'],
                                context_greeks=raw_greeks
                            )
                            logger.info(f"Found Greeks for {ticker} {req_strike} {req_type}: delta={context['option_greeks']['delta']} [{context['option_greeks'].get('source', 'Original')}]")
                            break
                    else:
                        logger.warning(f"Could not find Greeks for {ticker} {req_strike} {req_type} in scan results")
                except Exception as e:
                    logger.warning(f"Greeks lookup error: {e}")

    except Exception as e:
        logger.warning(f"Context gather failed: {e}")
        # Continue without context rather than failing

    return scanner.reasoning_engine.analyze_ticker(ticker, strategy, expiry_date, data=kwargs, context=context)


def sanitize_for_json(obj):
    """
    Recursively convert numpy types to native Python types for JSON serialization.
    """
    import numpy as np
    from datetime import date, datetime

    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(v) for v in obj]
    elif isinstance(obj, (datetime, date)):
        return obj.isoformat()
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return sanitize_for_json(obj.tolist())
    elif isinstance(obj, np.bool_):
        return bool(obj)
    else:
        return obj


def get_sentiment_score(scanner, ticker):
    """
    Get sentiment score and details for a ticker
    Returns: (score, analysis_dict)
    """
    sentiment_score = 50
    sentiment_analysis = {'summary': 'Neutral', 'sentiment_breakdown': [], 'weighted_score': 0, 'headlines': []}

    try:
        # 1. Try Premium "News Sentiment" endpoint first
        premium_sentiment = scanner.finnhub_api.get_news_sentiment(ticker.replace('$', ''))

        if premium_sentiment and premium_sentiment != "FORBIDDEN" and 'sentiment' in premium_sentiment:  # Check structure
            # Finnhub returns score 0.0 - 1.0 (Bearish < 0.5 < Bullish)
            # We map this to 0-100
            s_score = premium_sentiment.get('sentiment', {}).get('bullishPercent', 0.5) * 100
            # Override with companyNewsScore if available (same logic as weekly scan)
            if 'companyNewsScore' in premium_sentiment:
                s_score = premium_sentiment['companyNewsScore'] * 100

            sentiment_score = s_score
            sentiment_analysis['summary'] = "Finnhub Institutional Sentiment Score"
            sentiment_analysis['weighted_score'] = sentiment_score
            # Add dummy breakdown from premium data if available
            sentiment_analysis['article_count'] = 100  # Proxy

            # Still try to get headlines for context!
            news = scanner.finnhub_api.get_company_news(ticker.replace('$', ''))
            if news:
                sentiment_analysis['headlines'] = [n.get('headline') for n in news[:10] if n.get('headline')]

        else:
            # 2. Fallback to Free "Company News" + Local Analysis
            news = scanner.finnhub_api.get_company_news(ticker.replace('$', ''))
            if news:
                news_articles = []
                headlines_list = []
                for n in news[:10]:  # Analyze top 10
                    if n.get('headline'):
                        headlines_list.append(n.get('headline'))

                    news_articles.append({
                        'headline': n.get('headline'),
                        'summary': n.get('summary'),
                        'url': n.get('url'),
                        'source': n.get('source'),
                        'published_date': datetime.fromtimestamp(n.get('datetime')).isoformat() if n.get('datetime') else ""
                    })

                sentiment_analysis['headlines'] = headlines_list
                sentiment_analysis = scanner.sentiment_analyzer.analyze_articles(news_articles)
                # RE-ATTACH headlines because analyze_articles might return a new dict or overwrite?
                # best to ensure it's there
                sentiment_analysis['headlines'] = headlines_list

                sentiment_score = scanner.sentiment_analyzer.calculate_sentiment_score(sentiment_analysis)
            else:
                pass

    except Exception as e:
        logger.warning(f"Sentiment Error: {e}")

    return sentiment_score, sentiment_analysis


def get_detailed_analysis(scanner, ticker, expiry_date=None):
    """
    Get detailed analysis for a specific ticker (for Analysis Modal)
    """
    try:
        ticker = scanner._normalize_ticker(ticker)
        logger.info(f"Generating Detailed Analysis for {ticker}...")

        # 1. Get History (ORATS Strict)
        history = None
        if scanner.use_orats:
            try:
                history = scanner.batch_manager.orats_api.get_history(ticker)
            except Exception as e:
                logger.warning(f"ORATS History Failed: {e}")

        if not history:
            logger.error("Strict Mode: No History Data")
            # return None or empty structure?
            # This function returns a dict usually? No, it returns ...?
            # Wait, let's check return type.
            # It returns `detailed_analysis` variable?
            pass

        # (Yahoo Fallback Removed)

        current_price = 0
        # Get Current Price
        # Get Current Price (ORATS)
        if scanner.use_orats:
            q = scanner.batch_manager.orats_api.get_quote(ticker)
            if q:
                current_price = q.get('price', 0)

        # 2. Calculate Indicators
        indicators = {
            'rsi': {'value': 0, 'signal': 'neutral'},
            'macd': {'signal': 'neutral'},
            'bollinger_bands': {'signal': 'neutral'},
            'moving_averages': {'signal': 'neutral'},
            'volume': {'signal': 'neutral'}
        }

        technical_score = 50

        if history:
            logger.debug("Preparing DataFrame...")
            df = scanner.technical_analyzer.prepare_dataframe(history)

            # Check explicitly
            if df is not None and not df.empty:
                logger.debug(f"DataFrame Ready: {len(df)} rows")

                # RSI
                logger.debug("Calc RSI...")
                rsi_val, rsi_sig = scanner.technical_analyzer.calculate_rsi(df)
                indicators['rsi'] = {'value': rsi_val, 'signal': rsi_sig}

                # MACD
                logger.debug("Calc MACD...")
                macd_vals, macd_sig = scanner.technical_analyzer.calculate_macd(df)
                if macd_vals:
                    indicators['macd'] = {'signal': macd_sig}

                # BB
                logger.debug("Calc BB...")
                bb_vals, bb_sig = scanner.technical_analyzer.calculate_bollinger_bands(df)
                if bb_vals:
                    indicators['bollinger_bands'] = {'signal': bb_sig}

                # MA
                logger.debug("Calc MA...")
                ma_vals, ma_sig = scanner.technical_analyzer.calculate_moving_averages(df)
                if ma_vals:
                    indicators['moving_averages'] = {'signal': ma_sig}

                # Volume
                logger.debug("Calc Volume...")
                vol_vals, vol_sig = scanner.technical_analyzer.analyze_volume(df)
                if vol_vals:
                    indicators['volume'] = {'signal': vol_sig}

                # Tech Score
                logger.debug("Calc Score...")
                # Fix: Pass indicators dict, not df. Returns scalar, not dict.
                technical_score = scanner.technical_analyzer.calculate_technical_score(indicators)
            else:
                logger.debug("DF is empty or None")

        # 3. Sentiment
        sentiment_score, sentiment_details = get_sentiment_score(scanner, ticker)

        # Derive weeks_out from expiry_date if provided
        weeks_out = 0
        if expiry_date:
            try:
                from datetime import date
                exp_dt = datetime.strptime(str(expiry_date), "%Y-%m-%d").date()
                today = date.today()
                days_diff = (exp_dt - today).days
                weeks_out = max(0, days_diff // 7)
                logger.info(f"[DETAIL] Targeting expiry {expiry_date} -> weeks_out={weeks_out}")
            except Exception as e:
                logger.warning(f"[DETAIL] Could not parse expiry '{expiry_date}': {e}, using weeks_out=0")

        # 4. Opportunities (Quick Scan — using card's expiry week)
        scan_res = scanner.scan_weekly_options(ticker, weeks_out=weeks_out)
        opportunities = scan_res.get('opportunities', []) if scan_res else []

        result = {
            'ticker': ticker,
            'current_price': current_price,
            'technical_score': technical_score,
            'sentiment_score': sentiment_score,
            'indicators': indicators,
            'sentiment_analysis': sentiment_details,
            'opportunities': opportunities
        }

        return sanitize_for_json(result)

    except Exception as e:
        logger.error(f"Error in get_detailed_analysis: {e}", exc_info=True)
        return None


def close(scanner):
    scanner.watchlist_service.close()
    scanner.db.close()
