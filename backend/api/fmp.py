"""
F10 FIX: Added proper logging (replacing print statements) and @retry_api
decorator for transient failure resilience, matching Finnhub/ORATS/Tradier pattern.
"""

import os
import logging
import requests
import time
from datetime import datetime
from backend.utils.retry import retry_api

logger = logging.getLogger(__name__)


class FMPAPI:
    # Stable API (v3 deprecated as of Aug 2025)
    STABLE_URL = "https://financialmodelingprep.com/stable"
    
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("FMP_API_KEY")
        self.session = requests.Session()

    def is_configured(self):
        """Check if FMP API key is available. (F10: added for consistency with other APIs)"""
        return bool(self.api_key)

    @retry_api(max_retries=2, base_delay=1.0)
    def _get_stable(self, endpoint, params=None):
        """Make a request to the FMP stable API."""
        if not self.api_key:
            logger.warning("FMP API Key missing")
            return None
            
        if params is None:
            params = {}
        params['apikey'] = self.api_key
        
        url = f"{self.STABLE_URL}/{endpoint}"
        try:
            response = self.session.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and not data:
                    return None  # Empty list
                return data
            elif response.status_code >= 500:
                response.raise_for_status()  # Let retry decorator handle 5xx
            else:
                logger.warning("FMP Error %d: %s", response.status_code, response.text[:100])
        except requests.exceptions.HTTPError:
            raise  # Propagate to retry decorator
        except Exception as e:
            logger.error("FMP Request Failed: %s", e)
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
