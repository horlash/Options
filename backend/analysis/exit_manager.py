"""
Exit Manager — G2 Remediation
Provides structured exit logic for single-leg calls and puts.

Strategies:
  - Time-based stops (DTE thresholds)
  - Profit targets (tiered take-profit)
  - Stop-loss levels (max drawdown)
  - Trailing stop logic
  - Earnings/event-based forced exits
"""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ExitManager:
    """
    Generates exit recommendations for a given opportunity.

    F18 NOTE: Trailing stop logic is calculated at scan time as a
    recommendation. It is NOT enforced in real-time by monitor_service.
    Future: integrate trailing-stop monitoring into update_price_snapshots().

    Usage:
        em = ExitManager()
        plan = em.generate_exit_plan(opportunity, strategy='LEAP', vix_regime='NORMAL')
        # plan = {
        #   'stop_loss_pct': -30,
        #   'profit_targets': [{'pct': 30, 'action': 'sell_50pct'}, ...],
        #   'time_stop_dte': 30,
        #   'trailing_stop_pct': 20,
        #   'earnings_rule': 'close_before',
        #   'summary': '...',
        # }
    """

    # --- Strategy-specific defaults ---
    DEFAULTS = {
        'LEAP': {
            'stop_loss_pct': -30,
            'profit_targets': [
                {'pct': 50,  'action': 'sell_33pct', 'label': 'Take 1/3 off at +50%'},
                {'pct': 100, 'action': 'sell_33pct', 'label': 'Take 1/3 off at +100%'},
                {'pct': 200, 'action': 'sell_remaining', 'label': 'Close at +200% (3x)'},
            ],
            'time_stop_dte': 30,    # Exit if < 30 DTE remaining
            'trailing_stop_pct': 25,
            'earnings_rule': 'hold_through',  # LEAPs typically hold through
        },
        'WEEKLY': {
            'stop_loss_pct': -40,
            'profit_targets': [
                {'pct': 30, 'action': 'sell_50pct', 'label': 'Take half at +30%'},
                {'pct': 75, 'action': 'sell_remaining', 'label': 'Close at +75%'},
            ],
            'time_stop_dte': 1,     # Exit day before expiry
            'trailing_stop_pct': 20,
            'earnings_rule': 'close_before',  # ALWAYS exit before earnings
        },
        '0DTE': {
            'stop_loss_pct': -50,
            'profit_targets': [
                {'pct': 20, 'action': 'sell_50pct', 'label': 'Scalp half at +20%'},
                {'pct': 50, 'action': 'sell_remaining', 'label': 'Close at +50%'},
            ],
            'time_stop_dte': 0,     # Same-day, no time stop
            'trailing_stop_pct': 15,
            'earnings_rule': 'close_before',
        },
    }

    def generate_exit_plan(self, opportunity, strategy='LEAP', vix_regime='NORMAL',
                           days_to_earnings=None, iv_percentile=50):
        """
        Generate a structured exit plan for a single-leg option position.

        Args:
            opportunity: dict with keys like premium, strike_price, days_to_expiry, delta, etc.
            strategy: 'LEAP', 'WEEKLY', '0DTE'
            vix_regime: 'NORMAL', 'ELEVATED', 'CRISIS'
            days_to_earnings: int or None
            iv_percentile: 0-100

        Returns:
            dict with exit plan details
        """
        defaults = self.DEFAULTS.get(strategy, self.DEFAULTS['LEAP']).copy()
        plan = {
            'strategy': strategy,
            'stop_loss_pct': defaults['stop_loss_pct'],
            'profit_targets': [t.copy() for t in defaults['profit_targets']],
            'time_stop_dte': defaults['time_stop_dte'],
            'trailing_stop_pct': defaults['trailing_stop_pct'],
            'earnings_rule': defaults['earnings_rule'],
            'adjustments': [],
        }

        premium = opportunity.get('premium', 0)
        dte = opportunity.get('days_to_expiry', 0)

        # --- VIX Regime Adjustments ---
        if vix_regime == 'CRISIS':
            plan['stop_loss_pct'] = max(-20, plan['stop_loss_pct'] + 10)  # Tighter stop
            plan['trailing_stop_pct'] = max(10, plan['trailing_stop_pct'] - 5)
            plan['adjustments'].append('CRISIS: Tightened stops (-20% max loss, trailing 10-20%)')

        elif vix_regime == 'ELEVATED':
            plan['stop_loss_pct'] = max(-25, plan['stop_loss_pct'] + 5)
            plan['adjustments'].append('ELEVATED VIX: Slightly tighter stops')

        # --- IV Percentile Adjustments ---
        iv_pct = float(iv_percentile) if iv_percentile else 50
        if iv_pct > 80:
            # IV is expensive — take profits earlier
            for target in plan['profit_targets']:
                target['pct'] = int(target['pct'] * 0.8)  # Lower targets by 20%
            plan['adjustments'].append(f'High IV ({iv_pct:.0f}%ile): Lowered profit targets 20%')

        elif iv_pct < 20:
            # IV is cheap — let winners run longer
            plan['trailing_stop_pct'] += 5
            plan['adjustments'].append(f'Low IV ({iv_pct:.0f}%ile): Wider trailing stop (+5%)')

        # --- Earnings Proximity ---
        if days_to_earnings is not None and days_to_earnings > 0:
            if days_to_earnings <= 7 and strategy != 'LEAP':
                plan['earnings_rule'] = 'close_before'
                plan['adjustments'].append(
                    f'Earnings in {days_to_earnings}d: CLOSE before event (binary risk)')
            elif days_to_earnings <= 3:
                plan['earnings_rule'] = 'close_before'
                plan['adjustments'].append(
                    f'Earnings in {days_to_earnings}d: CLOSE before event (all strategies)')

        # --- Generate Dollar Amounts ---
        if premium > 0:
            contract_cost = premium * 100
            plan['stop_loss_dollar'] = round(contract_cost * (plan['stop_loss_pct'] / 100), 2)
            for target in plan['profit_targets']:
                target['dollar'] = round(contract_cost * (target['pct'] / 100), 2)

        # --- Summary ---
        plan['summary'] = self._build_summary(plan, dte)

        return plan

    def _build_summary(self, plan, dte):
        """Build human-readable exit plan summary."""
        lines = [f"Exit Plan ({plan['strategy']})"]

        lines.append(f"  Stop Loss: {plan['stop_loss_pct']}%")

        for t in plan['profit_targets']:
            dollar_str = f" (${t['dollar']:.0f})" if 'dollar' in t else ''
            lines.append(f"  Target: {t['label']}{dollar_str}")

        if plan['time_stop_dte'] > 0:
            lines.append(f"  Time Stop: Exit if < {plan['time_stop_dte']} DTE")

        lines.append(f"  Trailing Stop: {plan['trailing_stop_pct']}%")
        lines.append(f"  Earnings Rule: {plan['earnings_rule']}")

        if plan['adjustments']:
            lines.append("  Adjustments:")
            for adj in plan['adjustments']:
                lines.append(f"    - {adj}")

        return "\n".join(lines)

    def should_exit(self, position, current_pnl_pct, dte_remaining,
                    days_to_earnings=None, exit_plan=None):
        """
        Real-time exit signal check.

        Args:
            position: dict with entry details
            current_pnl_pct: Current P&L as percentage (e.g., 35.0 = +35%)
            dte_remaining: Days to expiration remaining
            days_to_earnings: Days until next earnings (or None)
            exit_plan: Pre-generated exit plan dict

        Returns:
            dict with 'should_exit' (bool), 'reason', 'action'
        """
        if not exit_plan:
            return {'should_exit': False, 'reason': 'no_plan', 'action': 'hold'}

        # 1. Stop Loss
        if current_pnl_pct <= exit_plan['stop_loss_pct']:
            return {
                'should_exit': True,
                'reason': f"Stop loss hit ({current_pnl_pct:.1f}% <= {exit_plan['stop_loss_pct']}%)",
                'action': 'sell_all'
            }

        # 2. Time Stop
        if exit_plan['time_stop_dte'] > 0 and dte_remaining <= exit_plan['time_stop_dte']:
            return {
                'should_exit': True,
                'reason': f"Time stop ({dte_remaining} DTE <= {exit_plan['time_stop_dte']})",
                'action': 'sell_all'
            }

        # 3. Profit Targets (check in order)
        for target in exit_plan.get('profit_targets', []):
            if current_pnl_pct >= target['pct']:
                return {
                    'should_exit': True,
                    'reason': f"Profit target hit ({current_pnl_pct:.1f}% >= {target['pct']}%)",
                    'action': target['action']
                }

        # 4. Earnings proximity
        if (days_to_earnings is not None and days_to_earnings <= 1 and
                exit_plan.get('earnings_rule') == 'close_before'):
            return {
                'should_exit': True,
                'reason': f"Earnings tomorrow — close_before rule",
                'action': 'sell_all'
            }

        return {'should_exit': False, 'reason': 'hold', 'action': 'hold'}
