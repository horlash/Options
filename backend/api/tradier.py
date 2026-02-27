import requests
import time
from datetime import datetime, timedelta
from backend.config import Config
from backend.utils.retry import retry_api

class TradierAPI:
    """Tradier API for options chains with Greeks"""
    
    def __init__(self):
        self.api_key = Config.TRADIER_API_KEY if hasattr(Config, 'TRADIER_API_KEY') else None
        self.base_url = "https://api.tradier.com/v1"
        # Use sandbox for testing without account
        self.sandbox_url = "https://sandbox.tradier.com/v1"
        self.use_sandbox = Config.TRADIER_USE_SANDBOX if hasattr(Config, 'TRADIER_USE_SANDBOX') else False
        
        self.last_request_time = 0
        self.min_request_interval = 1.0  # 60 requests/minute = 1 per second
        
    def _rate_limit(self):
        """Rate limiting - 60 requests per minute"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        
        self.last_request_time = time.time()
    
    def _get_headers(self):
        """Get request headers with API key"""
        if not self.api_key:
            return None
        
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Accept': 'application/json'
        }
    
    def _get_base_url(self):
        """Get base URL (sandbox or production)"""
        return self.sandbox_url if self.use_sandbox else self.base_url
    
    def is_configured(self):
        """Check if Tradier API is configured"""
        return self.api_key is not None
    
    @retry_api(max_retries=2, base_delay=1.0)
    def get_quote(self, ticker):
        """Get real-time quote"""
        if not self.is_configured():
            return None
        
        self._rate_limit()
        
        try:
            url = f"{self._get_base_url()}/markets/quotes"
            params = {'symbols': ticker}
            
            response = requests.get(url, headers=self._get_headers(), params=params)
            
            if response.status_code == 200:
                data = response.json()
                quotes = data.get('quotes', {}).get('quote', {})
                
                if isinstance(quotes, list):
                    quotes = quotes[0] if quotes else {}
                
                return {
                    ticker: {
                        'lastPrice': quotes.get('last', 0),
                        'bidPrice': quotes.get('bid', 0),
                        'askPrice': quotes.get('ask', 0),
                        'highPrice': quotes.get('high', 0),
                        'lowPrice': quotes.get('low', 0),
                        'openPrice': quotes.get('open', 0),
                        'closePrice': quotes.get('prevclose', 0),
                        'totalVolume': quotes.get('volume', 0),
                        'mark': (quotes.get('bid', 0) + quotes.get('ask', 0)) / 2
                    }
                }
            else:
                print(f"Tradier quote error: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Error getting Tradier quote: {str(e)}")
            return None
    
    @retry_api(max_retries=2, base_delay=1.0)
    def get_expirations(self, ticker):
        """Get available expiration dates for a ticker"""
        if not self.is_configured():
            return None
        
        self._rate_limit()
        
        try:
            url = f"{self._get_base_url()}/markets/options/expirations"
            params = {'symbol': ticker}
            
            response = requests.get(url, headers=self._get_headers(), params=params)
            
            if response.status_code == 200:
                data = response.json()
                expirations = data.get('expirations', {}).get('date', [])
                return expirations if isinstance(expirations, list) else [expirations]
            else:
                print(f"Tradier expirations error: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Error getting Tradier expirations: {str(e)}")
            return None
    
    @retry_api(max_retries=2, base_delay=1.0)
    def get_options_chain(self, ticker, expiration, greeks=True):
        """
        Get options chain for a specific expiration with Greeks
        
        Args:
            ticker: Stock symbol
            expiration: Expiration date (YYYY-MM-DD)
            greeks: Include Greeks calculation (default True)
        
        Returns:
            Options chain data
        """
        if not self.is_configured():
            return None
        
        self._rate_limit()
        
        try:
            url = f"{self._get_base_url()}/markets/options/chains"
            params = {
                'symbol': ticker,
                'expiration': expiration,
                'greeks': 'true' if greeks else 'false'
            }
            
            response = requests.get(url, headers=self._get_headers(), params=params)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('options', {}).get('option', [])
            else:
                print(f"Tradier options chain error: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Error getting Tradier options chain: {str(e)}")
            return None
    
    @retry_api(max_retries=2, base_delay=1.0)
    def get_leap_options_chain(self, ticker, min_days=240):
        """
        Get LEAP options chains (8+ months out) with Greeks
        
        Args:
            ticker: Stock symbol
            min_days: Minimum days to expiration (default 240 = 8 months)
        
        Returns:
            Formatted options chain data compatible with scanner
        """
        if not self.is_configured():
            return None
        
        try:
            # Get all expirations
            expirations = self.get_expirations(ticker)
            
            if not expirations:
                print(f"No expirations found for {ticker}")
                return None
            
            # Filter for LEAP expirations (8+ months out)
            min_date = datetime.now() + timedelta(days=min_days)
            leap_expirations = [
                exp for exp in expirations
                if datetime.strptime(exp, '%Y-%m-%d') >= min_date
            ]
            
            if not leap_expirations:
                print(f"No LEAP expirations found for {ticker}")
                return None
            
            # Build options chain
            call_map = {}
            put_map = {}
            
            # Limit to first 10 expirations to avoid rate limits
            for exp_date in leap_expirations[:10]:
                options = self.get_options_chain(ticker, exp_date, greeks=True)
                
                if not options:
                    continue
                
                exp_key = f"{exp_date}:0"
                
                for option in options:
                    option_type = option.get('option_type')
                    strike = str(option.get('strike'))
                    
                    # Extract Greeks if available
                    greeks_data = option.get('greeks', {})
                    
                    option_data = {
                        'bid': option.get('bid', 0),
                        'ask': option.get('ask', 0),
                        'last': option.get('last', 0),
                        'mark': (option.get('bid', 0) + option.get('ask', 0)) / 2,
                        'totalVolume': option.get('volume', 0),
                        'openInterest': option.get('open_interest', 0),
                        'volatility': greeks_data.get('mid_iv', 0) if greeks_data else 0,
                        'delta': greeks_data.get('delta', 0) if greeks_data else 0,
                        'gamma': greeks_data.get('gamma', 0) if greeks_data else 0,
                        'theta': greeks_data.get('theta', 0) if greeks_data else 0,
                        'vega': greeks_data.get('vega', 0) if greeks_data else 0,
                        'rho': greeks_data.get('rho', 0) if greeks_data else 0,
                        'strikePrice': option.get('strike'),
                        'expirationDate': exp_date
                    }
                    
                    if option_type == 'call':
                        if exp_key not in call_map:
                            call_map[exp_key] = {}
                        call_map[exp_key][strike] = [option_data]
                    elif option_type == 'put':
                        if exp_key not in put_map:
                            put_map[exp_key] = {}
                        put_map[exp_key][strike] = [option_data]
            
            return {
                'callExpDateMap': call_map,
                'putExpDateMap': put_map,
                'symbol': ticker
            }
            
        except Exception as e:
            print(f"Error getting LEAP options chain: {str(e)}")
            return None
