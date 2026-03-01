import os
import requests
import logging
import time
from datetime import datetime, timedelta
from backend.config import Config
from backend.utils.retry import retry_api

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

    @retry_api(max_retries=2, base_delay=1.0)
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
            logger.warning(f"ORATS Ticker Universe Error: {e}")
            return {}

    @retry_api(max_retries=2, base_delay=1.0)
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
        except Exception:
            return False

    @retry_api(max_retries=2, base_delay=1.0)
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
            logger.warning(f"ORATS API Error (Chain): {e}")
            return None
        except Exception as e:
            logger.warning(f"ORATS Connection Error: {e}")
            return None

    @retry_api(max_retries=2, base_delay=1.0)
    def get_history(self, ticker, days=400):
        """
        Fetch historical price data via /hist/dailies.
        ORATS only accepts 'ticker' and optional 'tradeDate' (single date).
        We fetch all data and filter client-side to last N days.
        
        FIX-MINERV-A: Default changed from 365 to 400 calendar days.
        365 calendar days yields only ~250-251 trading days after removing
        weekends/holidays, which falls short of the 252-bar minimum required
        by calculate_minervini_criteria(). 400 calendar days yields ~275
        trading days — comfortable margin above the threshold.
        Zero API cost impact: ORATS returns all history; we filter client-side.
        
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
                    except (ValueError, KeyError, TypeError): continue
            
            # Sort by date asc
            candles.sort(key=lambda x: x['datetime'])
            
            # Return in Schwab/TDA format for compatibility
            return {'candles': candles, 'symbol': ticker, 'empty': len(candles) == 0}

        except requests.exceptions.HTTPError as e:
            if response.status_code == 403:
                logger.warning("ORATS Perms Error: Candles not enabled for this key.")
            else:
                logger.warning(f"ORATS API Error (History): {e}")
            return None
        except Exception as e:
            logger.warning(f"ORATS History Connection Error: {e}")
            return None

    @retry_api(max_retries=2, base_delay=1.0)
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
            logger.warning(f"ORATS API Error (Quote): {e}")
            return None
        except Exception as e:
            logger.warning(f"ORATS Quote Connection Error: {e}")
            return None

    @retry_api(max_retries=2, base_delay=1.0)
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
            logger.debug(f"ORATS: No contract found for {ticker} {strike} {expiry_date} {option_type}")
            return None

        except requests.exceptions.HTTPError as e:
            logger.warning(f"ORATS API Error (Option Quote): {e}")
            return None
        except Exception as e:
            logger.warning(f"ORATS Option Quote Error: {e}")
            return None

    def _standardize_response(self, orats_data):
        """
        Convert ORATS flattened data to nested structure (Schwab-like)
        ORATS returns a list of objects (one per strike/expiry).
        We need {callExpDateMap: {expiry: {strike: [option, ...]}}}
        """
        if not orats_data or "data" not in orats_data:
            logger.debug("No 'data' field in ORATS response")
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
            except (ValueError, TypeError):
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
    # SMART SECTOR SCAN: Bulk core data for pre-filtering
    # ═══════════════════════════════════════════════════════════════

    # ORATS sector ETF mapping: bestEtf → GICS Sector name (user-facing)
    SECTOR_ETF_MAP = {
        'XLK': 'Technology',
        'XLV': 'Healthcare',
        'XLF': 'Financials',
        'XLE': 'Energy',
        'XLI': 'Industrials',
        'XLY': 'Consumer Discretionary',
        'XLP': 'Consumer Staples',
        'XLU': 'Utilities',
        'XLRE': 'Real Estate',
        'XLB': 'Materials',
        'XLC': 'Communication Services',
    }

    # Reverse map: user-facing sector name → list of ETF codes
    SECTOR_NAME_MAP = {}
    for _etf, _name in SECTOR_ETF_MAP.items():
        SECTOR_NAME_MAP.setdefault(_name.lower(), []).append(_etf)

    @retry_api(max_retries=2, base_delay=1.0)
    def get_cores_bulk(self, sector=None, fields=None):
        """Fetch ORATS core data for entire universe in a single API call.

        Returns ~5,000+ tickers with options-specific intelligence:
        IV percentile, options volume, open interest, market width,
        momentum, earnings proximity, and more.

        Data is T-1 (prior trading day close) — suitable for screening
        and ranking candidates, NOT for live trade execution.

        SMART SECTOR SCAN: Replaces FMP screener as primary pre-filter.
        ORATS already knows which tickers are optionable — no coverage
        check needed downstream.

        Args:
            sector: Optional sector name to filter (e.g., 'Technology',
                    'Healthcare'). Matched against ORATS bestEtf field.
                    Also matches ORATS sectorName for industry-level
                    filtering (e.g., 'Technology Hardware & Equipment').
            fields: Optional comma-separated field list to reduce payload.
                    Defaults to the ~25 fields needed for smart ranking.

        Returns:
            list[dict]: Ticker records with options metrics, filtered
                        by sector if specified.
        """
        url = f"{self.base_url}/cores"
        params = {"token": self.api_key}

        # Request only the fields needed for ranking (reduces payload ~90%)
        if fields:
            params["fields"] = fields
        else:
            params["fields"] = (
                "ticker,tradeDate,sectorName,bestEtf,mktCap,stkVolu,"
                "ivPctile1y,ivPctile1m,avgOptVolu20d,"
                "cVolu,pVolu,cOi,pOi,"
                "mktWidthVol,iv30d,orHv20d,"
                "stkPxChng1wk,stkPxChng1m,stkPxChng6m,"
                "beta1y,daysToNextErn,impliedEarningsMove,"
                "orIvXern20d,iv200Ma,pxAtmIv"
            )

        try:
            # Larger timeout: full universe payload (~5k tickers)
            response = requests.get(url, params=params, timeout=(5, 60))
            response.raise_for_status()
            data = response.json()
            records = data.get("data", [])

            # Client-side sector filter
            if sector:
                sector_lower = sector.lower().strip()

                # Strategy 1: Match by bestEtf (broad sector)
                # e.g., 'Technology' → 'XLK'
                etf_codes = self.SECTOR_NAME_MAP.get(sector_lower, [])

                # Strategy 2: Match by sectorName (industry group)
                # e.g., 'Technology Hardware & Equipment' or 'Semiconductors'
                filtered = []
                for r in records:
                    best_etf = (r.get("bestEtf") or "").upper()
                    sector_name = (r.get("sectorName") or "").lower()

                    # Match if ETF matches broad sector
                    if best_etf in etf_codes:
                        filtered.append(r)
                    # Or if sectorName contains the search term (industry drill-down)
                    elif sector_lower in sector_name:
                        filtered.append(r)

                records = filtered

            logger.info(
                f"ORATS /cores: {len(records)} tickers"
                f"{f' in {sector}' if sector else ' (full universe)'}"
            )
            return records

        except requests.exceptions.HTTPError as e:
            if hasattr(e, 'response') and e.response is not None and e.response.status_code == 403:
                logger.warning("ORATS /cores: Permission denied — check API key tier")
            else:
                logger.warning(f"ORATS /cores API Error: {e}")
            raise  # Let retry decorator handle
        except requests.exceptions.Timeout:
            logger.warning("ORATS /cores: Timeout (60s) — universe fetch took too long")
            return []
        except Exception as e:
            logger.warning(f"ORATS /cores bulk fetch error: {e}")
            return []

    # ═══════════════════════════════════════════════════════════════
    # BATCH HISTORY: Parallel multi-ticker history fetch
    # ═══════════════════════════════════════════════════════════════

    def get_history_batch(self, tickers, days=400, max_workers=10, rate_limit_per_min=100):
        """Fetch historical price data for multiple tickers in parallel.

        Uses ThreadPoolExecutor with thread-safe rate limiting, matching
        the concurrency pattern from BatchManager.

        Performance: 30 tickers sequential ≈ 30-60s → parallel ≈ 5-8s
        (bounded by ORATS rate limit: 100 req/min for history endpoint).

        Args:
            tickers: List of ticker symbols to fetch
            days: Calendar days of history per ticker (default 400, same as get_history)
            max_workers: Thread pool size (default 10)
            rate_limit_per_min: Max requests per minute to ORATS /hist/dailies.
                                Default 100 (conservative; ORATS allows 100/min on hist).

        Returns:
            dict: {ticker: price_history_dict, ...}
                  Only includes tickers that returned valid data.
                  Failed tickers are logged and silently excluded.
        """
        import concurrent.futures
        import threading

        if not tickers:
            return {}

        results = {}
        total = len(tickers)
        processed = [0]  # Mutable counter for thread-safe increment
        delay = 60.0 / rate_limit_per_min if rate_limit_per_min > 0 else 0
        lock = threading.Lock()
        last_request_time = [0.0]  # Mutable for thread-safe update

        logger.info(
            f"ORATS get_history_batch: Starting parallel fetch for {total} tickers "
            f"({max_workers} workers, {rate_limit_per_min} req/min)"
        )
        start_time = time.time()

        def _fetch_single(ticker):
            """Fetch history for one ticker with rate limiting."""
            try:
                # Thread-safe rate limiting (same pattern as BatchManager)
                with lock:
                    elapsed = time.time() - last_request_time[0]
                    if elapsed < delay:
                        time.sleep(delay - elapsed)
                    last_request_time[0] = time.time()
                return self.get_history(ticker, days=days)
            except Exception as e:
                logger.warning(f"ORATS get_history_batch: Error fetching {ticker}: {e}")
                return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_ticker = {
                executor.submit(_fetch_single, t): t
                for t in tickers
            }

            for future in concurrent.futures.as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    data = future.result()
                    if data and not data.get('empty', True):
                        results[ticker] = data
                    processed[0] += 1
                    if processed[0] % 10 == 0:
                        logger.info(
                            f"ORATS get_history_batch: {processed[0]}/{total} fetched..."
                        )
                except Exception as exc:
                    logger.error(
                        f"ORATS get_history_batch: Unhandled error for {ticker}: {exc}"
                    )

        elapsed = time.time() - start_time
        logger.info(
            f"ORATS get_history_batch: Done. {len(results)}/{total} succeeded in {elapsed:.1f}s"
        )
        return results

    # ═══════════════════════════════════════════════════════════════
    # Phase 3: New API Methods (P0 prerequisites)
    # ═══════════════════════════════════════════════════════════════

    @retry_api(max_retries=2, base_delay=1.0)
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

    @retry_api(max_retries=2, base_delay=1.0)
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
