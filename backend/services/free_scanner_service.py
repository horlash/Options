from datetime import datetime
from backend.api.yahoo_finance import YahooFinanceAPI
from backend.api.free_news import FreeNewsAPIs
from backend.analysis.technical_indicators import TechnicalIndicators
from backend.analysis.sentiment_analyzer import SentimentAnalyzer
from backend.analysis.options_analyzer import OptionsAnalyzer
from backend.services.watchlist_service import WatchlistService
from backend.database.models import ScanResult, Opportunity, NewsCache, SessionLocal

class FreeScannerService:
    """Scanner service using only free data sources"""
    
    def __init__(self):
        self.market_api = YahooFinanceAPI()  # Free Yahoo Finance
        self.news_api = FreeNewsAPIs()  # Free news sources
        self.technical_analyzer = TechnicalIndicators()
        self.sentiment_analyzer = SentimentAnalyzer()
        self.options_analyzer = OptionsAnalyzer()
        self.watchlist_service = WatchlistService()
        self.db = SessionLocal()
        
    def scan_ticker(self, ticker):
        """
        Perform complete analysis on a single ticker using free data
        """
        print(f"\n{'='*50}")
        print(f"Scanning {ticker}...")
        print(f"{'='*50}")
        
        try:
            # 1. Get current price
            print(f"[1/5] Fetching current price...")
            quote = self.market_api.get_quote(ticker)
            if not quote or ticker not in quote:
                print(f"❌ Failed to get quote for {ticker}")
                return None
            
            current_price = quote[ticker].get('lastPrice', 0)
            print(f"✓ Current price: ${current_price:.2f}")
            
            # 2. Get price history for technical analysis
            print(f"[2/5] Analyzing technical indicators...")
            price_history = self.market_api.get_price_history(ticker)
            indicators = self.technical_analyzer.get_all_indicators(price_history)
            
            if not indicators:
                print(f"❌ Failed to calculate technical indicators")
                return None
            
            technical_score = self.technical_analyzer.calculate_technical_score(indicators)
            print(f"✓ Technical score: {technical_score:.1f}/100")
            
            # 3. Get news and analyze sentiment
            print(f"[3/5] Analyzing news sentiment...")
            news_articles = self.news_api.get_all_news(ticker)
            sentiment_analysis = self.sentiment_analyzer.analyze_articles(news_articles)
            sentiment_score = self.sentiment_analyzer.calculate_sentiment_score(sentiment_analysis)
            
            print(f"✓ Sentiment score: {sentiment_score:.1f}/100 ({sentiment_analysis['article_count']} articles)")
            
            # Cache news articles
            self._cache_news(ticker, news_articles, sentiment_analysis)
            
            # 4. Get options chain
            print(f"[4/5] Fetching options chain...")
            options_data = self.market_api.get_options_chain(ticker)
            
            if not options_data:
                print(f"❌ No options chain available for {ticker}")
                return {
                    'ticker': ticker,
                    'current_price': current_price,
                    'technical_score': technical_score,
                    'sentiment_score': sentiment_score,
                    'indicators': indicators,
                    'sentiment_analysis': sentiment_analysis,
                    'opportunities': []
                }
            
            # 5. Analyze options and find LEAP opportunities
            print(f"[5/5] Identifying LEAP opportunities...")
            opportunities = self.options_analyzer.parse_options_chain(options_data, current_price)
            
            if not opportunities:
                print(f"⚠ No LEAP opportunities found matching criteria")
                return {
                    'ticker': ticker,
                    'current_price': current_price,
                    'technical_score': technical_score,
                    'sentiment_score': sentiment_score,
                    'indicators': indicators,
                    'sentiment_analysis': sentiment_analysis,
                    'opportunities': []
                }
            
            # Rank opportunities
            ranked_opportunities = self.options_analyzer.rank_opportunities(
                opportunities,
                technical_score,
                sentiment_score
            )
            
            print(f"✓ Found {len(ranked_opportunities)} LEAP opportunities")
            
            # Save scan results
            self._save_scan_results(
                ticker,
                technical_score,
                sentiment_score,
                ranked_opportunities
            )
            
            return {
                'ticker': ticker,
                'current_price': current_price,
                'technical_score': technical_score,
                'sentiment_score': sentiment_score,
                'indicators': indicators,
                'sentiment_analysis': sentiment_analysis,
                'opportunities': ranked_opportunities
            }
            
        except Exception as e:
            print(f"❌ Error scanning {ticker}: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def scan_watchlist(self):
        """Scan all tickers in watchlist"""
        watchlist = self.watchlist_service.get_watchlist()
        
        if not watchlist:
            print("⚠ Watchlist is empty")
            return []
        
        print(f"\n🔍 Scanning {len(watchlist)} tickers from watchlist...")
        print(f"{'='*50}\n")
        
        results = []
        
        for item in watchlist:
            ticker = item['ticker']
            result = self.scan_ticker(ticker)
            
            if result:
                results.append(result)
        
        # Sort results by best opportunities
        results.sort(
            key=lambda x: x['opportunities'][0]['opportunity_score'] if x['opportunities'] else 0,
            reverse=True
        )
        
        print(f"\n{'='*50}")
        print(f"✅ Scan complete! Analyzed {len(results)} tickers")
        print(f"{'='*50}\n")
        
        return results
    
    def _cache_news(self, ticker, articles, sentiment_analysis):
        """Cache news articles in database"""
        try:
            # Clear old cache for this ticker
            self.db.query(NewsCache).filter(
                NewsCache.ticker == ticker
            ).delete()
            
            # Add new articles
            for i, article in enumerate(articles):
                if i < len(sentiment_analysis['sentiment_breakdown']):
                    sentiment = sentiment_analysis['sentiment_breakdown'][i]['sentiment']
                else:
                    sentiment = 0
                
                news_cache = NewsCache(
                    ticker=ticker,
                    headline=article.get('headline'),
                    summary=article.get('summary'),
                    source=article.get('source'),
                    url=article.get('url'),
                    published_date=article.get('published_date'),
                    sentiment_score=sentiment
                )
                
                self.db.add(news_cache)
            
            self.db.commit()
            
        except Exception as e:
            print(f"Error caching news: {str(e)}")
            self.db.rollback()
    
    def _save_scan_results(self, ticker, technical_score, sentiment_score, opportunities):
        """Save scan results to database"""
        try:
            # Calculate average opportunity score
            avg_opp_score = sum(o['opportunity_score'] for o in opportunities) / len(opportunities) if opportunities else 0
            
            # Save scan result
            scan_result = ScanResult(
                ticker=ticker,
                technical_score=technical_score,
                sentiment_score=sentiment_score,
                opportunity_score=avg_opp_score,
                profit_potential=opportunities[0]['profit_potential'] if opportunities else 0
            )
            
            self.db.add(scan_result)
            self.db.commit()
            
            scan_id = scan_result.id
            
            # Save top opportunities (limit to top 10)
            for opp in opportunities[:10]:
                opportunity = Opportunity(
                    scan_result_id=scan_id,
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
                    gamma=opp.get('gamma'),
                    theta=opp.get('theta'),
                    vega=opp.get('vega'),
                    opportunity_score=opp['opportunity_score']
                )
                
                self.db.add(opportunity)
            
            self.db.commit()
            
        except Exception as e:
            print(f"Error saving scan results: {str(e)}")
            self.db.rollback()
    
    def get_latest_results(self):
        """Get latest scan results from database"""
        try:
            results = self.db.query(ScanResult).order_by(
                ScanResult.scan_date.desc()
            ).limit(100).all()
            
            return [
                {
                    'ticker': r.ticker,
                    'scan_date': r.scan_date.isoformat(),
                    'technical_score': r.technical_score,
                    'sentiment_score': r.sentiment_score,
                    'opportunity_score': r.opportunity_score,
                    'profit_potential': r.profit_potential
                }
                for r in results
            ]
            
        except Exception as e:
            print(f"Error getting latest results: {str(e)}")
            return []
    
    def close(self):
        """Close all connections"""
        self.watchlist_service.close()
        self.db.close()
