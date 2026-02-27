from datetime import datetime, timedelta
import logging
from backend.config import Config

logger = logging.getLogger(__name__)

class OptionsAnalyzer:
    def __init__(self):
        self.min_leap_days = Config.MIN_LEAP_DAYS
        self.max_investment = Config.MAX_INVESTMENT_PER_POSITION
        self.min_profit_potential = Config.MIN_PROFIT_POTENTIAL
        # QW-8: Removed duplicate min_profit_potential assignment

    def parse_options_chain(self, options_data, current_price, min_profit_override=None):
        """
        Parse options chain data and filter for LEAPs
        
        Args:
            options_data: Options chain data from TD Ameritrade/Schwab
            current_price: Current stock price
            min_profit_override: Optional override for minimum profit potential (e.g. 30 for LEAPs)
        
        Returns:
            List of LEAP opportunities
        """
        if not options_data:
            return []
        
        opportunities = []
        symbol = options_data.get('symbol', '')
        
        # Dynamic Max Investment Logic
        # Indices (SPX, NDX, RUT) are expensive, allow up to $50k
        # Standard stocks get the configured safe limit (default $2k)
        if symbol.startswith('$') or symbol in ['SPX', 'NDX', 'RUT', 'VIX']:
            local_max_investment = 50000
        else:
            local_max_investment = self.max_investment
            
        # Process call options
        call_map = options_data.get('callExpDateMap', {}) or {}
        for exp_date_str, strikes in call_map.items():
            results = self._process_expiration(
                strikes, 
                exp_date_str, 
                'Call', 
                current_price,
                local_max_investment,
                symbol=symbol,
                min_profit_override=min_profit_override
            )
            if results:
                opportunities.extend(results)
        
        # Process put options
        put_map = options_data.get('putExpDateMap', {}) or {}
        for exp_date_str, strikes in put_map.items():
            results = self._process_expiration(
                strikes, 
                exp_date_str, 
                'Put', 
                current_price,
                local_max_investment,
                symbol=symbol,
                min_profit_override=min_profit_override
            )
            if results:
                opportunities.extend(results)
        
        return opportunities
    
    def _process_expiration(self, strikes, exp_date_str, option_type, current_price, max_investment_limit=None, symbol='', min_profit_override=None):
        """
        Process options for a specific expiration date
        
        Args:
            strikes: Strike price data
            exp_date_str: Expiration date string
            option_type: 'Call' or 'Put'
            current_price: Current stock price
            max_investment_limit: Custom limit for this batch (defaults to config)
            symbol: Ticker symbol (for exemptions)
            min_profit_override: Optional profit floor override
        
        Returns:
            List of opportunities for this expiration
        """
        opportunities = []
        
        # Use provided limit or fallback to global config
        limit = max_investment_limit if max_investment_limit is not None else self.max_investment
        
        # Parse expiration date
        try:
            # Format: "2024-12-20:365"
            exp_date = datetime.strptime(exp_date_str.split(':')[0], '%Y-%m-%d')
        except:
            return opportunities
        
        # Calculate days to expiry
        days_to_expiry = (exp_date - datetime.now()).days
        
        # NOTE: Reduced LEAP filter check here as it blocks weekly scans
        # The service layer handles expiration filtering (daily/weekly vs LEAPs)
        # if days_to_expiry < self.min_leap_days:
        #    return opportunities
        
        logger.debug(f"   Processing {len(strikes)} strikes for {exp_date_str} ({days_to_expiry} days)")
        rejected_reasons = []
        
        # Process each strike price
        for strike_str, option_list in strikes.items():
            strike_price = float(strike_str)
            
            # Get the first option contract (usually the most liquid)
            if not option_list:
                continue
            
            option = option_list[0]
            
            # Extract option details
            # Extract option details
            ask = option.get('ask', 0)
            bid = option.get('bid', 0)
            last = option.get('last', 0)
            
            # F8 FIX: Use ask price (worst-case buy fill) for profit calc
            # Mark price (midpoint) understates real entry cost
            if ask > 0 and bid > 0:
                premium = ask  # Worst-case fill for buyer
            else:
                premium = last if last > 0 else ask

            volume = option.get('totalVolume', 0)
            open_interest = option.get('openInterest', 0)
            
            # Skip if no premium or no liquidity
            if premium <= 0 or open_interest < 10:
                if premium <= 0:
                    rejected_reasons.append(f"Strike {strike_price}: No premium")
                else:
                    rejected_reasons.append(f"Strike {strike_price}: Low OI ({open_interest})")
                continue
            
            # Extract Greeks early for filtering logic
            delta = abs(option.get('delta', 0))
            
            # [PROFIT-TAKING STRATEGY] Delta Range Filter
            # NOTE: Only for LEAPs! Weekly/daily options need full delta range for gamma walls
            # Target: 0.50 - 0.80 (good probability + leverage)
            # Eliminate: <0.50 (lotto tickets), >0.80 (deep ITM stock replacement)
            
            # --- TWO-TIER EXEMPTION LOGIC ---
            clean_symbol = symbol.upper().replace('$', '')
            
            # LIST A: Non-Corporate (Indices + ETFs) -> Exempt from Fundamental Quality Checks (handled in Service)
            # LIST B: Pricing Anomalies (Indices Only) -> Exempt from Profit Math (Futures/Cash Settled)
            pricing_anomaly_list = ['VIX', 'SPX', 'NDX', 'RUT', 'DJI']
            is_pricing_anomaly = clean_symbol in pricing_anomaly_list
            
            is_leap = days_to_expiry >= self.min_leap_days
            
            # DELTA CHECK: Foolproof Three-Layer Defense
            # Layer 1: Hard floor 0.15 — blocks true lotto tickets (safety net, rarely triggers)
            # Layer 2: Hard ceiling 0.80 — blocks deep ITM stock replacement
            # Layer 3: 30% profit floor (downstream) — creates effective delta floor ~0.38
            #          because a 15% stock move can't generate 30%+ returns on delta <0.38
            # Old filter: delta 0.50-0.80 conflicted with $2000 cost cap for stocks >$100
            if is_leap and not is_pricing_anomaly:
                if delta > 0.80:
                    rejected_reasons.append(f"Strike {strike_price}: Delta too high ({delta:.2f} > 0.80 - deep ITM, use stock instead)")
                    continue
                if delta < 0.15:
                    rejected_reasons.append(f"Strike {strike_price}: Delta too low ({delta:.2f} < 0.15 - extreme lotto ticket)")
                    continue
            
            # Calculate contract cost (premium * 100 shares)
            contract_cost = premium * 100
            
            # [PROFIT-TAKING STRATEGY] Single Investment Limit
            # No exceptions - keeps costs reasonable for profit-taking plays
            effective_limit = limit  # Always $2,000 (or configured limit)
            
            # Filter by max investment
            if contract_cost > effective_limit:
                rejected_reasons.append(f"Strike {strike_price}: Too expensive (${contract_cost:.0f} > ${effective_limit:.0f})")
                continue
            
            # Calculate profit potential
            profit_potential = self._calculate_profit_potential(
                option_type,
                strike_price,
                premium,
                current_price
            )
            
            # Filter by minimum profit potential
            # [FIX] Bypass Profit Filter for Pricing Anomalies (VIX/SPX Futures)
            # NOTE: ETFs (SPY/QQQ) are NOT exempt. They must show math viability.
            # Determine effective profit floor
            profit_floor = min_profit_override if min_profit_override is not None else self.min_profit_potential
            
            if not is_pricing_anomaly and profit_potential < profit_floor:
                rejected_reasons.append(f"Strike {strike_price}: Low profit potential ({profit_potential:.1f}% < {profit_floor}%)")
                continue
            
            # Extract Greeks if available
            # Extract Greeks if available
            greeks = {
                'delta': option.get('delta', 0),
                'gamma': option.get('gamma', 0),
                'theta': option.get('theta', 0),
                'vega': option.get('vega', 0),
                'implied_volatility': option.get('volatility', 0)
            }
            
            # [PROFIT-TAKING STRATEGY] Strategy Classification
            # Delta 0.50-0.80 = Profit-taking sweet spot (LEAPs only)
            is_leap = days_to_expiry >= self.min_leap_days
            strategy_tag = 'profit_taking' if is_leap else 'standard'
            leverage_ratio = 0
            # QW-10: Put break-even fix — was always strike + premium
            if option_type == 'Call':
                break_even = strike_price + premium
            else:  # Put
                break_even = strike_price - premium
            
            # Calculate leverage for informational purposes
            if premium > 0:
                leverage_ratio = current_price / premium
            
            # Note: Deep ITM check removed - delta filter already excludes >0.80
            
            opportunities.append({
                'option_type': option_type,
                'strike_price': strike_price,
                'expiration_date': exp_date,
                'days_to_expiry': days_to_expiry,
                'premium': premium,
                'bid': bid,
                'contract_cost': contract_cost,
                'volume': volume,
                'open_interest': open_interest,
                'profit_potential': profit_potential,
                'strategy': strategy_tag,
                'leverage_ratio': round(leverage_ratio, 2),
                'break_even': round(break_even, 2),
                **greeks
            })
        
        # P0-1: Debug Summary — OUTSIDE the for-loop (was indented inside, causing early return)
        if rejected_reasons:
            logger.debug(f"   Rejected {len(rejected_reasons)} options. Top reasons:")
            for reason in rejected_reasons[:5]:
                logger.debug(f"     - {reason}")
        
        logger.debug(f"   Accepted {len(opportunities)} opportunities for {exp_date_str}")
        
        return opportunities
    
    def _calculate_profit_potential(self, option_type, strike_price, premium, current_price):
        """
        Calculate potential profit percentage for PROFIT-TAKING strategy.
        
        Strategy: Buy LEAPs, sell when stock moves 15-20%, capture appreciation
        Focus: % return on investment (not absolute dollars)
        
        Args:
            option_type: 'Call' or 'Put'
            strike_price: Option strike price
            premium: Option premium paid
            current_price: Current stock price
        
        Returns:
            Profit potential percentage
        """
        # [PROFIT-TAKING] Conservative assumption: 15% stock move
        # (vs previous 20% which favored deep ITM)
        
        if option_type == 'Call':
            # Bullish scenario: 15% rise over LEAP period
            target_price = current_price * 1.15
            
            # Calculate intrinsic value at target
            intrinsic_value = max(0, target_price - strike_price)
            
            # Profit = intrinsic value gain - premium paid
            profit = intrinsic_value - premium
            
        else:  # PUT
            # Bearish scenario: 15% drop
            target_price = current_price * 0.85
            
            # Calculate intrinsic value at target
            intrinsic_value = max(0, strike_price - target_price)
            
            # Profit = intrinsic value gain - premium paid
            profit = intrinsic_value - premium
        
        # [KEY CHANGE] Return PERCENTAGE, not absolute dollars
        # This favors cheaper ATM/OTM options with high % upside
        if premium > 0:
            profit_percentage = (profit / premium) * 100
        else:
            profit_percentage = 0
        
        return max(0, profit_percentage)
    
    def calculate_liquidity_score(self, opportunity):
        """
        Calculate liquidity score based on volume and open interest
        
        Args:
            opportunity: Opportunity dictionary
        
        Returns:
            Liquidity score (0-100)
        """
        volume = opportunity.get('volume', 0)
        open_interest = opportunity.get('open_interest', 0)
        
        # Score based on open interest (more important for LEAPs)
        oi_score = min(100, (open_interest / 1000) * 100)
        
        # Score based on volume
        vol_score = min(100, (volume / 100) * 100)
        
        # Weighted average (open interest more important for LEAPs)
        liquidity_score = (oi_score * 0.7) + (vol_score * 0.3)
        
        return liquidity_score
    
    def calculate_skew(self, options_data, current_price):
        """
        Calculate Volatility Skew (Bullish vs Bearish Sentiment).
        Skew = (OTM Call IV - OTM Put IV) / ATM IV
        
        We look for specific Moneyness roughly 6 months out (or first available LEAP):
        - ATM: Strike ~ 1.00x Price
        - OTM Call: Strike ~ 1.10x Price (10% OTM)
        - OTM Put: Strike ~ 0.90x Price (10% OTM)
        
        Returns:
            skew_percent: Raw skew value (e.g., 0.05 for 5%)
            skew_score: Normalized 0-100 score (50 is neutral, >50 bullish)
        """
        if not options_data or not current_price:
            return 0.0, 50.0
            
        call_map = options_data.get('callExpDateMap', {})
        put_map = options_data.get('putExpDateMap', {})
        
        # Find a suitable expiration (preferably earliest LEAP or furthest standard)
        # We just grab the first available expiration key to keep it fast, 
        # as Skew tends to be correlated across the term structure.
        if not call_map:
            return 0.0, 50.0
            
        # Get first expiration
        target_exp = list(call_map.keys())[0]
        call_strikes = call_map.get(target_exp, {})
        put_strikes = put_map.get(target_exp, {})
        
        if not call_strikes or not put_strikes:
            return 0.0, 50.0
            
        # Helper to find IV for a target price
        def get_iv(strikes_map, target_strike_price):
            closest_strike = None
            min_dist = float('inf')
            
            for strike_str in strikes_map.keys():
                try:
                    s = float(strike_str)
                    dist = abs(s - target_strike_price)
                    if dist < min_dist:
                        min_dist = dist
                        closest_strike = strikes_map[strike_str]
                except:
                    continue
            
            if closest_strike and closest_strike[0].get('volatility', 0) > 0:
                # return IV (schwab usually returns percentage or decimal, ensure decimal)
                iv = closest_strike[0].get('volatility')
                return iv / 100.0 if iv > 4.0 else iv # Handle if Schwab sends 25.0 instead of 0.25
            return None

        atm_iv = get_iv(call_strikes, current_price) # Use Calls for ATM
        otm_call_iv = get_iv(call_strikes, current_price * 1.10)
        otm_put_iv = get_iv(put_strikes, current_price * 0.90)
        
        if not atm_iv or not otm_call_iv or not otm_put_iv:
            return 0.0, 50.0
            
        # Calculate Skew
        # If Calls are 30% IV and Puts are 20% IV -> Positive Skew (Bullish)
        skew_raw = (otm_call_iv - otm_put_iv) / atm_iv
        
        # Normalize to Score (0-100)
        # Range expectation: -0.2 to +0.2
        # -0.2 (Bearish) -> Score 0
        # 0.0 (Neutral) -> Score 50
        # +0.2 (Bullish) -> Score 100
        
        skew_score = 50 + (skew_raw * 250) # Scale factor
        skew_score = max(0, min(100, skew_score))
        
        return skew_raw, skew_score

    def rank_opportunities(self, opportunities, technical_score, sentiment_score, skew_score=50, strategy="LEAP", current_price=None, fundamental_score=50, greeks_context=None, vix_regime='NORMAL', iv_percentile=50, days_to_earnings=None, implied_earnings_move=None):
        """
        Rank and score opportunities with Strategy-Specific Logic.
        Strategies: 'LEAP', 'WEEKLY', '0DTE'
        
        G4:  LEAP weights now sum to 1.00 (was 0.90)
        G6:  Greeks factor into scoring (delta confidence, theta efficiency, gamma risk)
        G10: Strategy-specific delta ranges enforce tighter bands
        G11: Open Interest minimum filter (per strategy)
        G12: Volume confirmation gate (per strategy)
        G13: Bid-ask spread filter (per strategy)
        G19: Score normalization — all sub-scores clamped to 0-100 before weighting
        G20: Audit trail — score_breakdown dict on every opportunity
        """
        scored_opportunities = []
        
        # --- G10: STRATEGY-SPECIFIC DELTA RANGES ---
        DELTA_RANGES = {
            'LEAP':   (0.40, 0.75),   # Was 0.15-0.80 — tightened for quality
            'WEEKLY': (0.30, 0.70),   # Swing trade range
            '0DTE':   (0.35, 0.60),   # Tight ATM focus for gamma plays
        }
        delta_min, delta_max = DELTA_RANGES.get(strategy, (0.15, 0.80))
        
        # --- G11: STRATEGY-SPECIFIC OI MINIMUMS ---
        OI_MINIMUMS = {
            'LEAP':   100,
            'WEEKLY': 500,
            '0DTE':   1000,
        }
        oi_min = OI_MINIMUMS.get(strategy, 10)
        
        # --- G12: STRATEGY-SPECIFIC VOLUME MINIMUMS ---
        VOL_MINIMUMS = {
            'LEAP':   10,
            'WEEKLY': 50,
            '0DTE':   100,
        }
        vol_min = VOL_MINIMUMS.get(strategy, 0)
        
        # --- G13: STRATEGY-SPECIFIC BID-ASK SPREAD LIMITS ---
        SPREAD_LIMITS = {
            'LEAP':   0.10,   # 10% max spread
            'WEEKLY': 0.05,   # 5% max spread
            '0DTE':   0.03,   # 3% max spread
        }
        spread_limit = SPREAD_LIMITS.get(strategy, 0.15)
        
        # --- G4: DEFINE WEIGHTS BASED ON STRATEGY (all sum to 1.00) ---
        if strategy in ["WEEKLY", "0DTE"]:
            # Short Term: Momentum & Flow are King
            W_TECH   = 0.40    # Technicals (Momentum)
            W_SKEW   = 0.15    # Flow/Skew/Gamma
            W_SENT   = 0.15    # News/Sentiment
            W_GREEKS = 0.15    # G6: Greeks quality score (NEW)
            W_PROF   = 0.05    # Profit Potential
            W_LIQ    = 0.10    # Liquidity
            # Sum: 0.40 + 0.15 + 0.15 + 0.15 + 0.05 + 0.10 = 1.00 ✓
            PROFIT_TARGET = 50 if strategy == "WEEKLY" else 30
        else:
            # LEAP (Long Term): Fundamentals & Value
            # G4 FIX: Was 0.90 total — now includes W_GREEKS to reach 1.00
            W_TECH   = 0.30    # Technicals (was 0.35)
            W_SENT   = 0.20    # Sentiment (was 0.25)
            W_SKEW   = 0.10    # Skew (was 0.15)
            W_GREEKS = 0.15    # G6: Greeks quality score (NEW — fills the 0.10 gap + rebalance)
            W_PROF   = 0.05    # Profit Potential
            W_LIQ    = 0.10    # Liquidity
            W_FUND   = 0.10    # Fundamental quality (from scanner)
            # Sum: 0.30 + 0.20 + 0.10 + 0.15 + 0.05 + 0.10 + 0.10 = 1.00 ✓
            PROFIT_TARGET = 200

        for opp in opportunities:
            # --- G10: Delta Range Filter ---
            delta_val = abs(opp.get('delta', 0) or 0)
            if delta_val > 0 and (delta_val < delta_min or delta_val > delta_max):
                opp['rejection_reason'] = f"Delta {delta_val:.2f} outside {strategy} range [{delta_min}-{delta_max}]"
                continue
            
            # --- G11: Open Interest Minimum Filter ---
            oi = opp.get('open_interest', 0) or 0
            if oi < oi_min:
                opp['rejection_reason'] = f"OI {oi} < {strategy} minimum {oi_min}"
                continue
            
            # --- G12: Volume Confirmation Gate ---
            opt_volume = opp.get('volume', 0) or 0
            if opt_volume < vol_min:
                opp['rejection_reason'] = f"Volume {opt_volume} < {strategy} minimum {vol_min}"
                continue
            
            # --- G13: Bid-Ask Spread Filter ---
            bid = opp.get('bid', 0) or 0
            ask = opp.get('premium', 0) or 0  # 'premium' is mid price (ask used as proxy when no ask field)
            if 'ask' in opp and opp['ask']:
                ask = opp['ask']
            mid = (bid + ask) / 2 if (bid + ask) > 0 else 0
            spread_pct = (ask - bid) / mid if mid > 0 else 0
            if spread_pct > spread_limit and bid > 0:
                opp['rejection_reason'] = f"Spread {spread_pct:.1%} > {strategy} limit {spread_limit:.0%}"
                continue
            
            # --- G19: Normalize all sub-scores to 0-100 ---
            norm_tech = max(0.0, min(100.0, float(technical_score)))
            norm_sent = max(0.0, min(100.0, float(sentiment_score)))
            norm_skew = max(0.0, min(100.0, float(skew_score)))
            norm_fund = max(0.0, min(100.0, float(fundamental_score)))
            
            # Calculate liquidity score
            liquidity_score = self.calculate_liquidity_score(opp)
            norm_liq = max(0.0, min(100.0, float(liquidity_score)))
            
            # --- PROFIT SCORE NORMALIZATION ---
            profit_score = min(100, (opp['profit_potential'] / PROFIT_TARGET) * 100) if PROFIT_TARGET > 0 else 0
            norm_prof = max(0.0, min(100.0, float(profit_score)))
            
            # --- G6: GREEKS QUALITY SCORE (0-100) ---
            greeks_score = self._calculate_greeks_score(opp, strategy)
            norm_greeks = max(0.0, min(100.0, float(greeks_score)))
            
            # --- WEIGHTED SCORE ---
            if strategy == "LEAP":
                opportunity_score = (
                    norm_tech   * W_TECH +
                    norm_sent   * W_SENT +
                    norm_skew   * W_SKEW +
                    norm_greeks * W_GREEKS +
                    norm_prof   * W_PROF +
                    norm_liq    * W_LIQ +
                    norm_fund   * W_FUND
                )
            else:
                opportunity_score = (
                    norm_tech   * W_TECH +
                    norm_sent   * W_SENT +
                    norm_skew   * W_SKEW +
                    norm_greeks * W_GREEKS +
                    norm_prof   * W_PROF +
                    norm_liq    * W_LIQ
                )

            # --- STRATEGY BONUSES / PENALTIES ---
            bonus_penalty = 0
            
            # 1. Delta Sweet Spot Bonus (LEAP ONLY)
            if strategy == "LEAP":
                if 0.60 <= delta_val <= 0.75:
                    bonus_penalty += 5  # Reduced from 10 — now part of Greeks score too

            # 2. Gamma Wall Bonus (0DTE/WEEKLY)
            if strategy in ["WEEKLY", "0DTE"]:
                if opp.get('gamma', 0) > 0.05:
                    bonus_penalty += 5

            # 3. VIX Regime Penalty (G8 awareness at scoring level)
            if vix_regime == 'CRISIS' and strategy != 'LEAP':
                bonus_penalty -= 10  # Penalize short-term trades in crisis
            elif vix_regime == 'ELEVATED' and strategy == '0DTE':
                bonus_penalty -= 5   # Extra caution for 0DTE in elevated VIX

            # 4. G9: IV Percentile — premium for buying low IV, penalty for high IV
            iv_pct = float(iv_percentile) if iv_percentile else 50
            if iv_pct < 20:
                bonus_penalty += 5   # IV is cheap — good time to buy options
            elif iv_pct > 80:
                bonus_penalty -= 5   # IV is expensive — overpaying for premium

            # 5. G14: Earnings Proximity — flag and penalize pre-earnings uncertainty
            if days_to_earnings is not None:
                dte = int(days_to_earnings)
                if 0 < dte <= 3:
                    bonus_penalty -= 10  # Binary event imminent
                elif 3 < dte <= 14:
                    bonus_penalty -= 5   # Approaching earnings

            # 6. G15: (Dividend impact handled at scanner level for LEAPs;
            #    here we note it in the breakdown)
            
            opportunity_score += bonus_penalty
            opportunity_score = max(1, min(99, float(opportunity_score)))  # Clamp 1-99
            
            # --- G20: AUDIT TRAIL — Score Breakdown ---
            score_breakdown = {
                'technical':    round(norm_tech, 1),
                'sentiment':    round(norm_sent, 1),
                'skew':         round(norm_skew, 1),
                'greeks':       round(norm_greeks, 1),
                'profit':       round(norm_prof, 1),
                'liquidity':    round(norm_liq, 1),
                'fundamental':  round(norm_fund, 1) if strategy == 'LEAP' else None,
                'weights': {
                    'W_TECH': W_TECH, 'W_SENT': W_SENT, 'W_SKEW': W_SKEW,
                    'W_GREEKS': W_GREEKS, 'W_PROF': W_PROF, 'W_LIQ': W_LIQ,
                    'W_FUND': W_FUND if strategy == 'LEAP' else 0,
                },
                'bonus_penalty': bonus_penalty,
                'vix_regime':    vix_regime,
                'iv_percentile': round(iv_pct, 1),
                'days_to_earnings': days_to_earnings,
                'implied_earnings_move': implied_earnings_move,
                'delta_range':   f"{delta_min}-{delta_max}",
                'spread_pct':    round(spread_pct, 4),
                'oi':            oi,
                'opt_volume':    opt_volume,
            }
            
            opp['liquidity_score'] = float(liquidity_score)
            opp['skew_score'] = float(skew_score)
            opp['greeks_score'] = float(greeks_score)
            opp['opportunity_score'] = float(opportunity_score)
            opp['score_breakdown'] = score_breakdown
            opp['days_to_expiry'] = int(opp['days_to_expiry'])
            
            scored_opportunities.append(opp)
        
        scored_opportunities.sort(
            key=lambda x: x['opportunity_score'],
            reverse=True
        )
        
        return scored_opportunities
    
    def _calculate_greeks_score(self, opp, strategy):
        """
        G6: Calculate a Greeks quality score (0-100) based on:
        - Delta confidence: Is delta in the optimal range for this strategy?
        - Theta efficiency: Is theta decay reasonable relative to premium?
        - Gamma risk: High gamma = high convexity (good for short-term, risky for LEAPs)
        """
        score = 50  # Neutral baseline
        
        delta = abs(opp.get('delta', 0) or 0)
        gamma = abs(opp.get('gamma', 0) or 0)
        theta = abs(opp.get('theta', 0) or 0)
        premium = opp.get('premium', 0) or 0
        
        # --- Delta Confidence ---
        if strategy == 'LEAP':
            # Sweet spot: 0.55-0.70 = ideal for profit-taking LEAPs
            if 0.55 <= delta <= 0.70:
                score += 20  # Optimal
            elif 0.50 <= delta <= 0.75:
                score += 10  # Acceptable
            elif delta < 0.45:
                score -= 15  # Too speculative
        elif strategy == 'WEEKLY':
            if 0.40 <= delta <= 0.60:
                score += 15  # Swing trade sweet spot
            elif delta > 0.65:
                score += 5   # Higher conviction but less leverage
        elif strategy == '0DTE':
            if 0.45 <= delta <= 0.55:
                score += 20  # ATM is king for 0DTE
            elif 0.40 <= delta <= 0.60:
                score += 10  # Near ATM acceptable
        
        # --- Theta Efficiency ---
        # Theta/Premium ratio: how much daily decay costs as % of position
        if premium > 0 and theta > 0:
            theta_pct = theta / premium  # Daily decay as fraction of premium
            if strategy == 'LEAP':
                # LEAPs should have low theta decay
                if theta_pct < 0.003:     # < 0.3% per day = very efficient
                    score += 15
                elif theta_pct < 0.005:   # < 0.5% per day = acceptable
                    score += 5
                else:
                    score -= 10           # Expensive time decay
            else:
                # Short-term: theta decay is expected, less penalty
                if theta_pct < 0.01:
                    score += 10
                elif theta_pct < 0.03:
                    score += 0  # Neutral
                else:
                    score -= 5
        
        # --- Gamma Risk/Reward ---
        if strategy in ['WEEKLY', '0DTE']:
            # High gamma is GOOD for short-term (convexity)
            if gamma > 0.05:
                score += 15
            elif gamma > 0.02:
                score += 5
        elif strategy == 'LEAP':
            # High gamma on LEAPs means near-expiry or very ATM — generally fine
            if gamma > 0.05:
                score -= 5  # Unusual for long-dated, slight concern
        
        return max(0, min(100, score))

    def calculate_gex_walls(self, options_data):
        """
        Calculate GEX (Gamma Exposure) Walls for the specific expiration chain.
        Returns:
            {
                'call_wall': strike with max call gamma,
                'put_wall': strike with max put gamma,
                'net_gex': total net gamma
            }
        """
        if not options_data:
            return None
            
        gex_by_strike = {}
        
        # Helper to process strikes
        def process_map(exp_map, is_call):
            for date_key, strikes in exp_map.items():
                for strike, opt_list in strikes.items():
                    if not opt_list: continue
                    opt = opt_list[0]
                    
                    gamma = opt.get('gamma', 0)
                    oi = opt.get('openInterest', 0)
                    
                    # GEX = Gamma * OI * 100 * Spot Price (Simplified Model: Gamma * OI * 100)
                    # For Walls, we just care about Magnitude
                    strike_val = float(strike)
                    gex_val = gamma * oi * 100
                    
                    if strike_val not in gex_by_strike:
                        gex_by_strike[strike_val] = {'call_gex': 0, 'put_gex': 0}
                        
                    if is_call:
                        gex_by_strike[strike_val]['call_gex'] += gex_val
                    else:
                        gex_by_strike[strike_val]['put_gex'] += gex_val

        process_map(options_data.get('callExpDateMap', {}), True)
        process_map(options_data.get('putExpDateMap', {}), False)
        
        if not gex_by_strike:
            return None
            
        # Find Walls
        call_wall = max(gex_by_strike.items(), key=lambda x: x[1]['call_gex'])
        put_wall = max(gex_by_strike.items(), key=lambda x: x[1]['put_gex'])
        
        total_call_gex = sum(x['call_gex'] for x in gex_by_strike.values())
        total_put_gex = sum(x['put_gex'] for x in gex_by_strike.values())
        
        return {
            'call_wall': call_wall[0],
            'put_wall': put_wall[0],
            'call_wall_gex': call_wall[1]['call_gex'],
            'put_wall_gex': put_wall[1]['put_gex'],
            'net_gex': total_call_gex - total_put_gex
        }
