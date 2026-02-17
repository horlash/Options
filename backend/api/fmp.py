
import os
import requests
import time
from datetime import datetime

class FMPAPI:
    BASE_URL = "https://financialmodelingprep.com/api/v3"
    
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("FMP_API_KEY")
        self.session = requests.Session()

    def _get(self, endpoint, params=None):
        if not self.api_key:
            print("❌ FMP API Key missing")
            return None
            
        if params is None:
            params = {}
        params['apikey'] = self.api_key
        
        url = f"{self.BASE_URL}/{endpoint}"
        try:
            response = self.session.get(url, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and not data:
                    return None # Empty list
                return data
            else:
                print(f"⚠️ FMP Error {response.status_code}: {response.text[:100]}")
        except Exception as e:
            print(f"⚠️ FMP Request Error: {e}")
        return None

    def get_quote(self, ticker):
        """
        Get real-time quote, PE, EPS, Earnings Date from FMP v3/quote.
        This endpoint is verified to work on Starter/Free plans.
        """
        data = self._get(f"quote/{ticker}")
        if data and isinstance(data, list):
            return data[0]
        return None

    def get_rating(self, ticker):
        """
        Get financial rating snapshot (S, A, B, C, D)
        Verified Endpoint on Starter Plan
        """
        # Note: Ratings Snapshot is on 'stable' not 'v3', so we handle URL manually
        url = f"https://financialmodelingprep.com/stable/ratings-snapshot?symbol={ticker}&apikey={self.api_key}"
        try:
            resp = self.session.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data and isinstance(data, list):
                    return data[0]
        except Exception as e:
             print(f"⚠️ FMP Rating Error: {e}")
        return None

    def get_available_tickers(self):
        """
        Get all tradable symbols.
        Used for autocomplete cache.
        """
        # We assume the user wants all stocks and ETFs
        # v3/available-traded/list
        data = self._get("available-traded/list")
        if data:
            return data
        return []

    def get_stock_news(self, ticker, limit=50):
        """
        Get stock news for sentiment analysis.
        """
        params = {'tickers': ticker, 'limit': limit}
        data = self._get("stock_news", params=params)
        if data:
            return data
        return []

    def get_stock_screener(self, sector=None, industry=None, min_market_cap=None, min_volume=None, limit=20):
        """
        Run stock screener.
        params:
            sector: Technology, Healthcare, etc.
            industry: Software - Infrastructure, etc.
            min_market_cap: Number (e.g. 1000000000)
            min_volume: Number (e.g. 500000)
            limit: Max results
        """
        params = {
            'limit': limit,
            'exchange': 'NYSE,NASDAQ,AMEX', # Filter for major US exchanges
            'isEtf': 'false', # Focus on stocks for sector scan
        }
        
        if sector:
            params['sector'] = sector
        if industry:
            params['industry'] = industry
        if min_market_cap:
            params['marketCapMoreThan'] = min_market_cap
        if min_volume:
            params['volumeMoreThan'] = min_volume
            
        return self._get("stock-screener", params=params)
