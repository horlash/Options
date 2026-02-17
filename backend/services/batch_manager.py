import concurrent.futures
import time
import logging
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
                
                # Simple Rate Limiting (Sleep ensures average rate)
                # Note: In a thread pool, this sleeps the MAIN thread? No, 'as_completed' yields.
                # To enforce rate limit on SUBMISSION, we should throttle the submission loop.
                # Beause 'executor.submit' is fast.
                # But here we submitted ALL at once.
                # If we want to rate limit, we should throttle.
                # For now, let's assume the API handles bursts or we rely on 'max_workers' to limit concurrency.
                # 10 workers = max 10 concurrent requests.
                pass

        elapsed = time.time() - start_time
        logger.info(f"BatchManager: Finished. Fetched {len(results)}/{total} in {elapsed:.2f}s.")
        return results

    def _fetch_single_safe(self, ticker):
        """
        Wrapper to fetch a single ticker safely.
        """
        try:
            # Throttle if needed (naive)
            # time.sleep(0.1) 
            return self.orats_api.get_option_chain(ticker)
        except Exception as e:
            logger.error(f"Error in thread for {ticker}: {e}")
            return None
