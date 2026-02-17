import time
from datetime import datetime, timedelta
from tda import auth, client
from tda.client import Client
import json
from backend.config import Config

class TDAmeritradeAPI:
    def __init__(self):
        self.api_key = Config.TD_AMERITRADE_API_KEY
        self.redirect_uri = Config.TD_AMERITRADE_REDIRECT_URI
        self.token_path = Config.TD_AMERITRADE_TOKEN_PATH
        self.client = None
        self.last_request_time = 0
        self.request_count = 0
        self.rate_limit = Config.TD_RATE_LIMIT
        
    def authenticate(self):
        """Authenticate with TD Ameritrade API using OAuth 2.0"""
        try:
            self.client = auth.client_from_token_file(
                self.token_path,
                self.api_key
            )
        except FileNotFoundError:
            # First time authentication - requires manual login
            from selenium import webdriver
            with webdriver.Chrome() as driver:
                self.client = auth.client_from_login_flow(
                    driver,
                    self.api_key,
                    self.redirect_uri,
                    self.token_path
                )
        return self.client is not None
    
    def _rate_limit(self):
        """Implement rate limiting - 120 requests per minute"""
        current_time = time.time()
        
        # Reset counter every minute
        if current_time - self.last_request_time > 60:
            self.request_count = 0
            self.last_request_time = current_time
        
        # Wait if we've hit the rate limit
        if self.request_count >= self.rate_limit:
            sleep_time = 60 - (current_time - self.last_request_time)
            if sleep_time > 0:
                time.sleep(sleep_time)
            self.request_count = 0
            self.last_request_time = time.time()
        
        self.request_count += 1
    
    def get_options_chain(self, ticker, contract_type='ALL', from_date=None, to_date=None):
        """
        Get options chain for a ticker
        
        Args:
            ticker: Stock ticker symbol
            contract_type: 'CALL', 'PUT', or 'ALL'
            from_date: Filter options expiring after this date
            to_date: Filter options expiring before this date
        
        Returns:
            Options chain data
        """
        if not self.client:
            self.authenticate()
        
        self._rate_limit()
        
        try:
            # Set default date range for LEAP options (8+ months out)
            if not from_date:
                from_date = datetime.now() + timedelta(days=Config.MIN_LEAP_DAYS)
            if not to_date:
                to_date = datetime.now() + timedelta(days=730)  # 2 years out
            
            response = self.client.get_option_chain(
                ticker,
                contract_type=Client.Options.ContractType(contract_type),
                from_date=from_date,
                to_date=to_date,
                include_quotes=True
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Error fetching options chain: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Exception in get_options_chain: {str(e)}")
            return None
    
    def get_price_history(self, ticker, period_type='year', period=1, frequency_type='daily', frequency=1):
        """
        Get historical price data for technical analysis
        
        Args:
            ticker: Stock ticker symbol
            period_type: 'day', 'month', 'year', 'ytd'
            period: Number of periods
            frequency_type: 'minute', 'daily', 'weekly', 'monthly'
            frequency: Frequency interval
        
        Returns:
            Historical price data
        """
        if not self.client:
            self.authenticate()
        
        self._rate_limit()
        
        try:
            response = self.client.get_price_history(
                ticker,
                period_type=Client.PriceHistory.PeriodType(period_type.upper()),
                period=Client.PriceHistory.Period(period),
                frequency_type=Client.PriceHistory.FrequencyType(frequency_type.upper()),
                frequency=Client.PriceHistory.Frequency(frequency)
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Error fetching price history: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Exception in get_price_history: {str(e)}")
            return None
    
    def get_quote(self, ticker):
        """Get real-time quote for a ticker"""
        if not self.client:
            self.authenticate()
        
        self._rate_limit()
        
        try:
            response = self.client.get_quote(ticker)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Error fetching quote: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Exception in get_quote: {str(e)}")
            return None
