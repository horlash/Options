import os
from datetime import datetime, timedelta
from backend.api.tradier import TradierAPI
from backend.api.fmp import FMPAPI
from backend.api.free_news import FreeNewsAPIs
from backend.api.finnhub import FinnhubAPI
from backend.analysis.technical_indicators import TechnicalIndicators
from backend.analysis.sentiment_analyzer import SentimentAnalyzer
from backend.analysis.options_analyzer import OptionsAnalyzer
from backend.services.watchlist_service import WatchlistService
from backend.services.batch_manager import BatchManager # [NEW]
from backend.database.models import ScanResult, Opportunity, NewsCache, SessionLocal
from backend.services.reasoning_engine import ReasoningEngine

class HybridScannerService:
    """Scanner service using ORATS + Finnhub for options analysis"""
    
    _ticker_cache = []
    _orats_universe = None  # Loaded from orats_universe.json

    def __init__(self):
        self.yahoo_api = None # YahooFinanceAPI() # REMOVED (Strict Mode)
        self.tradier_api = TradierAPI()  # Tradier for Greeks
        # self.schwab_api = SchwabAPI()   # REMOVED
        self.fmp_api = FMPAPI() # Financial Modeling Prep (Price/PE/News/Screener)
        self.finnhub_api = FinnhubAPI() # Finnhub (Sentiment)
        self.news_api = FreeNewsAPIs()  # Free news sources
        self.technical_analyzer = TechnicalIndicators()
        self.sentiment_analyzer = SentimentAnalyzer()
        self.options_analyzer = OptionsAnalyzer()
        self.reasoning_engine = ReasoningEngine()
        self.watchlist_service = WatchlistService()
        self.batch_manager = BatchManager() # [NEW] ORATS Batch Manager
        self.db = SessionLocal()
        
        # Check configuration
        self.use_tradier = self.tradier_api.is_configured()
        self.use_schwab = False # DISABLED
        self.use_orats = self.batch_manager.orats_api.is_configured() if hasattr(self.batch_manager, 'orats_api') else False

        # Initialize Ticker Cache if empty
        if not HybridScannerService._ticker_cache:
            self._refresh_ticker_cache()
        
        # Load ORATS universe for coverage checks
        if HybridScannerService._orats_universe is None:
            self._load_orats_universe()
        
        if self.use_orats:
             print("[OK] ORATS API configured - Primary Source (History + Options)")
        else:
             print("[WARNING] ORATS API NOT configured - Critical Error for Full Switch")

    def _refresh_ticker_cache(self):
        """Load tickers from local JSON file (backend/data/tickers.json)"""
        print("[LOADING] Ticker Cache...")
        
        # Path to local ticker file
        import json
        from datetime import datetime, timedelta
        
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
                    print(f"[WARNING] Ticker list is {age_days} days old (>90 days)")
                    print(f"[WARNING] Run 'python backend/scripts/refresh_tickers.py' to update")
                else:
                    print(f"[OK] Ticker list age: {age_days} days (updated {last_updated.strftime('%Y-%m-%d')})")
            
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
            print(f"[OK] Loaded {len(filtered)} tickers from local cache")
            
        except FileNotFoundError:
            print(f"[ERROR] Ticker file not found: {local_path}")
            print(f"[WARNING] Run 'python backend/scripts/refresh_tickers.py' to create it")
            HybridScannerService._ticker_cache = []
        except Exception as e:
            print(f"[ERROR] Error loading tickers: {e}")
            HybridScannerService._ticker_cache = []

    def get_cached_tickers(self):
        return HybridScannerService._ticker_cache

    def _load_orats_universe(self):
        """Load ORATS ticker universe from local cache for O(1) coverage lookups."""
        import json
        orats_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'orats_universe.json')
        try:
            with open(orats_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            universe = set(data.get('tickers', {}).keys())
            HybridScannerService._orats_universe = universe
            
            # Check age
            last_updated = data.get('last_updated', '')
            if last_updated:
                from datetime import datetime
                updated_dt = datetime.fromisoformat(last_updated)
                age_days = (datetime.now() - updated_dt).days
                if age_days > 7:
                    print(f"⚠️ ORATS universe cache is {age_days} days old. Run 'python backend/scripts/refresh_tickers_v3.py'")
                else:
                    print(f"✅ ORATS universe: {len(universe)} tickers (cache age: {age_days} days)")
            else:
                print(f"✅ ORATS universe: {len(universe)} tickers loaded")
        except FileNotFoundError:
            print("⚠️ ORATS universe cache not found. Run 'python backend/scripts/refresh_tickers_v3.py'")
            HybridScannerService._orats_universe = set()
        except Exception as e:
            print(f"⚠️ Error loading ORATS universe: {e}")
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

    def scan_ticker(self, ticker, strict_mode=True, pre_fetched_data=None):
        """
        Perform complete LEAP analysis on a single ticker
        strict_mode: If True, blocks tickers with poor fundamentals (ROE/Margin).
                     If False, allows them but marks as "Speculative".
        pre_fetched_data: Optional injected option chain data (for batch processing)
        """
        ticker = self._normalize_ticker(ticker)
        print(f"\n{'='*50}")
        print(f"Scanning {ticker} (LEAPS)...")
        print(f"{'='*50}")
        
        # [ORATS COVERAGE CHECK] Skip tickers not in ORATS universe
        if not self._is_orats_covered(ticker):
            print(f"⚠️ {ticker} not in ORATS universe. Skipping.")
            return None
        
        # Initialize badges early for strict mode logging
        fund_badges = []
        fund_score = 0
        
        try:
            # [PHASE 1] EXPERT QUALITY MOAT CHECK (Finnhub)
            print(f"[0/5] Checking Quality Moat (Finnhub)...")
            
            # [FIX] Exemption Lists
            clean_ticker = ticker.replace('$', '').upper()
            non_corporate_list = ['VIX', 'SPX', 'NDX', 'RUT', 'DJI', 'SPY', 'QQQ', 'IWM', 'DIA', 'TLT', 'GLD', 'SLV']
            is_non_corporate = clean_ticker in non_corporate_list
            
            if is_non_corporate:
                print(f"   ℹ️  Exempt from Corporate Fundamentals (Index/ETF): {ticker}")
            elif self.finnhub_api:
                financials = self.finnhub_api.get_basic_financials(clean_ticker)
                
                if financials == "FORBIDDEN":
                    print("⚠️ Finnhub Limit Reached or Feature Blocked. Aborting Scan (Strict Quality Mode).")
                    return None
                
                if financials:
                    roe = financials.get('roe')
                    gross_margin = financials.get('gross_margin')
                    
                    # FIX: Finnhub returns raw percentages (15.5 = 15.5%), DO NOT multiply by 100
                    # if roe is not None:
                    #     roe = roe * 100
                    # if gross_margin is not None:
                    #     gross_margin = gross_margin * 100
                    
                    print(f"   • ROE: {roe}% (Target > 15%)")
                    print(f"   • Gross Margin: {gross_margin}% (Target > 40%)")

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
                         print(f"❌ Quality Check Failed: {', '.join(quality_fail_reasons)}")
                         
                         if strict_mode:
                             return None
                        
                         # Non-strict mode: Flag as Speculative
                         print("⚠️ STRICT MODE OFF: Continuing as EXPLORATORY/SPECULATIVE scan.")
                         fund_score = 0 # Penalize heavily
                         fund_badges.append("Speculative ⚠️")
                         fund_badges.append(f"Bad Fund: {quality_fail_reasons[0]}") # Show primary reason
                         
                         # Ensure we don't return None, but proceed
                    else:
                        print("✓ Quality Check Passed (Moat Detected)")
                else:
                    print("⚠️ No Finnhub Data. Skipping Quality Check (Proceeding with Caution).")
            
            # [PHASE 2] MULTI-TIMEFRAME ANALYSIS (MTA)
            # Strict Mode: Use ORATS Daily History for Trend Analysis
            print(f"[1/5] MTA Trend Alignment (ORATS Strict)...")
            
            price_history = None
            if self.use_orats:
                 try:
                     price_history = self.batch_manager.orats_api.get_history(ticker)
                 except Exception as e:
                     print(f"❌ ORATS History Failed: {e}")
            
            if not price_history:
                print("❌ Strict Mode: No History Data. Aborting.")
                return None
            
            df = self.technical_analyzer.prepare_dataframe(price_history)            
            if df is None or len(df) < 50:
                print("❌ Insufficient Data for Analysis.")
                return None
            
            # Use SMA 200 (Daily) as proxy for Long-Term Trend
            current_price = df['Close'].iloc[-1]
            sma_200 = df['Close'].rolling(window=200).mean().iloc[-1]
            
            # Handle cases with <200 days data (use shorter SMA)
            if str(sma_200) == 'nan':
                 sma_200 = df['Close'].rolling(window=50).mean().iloc[-1]
            
            if str(sma_200) != 'nan' and current_price < sma_200:
                print(f"❌ Downtrend (Price {current_price:.2f} < Long-Term SMA {sma_200:.2f})")
                return None
            
            print(f"✓ Trend Bullish (Price > Long-Term SMA)")

            # 1. Get Fundamental Data (Hybrid Strategy)
            print(f"[1/5] Fetching Fundamentals (FMP + Yahoo)...")
            fmp_quote = None
            fmp_rating = None
            y_fundamentals = None
            try:
                # Remove $ for data providers
                clean_ticker = ticker.replace('$', '')
                if self.fmp_api:
                    fmp_quote = self.fmp_api.get_quote(clean_ticker)
                    fmp_rating = self.fmp_api.get_rating(clean_ticker)
                
                # (Yahoo Fundamentals Removed - Strict Mode)
            except Exception as e:
                print(f"⚠️ Fundamental fetch warning: {e}")

            current_price = 0
            pe_ratio = 0
            
            # 2. Get Real-Time Price (ORATS Priority)
            if self.use_orats:
                print("[2/5] Fetching Real-Time Price (ORATS)...")
                # Use batch manager's API instance
                q = self.batch_manager.orats_api.get_quote(ticker)
                if q:
                    current_price = q.get('price') or 0
                    print(f"✓ Price (ORATS): ${current_price:.2f}")
            
            if not current_price:
                 print("❌ Strict Mode: ORATS Price Failed")
                 return None
                
            # 3. Calculate Fundamental Score
            # fund_score and fund_badges already initialized at top

            
            # A. FMP Rating (New!)
            if fmp_rating:
                r_score = fmp_rating.get('ratingScore', 0)
                r_letter = fmp_rating.get('rating', 'N/A')
                # 5=S, 4=A, 3=B, 2=C, 1=D
                if r_score >= 4: # S or A
                    fund_score += 15
                    fund_badges.append(f"FMP Rating: {r_letter} ⭐")
                elif r_score == 3: # B
                    fund_score += 10
                    fund_badges.append(f"FMP Rating: {r_letter}")

            # (Yahoo Fundamentals Removed - Strict Mode)
            
            # 4. Technical Analysis
            print(f"[3/5] Analyzing technical indicators (ORATS Data)...")
            
            # price_history verified in Phase 1

            indicators = self.technical_analyzer.get_all_indicators(price_history)
            
            if not indicators:
                print(f"❌ Failed to calculate technical indicators")
                return None
            
            technical_score = self.technical_analyzer.calculate_technical_score(indicators)
            print(f"✓ Technical score: {technical_score:.1f}/100")
            
            # 5. Sentiment (RESTORED FINNHUB)
            print(f"[4/5] Analyzing news sentiment (Finnhub)...")
            sentiment_score = 50 
            sentiment_analysis = {'summary': 'Neutral', 'sentiment_breakdown': []}
            
            try:
                # 1. Try Premium "News Sentiment" endpoint first
                premium_sentiment = self.finnhub_api.get_news_sentiment(clean_ticker)
                
                if premium_sentiment and premium_sentiment != "FORBIDDEN" and 'sentiment' in premium_sentiment:
                    # Finnhub returns score 0.0 - 1.0 (Bearish < 0.5 < Bullish) -> Map to 0-100
                    s_score = premium_sentiment.get('sentiment', {}).get('bullishPercent', 0.5) * 100
                    # Alternatively, use their 'companyNewsScore' (0-1)
                    if 'companyNewsScore' in premium_sentiment:
                         s_score = premium_sentiment['companyNewsScore'] * 100
                         
                    sentiment_score = s_score
                    print(f"✓ Finnhub Premium Score: {sentiment_score:.1f}")
                    sentiment_analysis['summary'] = "Finnhub Institutional Sentiment Score"
                    
                else:
                    # 2. Fallback for Indices or Free Tier
                    # If it's an Index, Finnhub often returns nothing for sentiment.
                    if is_non_corporate:
                         print("ℹ️ Index/ETF Detected: Skipping Sentiment Score (Data Unavailable)")
                    else:
                         print("ℹ️ Using Free Tier or Data Gap: Analyzing Headlines...")
                    
                    news = self.finnhub_api.get_company_news(clean_ticker)
                    
                    news_articles = []
                    if news:
                        for n in news[:15]: # Analyze top 15
                            news_articles.append({
                                'headline': n.get('headline'),
                                'summary': n.get('summary'),
                                'url': n.get('url'),
                                'source': n.get('source'),
                                'published_date': datetime.fromtimestamp(n.get('datetime')).isoformat() if n.get('datetime') else ""
                            })
                        print(f"   • Analyzed {len(news_articles)} Finnhub articles")
                    
                    if not news_articles:
                         # 3. Ultimate Fallback to Free News APIs (Google/Yahoo)
                         print("⚠️ No Finnhub news found, falling back to Google/Yahoo...")
                         news_articles = self.news_api.get_all_news(clean_ticker)

                    sentiment_analysis = self.sentiment_analyzer.analyze_articles(news_articles)
                    sentiment_score = self.sentiment_analyzer.calculate_sentiment_score(sentiment_analysis)
                    print(f"✓ Sentiment score: {sentiment_score:.1f}/100")
                        
            except Exception as e:
                print(f"⚠️ Sentiment Error: {e}")
                # Keep default 50
            
            # Cache news (optional, implemented in _cache_news)
            
            # 6. Options Chain
            print(f"[5/5] Identifying LEAP opportunities...")
            opportunities = []
            options_data = None
            
            # [PHASE 3] ORATS / BATCH LOGIC
            if pre_fetched_data:
                 print(f"   ℹ️  Using Pre-Fetched Option Data (Batch Mode)")
                 options_data = pre_fetched_data
            elif self.use_orats:
                 print(f"   ℹ️  Fetching from ORATS API...")
                 try:
                     options_data = self.batch_manager.orats_api.get_option_chain(ticker)
                 except Exception as e:
                     print(f"   ⚠️ ORATS Fetch Failed: {e}")
                     options_data = None
            
            # Fallback to Schwab
            if not options_data and self.use_schwab:
                print(f"   ℹ️  Fetching from Schwab API (Observed Date Calculation)...")
                options_data = self.schwab_api.get_leap_options_chain(ticker, min_days=150)  # 5+ months

            if options_data:
                 # Enforce 30% Profit Floor for LEAPs
                 parsed_opps = self.options_analyzer.parse_options_chain(options_data, current_price, min_profit_override=30)
                 
                 # [FIX] ORATS returns ALL expiries. Filter for LEAPs (150+ days) manually if using ORATS
                 # Schwab API already filters min_days=150 internally.
                 # We apply a safety filter here for all data sources.
                 if parsed_opps:
                     leap_opps = [o for o in parsed_opps if o['days_to_expiry'] >= 150]
                     print(f"   • Filtered {len(parsed_opps)} options -> {len(leap_opps)} LEAPs (>150 days)")
                     opportunities.extend(leap_opps)
            
            # [PHASE 3] VOLATILITY SKEW ANALYSIS
            # Calculate Skew (Call IV - Put IV) to detect "Smart Money" sentiment
            skew_score = 50 # Default Neutral
            if self.use_schwab and options_data:
                skew_raw, skew_score = self.options_analyzer.calculate_skew(options_data, current_price)
                
                skew_label = "Neutral"
                if skew_raw > 0.03: skew_label = "Bullish"
                elif skew_raw < -0.05: skew_label = "Bearish"
                
                print(f"   • Volatility Skew: {skew_raw:.1%} ({skew_label}) [Score: {skew_score:.0f}]")

            # Rank
            ranked_opportunities = self.options_analyzer.rank_opportunities(
                opportunities, 
                technical_score, 
                sentiment_score,
                skew_score=skew_score,
                strategy="LEAP",
                current_price=current_price
            )
            
            # Save Results
            self._save_scan_results(ticker, technical_score, sentiment_score, ranked_opportunities)

            result = {
                'ticker': ticker,
                'current_price': current_price,
                'technical_score': technical_score,
                'sentiment_score': sentiment_score,
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
                'data_source': 'ORATS' if self.use_orats else 'Schwab'
            }
            return self._sanitize_for_json(result)

        except Exception as e:
            print(f"❌ Error scanning {ticker}: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    def scan_watchlist(self):
        """Scan all tickers in watchlist"""
        watchlist = self.watchlist_service.get_watchlist()
        if not watchlist:
            return []
        
        tickers = [item['ticker'] for item in watchlist]
        
        # [PHASE 3] Batch Fetching
        batch_data = {}
        if self.use_orats:
            print(f"🚀 Batch Fetching Options for {len(tickers)} tickers (ORATS)...")
            try:
                batch_data = self.batch_manager.fetch_option_chains(tickers)
            except Exception as e:
                print(f"⚠️ Batch Fetch Failed: {e}")
        
        results = []
        for item in watchlist:
            t = item['ticker']
            # Pass pre-fetched data if available
            opts = batch_data.get(t)
            
            result = self.scan_ticker(t, pre_fetched_data=opts)
            if result:
                results.append(result)
        
        # Sort
        results.sort(key=lambda x: x['opportunities'][0]['opportunity_score'] if x['opportunities'] else 0, reverse=True)
        return results

        return final_results

    def _calculate_greeks_black_scholes(self, S, K, T, sigma, r=0.045, opt_type='call'):
        """
        Estimate Greeks using Black-Scholes (Pure Python, no scipy).
        S: Spot Price
        K: Strike Price
        T: Time to Expiry (years)
        sigma: Volatility (decimal, e.g. 0.30)
        r: Risk-free rate
        """
        import math
        
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
            else: # Put
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
            print(f"⚠️ BS Calc Error: {e}")
            return {'delta': 0, 'gamma': 0, 'theta': 0, 'source': 'Error'}

    def _enrich_greeks(self, ticker, strike, expiry_date_str, opt_type, current_price, iv, context_greeks):
        """
        Ensure Greeks are populated on weekends.
        Strategy: ORATS (Live) -> Tradier (Live/Last) -> Black-Scholes (Est) -> Unavailable
        """
        # 1. Check if ORATS gave us good Greeks (Delta != 0)
        if abs(context_greeks.get('delta', 0)) > 0.001:
            context_greeks['source'] = 'ORATS (Live)'
            return context_greeks
            
        print(f"⚠️ ORATS Greeks are 0. Attempting enrichment for {ticker}...")

        # 2. Try Tradier API (if configured)
        if self.use_tradier:
            try:
                # Tradier format: YYYY-MM-DD
                chain = self.tradier_api.get_option_chain(ticker, expiry_date_str)
                if chain:
                    # Find matching strike
                    for opt in chain:
                        if (abs(opt.get('strike', 0) - strike) < 0.01 and 
                            opt.get('option_type', '').lower() == opt_type.lower()):
                            greeks = opt.get('greeks', {})
                            if greeks and greeks.get('delta'):
                                print("  ✅ Found Greeks via Tradier")
                                return {
                                    'delta': greeks.get('delta'),
                                    'gamma': greeks.get('gamma'),
                                    'theta': greeks.get('theta'),
                                    'iv': context_greeks.get('iv', 0), # Keep original IV logic
                                    'oi': context_greeks.get('oi', 0),
                                    'volume': context_greeks.get('volume', 0),
                                    'source': 'Tradier (Live)'
                                }
            except Exception as e:
                print(f"  ⚠️ Tradier fallback failed: {e}")

        # 3. Try Black-Scholes (Calculation)
        # Needs IV > 0 and Time > 0
        from datetime import datetime
        try:
            exp_dt = datetime.strptime(expiry_date_str, "%Y-%m-%d")
            days_to_exp = (exp_dt - datetime.now()).days
            T = max(1, days_to_exp) / 365.0
            
            # Use 'iv' from ORATS (smvVol usually present even if Greeks aren't)
            # If iv is 0, we can't calc BS.
            sigma = context_greeks.get('iv', 0) / 100.0
            
            if sigma > 0 and current_price > 0:
                bs_greeks = self._calculate_greeks_black_scholes(
                    S=current_price,
                    K=strike,
                    T=T,
                    sigma=sigma,
                    opt_type=opt_type
                )
                if bs_greeks['delta'] != 0:
                    print(f"  ✅ Calculated Greeks via Black-Scholes (IV={sigma:.1%})")
                    # Merge with original (keep IO/Vol)
                    context_greeks.update(bs_greeks)
                    return context_greeks
            else:
                print(f"  ⚠️ Cannot calc BS: IV={sigma:.2f}, Price={current_price}")
        except Exception as e:
            print(f"  ⚠️ BS Setup Error: {e}")

        # 4. Give up
        context_greeks['source'] = 'Unavailable (Market Closed)'
        return context_greeks

    def scan_sector_top_picks(self, sector, min_volume, min_market_cap, limit=15, weeks_out=None, industry=None):
        """
        Run a 'Smart Scan' on a sector.
        1. Query FMP Screener for top candidates.
        2. Run deep LEAP scan OR Weekly scan (based on weeks_out) on them.
        3. [NEW] Run AI Analysis on Top 3 Global Picks.
        4. Return combined opportunities.
        """
        mode_label = "LEAPS" if weeks_out is None else f"WEEKLY (+{weeks_out})"
        ind_label = f" | {industry}" if industry else ""
        print(f"🚀 Starting Sector Scan: {sector}{ind_label} [{mode_label}] [Cap > {min_market_cap}, Vol > {min_volume}]")
        
        # 1. Pre-filter (FMP)
        candidates = []
        try:
             candidates = self.fmp_api.get_stock_screener(
                sector=sector,
                industry=industry,
                min_market_cap=min_market_cap,
                min_volume=min_volume,
                limit=limit 
            )
        except Exception as e:
             print(f"⚠️ FMP Screener API Failed: {e}")
             # Fallback logic omitted for brevity in this block update, assumed handled in full file if needed
             pass

        if not candidates:
            # Quick local cache fallback (simplified for edit)
            cached = self.get_cached_tickers()
            # Handle case where marketCap/volume exists as key but value is None (from partial enrichment)
            matches = [
                t for t in cached 
                if t.get('sector') == sector 
                and (t.get('marketCap') or 0) >= int(min_market_cap or 0)
            ]
            matches.sort(key=lambda x: (x.get('marketCap') or 0), reverse=True)
            candidates = matches[:15]
            
        if not candidates:
            print("❌ No candidates found in sector screener")
            return []
            
        print(f"📋 Found {len(candidates)} candidates. Starting deep scan...")
        
        # [ORATS COVERAGE PRE-FILTER] Skip tickers not in ORATS universe
        tickers = [c['symbol'] for c in candidates]
        if HybridScannerService._orats_universe:
            original_count = len(tickers)
            tickers = [t for t in tickers if self._is_orats_covered(t)]
            skipped = original_count - len(tickers)
            if skipped > 0:
                print(f"⏭️ Skipped {skipped} tickers not in ORATS universe ({len(tickers)} remaining)")
            # Also filter candidates list to stay in sync
            candidates = [c for c in candidates if c['symbol'] in tickers]
        
        # [PHASE 3] Batch Fetching
        batch_data = {}
        if self.use_orats:
            print(f"🚀 Batch Fetching Options for {len(tickers)} tickers (ORATS)...")
            try:
                batch_data = self.batch_manager.fetch_option_chains(tickers)
            except Exception as e:
                print(f"⚠️ Batch Fetch Failed: {e}")

        # 2. Deep Scan
        all_results = []
        for cand in candidates:
            ticker = cand['symbol']
            opts = batch_data.get(ticker)
            
            # Choose Scan Mode
            if weeks_out is not None:
                res = self.scan_weekly_options(ticker, weeks_out=weeks_out, pre_fetched_data=opts)
            else:
                res = self.scan_ticker(ticker, pre_fetched_data=opts) # LEAP
            
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
        print(f"🎯 Filtered down to Top {len(top_100)} Global Opportunities")

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
        print(f"🤖 Running AI Analysis on Top {len(top_3_tickers)} Picks...")
        
        for res in top_3_tickers:
            t = res['ticker']
            strat = "LEAP" if weeks_out is None else "WEEKLY"
            
            # We already have context in 'res', let's re-use it if possible or just call the engine
            # The 'get_ai_analysis' helper re-fetches data which is slow.
            # Let's call reasoning_engine directly using the data we JUST fetched to save time!
            
            # Construct Context from existing result
            context = {
                'current_price': res.get('current_price'),
                'headlines': res.get('sentiment_analysis', {}).get('headlines', []),
                'technicals': {
                    'rsi': f"{res.get('indicators', {}).get('rsi', 0):.1f}",
                    'trend': res.get('indicators', {}).get('trend', 'Neutral'),
                    'atr': f"{res.get('indicators', {}).get('atr', 0):.2f}",
                     'hv_rank': f"{res.get('indicators', {}).get('hv_rank', 0):.1f}"
                },
                'gex': {
                    'call_wall': res.get('gex_data', {}).get('call_wall', 'N/A'),
                    'put_wall': res.get('gex_data', {}).get('put_wall', 'N/A')
                }
            }
            
            try:
                print(f"   > Analyzing {t}...")
                ai_output = self.reasoning_engine.analyze_ticker(t, strat, None, context=context)
                res['ai_analysis'] = ai_output # Attach to result
            except Exception as e:
                print(f"   ⚠️ AI Failed for {t}: {e}")
                res['ai_analysis'] = {'thesis': "AI Analysis Failed", 'risk_assessment': "N/A"}

        return final_results
    
    def _cache_news(self, ticker, articles, sentiment_analysis):
        # ... (Same as before, keep concise in overwrite or rely on import if it was external, but it was inline)
        pass # Simplified for brevity in this overwrite if it wasn't critical logic for *this* step, 
             # BUT WAIT! I should preserve it. 
             # I will copy the implementation from Step 1602.
        
        try:
             self.db.query(NewsCache).filter(NewsCache.ticker == ticker).delete()
             for i, article in enumerate(articles):
                 s = sentiment_analysis['sentiment_breakdown'][i]['sentiment'] if i < len(sentiment_analysis['sentiment_breakdown']) else 0
                 self.db.add(NewsCache(
                     ticker=ticker,
                     headline=article.get('headline'),
                     summary=article.get('summary'),
                     source=article.get('source'),
                     url=article.get('url'),
                     published_date=article.get('published_date'),
                     sentiment_score=s
                 ))
             self.db.commit()
        except:
             self.db.rollback()

    def _save_scan_results(self, ticker, technical_score, sentiment_score, opportunities):
        try:
            avg_score = sum(o['opportunity_score'] for o in opportunities) / len(opportunities) if opportunities else 0
            res = ScanResult(ticker=ticker, technical_score=technical_score, sentiment_score=sentiment_score, opportunity_score=avg_score, profit_potential=opportunities[0]['profit_potential'] if opportunities else 0)
            self.db.add(res)
            self.db.commit()
            
            for opp in opportunities[:10]:
                self.db.add(Opportunity(
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
            self.db.commit()
        except:
            self.db.rollback()

    def get_latest_results(self):
        try:
            results = self.db.query(ScanResult).order_by(ScanResult.scan_date.desc()).limit(100).all()
            return [{'ticker': r.ticker, 'opportunity_score': r.opportunity_score} for r in results]
        except:
            return []

    def scan_weekly_options(self, ticker, weeks_out=0, strategy_tag="WEEKLY", pre_fetched_data=None):
        import math # Ensure math is available
        """
        Perform 'Weekly' or '0DTE' analysis.
        Incorporating Advanced Prop Trading Logic.
        pre_fetched_data: Optional injected option chain (for Batch Mode)
        """
        ticker = self._normalize_ticker(ticker)
        print(f"\n{'='*50}")
        print(f"Scanning {ticker} (WEEKLY + {weeks_out}) [Advanced Mode]...")
        # 0. Date Setup
        today = datetime.now().date()
        target_friday = today + timedelta((3-today.weekday()) % 7) # This Friday
        target_friday += timedelta(weeks=weeks_out)
        target_friday_str = target_friday.strftime('%Y-%m-%d')
        print(f"[TARGET] Expiry: {target_friday_str} (Friday)")
        print(f"{'='*50}")
        
        try:
            # 1. Fetch Price & Technical History (1 Year)
            # Using ORATS Priority -> Yahoo Fallback
            print(f"[1/6] Fetching History & Technicals...")
            price_history = None
            
            # ORATS Primary
            if self.use_orats:
                 try:
                     price_history = self.batch_manager.orats_api.get_history(ticker)
                     if price_history:
                         print(f"   ℹ️  History fetched from ORATS ({len(price_history.get('candles', []))} candles)")
                 except Exception as e:
                     print(f"   ⚠️ ORATS History Error: {e}")

            # (Yahoo History Fallback Removed - Strict Mode)
            


            if not price_history:
                print("❌ Failed to get price history")
                return None

            # Calculate Indicators
            indicators = self.technical_analyzer.get_all_indicators(price_history)
            df = self.technical_analyzer.prepare_dataframe(price_history)
            
            # [FIX] Fetch LIVE Quote to ensure we have the real-time price, not yesterday's close
            # [FIX] Fetch LIVE Quote (ORATS)
            try:
                real_time_price = 0
                if self.use_orats:
                     q = self.batch_manager.orats_api.get_quote(ticker)
                     if q:
                         real_time_price = q.get('price', 0)
                
                
                # (Yahoo Quote Fallback Removed - Strict Mode)

                if real_time_price:
                    print(f"⚡ Live Price Fetched: ${real_time_price:.2f} (Updating History)")
                    df.iloc[-1, df.columns.get_loc('Close')] = real_time_price
            except Exception as e:
                print(f"⚠️ Live Quote Error: {e}, using history close.")

            current_price = df['Close'].iloc[-1]
            current_date = df.index[-1].date()
            print(f"Current Price: ${current_price:.2f}")

            # Advanced Metrics
            atr = self.technical_analyzer.calculate_atr(df)
            hv_rank = self.technical_analyzer.calculate_hv_rank(df)
            
            # Relative Strength vs SPY
            rs_score = 0
            if not hasattr(self, '_spy_history'):
                print("Fetching SPY History for Relative Strength (ORATS)...")
                if self.use_orats:
                     try:
                         # Use ORATS for SPY history
                         self._spy_history = self.batch_manager.orats_api.get_history('SPY')
                     except Exception as e:
                         print(f"⚠️ SPY History Failed: {e}")
                         self._spy_history = None
                
            if self._spy_history:
                df_spy = self.technical_analyzer.prepare_dataframe(self._spy_history)
                rs_score = self.technical_analyzer.calculate_relative_strength(df, df_spy)
                print(f"✓ Relative Strength vs SPY: {rs_score:.2f}%")
            
            technical_score = self.technical_analyzer.calculate_technical_score(indicators)
            print(f"✓ Technical Score: {technical_score:.1f} | ATR: {atr:.2f} | HV Rank: {hv_rank:.1f}")

            # 2. Sentiment Check (FINNHUB)
            print(f"[2/6] Analyzing Sentiment (Finnhub)...")
            sentiment_score = 50 
            sentiment_analysis = {'summary': 'Neutral', 'sentiment_breakdown': []}
            
            try:
                # 1. Try Premium "News Sentiment" endpoint first
                premium_sentiment = self.finnhub_api.get_news_sentiment(ticker.replace('$',''))
                
                if premium_sentiment and premium_sentiment != "FORBIDDEN" and 'sentiment' in premium_sentiment: # Check structure
                    # Finnhub returns score 0.0 - 1.0 (Bearish < 0.5 < Bullish)
                    # We map this to 0-100
                    s_score = premium_sentiment.get('sentiment', {}).get('bullishPercent', 0.5) * 100
                    # Alternatively, use their 'companyNewsScore' (0-1)
                    if 'companyNewsScore' in premium_sentiment:
                         s_score = premium_sentiment['companyNewsScore'] * 100
                         
                    sentiment_score = s_score
                    print(f"✓ Finnhub Premium Score: {sentiment_score:.1f}")
                    sentiment_analysis['summary'] = "Finnhub Institutional Sentiment Score"
                    
                else:
                    # 2. Fallback to Free "Company News" + Local Analysis
                    print("ℹ️ Using Free Tier: Analyzing Headlines...")
                    news = self.finnhub_api.get_company_news(ticker.replace('$',''))
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
                        
                        sentiment_analysis = self.sentiment_analyzer.analyze_articles(news_articles)
                        sentiment_score = self.sentiment_analyzer.calculate_sentiment_score(sentiment_analysis)
                        print(f"✓ Finnhub Headline Analysis Score: {sentiment_score:.1f}")
                    else:
                        print("⚠️ No Finnhub news found.")
                        
            except Exception as e:
                print(f"⚠️ Sentiment Error: {e}")
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
                print(f"🎯 Target Expiry (0DTE - Same Day): {target_friday_str}")
                
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
                print(f"🎯 Target Expiry (This Week): {target_friday_str}")
                
            else:
                # WEEKLY "Next Week" / "2 Weeks Out": Calculate future Fridays
                days_ahead = (4 - today.weekday() + 7) % 7
                target_friday = today + timedelta(days=days_ahead + (weeks_out * 7))
                target_friday_str = target_friday.strftime('%Y-%m-%d')
                print(f"🎯 Target Expiry (+{weeks_out} week(s)): {target_friday_str}")

            earnings_date = None
            has_earnings_risk = False
            # (Yahoo Earnings Check Removed - Strict Mode)

            # 4. Fetch Options & GEX
            print(f"[3/6] Fetching Options Chain...")
            opts = None

            # [PHASE 3] ORATS / BATCH LOGIC
            if pre_fetched_data:
                opts = pre_fetched_data
            elif self.use_orats:
                 try:
                     opts = self.batch_manager.orats_api.get_option_chain(ticker)
                 except: opts = None
            
            # ORATS Post-Processing: Filtering for Target Expiry (Weekly/0DTE)
            # ORATS returns full chain. Schwab returns filtered chain.
            # We must filter opts to ONLY contain target_friday keys to mimic Schwab behavior for GEX/Analysis.
            if opts and (self.use_orats or pre_fetched_data):
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
                    print(f"   ⚠️ Target expiry {target_friday_str} not found in ORATS chain")
                    opts = None

            # (Schwab Fallback Removed - Strict Mode)
            
            if not opts:
                 print("❌ No options found")
                 return None

            # Calculate GEX Walls
            gex_data = self.options_analyzer.calculate_gex_walls(opts)
            if gex_data:
                print(f"✓ Gamma Walls: Call ${gex_data['call_wall']} | Put ${gex_data['put_wall']}")

            # 5. Filter & Analyze Opportunities
            print(f"[4/6] Filtering Opportunities...")
            
            # DEBUG DATA AVAILABILITY
            print(f"DEBUG: Target Friday: {target_friday_str}")
            print(f"DEBUG: Call Keys: {list(opts.get('callExpDateMap', {}).keys())}")
            print(f"DEBUG: Put Keys: {list(opts.get('putExpDateMap', {}).keys())}")
            
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
                            print(f"  SKIPPED {ticker} {strike} {otype}: bid={bid} ask={ask} last={last} mark={mark}")
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
                    if otype == 'Call' and not is_uptrend: continue
                    if otype == 'Put' and is_uptrend: continue

                    # Standard RSI/RS Logic (Skip for Tactical/Scalp)
                    # 2. RSI Check (Avoid Exhaustion)
                    if otype == 'Call' and rsi_val > 70: continue 
                    if otype == 'Put' and rsi_val < 30: continue 

                    # 3. Relative Strength (RS) Check
                    if otype == 'Call' and rs_score < -2.0: continue 
                    if otype == 'Put' and rs_score > 2.0: continue

                # 4. Bid/Ask Spread (Liquidity) - Keep for all
                if ask > 0:
                     spread_pct = (ask - bid) / ask
                     if spread_pct > 0.25 and not is_tactical: 
                         continue # Relax for tactical?

                # 5. Delta (Probability)
                delta = abs(opt.get('delta', 0))
                min_delta = 0.15
                if ticker.startswith('$') or ticker in ['SPX', 'NDX', 'RUT']: min_delta = 0.05
                if delta < min_delta and not is_tactical: 
                    continue # Allow lower delta for lottos?
                
                # 6. Smart Money / Activity
                oi = opt.get('openInterest', 0)
                vol = opt.get('totalVolume', 0)
                
                is_smart_money = (vol > oi and vol > 50) or (vol > 100)
                if (oi < 100) and (vol < 20) and (not is_smart_money):
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
        
            # Use Centralized Ranker with Strategy Logic (WEEKLY/0DTE)
            # This applies the correct weights and profit normalization
            ranked_opps_dicts = self.options_analyzer.rank_opportunities(
                opportunities,
                technical_score,
                sentiment_score,
                skew_score=50, # Default for now in Weekly
                strategy=strategy_tag, # "WEEKLY" or "0DTE"
                current_price=current_price
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
                obj.delta = d.get('delta')
                
                final_opp_objects.append(obj)
                
            opportunities = final_opp_objects[:100]
            
            print(f"✓ Found {len(opportunities)} Valid Opportunities")

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
                        'play_type': getattr(o, 'play_type', 'value')
                    }
                    for o in opportunities
                ],
                'timestamp': datetime.now().isoformat(),
                'data_source': 'ORATS+Finnhub' if self.use_orats else 'Schwab+Finnhub'
            }
            return self._sanitize_for_json(result)

        except Exception as e:
            print(f"❌ Error in advanced weekly scan: {e}")
            import traceback
            traceback.print_exc()
            return None

    def scan_0dte_options(self, ticker):
        """
        Specialized 0DTE Scan (Intraday).
        Focus: Gamma Walls, VWAP (if avail), Momentum.
        RESTRICTED: Only Indices/Major ETFs (SPX, NDX, etc).
        """
        allowed_indices = ['$SPX', '$NDX', '$RUT', '$DJX', 'SPY', 'QQQ', 'IWM', 'SPX', 'NDX', 'RUT', 'DJX']
        normalized = ticker.upper().strip()  # Simple normalization
        
        if normalized not in allowed_indices:
             print(f"⛔ 0DTE Scan BLOCKED for {normalized} (Indices Only)")
             raise ValueError(f"0DTE for Ticker {normalized} Not Supported")

        return self.scan_weekly_options(ticker, weeks_out=0, strategy_tag="0DTE")

    def get_ai_analysis(self, ticker, strategy="LEAP", expiry_date=None, **kwargs):
        """
        Call the AI Reasoning Engine with Rich Context (News, Tech, GEX).
        """
        print(f"🤖 AI Analysis Requested for {ticker} (Strategy: {strategy})...")
        
        # 1. Gather Context (Reuse Scan Logic)
        context = {
            'headlines': [],
            'technicals': {},
            'gex': {}
        }
        
        try:
            # We use scan_weekly_options as a 'Data Fetcher'
            # It's heavy, but gives us everything (Price, Indicators, News, GEX)
            # For 0DTE strategy, we might want scan_0dte_options for tighter GEX, 
            # but weekly is a safe general fetcher.
            scan_result = self.scan_weekly_options(ticker, weeks_out=0)
            
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
                print(f"📊 SIGNALS: RSI={context['technicals']['rsi']}({context['technicals']['rsi_signal']}) | "
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

                # E. Option Greeks (Fix 3: Find specific option if strike+type provided)
                req_strike = kwargs.get('strike')
                req_type = kwargs.get('type')
                if req_strike and req_type:
                    try:
                        strike_f = float(req_strike)
                        opps = scan_result.get('opportunities', [])
                        # Need expiry for Tradier/BS
                        expiry_date_str = scan_result.get('expiry_date') # e.g. "2026-07-17"
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
                                context['option_greeks'] = self._enrich_greeks(
                                    ticker=ticker,
                                    strike=strike_f,
                                    expiry_date_str=expiry_date_str,
                                    opt_type=str(req_type).lower(),
                                    current_price=current_price,
                                    iv=raw_greeks['iv'],
                                    context_greeks=raw_greeks
                                )
                                print(f"  ✓ Found Greeks for {ticker} {req_strike} {req_type}: delta={context['option_greeks']['delta']} [{context['option_greeks'].get('source', 'Original')}]")
                                break
                        else:
                            print(f"  ⚠️ Could not find Greeks for {ticker} {req_strike} {req_type} in scan results")
                    except Exception as e:
                        print(f"  ⚠️ Greeks lookup error: {e}")
                    
        except Exception as e:
            print(f"⚠️ Context gather failed: {e}")
            # Continue without context rather than failing
            
        return self.reasoning_engine.analyze_ticker(ticker, strategy, expiry_date, data=kwargs, context=context)

    def _sanitize_for_json(self, obj):
        """
        Recursively convert numpy types to native Python types for JSON serialization.
        """
        import numpy as np
        from datetime import date, datetime
        
        if isinstance(obj, dict):
            return {k: self._sanitize_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._sanitize_for_json(v) for v in obj]
        elif isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray): 
            return self._sanitize_for_json(obj.tolist())
        elif isinstance(obj, np.bool_):
            return bool(obj)
        else:
            return obj



    def get_sentiment_score(self, ticker):
        """
        Get sentiment score and details for a ticker
        Returns: (score, analysis_dict)
        """
        sentiment_score = 50 
        sentiment_analysis = {'summary': 'Neutral', 'sentiment_breakdown': [], 'weighted_score': 0, 'headlines': []}
        
        try:
            # 1. Try Premium "News Sentiment" endpoint first
            premium_sentiment = self.finnhub_api.get_news_sentiment(ticker.replace('$',''))
            
            if premium_sentiment and premium_sentiment != "FORBIDDEN" and 'sentiment' in premium_sentiment: # Check structure
                # Finnhub returns score 0.0 - 1.0 (Bearish < 0.5 < Bullish)
                # We map this to 0-100
                s_score = premium_sentiment.get('sentiment', {}).get('bullishPercent', 0.5) * 100
                # Alternatively, use their 'companyNewsScore' (0-1)
                # if 'companyNewsScore' in premium_sentiment:
                #      s_score = premium_sentiment['companyNewsScore'] * 100
                     
                sentiment_score = s_score
                # print(f"✓ Finnhub Premium Score: {sentiment_score:.1f}")
                sentiment_analysis['summary'] = "Finnhub Institutional Sentiment Score"
                sentiment_analysis['weighted_score'] = sentiment_score
                # Add dummy breakdown from premium data if available
                sentiment_analysis['article_count'] = 100 # Proxy
                
                # Still try to get headlines for context!
                news = self.finnhub_api.get_company_news(ticker.replace('$',''))
                if news:
                    sentiment_analysis['headlines'] = [n.get('headline') for n in news[:10] if n.get('headline')]
                
            else:
                # 2. Fallback to Free "Company News" + Local Analysis
                # print("ℹ️ Using Free Tier: Analyzing Headlines...")
                news = self.finnhub_api.get_company_news(ticker.replace('$',''))
                if news:
                    news_articles = []
                    headlines_list = []
                    for n in news[:10]: # Analyze top 10
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
                    sentiment_analysis = self.sentiment_analyzer.analyze_articles(news_articles)
                    # RE-ATTACH headlines because analyze_articles might return a new dict or overwrite?
                    # best to ensure it's there
                    sentiment_analysis['headlines'] = headlines_list
                    
                    sentiment_score = self.sentiment_analyzer.calculate_sentiment_score(sentiment_analysis)
                    # print(f"✓ Finnhub Headline Analysis Score: {sentiment_score:.1f}")
                else:
                    # print("⚠️ No Finnhub news found.")
                    pass
                    
        except Exception as e:
            print(f"⚠️ Sentiment Error: {e}")
            
        return sentiment_score, sentiment_analysis

    def get_detailed_analysis(self, ticker):
        """
        Get detailed analysis for a specific ticker (for Analysis Modal)
        """
        try:
            ticker = self._normalize_ticker(ticker)
            print(f"Generating Detailed Analysis for {ticker}...")
            
            # 1. Get History (ORATS Strict)
            history = None
            if self.use_orats:
                 try:
                     history = self.batch_manager.orats_api.get_history(ticker)
                 except Exception as e:
                     print(f"⚠️ ORATS History Failed: {e}")

            if not history:
                print("❌ Strict Mode: No History Data")
                # return None or empty structure? 
                # This function returns a dict usually? No, it returns ...? 
                # Wait, let's check return type. 
                # It returns `detailed_analysis` variable?
                pass
            
            # (Yahoo Fallback Removed)

            current_price = 0
            # Get Current Price
            # Get Current Price (ORATS)
            if self.use_orats:
                q = self.batch_manager.orats_api.get_quote(ticker)
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
                print("   [DEBUG] Preparing DataFrame...")
                df = self.technical_analyzer.prepare_dataframe(history)
                
                # Check explicitly
                if df is not None and not df.empty:
                    print(f"   [DEBUG] DataFrame Ready: {len(df)} rows")
                    
                    # RSI
                    print("   [DEBUG] Calc RSI...")
                    rsi_val, rsi_sig = self.technical_analyzer.calculate_rsi(df)
                    indicators['rsi'] = {'value': rsi_val, 'signal': rsi_sig}
                    
                    # MACD
                    print("   [DEBUG] Calc MACD...")
                    macd_vals, macd_sig = self.technical_analyzer.calculate_macd(df)
                    if macd_vals:
                        indicators['macd'] = {'signal': macd_sig}
                        
                    # BB
                    print("   [DEBUG] Calc BB...")
                    bb_vals, bb_sig = self.technical_analyzer.calculate_bollinger_bands(df)
                    if bb_vals:
                        indicators['bollinger_bands'] = {'signal': bb_sig}
                    
                    # MA
                    print("   [DEBUG] Calc MA...")
                    ma_vals, ma_sig = self.technical_analyzer.calculate_moving_averages(df)
                    if ma_vals:
                        indicators['moving_averages'] = {'signal': ma_sig}
                        
                    # Volume
                    print("   [DEBUG] Calc Volume...")
                    vol_vals, vol_sig = self.technical_analyzer.analyze_volume(df)
                    if vol_vals:
                         indicators['volume'] = {'signal': vol_sig}

                    # Tech Score
                    print("   [DEBUG] Calc Score...")
                    # Fix: Pass indicators dict, not df. Returns scalar, not dict.
                    technical_score = self.technical_analyzer.calculate_technical_score(indicators)
                else:
                    print("   [DEBUG] DF is empty or None")

            # 3. Sentiment
            sentiment_score, sentiment_details = self.get_sentiment_score(ticker)
            
            # 4. Opportunities (Quick Scan)
            scan_res = self.scan_weekly_options(ticker, weeks_out=0) # Reuse standard scan
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
            
            return self._sanitize_for_json(result)

        except Exception as e:
            print(f"❌ Error in get_detailed_analysis: {e}")
            import traceback
            traceback.print_exc()
            return None

    def close(self):
        self.watchlist_service.close()
        self.db.close()
