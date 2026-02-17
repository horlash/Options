
import os
import requests
import time
from datetime import datetime

class FMPAPI:
    # Stable API (v3 deprecated as of Aug 2025)
    STABLE_URL = "https://financialmodelingprep.com/stable"
    
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("FMP_API_KEY")
        self.session = requests.Session()

    def _get_stable(self, endpoint, params=None):
        """Make a request to the FMP stable API."""
        if not self.api_key:
            print("❌ FMP API Key missing")
            return None
            
        if params is None:
            params = {}
        params['apikey'] = self.api_key
        
        url = f"{self.STABLE_URL}/{endpoint}"
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
        Get real-time quote, PE, EPS, Earnings Date.
        Stable endpoint: /stable/quote?symbol=AAPL
        """
        data = self._get_stable("quote", params={"symbol": ticker})
        if data and isinstance(data, list):
            return data[0]
        return None

    def get_rating(self, ticker):
        """
        Get financial rating snapshot (S, A, B, C, D).
        Stable endpoint: /stable/ratings-snapshot?symbol=AAPL
        """
        data = self._get_stable("ratings-snapshot", params={"symbol": ticker})
        if data and isinstance(data, list):
            return data[0]
        return None

    def get_available_tickers(self):
        """
        Get all tradable symbols.
        Stable endpoint: /stable/available-traded-list
        """
        data = self._get_stable("available-traded-list")
        if data:
            return data
        return []

    def get_stock_news(self, ticker, limit=50):
        """
        Get stock news for sentiment analysis.
        Stable endpoint: /stable/stock-news?symbol=AAPL&limit=50
        Note: Finnhub handles news in the main scanner, this is a backup.
        """
        data = self._get_stable("stock-news", params={"symbol": ticker, "limit": limit})
        if data:
            return data
        return []

    def get_stock_screener(self, sector=None, industry=None, min_market_cap=None, min_volume=None, limit=20):
        """
        Run stock screener to find sector candidates.
        Stable endpoint: /stable/company-screener
        """
        params = {
            'limit': limit,
            'exchange': 'NYSE,NASDAQ,AMEX',
            'isEtf': 'false',
        }
        
        if sector:
            params['sector'] = sector
        if industry:
            params['industry'] = industry
        if min_market_cap:
            params['marketCapMoreThan'] = min_market_cap
        if min_volume:
            params['volumeMoreThan'] = min_volume
            
        return self._get_stable("company-screener", params=params)
