"""
Context Service — The "Time Capsule" Builder
==============================================
Point 6: Backtesting Data Model & Schema

Captures rich context at trade entry and exit for backtesting and ML labeling.
Writes all data into the PaperTrade.trade_context JSONB column.

Three main operations:
  1. capture_entry_context()  — At trade placement: signals, market regime, order book
  2. capture_exit_context()   — At trade close: exit conditions, market state
  3. calculate_targets()      — Post-close: MFE/MAE/PnL targets for ML labeling
"""

import logging
from datetime import datetime

log = logging.getLogger(__name__)


class ContextService:
    """Collects and persists rich trading context for backtesting analysis."""

    # Sector ETF mapping for market regime context
    SECTOR_ETFS = {
        'XLK': ['AAPL', 'MSFT', 'NVDA', 'AMD', 'AVGO', 'ORCL', 'CRM', 'ADBE', 'CSCO', 'ACN',
                 'INTC', 'IBM', 'QCOM', 'TXN', 'AMAT', 'MU', 'LRCX', 'KLAC', 'SNPS', 'CDNS',
                 'NOW', 'PANW', 'CRWD', 'FTNT', 'PLTR', 'DELL', 'HPE', 'MRVL', 'ON', 'NXPI'],
        'XLF': ['JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'BLK', 'SCHW', 'AXP', 'SPGI'],
        'XLV': ['UNH', 'JNJ', 'LLY', 'PFE', 'ABBV', 'MRK', 'TMO', 'ABT', 'DHR', 'BMY'],
        'XLY': ['AMZN', 'TSLA', 'HD', 'MCD', 'NKE', 'SBUX', 'TJX', 'LOW', 'BKNG', 'CMG'],
        'XLC': ['META', 'GOOGL', 'GOOG', 'NFLX', 'DIS', 'CMCSA', 'T', 'VZ', 'TMUS', 'CHTR'],
        'XLE': ['XOM', 'CVX', 'COP', 'EOG', 'SLB', 'MPC', 'PSX', 'VLO', 'OXY', 'HAL'],
        'XLI': ['RTX', 'HON', 'UPS', 'BA', 'CAT', 'DE', 'LMT', 'GE', 'MMM', 'UNP'],
        'XLP': ['PG', 'KO', 'PEP', 'COST', 'WMT', 'PM', 'MO', 'CL', 'MDLZ', 'EL'],
        'XLU': ['NEE', 'DUK', 'SO', 'D', 'AEP', 'SRE', 'EXC', 'XEL', 'ED', 'WEC'],
        'XLRE': ['PLD', 'AMT', 'CCI', 'EQIX', 'PSA', 'SPG', 'O', 'WELL', 'DLR', 'AVB'],
        'XLB': ['LIN', 'APD', 'SHW', 'ECL', 'FCX', 'NEM', 'NUE', 'VMC', 'MLM', 'DOW'],
    }

    def __init__(self, orats_api=None, scanner=None):
        """
        Args:
            orats_api: OratsAPI instance for fetching quotes and Greeks
            scanner: HybridScannerService instance for technical analysis data
        """
        self.orats = orats_api
        self.scanner = scanner

    # ─── Public API ───────────────────────────────────────────────

    def capture_entry_context(self, ticker, option_type, strike, expiry,
                               entry_price, scanner_result=None):
        """Capture rich context at the moment of trade entry.

        Returns a dict suitable for writing to PaperTrade.trade_context.
        """
        context = {
            'captured_at': datetime.utcnow().isoformat() + 'Z',
            'capture_type': 'ENTRY',
        }

        # 1. Signals snapshot (technical indicators)
        context['signals_snapshot'] = self._get_signals_snapshot(
            ticker, scanner_result
        )

        # 2. Market regime (SPY, VIX, sector)
        context['market_regime'] = self._get_market_regime(ticker)

        # 3. Order book state (bid/ask, Greeks, liquidity)
        context['order_book_state'] = self._get_order_book_state(
            ticker, option_type, strike, expiry, entry_price
        )

        # 4. AI reasoning log (if scanner result contains it)
        if scanner_result and scanner_result.get('ai_analysis'):
            ai = scanner_result['ai_analysis']
            context['ai_reasoning_log'] = {
                'score': ai.get('score'),
                'verdict': ai.get('verdict'),
                'conviction': ai.get('conviction'),
                'summary': ai.get('summary', '')[:500],  # Truncate to save space
                'factors': ai.get('factors', []),
            }

        log.info(f"[Context] Entry context captured for {ticker} "
                 f"({option_type} ${strike}) — "
                 f"keys: {list(context.keys())}")
        return context

    def capture_exit_context(self, trade, close_price, close_reason):
        """Capture context at trade exit. Merges into existing trade_context.

        Args:
            trade: PaperTrade ORM object
            close_price: The exit price
            close_reason: Why the trade was closed (SL_HIT, TP_HIT, MANUAL, EXPIRED)
        """
        exit_ctx = {
            'captured_at': datetime.utcnow().isoformat() + 'Z',
            'capture_type': 'EXIT',
            'close_price': close_price,
            'close_reason': close_reason,
            'duration_hours': None,
        }

        # Calculate trade duration
        if trade.created_at:
            duration = datetime.utcnow() - trade.created_at
            exit_ctx['duration_hours'] = round(duration.total_seconds() / 3600, 2)

        # Get exit market conditions
        exit_ctx['market_regime'] = self._get_market_regime(trade.ticker)

        # Merge into existing context
        existing = dict(trade.trade_context or {})
        existing['exit_context'] = exit_ctx
        return existing

    def calculate_targets(self, trade, price_snapshots):
        """Calculate ML target variables from price history post-close.

        Args:
            trade: PaperTrade ORM object (must be CLOSED)
            price_snapshots: List of PriceSnapshot objects for this trade

        Returns dict of target variables to merge into trade_context.
        """
        if not price_snapshots or not trade.entry_price:
            return {}

        entry = trade.entry_price
        # PriceSnapshot stores the option mark price in mark_price column
        prices = [s.mark_price for s in price_snapshots if s.mark_price is not None]

        if not prices:
            return {}

        targets = {}

        # MFE: Maximum Favorable Excursion (best price during trade)
        # MAE: Maximum Adverse Excursion (worst price during trade)
        if trade.direction == 'BUY':
            max_price = max(prices)
            min_price = min(prices)
            targets['target_mfe_pct'] = round(
                ((max_price - entry) / entry) * 100, 2
            )
            targets['target_mae_pct'] = round(
                ((entry - min_price) / entry) * 100, 2
            )
            # Dollar values for frontend efficiency calculation
            # mfe = max favorable price move per contract (dollar diff)
            targets['mfe'] = round(max_price - entry, 4)
            targets['mae'] = round(entry - min_price, 4)
        else:  # SELL (short)
            max_price = max(prices)
            min_price = min(prices)
            targets['target_mfe_pct'] = round(
                ((entry - min_price) / entry) * 100, 2
            )
            targets['target_mae_pct'] = round(
                ((max_price - entry) / entry) * 100, 2
            )
            targets['mfe'] = round(entry - min_price, 4)
            targets['mae'] = round(max_price - entry, 4)

        # P&L at various time intervals
        for i, label in [(3, '15m'), (6, '30m'), (12, '1h')]:
            if len(prices) > i:
                pnl = ((prices[i] - entry) / entry) * 100
                if trade.direction != 'BUY':
                    pnl = -pnl
                targets[f'target_pnl_{label}'] = round(pnl, 2)

        # Final realized P&L
        if trade.exit_price:
            realized = ((trade.exit_price - entry) / entry) * 100
            if trade.direction != 'BUY':
                realized = -realized
            targets['target_realized_pnl_pct'] = round(realized, 2)

        log.info(f"[Context] ML targets calculated for trade {trade.id}: "
                 f"MFE={targets.get('target_mfe_pct')}%, "
                 f"MAE={targets.get('target_mae_pct')}%, "
                 f"mfe=${targets.get('mfe')}, mae=${targets.get('mae')}")
        return targets

    # ─── Internal Collectors ──────────────────────────────────────

    def _get_signals_snapshot(self, ticker, scanner_result=None):
        """Collect multi-timeframe technical signals."""
        snapshot = {}

        # Use scanner result if provided (already has technicals)
        if scanner_result:
            tech = scanner_result.get('technicals', {})
            snapshot['daily'] = {
                'rsi': tech.get('rsi'),
                'macd_signal': tech.get('macd_signal'),
                'ma_signal': tech.get('ma_signal'),
                'bb_signal': tech.get('bb_signal'),
                'bb_squeeze': tech.get('bb_squeeze', False),
                'volume_signal': tech.get('volume_signal'),
                'volume_zscore': tech.get('volume_zscore'),
                'sma_5': tech.get('sma_5'),
                'sma_50': tech.get('sma_50'),
                'sma_200': tech.get('sma_200'),
                'atr': tech.get('atr'),
                'hv_rank': tech.get('hv_rank'),
                'score': tech.get('score'),
            }
            # Sentiment
            sent = scanner_result.get('sentiment', {})
            if sent:
                snapshot['sentiment'] = {
                    'score': sent.get('score'),
                    'headline_count': sent.get('headline_count', 0),
                    'source': sent.get('source'),
                }
        elif self.scanner:
            # Try to get fresh technicals from the scanner
            try:
                result = self.scanner.scan_ticker(ticker, strict_mode=False)
                if result and isinstance(result, dict):
                    tech = result.get('technicals', {})
                    snapshot['daily'] = {
                        'rsi': tech.get('rsi'),
                        'macd_signal': tech.get('macd_signal'),
                        'score': tech.get('score'),
                    }
            except Exception as e:
                log.warning(f"[Context] Failed to get signals for {ticker}: {e}")
                snapshot['daily'] = {'error': str(e)}

        return snapshot

    def _get_market_regime(self, ticker):
        """Capture macro market conditions: SPY quote, VIX, sector ETF."""
        regime = {}

        if not self.orats:
            return regime

        # SPY (broad market proxy)
        try:
            spy_quote = self.orats.get_quote('SPY')
            if spy_quote and spy_quote.get('price'):
                regime['spy'] = {
                    'price': spy_quote['price'],
                    'pct_change': spy_quote.get('pctChange'),
                    'volume': spy_quote.get('volume'),
                }
        except Exception as e:
            log.debug(f"[Context] SPY quote failed: {e}")

        # VIX (volatility index)
        try:
            vix_quote = self.orats.get_quote('VIX')
            if vix_quote and vix_quote.get('price'):
                regime['vix'] = {
                    'price': vix_quote['price'],
                    'pct_change': vix_quote.get('pctChange'),
                }
        except Exception as e:
            log.debug(f"[Context] VIX quote failed: {e}")

        # Sector ETF for this ticker
        sector_etf = self._find_sector_etf(ticker)
        if sector_etf:
            try:
                sector_quote = self.orats.get_quote(sector_etf)
                if sector_quote and sector_quote.get('price'):
                    regime['sector'] = {
                        'etf': sector_etf,
                        'price': sector_quote['price'],
                        'pct_change': sector_quote.get('pctChange'),
                    }
            except Exception as e:
                log.debug(f"[Context] Sector {sector_etf} quote failed: {e}")

        return regime

    def _get_order_book_state(self, ticker, option_type, strike, expiry,
                               entry_price):
        """Capture option-specific liquidity and Greeks at entry."""
        state = {
            'entry_price': entry_price,
            'option_type': option_type,
            'strike': strike,
            'expiry': expiry,
        }

        if not self.orats:
            return state

        # Try to get the option chain for bid/ask and Greeks
        try:
            chain = self.orats.get_option_chain(ticker)
            if chain:
                option_data = self._find_option_in_chain(
                    chain, option_type, strike, expiry
                )
                if option_data:
                    state.update({
                        'bid': option_data.get('bid'),
                        'ask': option_data.get('ask'),
                        'spread_pct': self._calc_spread_pct(
                            option_data.get('bid'),
                            option_data.get('ask'),
                        ),
                        'volume': option_data.get('totalVolume',
                                                   option_data.get('volume')),
                        'open_interest': option_data.get('openInterest'),
                        'greeks': {
                            'delta': option_data.get('delta'),
                            'gamma': option_data.get('gamma'),
                            'theta': option_data.get('theta'),
                            'vega': option_data.get('vega'),
                            'iv': option_data.get('volatility',
                                                   option_data.get('iv')),
                        },
                    })
        except Exception as e:
            log.warning(f"[Context] Order book fetch failed for {ticker}: {e}")

        return state

    # ─── Helpers ──────────────────────────────────────────────────

    def _find_sector_etf(self, ticker):
        """Find the sector ETF for a given ticker."""
        ticker_upper = ticker.upper()
        for etf, members in self.SECTOR_ETFS.items():
            if ticker_upper in members:
                return etf
        return None

    def _find_option_in_chain(self, chain, option_type, strike, expiry):
        """Find a specific option contract in a standardized chain response."""
        try:
            is_call = option_type.upper() in ('CALL', 'C')
            map_key = 'callExpDateMap' if is_call else 'putExpDateMap'
            exp_map = chain.get(map_key, {})

            # Try exact expiry key, then partial match
            for exp_key, strikes in exp_map.items():
                if expiry in exp_key or exp_key.startswith(str(expiry)):
                    strike_str = str(float(strike))
                    if strike_str in strikes:
                        options = strikes[strike_str]
                        return options[0] if options else None
                    # Try without decimal
                    strike_int = str(int(float(strike)))
                    if strike_int in strikes:
                        options = strikes[strike_int]
                        return options[0] if options else None
        except Exception as e:
            log.debug(f"[Context] Chain search failed: {e}")
        return None

    @staticmethod
    def _calc_spread_pct(bid, ask):
        """Calculate bid-ask spread as a percentage of the midpoint."""
        if not bid or not ask or bid <= 0:
            return None
        mid = (bid + ask) / 2
        return round(((ask - bid) / mid) * 100, 2) if mid > 0 else None
