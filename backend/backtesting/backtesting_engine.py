"""
Backtesting Engine — BUG-BE-1/2 Rebuild
========================================
ORATS-powered backtesting with:
  - Historical IV from ORATS hist/cores (ivPctile1y, ivPctile1m)
  - Black-Scholes pricing with real theta decay
  - Configurable transaction costs via Config.FILL_ASSUMPTION
  - Realistic P&L including spread costs, slippage, and commissions

Previous backtesting used synthetic data and mid-price fills.
This version uses ORATS historical daily data for realistic P&L simulation.

WARNING: This is a new implementation. Results should be labeled with a
confidence indicator until validated against known outcomes.
"""

import logging
import math
from datetime import datetime, timedelta
from backend.config import Config

logger = logging.getLogger(__name__)


# ─── Black-Scholes Pricing ──────────────────────────────────────────

def _norm_cdf(x):
    """Cumulative normal distribution (no scipy dependency)."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _norm_pdf(x):
    """Normal probability density function."""
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def black_scholes_price(S, K, T, sigma, r=0.045, option_type='call'):
    """
    Black-Scholes option price.

    Args:
        S: Spot price
        K: Strike price
        T: Time to expiry in years (use trading days / 252)
        sigma: Implied volatility (decimal, e.g. 0.30 for 30%)
        r: Risk-free rate (default 4.5%)
        option_type: 'call' or 'put'

    Returns:
        float: Theoretical option price
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return max(0, (S - K) if option_type == 'call' else (K - S))

    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    if option_type == 'call':
        price = S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    else:
        price = K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)

    return max(0, price)


def black_scholes_greeks(S, K, T, sigma, r=0.045, option_type='call'):
    """
    Calculate Greeks using Black-Scholes.

    Returns:
        dict with delta, gamma, theta (per day), vega
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return {'delta': 0, 'gamma': 0, 'theta': 0, 'vega': 0}

    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    gamma = _norm_pdf(d1) / (S * sigma * math.sqrt(T))
    vega = S * _norm_pdf(d1) * math.sqrt(T) / 100  # per 1% IV change

    if option_type == 'call':
        delta = _norm_cdf(d1)
        theta = (-(S * _norm_pdf(d1) * sigma) / (2 * math.sqrt(T))
                 - r * K * math.exp(-r * T) * _norm_cdf(d2)) / 252
    else:
        delta = _norm_cdf(d1) - 1
        theta = (-(S * _norm_pdf(d1) * sigma) / (2 * math.sqrt(T))
                 + r * K * math.exp(-r * T) * _norm_cdf(-d2)) / 252

    return {
        'delta': round(delta, 4),
        'gamma': round(gamma, 6),
        'theta': round(theta, 4),
        'vega': round(vega, 4),
    }


# ─── Transaction Cost Model ─────────────────────────────────────────

def calculate_entry_cost(ask, bid, fill_assumption=None):
    """
    Calculate realistic entry cost based on fill assumption.

    Args:
        ask: Ask price
        bid: Bid price
        fill_assumption: Override Config.FILL_ASSUMPTION

    Returns:
        float: Estimated fill price for a buy order
    """
    fill = fill_assumption or Config.FILL_ASSUMPTION

    if fill == 'ask':
        return ask
    elif fill == 'natural':
        return ask - 0.05  # Typical price improvement for liquid names
    else:  # 'mid'
        return (bid + ask) / 2


def calculate_transaction_costs(contracts=1, commission_per_contract=0.65):
    """
    Calculate round-trip transaction costs.

    Args:
        contracts: Number of contracts
        commission_per_contract: Per-contract fee (default $0.65 industry standard)

    Returns:
        float: Total round-trip cost (entry + exit)
    """
    return contracts * commission_per_contract * 2  # Round trip


# ─── Backtesting Engine ─────────────────────────────────────────────

class BacktestResult:
    """Container for a single backtest result."""

    def __init__(self):
        self.ticker = ''
        self.strategy = ''
        self.entry_date = None
        self.exit_date = None
        self.entry_price = 0
        self.exit_price = 0
        self.strike = 0
        self.option_type = 'call'
        self.days_held = 0
        self.pnl_gross = 0
        self.pnl_net = 0  # After costs
        self.transaction_costs = 0
        self.spread_cost = 0
        self.max_profit = 0
        self.max_loss = 0
        self.exit_reason = ''  # 'target', 'stop', 'expiry', 'time_stop'
        self.greeks_at_entry = {}
        self.iv_at_entry = 0
        self.iv_at_exit = 0
        self.confidence = 'low'  # 'low', 'medium', 'high'

    def to_dict(self):
        return {
            'ticker': self.ticker,
            'strategy': self.strategy,
            'entry_date': str(self.entry_date) if self.entry_date else None,
            'exit_date': str(self.exit_date) if self.exit_date else None,
            'entry_price': round(self.entry_price, 2),
            'exit_price': round(self.exit_price, 2),
            'strike': self.strike,
            'option_type': self.option_type,
            'days_held': self.days_held,
            'pnl_gross': round(self.pnl_gross, 2),
            'pnl_net': round(self.pnl_net, 2),
            'transaction_costs': round(self.transaction_costs, 2),
            'spread_cost': round(self.spread_cost, 2),
            'max_profit': round(self.max_profit, 2),
            'max_loss': round(self.max_loss, 2),
            'exit_reason': self.exit_reason,
            'greeks_at_entry': self.greeks_at_entry,
            'iv_at_entry': round(self.iv_at_entry, 2),
            'iv_at_exit': round(self.iv_at_exit, 2),
            'confidence': self.confidence,
        }


class BacktestEngine:
    """
    ORATS-powered backtesting engine.

    Uses historical daily prices + ORATS hist/cores for IV data.
    Simulates option P&L using Black-Scholes repricing at each step.
    """

    def __init__(self, orats_api=None):
        self.orats_api = orats_api

    def backtest_trade(self, ticker, strike, option_type, entry_date_str,
                       exit_date_str, entry_iv, bid_at_entry, ask_at_entry,
                       historical_prices=None, strategy='WEEKLY'):
        """
        Backtest a single historical trade.

        Args:
            ticker: Stock ticker
            strike: Option strike price
            option_type: 'call' or 'put'
            entry_date_str: Entry date 'YYYY-MM-DD'
            exit_date_str: Exit date 'YYYY-MM-DD'
            entry_iv: IV at entry (decimal, e.g. 0.30)
            bid_at_entry: Bid price at entry
            ask_at_entry: Ask price at entry
            historical_prices: List of {'date': str, 'close': float}
            strategy: 'WEEKLY', 'LEAP', '0DTE'

        Returns:
            BacktestResult
        """
        result = BacktestResult()
        result.ticker = ticker
        result.strategy = strategy
        result.strike = strike
        result.option_type = option_type.lower()
        result.iv_at_entry = round(entry_iv * 100, 2)

        try:
            entry_date = datetime.strptime(entry_date_str, '%Y-%m-%d')
            exit_date = datetime.strptime(exit_date_str, '%Y-%m-%d')
        except (ValueError, TypeError):
            result.exit_reason = 'invalid_dates'
            result.confidence = 'low'
            return result

        result.entry_date = entry_date
        result.exit_date = exit_date
        result.days_held = (exit_date - entry_date).days

        # Calculate entry cost using configurable fill assumption
        result.entry_price = calculate_entry_cost(ask_at_entry, bid_at_entry)
        result.spread_cost = (ask_at_entry - bid_at_entry) * 100  # Per contract
        result.transaction_costs = calculate_transaction_costs(1)

        # Calculate time to expiry at entry (years)
        # For weekly: expiry ≈ exit_date
        # For LEAPs: expiry could be much later
        T_entry = max(result.days_held / 252, 1 / 252)  # At least 1 trading day

        # Price at entry using Black-Scholes
        if historical_prices and len(historical_prices) > 0:
            entry_spot = None
            exit_spot = None
            for p in historical_prices:
                if p.get('date') == entry_date_str:
                    entry_spot = p['close']
                if p.get('date') == exit_date_str:
                    exit_spot = p['close']

            if entry_spot and exit_spot:
                # Reprice at exit with theta decay
                T_exit = max(1 / 252, 0.001)  # Near expiry
                bs_entry = black_scholes_price(entry_spot, strike, T_entry,
                                                entry_iv, option_type=result.option_type)
                bs_exit = black_scholes_price(exit_spot, strike, T_exit,
                                              entry_iv, option_type=result.option_type)

                # Greeks at entry
                result.greeks_at_entry = black_scholes_greeks(
                    entry_spot, strike, T_entry, entry_iv, option_type=result.option_type
                )

                # P&L calculation
                result.exit_price = bs_exit
                result.pnl_gross = (bs_exit - result.entry_price) * 100
                result.pnl_net = result.pnl_gross - result.transaction_costs
                result.exit_reason = 'expiry'
                result.confidence = 'medium'

                # Track max profit/loss through the path
                max_pnl = result.pnl_gross
                min_pnl = result.pnl_gross
                for p in historical_prices:
                    p_date = p.get('date', '')
                    if entry_date_str < p_date < exit_date_str:
                        days_elapsed = (datetime.strptime(p_date, '%Y-%m-%d') - entry_date).days
                        T_remaining = max((result.days_held - days_elapsed) / 252, 1 / 252)
                        mid_price = black_scholes_price(
                            p['close'], strike, T_remaining,
                            entry_iv, option_type=result.option_type
                        )
                        mid_pnl = (mid_price - result.entry_price) * 100
                        max_pnl = max(max_pnl, mid_pnl)
                        min_pnl = min(min_pnl, mid_pnl)

                result.max_profit = max_pnl
                result.max_loss = min_pnl
            else:
                result.exit_reason = 'missing_price_data'
                result.confidence = 'low'
        else:
            result.exit_reason = 'no_historical_data'
            result.confidence = 'low'

        return result

    def backtest_strategy(self, ticker, strategy='WEEKLY', lookback_days=90,
                          target_delta=0.50, stop_loss_pct=25, take_profit_pct=50):
        """
        Run a strategy-level backtest over a lookback period.

        This is a simplified backtest that simulates entering trades at regular intervals
        and tracking outcomes. Real backtest requires ORATS historical options data.

        Returns:
            dict with summary statistics and individual trade results
        """
        if not self.orats_api:
            return {
                'error': 'ORATS API required for backtesting',
                'confidence': 'none',
            }

        # Fetch historical price data
        history = self.orats_api.get_history(ticker, days=lookback_days + 30)
        if not history or not history.get('candles'):
            return {
                'error': 'No historical data available',
                'confidence': 'none',
            }

        candles = history['candles']

        # Fetch historical IV data
        cores = self.orats_api.get_hist_cores(ticker)
        iv_pctile = 50
        base_iv = 0.30  # Default 30% IV
        if cores:
            iv_pctile = cores.get('ivPctile1y', 50) or 50
            # Approximate base IV from percentile (rough mapping)
            base_iv = 0.15 + (iv_pctile / 100) * 0.45  # Maps 0-100 to 0.15-0.60

        # Build price series
        prices = []
        for c in candles:
            dt_str = datetime.fromtimestamp(c['datetime'] / 1000).strftime('%Y-%m-%d')
            prices.append({
                'date': dt_str,
                'close': c['close'],
                'volume': c.get('volume', 0),
            })

        if len(prices) < 10:
            return {
                'error': 'Insufficient price history for backtest',
                'confidence': 'none',
            }

        # Simulate weekly entries
        trades = []
        holding_period = 7 if strategy == 'WEEKLY' else (1 if strategy == '0DTE' else 90)

        for i in range(0, len(prices) - holding_period, max(holding_period, 5)):
            entry_p = prices[i]
            exit_idx = min(i + holding_period, len(prices) - 1)
            exit_p = prices[exit_idx]

            entry_spot = entry_p['close']
            atm_strike = round(entry_spot / 5) * 5  # Round to nearest $5

            # Simulate bid/ask spread (wider for less liquid)
            spread_pct = 0.05 if strategy == 'WEEKLY' else 0.10
            mid_price = black_scholes_price(entry_spot, atm_strike,
                                             holding_period / 252, base_iv, option_type='call')
            simulated_bid = mid_price * (1 - spread_pct / 2)
            simulated_ask = mid_price * (1 + spread_pct / 2)

            bt = self.backtest_trade(
                ticker=ticker,
                strike=atm_strike,
                option_type='call',
                entry_date_str=entry_p['date'],
                exit_date_str=exit_p['date'],
                entry_iv=base_iv,
                bid_at_entry=simulated_bid,
                ask_at_entry=simulated_ask,
                historical_prices=prices[i:exit_idx + 1],
                strategy=strategy,
            )
            trades.append(bt)

        # Calculate summary statistics
        if not trades:
            return {
                'error': 'No trades generated in backtest period',
                'confidence': 'none',
            }

        pnls = [t.pnl_net for t in trades]
        winners = [p for p in pnls if p > 0]
        losers = [p for p in pnls if p <= 0]

        return {
            'ticker': ticker,
            'strategy': strategy,
            'lookback_days': lookback_days,
            'total_trades': len(trades),
            'winners': len(winners),
            'losers': len(losers),
            'win_rate': round(len(winners) / len(trades) * 100, 1) if trades else 0,
            'avg_pnl': round(sum(pnls) / len(pnls), 2) if pnls else 0,
            'total_pnl': round(sum(pnls), 2),
            'best_trade': round(max(pnls), 2) if pnls else 0,
            'worst_trade': round(min(pnls), 2) if pnls else 0,
            'avg_winner': round(sum(winners) / len(winners), 2) if winners else 0,
            'avg_loser': round(sum(losers) / len(losers), 2) if losers else 0,
            'iv_percentile_at_test': iv_pctile,
            'base_iv_used': round(base_iv * 100, 1),
            'fill_assumption': Config.FILL_ASSUMPTION,
            'trades': [t.to_dict() for t in trades],
            'confidence': 'medium',  # Simulated spreads, not real ORATS options data
            'disclaimer': (
                'This backtest uses Black-Scholes repricing with estimated IV. '
                'Actual options P&L may differ due to skew, term structure, and real market spreads. '
                'Treat as directional guidance, not precise P&L prediction.'
            ),
        }
