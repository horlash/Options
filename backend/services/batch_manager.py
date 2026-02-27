import concurrent.futures
import time
import logging
import threading
from typing import List, Dict, Any
from backend.api.orats import OratsAPI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BatchManager:
    def __init__(self, max_workers=10, rate_limit_per_min=500):
        """
        Manage concurrent API requests.
        :param max_workers: Number of threads.
        :param rate_limit_per_min: Max requests per minute.
        """
        self.max_workers = max_workers
        self.rate_limit = rate_limit_per_min
        self.delay = 60.0 / self.rate_limit if rate_limit_per_min > 0 else 0
        self.orats_api = OratsAPI()
        # F12 FIX: Thread-safe rate limiter
        self._lock = threading.Lock()
        self._last_request_time = 0.0

    def fetch_option_chains(self, tickers: List[str]) -> Dict[str, Any]:
        """
        Fetch option chains for a list of tickers concurrently.
        """
        results = {}
        processed = 0
        total = len(tickers)
        
        logger.info(f"BatchManager: Starting fetch for {total} tickers with {self.max_workers} workers.")
        start_time = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Create a dictionary to map future to ticker
            future_to_ticker = {
                executor.submit(self._fetch_single_safe, ticker): ticker 
                for ticker in tickers
            }
            
            for future in concurrent.futures.as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    data = future.result()
                    if data:
                        results[ticker] = data
                    processed += 1
                    if processed % 10 == 0:
                        logger.info(f"BatchManager: Processed {processed}/{total} tickers...")
                except Exception as exc:
                    logger.error(f"BatchManager: Error fetching {ticker}: {exc}")
                
                # F12: Rate limiting now handled in _fetch_single_safe
                pass

        elapsed = time.time() - start_time
        logger.info(f"BatchManager: Finished. Fetched {len(results)}/{total} in {elapsed:.2f}s.")
        return results

    def _fetch_single_safe(self, ticker):
        """
        Wrapper to fetch a single ticker safely with rate limiting.
        """
        try:
            # F12 FIX: Thread-safe rate limiting
            with self._lock:
                elapsed = time.time() - self._last_request_time
                if elapsed < self.delay:
                    time.sleep(self.delay - elapsed)
                self._last_request_time = time.time()
            return self.orats_api.get_option_chain(ticker)
        except Exception as e:
            logger.error(f"Error in thread for {ticker}: {e}")
            return None
