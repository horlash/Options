"""
Position Sizer — G7 Remediation
Implements Kelly Criterion-based position sizing for single-leg options.

Features:
  - Kelly fraction with configurable fractional multiplier (default: half-Kelly)
  - Strategy-aware sizing (LEAP, WEEKLY, 0DTE)
  - VIX regime adjustments
  - Maximum position size caps
  - Account-aware sizing
"""

import logging
import math

logger = logging.getLogger(__name__)


class PositionSizer:
    """
    Calculate optimal position size for a single-leg option trade.

    F15 NOTE: Kelly criterion uses static win_rate (default 0.55).
    Future: adapt win_rate from actual trade history in paper_trades table.
    F16 NOTE: VIX adjustment is global. Future: per-ticker beta-adjusted sizing.

    Usage:
        ps = PositionSizer(account_size=50000)
        sizing = ps.calculate(opportunity, strategy='LEAP', vix_regime='NORMAL')
        # sizing = {
        #   'contracts': 2,
        #   'total_cost': 1200.00,
        #   'pct_of_account': 2.4,
        #   'kelly_fraction': 0.12,
        #   'method': 'half_kelly',
        #   'adjustments': [...],
        # }
    """

    # --- Strategy-specific risk limits ---
    STRATEGY_LIMITS = {
        'LEAP': {
            'max_pct_per_trade': 5.0,     # Max 5% of account per LEAP position
            'max_contracts': 10,
            'kelly_multiplier': 0.5,       # Half-Kelly (conservative)
            'min_contracts': 1,
        },
        'WEEKLY': {
            'max_pct_per_trade': 3.0,     # Max 3% of account per weekly trade
            'max_contracts': 5,
            'kelly_multiplier': 0.33,      # Third-Kelly (aggressive decay)
            'min_contracts': 1,
        },
        '0DTE': {
            'max_pct_per_trade': 1.5,     # Max 1.5% of account per 0DTE
            'max_contracts': 3,
            'kelly_multiplier': 0.25,      # Quarter-Kelly (max protection)
            'min_contracts': 1,
        },
    }

    def __init__(self, account_size=50000, max_total_exposure_pct=25.0):
        """
        Args:
            account_size: Total account value in dollars
            max_total_exposure_pct: Maximum total portfolio exposure (all positions) as % of account
        """
        self.account_size = account_size
        self.max_total_exposure_pct = max_total_exposure_pct

    def calculate_kelly_fraction(self, win_probability, avg_win_pct, avg_loss_pct):
        """
        Calculate Kelly fraction: f* = (p * b - q) / b
        where:
            p = probability of win
            q = 1 - p (probability of loss)
            b = ratio of avg win to avg loss

        Args:
            win_probability: Estimated probability of profit (0.0 to 1.0)
            avg_win_pct: Expected average win in % (e.g., 50 for +50%)
            avg_loss_pct: Expected average loss in % (e.g., 30 for -30%)

        Returns:
            Kelly fraction (0.0 to 1.0), capped at 0.25
        """
        if avg_loss_pct <= 0 or win_probability <= 0:
            return 0.0

        p = min(1.0, max(0.0, win_probability))
        q = 1.0 - p
        b = avg_win_pct / avg_loss_pct  # Win/loss ratio

        kelly = (p * b - q) / b if b > 0 else 0.0

        # Cap Kelly at 25% to prevent over-betting
        return max(0.0, min(0.25, kelly))

    def estimate_win_probability(self, opportunity, strategy='LEAP'):
        """
        Estimate win probability from opportunity data.
        Uses delta as primary proxy (delta ≈ probability of finishing ITM).
        Adjusts based on technical score and sentiment.
        """
        delta = abs(opportunity.get('delta', 0) or 0)
        opp_score = opportunity.get('opportunity_score', 50)

        if delta > 0:
            # Delta is the best single proxy for ITM probability
            # Adjust slightly based on our scoring
            score_adjustment = (opp_score - 50) / 200  # ±0.25 max adjustment
            win_prob = delta + score_adjustment
        else:
            # No delta — use score as rough proxy
            win_prob = opp_score / 100

        return max(0.05, min(0.95, win_prob))

    def calculate(self, opportunity, strategy='LEAP', vix_regime='NORMAL',
                  current_exposure_pct=0.0):
        """
        Calculate position size for a single-leg option trade.

        Args:
            opportunity: dict with premium, delta, opportunity_score, etc.
            strategy: 'LEAP', 'WEEKLY', '0DTE'
            vix_regime: 'NORMAL', 'ELEVATED', 'CRISIS'
            current_exposure_pct: Current total portfolio exposure as % of account

        Returns:
            dict with contracts, total_cost, kelly_fraction, method, etc.
        """
        limits = self.STRATEGY_LIMITS.get(strategy, self.STRATEGY_LIMITS['LEAP'])
        premium = opportunity.get('premium', 0) or 0
        contract_cost = premium * 100
        adjustments = []

        if contract_cost <= 0:
            return {
                'contracts': 0,
                'total_cost': 0,
                'pct_of_account': 0,
                'kelly_fraction': 0,
                'method': 'error_no_premium',
                'adjustments': ['Premium is zero — cannot size'],
            }

        # 1. Calculate Kelly fraction
        win_prob = self.estimate_win_probability(opportunity, strategy)
        profit_potential = opportunity.get('profit_potential', 30)
        stop_loss = 30 if strategy == 'LEAP' else 40  # From exit_manager defaults

        kelly_raw = self.calculate_kelly_fraction(
            win_probability=win_prob,
            avg_win_pct=profit_potential,
            avg_loss_pct=stop_loss,
        )

        # 2. Apply strategy multiplier (fractional Kelly)
        kelly_adjusted = kelly_raw * limits['kelly_multiplier']
        adjustments.append(f"Kelly: {kelly_raw:.3f} × {limits['kelly_multiplier']} = {kelly_adjusted:.3f}")

        # 3. VIX regime adjustment
        if vix_regime == 'CRISIS':
            kelly_adjusted *= 0.5
            adjustments.append('CRISIS: Halved position size')
        elif vix_regime == 'ELEVATED':
            kelly_adjusted *= 0.75
            adjustments.append('ELEVATED VIX: Reduced position size 25%')

        # 4. Calculate dollar amount and contracts
        dollar_amount = self.account_size * kelly_adjusted
        contracts = max(1, math.floor(dollar_amount / contract_cost))

        # 5. Apply caps
        max_dollar = self.account_size * (limits['max_pct_per_trade'] / 100)
        if contracts * contract_cost > max_dollar:
            contracts = max(1, math.floor(max_dollar / contract_cost))
            adjustments.append(f"Capped at {limits['max_pct_per_trade']}% of account (${max_dollar:.0f})")

        if contracts > limits['max_contracts']:
            contracts = limits['max_contracts']
            adjustments.append(f"Capped at {limits['max_contracts']} contracts")

        # 6. Check total portfolio exposure
        remaining_capacity = self.max_total_exposure_pct - current_exposure_pct
        if remaining_capacity <= 0:
            return {
                'contracts': 0,
                'total_cost': 0,
                'pct_of_account': 0,
                'kelly_fraction': kelly_adjusted,
                'method': 'exposure_limit_reached',
                'adjustments': [f'Total exposure {current_exposure_pct:.1f}% >= limit {self.max_total_exposure_pct}%'],
            }

        max_from_exposure = self.account_size * (remaining_capacity / 100)
        if contracts * contract_cost > max_from_exposure:
            contracts = max(1, math.floor(max_from_exposure / contract_cost))
            adjustments.append(f"Reduced for portfolio exposure (remaining: {remaining_capacity:.1f}%)")

        contracts = max(limits['min_contracts'], contracts)

        total_cost = contracts * contract_cost
        pct_of_account = (total_cost / self.account_size) * 100

        return {
            'contracts': contracts,
            'total_cost': round(total_cost, 2),
            'pct_of_account': round(pct_of_account, 2),
            'kelly_fraction': round(kelly_adjusted, 4),
            'kelly_raw': round(kelly_raw, 4),
            'win_probability': round(win_prob, 3),
            'method': f"fractional_kelly ({limits['kelly_multiplier']}x)",
            'max_pct_per_trade': limits['max_pct_per_trade'],
            'max_contracts': limits['max_contracts'],
            'adjustments': adjustments,
        }
