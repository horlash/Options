
import schwab
import os
from datetime import datetime, timedelta, timezone
from schwab.auth import client_from_token_file
from backend.config import Config
import time

class SchwabAPI:
    """Charles Schwab API implementation for quotes and options chains"""

    def __init__(self):
        self.api_key = Config.SCHWAB_API_KEY
        self.app_secret = Config.SCHWAB_API_SECRET
        self.token_path = Config.SCHWAB_TOKEN_PATH
        self.client = None
        self._initialize_client()

    def _initialize_client(self):
        """Initialize the Schwab client from token file"""
        print(f"DEBUG: Initializing SchwabAPI... Token Path: {self.token_path}")
        if not self.api_key or not self.app_secret:
            print("DEBUG: API Key/Secret missing")
            return

        if not os.path.exists(self.token_path):
            print(f"DEBUG: Token file not found at {self.token_path}")
            return

        try:
            self.client = client_from_token_file(
                self.token_path, 
                self.api_key, 
                self.app_secret,
                enforce_enums=False
            )
            print("DEBUG: Schwab Client created successfully object")
        except Exception as e:
            print(f"Error initializing Schwab client: {e}")
            self.client = None

    def is_configured(self):
        """Check if Schwab API is configured and accessible"""
        return self.client is not None

    def get_quote(self, ticker):
        """Get real-time quote for a single ticker"""
        if not self.is_configured():
            return None

        try:
            # Schwab allows getting quotes for list of symbols
            # Using direct method from client
            resp = self.client.get_quotes([ticker])
            if resp.status_code != 200:
                print(f"Schwab quote error: {resp.status_code}")
                return None

            data = resp.json()
            print(f"DEBUG RAW QUOTE DATA for {ticker}: {data}")
            if ticker not in data:
                print(f"DEBUG: {ticker} not in data keys: {list(data.keys())}")
                return None

            q = data[ticker]['quote']
            ref = data[ticker]['reference']
            
            # Normalize to match Tradier/Yahoo format
            return {
                ticker: {
                    'lastPrice': q.get('lastPrice', 0),
                    'bidPrice': q.get('bidPrice', 0),
                    'askPrice': q.get('askPrice', 0),
                    'highPrice': q.get('highPrice', 0),
                    'lowPrice': q.get('lowPrice', 0),
                    'openPrice': q.get('openPrice', 0),
                    'closePrice': q.get('closePrice', 0),
                    'totalVolume': q.get('totalVolume', 0),
                    'mark': (q.get('bidPrice', 0) + q.get('askPrice', 0)) / 2 if q.get('bidPrice') and q.get('askPrice') else q.get('lastPrice', 0)
                }
            }
        except Exception as e:
            print(f"Error getting Schwab quote: {e}")
            return None

    def get_leap_options_chain(self, ticker, min_days=240, days_forward=700, from_date=None, to_date=None):
        """
        Get options chains.
        min_days: Start fetching options expiring after this many days.
        days_forward: Fetch options for this many days after the start date.
        from_date/to_date: specific date objects (override min_days/days_forward)
        """
        if not self.is_configured():
            return None

        try:
            # Calculate date range if not explicitly provided
            if not from_date:
                from_date = datetime.now() + timedelta(days=min_days)
            if not to_date:
                # If from_date was passed but not to_date, base calc on from_date
                calc_base = from_date if isinstance(from_date, datetime) else datetime.combine(from_date, datetime.min.time())
                to_date = calc_base + timedelta(days=days_forward)

            # Ensure we are passing date objects, not datetime
            if isinstance(from_date, datetime):
                from_date = from_date.date()
            if isinstance(to_date, datetime):
                to_date = to_date.date()

            # Schwab option chain parameters
            # We want both CALL and PUT, and explicit date range
            params = {
                # 'symbol': ticker, # Removed to avoid duplicate arg error
                'from_date': from_date,
                'to_date': to_date,
            }
            
            print(f"DEBUG: calling get_option_chain for {ticker} with params: {params}")
            print(f"DEBUG: Types - from_date: {type(params['from_date'])}, to_date: {type(params['to_date'])}")
            
            print(f"DEBUG: calling get_option_chain with {params}")
            
            
            # Using direct method from client
            resp = self.client.get_option_chain(
                ticker, 
                **params
            )
            
            if resp.status_code != 200:
                print(f"Schwab option chain error: {resp.status_code}")
                print(f"Error Body: {resp.text}")
                return None

            data = resp.json()
            
            if data.get('status') != 'SUCCESS':
                return None

            # Parse response into our expected format
            call_map = {}
            put_map = {}
            
            # Data structure from Schwab:
            # { 'callExpDateMap': { 'date:days': { 'strike': [option_info] } }, ... }
            # Actually Schwab response structure is slightly different or similar depending on endpoint version.
            # Assuming 'callExpDateMap' and 'putExpDateMap' keys exist as per TD/Schwab standard.

            raw_calls = data.get('callExpDateMap', {})
            raw_puts = data.get('putExpDateMap', {})

            for date_key, strikes in raw_calls.items():
                # date_key format usually "yyyy-MM-dd:days_to_expiry"
                exp_date_str = date_key.split(':')[0]
                
                exp_map_key = f"{exp_date_str}:0" # Format expected by our parser
                
                if exp_map_key not in call_map:
                    call_map[exp_map_key] = {}

                for strike, options in strikes.items():
                    # options is a list, usually len 1
                    for opt in options:
                        option_data = self._normalize_option(opt, exp_date_str)
                        if option_data:
                            if strike not in call_map[exp_map_key]:
                                call_map[exp_map_key][strike] = []
                            call_map[exp_map_key][strike].append(option_data)

            for date_key, strikes in raw_puts.items():
                exp_date_str = date_key.split(':')[0]
                exp_map_key = f"{exp_date_str}:0"

                if exp_map_key not in put_map:
                    put_map[exp_map_key] = {}

                for strike, options in strikes.items():
                    for opt in options:
                        option_data = self._normalize_option(opt, exp_date_str)
                        if option_data:
                            if strike not in put_map[exp_map_key]:
                                put_map[exp_map_key][strike] = []
                            put_map[exp_map_key][strike].append(option_data)

            return {
                'callExpDateMap': call_map,
                'putExpDateMap': put_map,
                'symbol': ticker
            }

        except Exception as e:
            print(f"Error getting Schwab options chain: {e}")
            return None

    def get_price_history(self, ticker, period_type='year', period=1, frequency_type='daily', frequency=1):
        """
        Get historical price data (OHLCV) for technical analysis.
        Returns: {'candles': [{'datetime': ms, 'open': ...}]}
        """
        if not self.is_configured():
            return None

        try:
            # Fetch historical data using args
            resp = self.client.get_price_history(
                ticker,
                period_type=period_type,
                period=period,
                frequency_type=frequency_type,
                frequency=frequency
            )
            
            if resp.status_code != 200:
                print(f"Schwab history error: {resp.status_code}")
                return None
                
            data = resp.json()
            if not data or 'candles' not in data:
                return None
                
            # Normalize candles
            normalized_candles = []
            for c in data['candles']:
                # Schwab returns 'datetime' in ms already usually
                normalized_candles.append({
                    'datetime': c.get('datetime'),
                    'open': c.get('open'),
                    'high': c.get('high'),
                    'low': c.get('low'),
                    'close': c.get('close'),
                    'volume': c.get('volume')
                })
                
            return {'candles': normalized_candles}

        except Exception as e:
            print(f"Error getting Schwab history for {ticker}: {e}")
            return None

    def search_instruments(self, query):
        """
        Search for instruments/tickers by symbol.
        
        Args:
            query: Search term (ticker symbol)
            
        Returns:
            List of matching instruments with symbol, name, exchange data
        """
        if not self.is_configured():
            return []
        
        try:
            # Using get_instruments from schwab-py with SYMBOL_SEARCH projection
            resp = self.client.get_instruments(
                query,
                schwab.client.Client.Instruments.Projection.SYMBOL_SEARCH
            )
            
            if resp.status_code != 200:
                print(f"Schwab instruments error ({query}): {resp.status_code}")
                return []
            
            data = resp.json()
            
            # Normalize response to our format
            instruments = []
            for symbol, info in data.items():
                # Filter to equity instruments only
                asset_type = info.get('assetType', '')
                if asset_type not in ['EQUITY', 'ETF']:
                    continue
                
                instruments.append({
                    'symbol': info.get('symbol', symbol),
                    'name': info.get('description', ''),
                    'exchange': info.get('exchange', 'US'),
                    'assetType': asset_type
                })
            
            return instruments
            
        except Exception as e:
            print(f"Error searching Schwab instruments ({query}): {e}")
            return []

    def _normalize_option(self, opt, exp_date):
        """Convert Schwab option data to local standard format"""
        try:
            # Extract Greeks if available (often 0 if not calculated by Schwab yet)
            # Schwab keys: 'delta', 'gamma', etc.
            
            return {
                'bid': opt.get('bid', 0),
                'ask': opt.get('ask', 0),
                'last': opt.get('last', 0),
                'mark': (opt.get('bid', 0) + opt.get('ask', 0)) / 2 if opt.get('bid') and opt.get('ask') else opt.get('last', 0),
                'totalVolume': opt.get('totalVolume', 0),
                'openInterest': opt.get('openInterest', 0),
                'volatility': opt.get('volatility', 0) / 100.0 if opt.get('volatility', 0) > 4.0 else opt.get('volatility', 0),
                'delta': opt.get('delta', 0),
                'gamma': opt.get('gamma', 0),
                'theta': opt.get('theta', 0),
                'vega': opt.get('vega', 0),
                'rho': opt.get('rho', 0),
                'strikePrice': opt.get('strikePrice'),
                'expirationDate': exp_date
            }
        except Exception:
            return None
