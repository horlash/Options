import os
import requests
import logging
import datetime

logger = logging.getLogger(__name__)

class FinnhubAPI:
    BASE_URL = "https://finnhub.io/api/v1"
    
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("FINNHUB_API_KEY")
        self.session = requests.Session()
        
    def is_configured(self):
        return bool(self.api_key)

    def _get(self, endpoint, params=None):
        if not self.api_key:
            return None
            
        if params is None: 
            params = {}
        params['token'] = self.api_key
        
        try:
            resp = self.session.get(f"{self.BASE_URL}/{endpoint}", params=params, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 403:
                print(f"⚠️ Finnhub 403 (Premium Feature Blocked): {endpoint}")
                return "FORBIDDEN"
            else:
                print(f"⚠️ Finnhub Error {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            print(f"❌ Finnhub Request Failed: {e}")
        return None

    def get_news_sentiment(self, ticker):
        """
        Attempt to get Premium Sentiment Score.
        Returns: 
            stats dictionary if available
            None if error
            'FORBIDDEN' if free tier limitations
        """
        return self._get("news-sentiment", {'symbol': ticker})

    def get_company_news(self, ticker):
        """
        Get recent company news (Free Tier Compatible).
        Returns list of articles {headline, summary, url, datetime}
        """
        # Get last 5 days
        today = datetime.date.today()
        start = today - datetime.timedelta(days=5)
        
        params = {
            'symbol': ticker,
            'from': start.strftime('%Y-%m-%d'),
            'to': today.strftime('%Y-%m-%d')
        }
        return self._get("company-news", params)

    def get_basic_financials(self, ticker):
        """
        Get Basic Financials (Free Tier Compatible).
        Returns: Dict with {roe, roi, gross_margin, operating_margin} or None
        """
        data = self._get("stock/metric", {'symbol': ticker, 'metric': 'all'})
        
        if data == "FORBIDDEN":
            return "FORBIDDEN"
            
        if not data or 'metric' not in data:
            return None
            
        metrics = data['metric']
        
        return {
            'roe': metrics.get('roeTTM'),
            'roi': metrics.get('roiTTM'),
            'gross_margin': metrics.get('grossMarginTTM'),
            'operating_margin': metrics.get('operatingMarginTTM')
        }

    def get_earnings_calendar(self, symbol=None, from_date=None, to_date=None):
        """Fetch upcoming earnings dates from Finnhub calendar.

        Verified working on free tier. Returns list of dicts with:
        - date, epsActual, epsEstimate, hour (bmo/amc), quarter,
          revenueActual, revenueEstimate, symbol, year

        Args:
            symbol: Optional ticker filter (e.g. 'AAPL')
            from_date: Start date 'YYYY-MM-DD' (default: today)
            to_date: End date 'YYYY-MM-DD' (default: today + 14 days)

        Returns:
            List of earnings entries, or None on error.
        """
        today = datetime.date.today()
        params = {
            'from': from_date or today.strftime('%Y-%m-%d'),
            'to': to_date or (today + datetime.timedelta(days=14)).strftime('%Y-%m-%d'),
        }
        if symbol:
            params['symbol'] = symbol

        data = self._get('calendar/earnings', params)
        if data == 'FORBIDDEN' or data is None:
            return None

        earnings = data.get('earningsCalendar', [])
        if symbol:
            # Filter to exact symbol match
            earnings = [e for e in earnings if e.get('symbol', '').upper() == symbol.upper()]
        return earnings
