"""
Ticker Lookup Utility

Loads tickers.json once at import time and provides fast O(1) lookups
for company name, sector, and industry. Used by reasoning_engine.py 
and free_news.py to avoid hardcoded ticker dictionaries.

Usage:
    from backend.utils.ticker_lookup import TickerLookup
    
    lookup = TickerLookup()
    lookup.get_company_name('MA')   # -> 'Mastercard Inc'
    lookup.get_sector('MA')         # -> 'Financial Services'
    lookup.get_industry('MA')       # -> 'Credit Services'
"""

import json
import os
from pathlib import Path


class TickerLookup:
    """Singleton-style ticker lookup from tickers.json"""
    
    _instance = None
    _data = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance
    
    def _load(self):
        """Load tickers.json into a fast lookup dict."""
        data_file = Path(__file__).parent.parent / 'data' / 'tickers.json'
        
        self._data = {}
        
        if not data_file.exists():
            print(f"⚠️ TickerLookup: {data_file} not found")
            return
            
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            
            tickers = raw.get('tickers', [])
            
            for t in tickers:
                symbol = t.get('symbol', '').upper()
                if symbol:
                    self._data[symbol] = {
                        'name': t.get('name', ''),
                        'sector': t.get('sector', ''),
                        'industry': t.get('industry', ''),
                    }
            
            print(f"✓ TickerLookup loaded: {len(self._data)} tickers")
            
        except Exception as e:
            print(f"⚠️ TickerLookup load error: {e}")
    
    def get_company_name(self, ticker):
        """Get company name for a ticker. Returns ticker itself if not found."""
        info = self._data.get(ticker.upper(), {})
        return info.get('name', '') or ticker
    
    def get_sector(self, ticker):
        """Get sector for a ticker. Returns empty string if not found."""
        info = self._data.get(ticker.upper(), {})
        return info.get('sector', '')
    
    def get_industry(self, ticker):
        """Get industry for a ticker. Returns empty string if not found."""
        info = self._data.get(ticker.upper(), {})
        return info.get('industry', '')
    
    def get_all(self, ticker):
        """Get all info (name, sector, industry) for a ticker."""
        return self._data.get(ticker.upper(), {
            'name': ticker,
            'sector': '',
            'industry': ''
        })
    
    def is_known(self, ticker):
        """Check if ticker exists in the lookup."""
        return ticker.upper() in self._data
