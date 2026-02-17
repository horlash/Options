import yfinance as yf
from datetime import datetime, timedelta
import time

class YahooFinanceAPI:
    """Free alternative to TD Ameritrade using Yahoo Finance"""
    
    def __init__(self):
        self.last_request_time = 0
        self.min_request_interval = 0.5  # 500ms between requests to be respectful
        
    def _rate_limit(self):
        """Simple rate limiting"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        
        self.last_request_time = time.time()
    
    def get_quote(self, ticker):
        """Get current quote for a ticker"""
        self._rate_limit()
        
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            return {
                ticker: {
                    'lastPrice': info.get('currentPrice', info.get('regularMarketPrice', 0)),
                    'bidPrice': info.get('bid', 0),
                    'askPrice': info.get('ask', 0),
                    'highPrice': info.get('dayHigh', 0),
                    'lowPrice': info.get('dayLow', 0),
                    'openPrice': info.get('open', 0),
                    'closePrice': info.get('previousClose', 0),
                    'totalVolume': info.get('volume', 0),
                    'mark': info.get('currentPrice', 0)
                }
            }
        except Exception as e:
            print(f"Error getting quote for {ticker}: {str(e)}")
            return None
    
    def get_price_history(self, ticker, period='1y', interval='1d'):
        """
        Get historical price data
        
        Args:
            ticker: Stock ticker
            period: Valid periods: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max
            interval: Valid intervals: 1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,1wk,1mo,3mo
        """
        self._rate_limit()
        
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period=period, interval=interval)
            
            if hist.empty:
                return None
            
            # Convert to format expected by technical indicators
            candles = []
            for index, row in hist.iterrows():
                candles.append({
                    'datetime': int(index.timestamp() * 1000),
                    'open': row['Open'],
                    'high': row['High'],
                    'low': row['Low'],
                    'close': row['Close'],
                    'volume': row['Volume']
                })
            
            return {'candles': candles}
            
        except Exception as e:
            print(f"Error getting price history for {ticker}: {str(e)}")
            return None

    def get_next_earnings_date(self, ticker):
        """
        Get next earnings date for a ticker
        
        Returns:
            datetime.date or None
        """
        self._rate_limit()
        try:
            stock = yf.Ticker(ticker)
            cal = stock.calendar
            
            # yfinance returns a dict with 'Earnings Date' list
            if isinstance(cal, dict):
                dates = cal.get('Earnings Date')
                if dates and len(dates) > 0:
                    # Filter for future dates only
                    today = datetime.now().date()
                    future_dates = []
                    
                    for d in dates:
                         # Handle if d is datetime or date
                        check_date = d.date() if isinstance(d, datetime) else d
                        if check_date >= today:
                            future_dates.append(check_date)
                    
                    if future_dates:
                        # Return the earliest future date
                        return sorted(future_dates)[0]
            
            return None
        except Exception as e:
            print(f"Error getting earnings date for {ticker}: {str(e)}")
            return None

        """
        Get options chain data from Yahoo Finance
        """
        self._rate_limit()
        
        try:
            stock = yf.Ticker(ticker)
            
            # Get all expiration dates
            expirations = stock.options
            
            if not expirations:
                print(f"No options available for {ticker}")
                return None
            
            # Filter for dates 8+ months out (240 days)
            min_date = datetime.now() + timedelta(days=240)
            leap_expirations = [
                exp for exp in expirations 
                if datetime.strptime(exp, '%Y-%m-%d') >= min_date
            ]
            
            if not leap_expirations:
                print(f"No LEAP options found for {ticker}")
                return None
            
            # Build options chain in TD Ameritrade format
            call_map = {}
            put_map = {}
            
            for exp_date in leap_expirations[:10]:  # Limit to first 10 expirations
                try:
                    opt = stock.option_chain(exp_date)
                    
                    # Process calls
                    calls = opt.calls
                    if not calls.empty:
                        exp_key = f"{exp_date}:0"
                        call_map[exp_key] = {}
                        
                        for _, row in calls.iterrows():
                            strike = str(row['strike'])
                            call_map[exp_key][strike] = [{
                                'bid': row['bid'],
                                'ask': row['ask'],
                                'last': row['lastPrice'],
                                'mark': (row['bid'] + row['ask']) / 2,
                                'totalVolume': row['volume'],
                                'openInterest': row['openInterest'],
                                'volatility': row['impliedVolatility'],
                                'delta': 0,  # Yahoo doesn't provide Greeks
                                'gamma': 0,
                                'theta': 0,
                                'vega': 0,
                                'strikePrice': row['strike'],
                                'expirationDate': exp_date
                            }]
                    
                    # Process puts
                    puts = opt.puts
                    if not puts.empty:
                        exp_key = f"{exp_date}:0"
                        put_map[exp_key] = {}
                        
                        for _, row in puts.iterrows():
                            strike = str(row['strike'])
                            put_map[exp_key][strike] = [{
                                'bid': row['bid'],
                                'ask': row['ask'],
                                'last': row['lastPrice'],
                                'mark': (row['bid'] + row['ask']) / 2,
                                'totalVolume': row['volume'],
                                'openInterest': row['openInterest'],
                                'volatility': row['impliedVolatility'],
                                'delta': 0,
                                'gamma': 0,
                                'theta': 0,
                                'vega': 0,
                                'strikePrice': row['strike'],
                                'expirationDate': exp_date
                            }]
                
                except Exception as e:
                    print(f"Error processing expiration {exp_date}: {str(e)}")
                    continue
            
            return {
                'callExpDateMap': call_map,
                'putExpDateMap': put_map,
                'symbol': ticker
            }
            
        except Exception as e:
            print(f"Error getting options chain for {ticker}: {str(e)}")
            return None
    def get_fundamentals(self, ticker):
        """
        Get fundamental data for 'Transcription Strategy'
        - Analyst Ratings, EPS Growth, Institutional Ownership
        """
        self._rate_limit()
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            return {
                'analyst_rating': info.get('recommendationKey', 'none').replace('_', ' ').title(), # e.g. "Strong Buy"
                'target_price': info.get('targetMeanPrice'),
                'trailing_eps': info.get('trailingEps'),
                'forward_eps': info.get('forwardEps'),
                'pe_ratio': info.get('trailingPE'),
                'forward_pe': info.get('forwardPE'),
                'institutional_ownership': info.get('heldPercentInstitutions'), # 0.80 = 80%
                'sector': info.get('sector'),
                'industry': info.get('industry'),
                'beta': info.get('beta'),
                'return_on_equity': info.get('returnOnEquity'),  # For Moat Check
                'gross_margins': info.get('grossMargins'),        # For Moat Check
                'profit_margins': info.get('profitMargins')       # For Banks (Net Margin)
            }
        except Exception as e:
            print(f"⚠️ Yahoo Fundamentals Error for {ticker}: {e}")
            return None
