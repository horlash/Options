import os
import requests
import logging
import time
from datetime import datetime, timedelta
from backend.config import Config

logger = logging.getLogger(__name__)

class OratsAPI:
    # ORATS index aliases: map common ticker names to ORATS-expected symbols
    # Verified via live API: ORATS uses plain SPX/NDX/VIX (NOT $SPX.X format)
    # DJI -> DJX because ORATS lists DJX, not DJI
    INDEX_ALIASES = {
        'DJI': 'DJX',    # Dow Jones — ORATS uses DJX
        # RUT excluded — ORATS has inconsistent coverage
    }

    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("ORATS_API_KEY")
        self.base_url = "https://api.orats.io/datav2"
        
        if not self.api_key:
            raise ValueError("ORATS_API_KEY not found in environment variables")

    def is_configured(self):
        """Check if API key is present"""
        return bool(self.api_key)

    def _clean_ticker(self, ticker):
        """Format ticker for ORATS API.
        Strips $ prefix, applies aliases (DJI -> DJX).
        ORATS uses plain tickers: SPX, NDX, VIX, AAPL, SPY.
        """
        clean = ticker.replace('$', '').replace('.X', '').strip().upper()
        return self.INDEX_ALIASES.get(clean, clean)

    def get_ticker_universe(self):
        """Fetch complete ORATS ticker universe with date ranges.
        Returns dict: {ticker: {minDate, maxDate}} for all ~5,000+ supported symbols.
        """
        url = f"{self.base_url}/tickers"
        params = {"token": self.api_key}
        try:
            response = requests.get(url, params=params, timeout=(5, 30))  # QW-5
            response.raise_for_status()
            data = response.json()
            universe = {}
            for t in data.get("data", []):
                universe[t.get("ticker", "")] = {
                    "minDate": t.get("minDate"),
                    "maxDate": t.get("maxDate")
                }
            return universe
        except Exception as e:
            print(f"ORATS Ticker Universe Error: {e}")
            return {}

    def check_ticker(self, ticker):
        """Check if a specific ticker exists in ORATS coverage."""
        ticker = self._clean_ticker(ticker)
        url = f"{self.base_url}/tickers"
        params = {"token": self.api_key, "ticker": ticker}
        try:
            response = requests.get(url, params=params, timeout=(5, 30))  # QW-5
            response.raise_for_status()
            data = response.json()
            return bool(data.get("data"))
        except:
            return False

    def get_option_chain(self, ticker):
        """
        Fetch option chain (strikes) for a ticker.
        Returns standardized format compatible with internal logic.
        """
        ticker = self._clean_ticker(ticker)
        url = f"{self.base_url}/live/strikes"
        params = {
            "token": self.api_key,
            "ticker": ticker
        }
        
        try:
            response = requests.get(url, params=params, timeout=(5, 30))  # QW-5
            response.raise_for_status()
            data = response.json()
            return self._standardize_response(data)
        except requests.exceptions.HTTPError as e:
            print(f"ORATS API Error (Chain): {e}")
            return None
        except Exception as e:
            print(f"ORATS Connection Error: {e}")
            return None

    def get_history(self, ticker, days=365):
        """
        Fetch historical price data via /hist/dailies.
        ORATS only accepts 'ticker' and optional 'tradeDate' (single date).
        We fetch all data and filter client-side to last N days.
        Returns dict: {'candles': [...], 'symbol': ticker, 'empty': bool}
        """
        ticker = self._clean_ticker(ticker)
        url = f"{self.base_url}/hist/dailies"
        
        params = {
            "token": self.api_key,
            "ticker": ticker,
        }
        
        try:
            response = requests.get(url, params=params, timeout=(5, 30))  # QW-5
            response.raise_for_status()
            data = response.json()
            
            # Client-side date filtering (ORATS returns all available history)
            cutoff = datetime.now() - timedelta(days=days)
            candles = []
            if "data" in data:
                for row in data["data"]:
                    # ORATS hist/dailies fields: tradeDate, open, hiPx, loPx, clsPx, stockVolume
                    try:
                        dt = datetime.strptime(row.get("tradeDate"), "%Y-%m-%d")
                        if dt < cutoff:
                            continue  # Skip data older than requested range
                        candles.append({
                            "datetime": int(dt.timestamp() * 1000), 
                            "open": row.get("open"),
                            "high": row.get("hiPx"),
                            "low": row.get("loPx"),
                            "close": row.get("clsPx"),
                            "volume": row.get("stockVolume")
                        })
                    except: continue
            
            # Sort by date asc
            candles.sort(key=lambda x: x['datetime'])
            
            # Return in Schwab/TDA format for compatibility
            return {'candles': candles, 'symbol': ticker, 'empty': len(candles) == 0}

        except requests.exceptions.HTTPError as e:
            if response.status_code == 403:
                print(f"ORATS Perms Error: Candles not enabled for this key.")
            else:
                print(f"ORATS API Error (History): {e}")
            return None
        except Exception as e:
            print(f"ORATS History Connection Error: {e}")
            return None

    def get_quote(self, ticker):
        """
        Fetch real-time (snapshot) quote using /live/strikes endpoint (or /strikes).
        Returns dict with 'price', 'volume', etc.
        """
        ticker = self._clean_ticker(ticker)
        # User suggested: https://api.orats.io/datav2/live/strikes
        url = f"{self.base_url}/live/strikes" 
        params = {
            "token": self.api_key,
            "ticker": ticker
        }
        try:
            response = requests.get(url, params=params, timeout=(5, 30))  # QW-5
            response.raise_for_status()
            data = response.json()
            
            # Data format: { data: [ { ticker:..., price:... } ] }
            if "data" in data and len(data["data"]) > 0:
                item = data["data"][0]
                
                # Prefer 'stockPrice' per documentation, fallback to 'tickerPrice' or 'price'
                price = item.get("stockPrice")
                if price is None: price = item.get("tickerPrice")
                if price is None: price = item.get("price")
                if price is None: price = item.get("last")
                if price is None: price = item.get("pxCls") # Closing Price
                if price is None: price = item.get("priorCls") # Prior Close
                
                # Volume
                volume = item.get("volume")
                if volume is None: volume = item.get("stockVolume")
                if volume is None: volume = item.get("unadjStockVolume")
                
                # Bid/Ask
                bid = item.get("bid") or item.get("stockBid")
                ask = item.get("ask") or item.get("stockAsk")
                
                return {
                    "symbol": item.get("ticker", ticker),
                    "price": float(price) if price is not None else 0.0,
                    "volume": int(volume) if volume is not None else 0,
                    "bid": float(bid) if bid is not None else 0.0,
                    "ask": float(ask) if ask is not None else 0.0
                }
            return None

        except requests.exceptions.HTTPError as e:
            print(f"ORATS API Error (Quote): {e}")
            return None
        except Exception as e:
            print(f"ORATS Quote Connection Error: {e}")
            return None

    def get_option_quote(self, ticker, strike, expiry_date, option_type='CALL'):
        """
        Fetch real-time price for a specific option contract.
        
        Fetches all strikes from /live/strikes and filters to match
        the exact contract by expiry, strike, and type.
        
        Args:
            ticker: Underlying ticker (e.g. 'GOOG')
            strike: Strike price (e.g. 310)
            expiry_date: Expiry as 'YYYY-MM-DD' string (e.g. '2026-02-27')
            option_type: 'CALL' or 'PUT'
            
        Returns:
            dict with 'bid', 'ask', 'mark', 'underlying', 'volume', 'oi'
            or None if not found
        """
        ticker = self._clean_ticker(ticker)
        url = f"{self.base_url}/live/strikes"
        params = {
            "token": self.api_key,
            "ticker": ticker
        }
        try:
            response = requests.get(url, params=params, timeout=(5, 30))  # QW-5
            response.raise_for_status()
            data = response.json()
            
            if "data" not in data or not data["data"]:
                return None
            
            # Find the matching strike+expiry row
            strike_f = float(strike)
            is_call = option_type.upper() == 'CALL'
            
            for item in data["data"]:
                item_expiry = item.get("expirDate", "")
                item_strike = float(item.get("strike", 0))
                
                if item_expiry == expiry_date and abs(item_strike - strike_f) < 0.01:
                    # Found the matching contract row
                    underlying = (
                        item.get("stockPrice") or 
                        item.get("tickerPrice") or 
                        item.get("price") or 0.0
                    )
                    
                    if is_call:
                        bid = item.get("callBidPrice", 0) or 0
                        ask = item.get("callAskPrice", 0) or 0
                        value = item.get("callValue", 0) or 0
                        volume = item.get("callVolume", 0) or 0
                        oi = item.get("callOpenInterest", 0) or 0
                    else:
                        bid = item.get("putBidPrice", 0) or 0
                        ask = item.get("putAskPrice", 0) or 0
                        value = item.get("putValue", 0) or 0
                        volume = item.get("putVolume", 0) or 0
                        oi = item.get("putOpenInterest", 0) or 0
                    
                    # Mark = theoretical value if available, else mid-price
                    mark = value if value > 0 else (bid + ask) / 2 if (bid + ask) > 0 else 0

                    # Greeks (shared per strike row in ORATS)
                    delta = item.get("delta", 0) or 0
                    gamma = item.get("gamma", 0) or 0
                    theta = item.get("theta", 0) or 0
                    vega = item.get("vega", 0) or 0
                    iv_key = "callMidIv" if is_call else "putMidIv"
                    iv_raw = item.get(iv_key) or item.get("smvVol") or 0
                    iv = round(iv_raw * 100, 2) if iv_raw and iv_raw < 10 else iv_raw

                    # Negate delta for puts
                    if not is_call:
                        delta = -(abs(delta))

                    return {
                        "bid": float(bid),
                        "ask": float(ask),
                        "mark": float(mark),
                        "underlying": float(underlying),
                        "volume": int(volume),
                        "oi": int(oi),
                        "delta": float(delta),
                        "gamma": float(gamma),
                        "theta": float(theta),
                        "vega": float(vega),
                        "iv": float(iv),
                    }
            
            # No matching contract found
            print(f"ORATS: No contract found for {ticker} {strike} {expiry_date} {option_type}")
            return None

        except requests.exceptions.HTTPError as e:
            print(f"ORATS API Error (Option Quote): {e}")
            return None
        except Exception as e:
            print(f"ORATS Option Quote Error: {e}")
            return None

    def _standardize_response(self, orats_data):
        """
        Convert ORATS flattened data to nested structure (Schwab-like)
        ORATS returns a list of objects (one per strike/expiry).
        We need {callExpDateMap: {expiry: {strike: [option, ...]}}}
        """
        if not orats_data or "data" not in orats_data:
            print("DEBUG: No 'data' field in response")
            return {}

        raw_list = orats_data["data"]
        if len(raw_list) > 0:
             # Debugging removed for production
             pass

        
        call_map = {}
        put_map = {}
        
        for item in raw_list:
            # ORATS "Wide" Format: One row per strike, containing both Call and Put columns
            # Fields: ticker, expirDate, strike, callBid, callAsk, putBid, putAsk, etc.
            
            expiry = item.get("expirDate")
            strike = str(item.get("strike"))
            if not expiry or not strike:
                continue

            # Calculate DTE once
            days_to_expiry = 0
            try:
                exp_date = datetime.strptime(expiry, "%Y-%m-%d")
                days_to_expiry = (exp_date - datetime.now()).days
                exp_key = f"{expiry}:{days_to_expiry}"
            except:
                exp_key = expiry
                days_to_expiry = 0

            # --- PROCESS CALL ---
            call_obj = {
                "putCall": "CALL",
                "symbol": f"{item.get('ticker')}_{expiry}_C{strike}",
                "description": f"{item.get('ticker')} {expiry} {strike} CALL",
                "bid": item.get("callBidPrice", 0),
                "ask": item.get("callAskPrice", 0),
                "last": item.get("callPrice", 0), 
                "mark": item.get("callValue", 0) or ((item.get("callBidPrice",0) + item.get("callAskPrice",0))/2), 
                "totalVolume": item.get("callVolume", 0),
                "openInterest": item.get("callOpenInterest", 0),
                "volatility": item.get("callMidIv", 0) * 100 if item.get("callMidIv") else 0,
                "delta": item.get("delta", 0),
                "gamma": item.get("gamma", 0),
                "theta": item.get("theta", 0),
                "vega": item.get("vega", 0),
                "rho": item.get("rho", 0),
                "strikePrice": float(strike),
                "expirationDate": expiry,
                "daysToExpiration": days_to_expiry
            }
            
            # Helper to map standard keys if they differ (e.g. callIv vs callIvInfinity)
            # ORATS standard keys: callBid, callAsk, callMeanPrice (mark?), callVol?
            # I will use .get() with defaults.
            # Update: Orats DataV2 often uses 'callBid', 'callAsk', 'callVolume', 'callOpenInterest', 'smvVol' (IV).
            # Wait, if IV is shared? No, usually separate.
            # I will add a fallback for IV.
            if call_obj['volatility'] == 0:
                 call_obj['volatility'] = item.get("smvVol", 0) * 100 # Smoothed Vol?

            if exp_key not in call_map: call_map[exp_key] = {}
            if strike not in call_map[exp_key]: call_map[exp_key][strike] = []
            call_map[exp_key][strike].append(call_obj)

            # --- PROCESS PUT ---
            put_obj = {
                "putCall": "PUT",
                "symbol": f"{item.get('ticker')}_{expiry}_P{strike}",
                "description": f"{item.get('ticker')} {expiry} {strike} PUT",
                "bid": item.get("putBidPrice", 0),
                "ask": item.get("putAskPrice", 0),
                "last": item.get("putPrice", 0),
                "mark": item.get("putValue", 0) or ((item.get("putBidPrice",0) + item.get("putAskPrice",0))/2),
                "totalVolume": item.get("putVolume", 0),
                "openInterest": item.get("putOpenInterest", 0),
                "volatility": item.get("putMidIv", 0) * 100 if item.get("putMidIv") else 0,
                "delta": -(abs(item.get("delta", 0))),
                "gamma": item.get("gamma", 0),
                "theta": item.get("theta", 0),
                "vega": item.get("vega", 0),
                "rho": -(item.get("rho", 0)),
                "strikePrice": float(strike),
                "expirationDate": expiry,
                "daysToExpiration": days_to_expiry
            }
            
            if put_obj['volatility'] == 0:
                 put_obj['volatility'] = item.get("smvVol", 0) * 100

            if exp_key not in put_map: put_map[exp_key] = {}
            if strike not in put_map[exp_key]: put_map[exp_key][strike] = []
            put_map[exp_key][strike].append(put_obj)

        return {
            "symbol": raw_list[0].get("ticker") if raw_list else "UNKNOWN",
            "callExpDateMap": call_map,
            "putExpDateMap": put_map
        }

    # ═══════════════════════════════════════════════════════════════
    # Phase 3: New API Methods (P0 prerequisites)
    # ═══════════════════════════════════════════════════════════════

    def get_live_summary(self, ticker):
        """Fetch live/summaries for real-time IV term structure and skew.

        Returns dict with 129 fields including:
        - rSlp30: 30-day risk-neutral skew slope
        - skewing: skew persistence metric
        - contango: term structure shape
        - dlt25Iv30d / dlt75Iv30d: 25-delta put/call IV (30-day)
        """
        ticker = self._clean_ticker(ticker)
        url = f"{self.base_url}/live/summaries"
        params = {"token": self.api_key, "ticker": ticker}

        try:
            response = requests.get(url, params=params, timeout=(5, 30))
            response.raise_for_status()
            data = response.json()
            if "data" in data and len(data["data"]) > 0:
                return data["data"][0]
            return None
        except Exception as e:
            logger.warning(f"ORATS live/summaries error for {ticker}: {e}")
            return None

    def get_hist_cores(self, ticker, trade_date=None):
        """Fetch hist/cores for historical IV rank, earnings, and dividend data.

        Returns dict with 340 fields including:
        - ivPctile1y: IV percentile (1-year lookback)
        - ivPctile1m: IV percentile (1-month lookback)
        - daysToNextErn: days to next earnings
        - impliedEarningsMove: market-implied earnings move
        - divDate: next dividend date
        - contango: term structure shape
        - slope: volatility slope

        Note: T-1 delay (yesterday's data). Use for historical context.
        """
        ticker = self._clean_ticker(ticker)
        url = f"{self.base_url}/hist/cores"
        params = {"token": self.api_key, "ticker": ticker}
        if trade_date:
            params["tradeDate"] = trade_date  # YYYY-MM-DD

        try:
            response = requests.get(url, params=params, timeout=(5, 30))
            response.raise_for_status()
            data = response.json()
            if "data" in data and len(data["data"]) > 0:
                # Return the most recent entry (last in list)
                return data["data"][-1]
            return None
        except Exception as e:
            logger.warning(f"ORATS hist/cores error for {ticker}: {e}")
            return None
