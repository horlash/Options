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
            
            # Use Mark Price (Midpoint) for fair value
            if ask > 0 and bid > 0:
                premium = (ask + bid) / 2
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

    def rank_opportunities(self, opportunities, technical_score, sentiment_score, skew_score=50, strategy="LEAP", current_price=None):
        """
        Rank and score opportunities with Strategy-Specific Logic.
        Strategies: 'LEAP', 'WEEKLY', '0DTE'
        """
        scored_opportunities = []
        
        # --- DEFINE WEIGHTS BASED ON STRATEGY ---
        if strategy in ["WEEKLY", "0DTE"]:
            # Short Term: Momentum & Flow are King
            W_TECH = 0.50      # Technicals (Momentum)
            W_SKEW = 0.20      # Flow/Skew/Gamma
            W_SENT = 0.20      # News/Sentiment
            W_PROF = 0.05      # Profit Potential (Less important, we want speed)
            W_LIQ  = 0.05      # Liquidity (Always needed)
            PROFIT_TARGET = 50 if strategy == "WEEKLY" else 30 # Normalize score at 50% or 30%
        else:
            # LEAP (Long Term): Fundamentals & Value
            # P0-15: Rebalanced LEAP weights — W_PROF reduced from 0.20 to 0.05
            # to prevent high-premium OTM options dominating over quality ITM setups
            W_TECH = 0.35
            W_SENT = 0.25      # +5% (reallocated from profit reduction)
            W_SKEW = 0.15
            W_PROF = 0.05      # Was 0.20 — now matches WEEKLY/0DTE spec
            W_LIQ  = 0.10
            W_FUND = 0.10      # NEW: fundamental quality placeholder
            PROFIT_TARGET = 200 # Normalize score at 200%

        for opp in opportunities:
            # Calculate liquidity score
            liquidity_score = self.calculate_liquidity_score(opp)
            
            # --- PROFIT SCORE NORMALIZATION ---
            # Cap at 100. If potential is 25% and target is 50%, score is 50.
            profit_score = min(100, (opp['profit_potential'] / PROFIT_TARGET) * 100)
            
            # --- WEIGHTED SCORE ---
            # P0-15: Removed dead duplicate formula that used W_SKEW for sentiment
            opportunity_score = (
                float(technical_score) * W_TECH +
                float(sentiment_score) * W_SENT +
                float(skew_score) * W_SKEW +
                float(profit_score) * W_PROF +
                float(liquidity_score) * W_LIQ
            )

            # --- STRATEGY BONUSES / PENALTIES ---
            
            # 1. [PROFIT-TAKING] Delta Sweet Spot Bonus (LEAP ONLY)
            # Reward options in the 0.60-0.75 sweet spot
            if strategy == "LEAP":
                delta_val = opp.get('delta', 0)
                if 0.60 <= delta_val <= 0.75:
                    opportunity_score += 10  # Bonus for optimal profit-taking delta
                    
            # 2. [REMOVED] Stock Replacement Bonus
            # Old logic: Bonused delta >= 0.80, now filtered out entirely
                
            # 3. Delta Too Low Penalty (LEAP ONLY)
            # Should never trigger since we filter <0.50, but keep as safety
            if strategy == "LEAP" and opp.get('delta', 0) < 0.55:
                opportunity_score -= 10  # Extra penalty for borderline lotto tickets

            # 3. Gamma Wall Bonus (0DTE/WEEKLY)
            # This requires 'current_price' passed to function
            # Logic: If price is within 1% of Strike, and Strike is a "Wall", boost.
            # (Simplified: High Gamma Badge check)
            if strategy in ["WEEKLY", "0DTE"]:
                if opp.get('gamma', 0) > 0.05: # High Gamma
                     opportunity_score += 10

            opp['liquidity_score'] = float(liquidity_score)
            opp['skew_score'] = float(skew_score)
            opp['opportunity_score'] = min(99, float(opportunity_score)) # Cap at 99
            opp['days_to_expiry'] = int(opp['days_to_expiry'])
            
            scored_opportunities.append(opp)
        
        scored_opportunities.sort(
            key=lambda x: x['opportunity_score'],
            reverse=True
        )
        
        return scored_opportunities

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
