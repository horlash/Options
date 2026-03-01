import pandas as pd
import ta
import numpy as np
import logging
from backend.config import Config

logger = logging.getLogger(__name__)

class TechnicalIndicators:
    def __init__(self):
        self.rsi_oversold = Config.RSI_OVERSOLD
        self.rsi_overbought = Config.RSI_OVERBOUGHT
        
    def prepare_dataframe(self, price_history):
        """
        Convert price history to pandas DataFrame
        
        Args:
            price_history: Price history data from TD Ameritrade
        
        Returns:
            DataFrame with OHLCV data
        """
        if not price_history or 'candles' not in price_history:
            return None
        
        candles = price_history['candles']
        
        df = pd.DataFrame(candles)
        df['datetime'] = pd.to_datetime(df['datetime'], unit='ms')
        df.set_index('datetime', inplace=True)
        
        # Rename columns to standard format
        df.rename(columns={
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume'
        }, inplace=True)
        
        return df
    
    def calculate_rsi(self, df, period=14):
        """
        Calculate Relative Strength Index
        
        Args:
            df: DataFrame with price data
            period: RSI period (default 14)
        
        Returns:
            RSI value and signal
        """
        if df is None or len(df) < period:
            return None, 'neutral'
        
        rsi_indicator = ta.momentum.RSIIndicator(close=df['Close'], window=period)
        rsi = rsi_indicator.rsi()
        current_rsi = rsi.iloc[-1]
        
        # Determine signal (5-zone system)
        if current_rsi < self.rsi_oversold:
            signal = 'oversold'      # < 30 — strong buy signal
        elif current_rsi < 40:
            signal = 'near oversold'  # 30-40 — approaching buy zone
        elif current_rsi > self.rsi_overbought:
            signal = 'overbought'     # > 70 — strong sell signal
        elif current_rsi > 60:
            signal = 'near overbought' # 60-70 — approaching sell zone
        else:
            signal = 'neutral'         # 40-60 — no signal
        
        return current_rsi, signal
    
    def calculate_macd(self, df, fast=12, slow=26, signal=9):
        """
        Calculate MACD (Moving Average Convergence Divergence)
        
        Args:
            df: DataFrame with price data
            fast: Fast EMA period
            slow: Slow EMA period
            signal: Signal line period
        
        Returns:
            MACD values and signal
        """
        if df is None or len(df) < slow:
            return None, 'neutral'
        
        macd_indicator = ta.trend.MACD(close=df['Close'], window_slow=slow, window_fast=fast, window_sign=signal)
        
        macd_line = macd_indicator.macd().iloc[-1]
        signal_line = macd_indicator.macd_signal().iloc[-1]
        histogram = macd_indicator.macd_diff().iloc[-1]
        
        # Get last 3 histogram bars for momentum detection
        hist_series = macd_indicator.macd_diff().dropna().tail(3).tolist()
        
        # Determine signal with histogram momentum (2-bar confirmation)
        if macd_line > signal_line and histogram > 0:
            # Check if histogram is shrinking for 2+ consecutive bars
            if (len(hist_series) >= 3 and 
                hist_series[-1] < hist_series[-2] < hist_series[-3]):
                signal_type = 'weakening bullish'  # Trend losing steam
            else:
                signal_type = 'bullish'
        elif macd_line < signal_line and histogram < 0:
            # Check if bearish histogram is shrinking (becoming less negative)
            if (len(hist_series) >= 3 and 
                hist_series[-1] > hist_series[-2] > hist_series[-3]):
                signal_type = 'weakening bearish'  # Bear trend fading
            else:
                signal_type = 'bearish'
        else:
            signal_type = 'neutral'
        
        return {
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        }, signal_type
    
    def calculate_bollinger_bands(self, df, period=20, std=2):
        """
        Calculate Bollinger Bands
        
        Args:
            df: DataFrame with price data
            period: Moving average period
            std: Standard deviation multiplier
        
        Returns:
            Bollinger Bands values and signal
        """
        if df is None or len(df) < period:
            return None, 'neutral'
        
        bb_indicator = ta.volatility.BollingerBands(close=df['Close'], window=period, window_dev=std)
        
        current_price = df['Close'].iloc[-1]
        upper_band = bb_indicator.bollinger_hband().iloc[-1]
        middle_band = bb_indicator.bollinger_mavg().iloc[-1]
        lower_band = bb_indicator.bollinger_lband().iloc[-1]
        
        # Calculate bandwidth and percentile for squeeze detection
        bandwidth = (upper_band - lower_band) / middle_band if middle_band > 0 else 0
        bb_width_series = (bb_indicator.bollinger_hband() - bb_indicator.bollinger_lband()) / bb_indicator.bollinger_mavg()
        bb_width_history = bb_width_series.dropna().tail(100)
        bandwidth_percentile = (bb_width_history < bandwidth).sum() / len(bb_width_history) * 100 if len(bb_width_history) > 0 else 50
        
        # Price position within bands (0 = lower, 100 = upper)
        band_range = upper_band - lower_band
        band_position = ((current_price - lower_band) / band_range * 100) if band_range > 0 else 50
        
        # Determine signal (squeeze-aware, 5-zone)
        is_squeeze = bandwidth_percentile < 20  # Bands in bottom 20% of width
        
        if is_squeeze:
            signal = 'squeeze'              # Volatility contraction — big move imminent
        elif current_price >= upper_band:
            signal = 'overbought'           # At/above upper band
        elif band_position > 75:
            signal = 'near overbought'      # Upper 25% of bands
        elif current_price <= lower_band:
            signal = 'oversold'             # At/below lower band
        elif band_position < 25:
            signal = 'near oversold'        # Lower 25% of bands
        else:
            signal = 'neutral'
        
        return {
            'upper': upper_band,
            'middle': middle_band,
            'lower': lower_band,
            'current_price': current_price,
            'bandwidth': bandwidth,
            'bandwidth_percentile': bandwidth_percentile,
            'band_position': band_position,
            'is_squeeze': is_squeeze
        }, signal
    
    def calculate_moving_averages(self, df):
        """
        Calculate 50-day and 200-day Simple Moving Averages
        
        Args:
            df: DataFrame with price data
        
        Returns:
            Moving averages and signal
        """
        if df is None or len(df) < 200:
            return None, 'neutral'
        
        sma_5_indicator = ta.trend.SMAIndicator(close=df['Close'], window=5)
        sma_50_indicator = ta.trend.SMAIndicator(close=df['Close'], window=50)
        sma_200_indicator = ta.trend.SMAIndicator(close=df['Close'], window=200)
        
        sma_5 = sma_5_indicator.sma_indicator().iloc[-1]
        sma_50 = sma_50_indicator.sma_indicator().iloc[-1]
        sma_200 = sma_200_indicator.sma_indicator().iloc[-1]
        current_price = df['Close'].iloc[-1]
        
        logger.debug(f"Calculated SMA5={sma_5}, SMA50={sma_50}")
        
        # 5-zone trend analysis with SMA200 safety net
        if sma_50 > sma_200 and current_price > sma_50:
            signal = 'bullish'             # Full uptrend: price > SMA50 > SMA200
        elif sma_50 > sma_200 and current_price > sma_200:
            signal = 'pullback bullish'    # Dip in uptrend: SMA200 < price < SMA50 (buy-the-dip)
        elif sma_50 > sma_200 and current_price < sma_200:
            signal = 'breakdown'           # SMA50 > SMA200 but price crashed below both — danger
        elif sma_50 < sma_200 and current_price < sma_50:
            signal = 'bearish'             # Full downtrend: price < SMA50 < SMA200
        elif sma_50 < sma_200 and current_price > sma_200:
            signal = 'rally bearish'       # Bear bounce above SMA200 — dead cat bounce
        else:
            signal = 'neutral'
        
        return {
            'sma_5': sma_5,
            'sma_50': sma_50,
            'sma_200': sma_200,
            'current_price': current_price
        }, signal
    
    def analyze_volume(self, df, period=20):
        """
        Analyze volume patterns
        
        Args:
            df: DataFrame with price data
            period: Period for average volume
        
        Returns:
            Volume analysis and signal
        """
        if df is None or len(df) < period:
            return None, 'neutral'
        
        avg_volume = df['Volume'].rolling(window=period).mean().iloc[-1]
        current_volume = df['Volume'].iloc[-1]
        
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
        
        # Z-score based volume tiers (ticker-adaptive)
        vol_series = df['Volume'].tail(50)
        vol_mean = vol_series.mean()
        vol_std = vol_series.std()
        
        if vol_mean > 0 and vol_std > 0:
            z_score = (current_volume - vol_mean) / vol_std
            if z_score > 2.0:
                signal = 'surging'     # >2 std dev — institutional/news-driven
            elif z_score > 0.5:
                signal = 'strong'      # Above average
            elif z_score > -0.5:
                signal = 'normal'      # Typical trading day
            else:
                signal = 'weak'        # Below average
        else:
            signal = 'normal'  # Can't calculate — assume normal (not weak)
        
        return {
            'current_volume': current_volume,
            'avg_volume': avg_volume,
            'volume_ratio': volume_ratio,
            'z_score': z_score if vol_mean > 0 and vol_std > 0 else 0
        }, signal
    
    def calculate_support_resistance(self, df, window=20):
        """
        Calculate support and resistance levels using pivot points
        
        Args:
            df: DataFrame with price data
            window: Window for calculating levels
        
        Returns:
            Support and resistance levels
        """
        if df is None or len(df) < window:
            return None
        
        # Use recent highs and lows
        recent_high = df['High'].rolling(window=window).max().iloc[-1]
        recent_low = df['Low'].rolling(window=window).min().iloc[-1]
        current_price = df['Close'].iloc[-1]
        
        # Simple pivot point calculation
        pivot = (recent_high + recent_low + current_price) / 3
        resistance_1 = (2 * pivot) - recent_low
        support_1 = (2 * pivot) - recent_high
        
        return {
            'resistance': resistance_1,
            'support': support_1,
            'pivot': pivot,
            'recent_high': recent_high,
            'recent_low': recent_low
        }
    
    def get_all_indicators(self, price_history):
        """
        Calculate all technical indicators with graceful degradation.
        
        FIX-MINERV-B: Each indicator is wrapped in try/except so that partial
        data (e.g., 50-199 bars) still produces useful results. Previously,
        if calculate_moving_averages() returned None (needs 200 bars), the
        downstream calculate_technical_score() could still consume it because
        all signals default to 'neutral'. However, any unexpected exception
        in a single indicator would crash the entire get_all_indicators() call
        and abort the scan. This fix ensures:
          1. Each indicator fails independently (no cascade)
          2. Safe defaults are used for any failed indicator
          3. A '_data_quality' key reports which indicators succeeded/degraded
        
        Args:
            price_history: Price history data
        
        Returns:
            Dictionary with all indicators and signals, or None if df fails
        """
        df = self.prepare_dataframe(price_history)
        
        if df is None:
            return None
        
        bars = len(df)
        data_quality = {'bars': bars, 'degraded': [], 'failed': []}
        
        # --- Safe defaults for each indicator ---
        rsi_value, rsi_signal = None, 'neutral'
        macd_values, macd_signal = None, 'neutral'
        bb_values, bb_signal = None, 'neutral'
        ma_values, ma_signal = None, 'neutral'
        volume_values, volume_signal = None, 'normal'
        sr_levels = None
        atr = 0
        hv_rank = 50
        rsi2_data = {'value': None, 'signal': 'neutral', 'exit_trigger': False}
        vwap_data = {'weekly_vwap': None, 'monthly_vwap': None, 'signal': 'neutral', 'score_boost': 0}
        minervini_data = {'score': 0, 'stage': 'UNCLASSIFIED', 'criteria': {},
                          'is_stage2': False, 'reason': 'insufficient_history'}
        
        # --- Calculate each indicator with independent error handling ---
        
        # RSI (needs 14 bars)
        try:
            rsi_value, rsi_signal = self.calculate_rsi(df)
        except Exception as e:
            logger.warning(f"FIX-MINERV-B: RSI calculation failed: {e}")
            data_quality['failed'].append('rsi')
        
        # MACD (needs 26 bars)
        try:
            macd_values, macd_signal = self.calculate_macd(df)
        except Exception as e:
            logger.warning(f"FIX-MINERV-B: MACD calculation failed: {e}")
            data_quality['failed'].append('macd')
        
        # Bollinger Bands (needs 20 bars)
        try:
            bb_values, bb_signal = self.calculate_bollinger_bands(df)
        except Exception as e:
            logger.warning(f"FIX-MINERV-B: Bollinger Bands calculation failed: {e}")
            data_quality['failed'].append('bollinger_bands')
        
        # Moving Averages (needs 200 bars — common degradation point)
        try:
            ma_values, ma_signal = self.calculate_moving_averages(df)
            if ma_values is None and bars < 200:
                data_quality['degraded'].append('moving_averages')
                logger.debug(f"FIX-MINERV-B: Moving averages degraded ({bars} bars < 200 required)")
        except Exception as e:
            logger.warning(f"FIX-MINERV-B: Moving averages calculation failed: {e}")
            data_quality['failed'].append('moving_averages')
        
        # Volume (needs 20 bars)
        try:
            volume_values, volume_signal = self.analyze_volume(df)  # QW-6: removed duplicate call
        except Exception as e:
            logger.warning(f"FIX-MINERV-B: Volume analysis failed: {e}")
            data_quality['failed'].append('volume')
        
        # Support/Resistance (needs 20 bars)
        try:
            sr_levels = self.calculate_support_resistance(df)
        except Exception as e:
            logger.warning(f"FIX-MINERV-B: Support/Resistance calculation failed: {e}")
            data_quality['failed'].append('support_resistance')
        
        # ATR (needs 14 bars)
        try:
            atr = self.calculate_atr(df)
        except Exception as e:
            logger.warning(f"FIX-MINERV-B: ATR calculation failed: {e}")
            data_quality['failed'].append('atr')
        
        # HV Rank (needs 30 bars)
        try:
            hv_rank = self.calculate_hv_rank(df)
        except Exception as e:
            logger.warning(f"FIX-MINERV-B: HV Rank calculation failed: {e}")
            data_quality['failed'].append('hv_rank')
        
        # S3: RSI-2 Connors Mean Reversion (needs 10 bars)
        try:
            rsi2_data = self.calculate_rsi2(df)
        except Exception as e:
            logger.warning(f"FIX-MINERV-B: RSI-2 calculation failed: {e}")
            data_quality['failed'].append('rsi2')
        
        # S7A: VWAP Institutional Levels (needs 22 bars)
        try:
            vwap_data = self.calculate_vwap_levels(df)
        except Exception as e:
            logger.warning(f"FIX-MINERV-B: VWAP calculation failed: {e}")
            data_quality['failed'].append('vwap')
        
        # S5: Minervini Stage 2 criteria (needs 252 bars — most demanding)
        try:
            minervini_data = self.calculate_minervini_criteria(df)
            if bars < 252:
                data_quality['degraded'].append('minervini')
        except Exception as e:
            logger.warning(f"FIX-MINERV-B: Minervini calculation failed: {e}")
            data_quality['failed'].append('minervini')
        
        if data_quality['failed']:
            logger.warning(
                f"FIX-MINERV-B: {len(data_quality['failed'])} indicators failed "
                f"({', '.join(data_quality['failed'])}), using safe defaults"
            )
        if data_quality['degraded']:
            logger.info(
                f"FIX-MINERV-B: {len(data_quality['degraded'])} indicators degraded "
                f"due to insufficient bars ({bars}): {', '.join(data_quality['degraded'])}"
            )
        
        return {
            'rsi': {
                'value': rsi_value,
                'signal': rsi_signal
            },
            'macd': {
                'values': macd_values,
                'signal': macd_signal
            },
            'bollinger_bands': {
                'values': bb_values,
                'signal': bb_signal
            },
            'moving_averages': {
                'values': ma_values,
                'signal': ma_signal
            },
            'volume': {
                'values': volume_values,
                'signal': volume_signal
            },
            'volatility': {
                'values': {
                    'atr': atr,
                    'hv_rank': hv_rank,  # BUG-TI-1 FIX: Properly labeled as HV Rank
                    # iv_percentile is added by the scanner from ORATS ivPctile1y
                    # DO NOT use hv_rank as a proxy for IV rank — they measure different things
                },
                'signal': 'neutral'
            },
            'support_resistance': sr_levels,
            # --- New Trading Systems ---
            'rsi2': rsi2_data,           # S3: Connors RSI-2
            'vwap': vwap_data,           # S7A: VWAP Levels
            'minervini': minervini_data,  # S5: Minervini Stage 2
            # --- FIX-MINERV-B: Data quality metadata ---
            '_data_quality': data_quality,
        }
    
    def calculate_technical_score(self, indicators):
        """
        Calculate overall technical score from all indicators.
        
        G19: Improved normalization — each indicator scored independently on [-1, +1],
        then weighted and mapped to 0-100 via consistent linear transform.
        Volume acts as a confidence multiplier (not additive) to avoid range overflow.
        
        Args:
            indicators: Dictionary of all indicators
        
        Returns:
            Technical score (0-100)
        """
        if not indicators:
            return 0
        
        # --- G19: Score each indicator on [-1.0, +1.0] scale independently ---
        indicator_scores = {}
        
        # RSI (5-zone)
        rsi_sig = indicators['rsi']['signal']
        rsi_map = {
            'oversold': 1.0, 'near oversold': 0.5, 'neutral': 0.0,
            'near overbought': -0.5, 'overbought': -1.0
        }
        indicator_scores['rsi'] = rsi_map.get(rsi_sig, 0.0)
        
        # MACD (with histogram momentum)
        macd_sig = indicators['macd']['signal']
        macd_map = {
            'bullish': 1.0, 'weakening bullish': 0.5, 'neutral': 0.0,
            'weakening bearish': -0.5, 'bearish': -1.0
        }
        indicator_scores['macd'] = macd_map.get(macd_sig, 0.0)
        
        # Bollinger Bands (squeeze-aware)
        bb_sig = indicators['bollinger_bands']['signal']
        bb_map = {
            'oversold': 1.0, 'near oversold': 0.5, 'squeeze': 0.0,
            'neutral': 0.0, 'near overbought': -0.5, 'overbought': -1.0
        }
        indicator_scores['bollinger_bands'] = bb_map.get(bb_sig, 0.0)
        
        # Moving Averages (with pullback/breakdown)
        ma_sig = indicators['moving_averages']['signal']
        ma_map = {
            'bullish': 1.0, 'pullback bullish': 0.5, 'neutral': 0.0,
            'rally bearish': -0.5, 'breakdown': -0.75, 'bearish': -1.0
        }
        indicator_scores['moving_averages'] = ma_map.get(ma_sig, 0.0)
        
        # --- Weighted sum (weights sum to 1.0, volume excluded as multiplier) ---
        weights = {
            'rsi': 0.235,              # Leading indicator
            'macd': 0.235,             # Momentum
            'bollinger_bands': 0.295,  # Squeeze = highest-value signal
            'moving_averages': 0.235,  # Trend direction
        }
        # Weights sum: 0.235 + 0.235 + 0.295 + 0.235 = 1.00
        
        weighted_sum = sum(
            indicator_scores[k] * weights[k]
            for k in weights
        )  # Range: [-1.0, +1.0]
        
        # Volume confirmation (multiplier, not additive — avoids range overflow)
        vol_sig = indicators['volume']['signal']
        vol_multiplier_map = {
            'surging': 1.15, 'strong': 1.08, 'normal': 1.0, 'weak': 0.95
        }
        vol_multiplier = vol_multiplier_map.get(vol_sig, 1.0)
        
        weighted_sum *= vol_multiplier  # Still bounded near [-1.15, +1.15]
        
        # --- G19: Linear normalization from [-1.15, +1.15] to [0, 100] ---
        normalized_score = ((weighted_sum + 1.15) / 2.30) * 100
        
        # Store indicator breakdown for audit trail (G20)
        indicators['_score_breakdown'] = {
            'indicator_scores': indicator_scores,
            'weights': weights,
            'weighted_sum': round(weighted_sum, 4),
            'volume_signal': vol_sig,
            'volume_multiplier': vol_multiplier,
        }
        
        return max(0, min(100, normalized_score))
    
    def calculate_atr(self, df, period=14):
        """
        Calculate Average True Range (ATR)
        """
        if df is None or len(df) < period:
            return 0
            
        atr_indicator = ta.volatility.AverageTrueRange(
            high=df['High'], 
            low=df['Low'], 
            close=df['Close'], 
            window=period
        )
        return atr_indicator.average_true_range().iloc[-1]

    def calculate_hv_rank(self, df, window=252):
        """
        Calculate Historical Volatility (HV) Rank.
        HV = StdDev(Ln(Close/Close_prev)) * Sqrt(252)
        HV Rank = Percentile of current HV over the last year.
        """
        if df is None or len(df) < 30: # Need some data
            return 50 # Default neutral
        
        # XC-5: Work on a copy to avoid SettingWithCopyWarning on caller's DataFrame
        df = df.copy()
            
        # Calculate Log Returns
        df['log_ret'] = np.log(df['Close'] / df['Close'].shift(1))
        
        # Calculate 20-day rolling HV (annualized)
        df['hv'] = df['log_ret'].rolling(window=20).std() * np.sqrt(252) * 100
        
        # Get one year of HV values (approx 252 trading days)
        last_year_hv = df['hv'].tail(window).dropna()
        
        if last_year_hv.empty:
            return 50
            
        current_hv = last_year_hv.iloc[-1]
        
        # Calculate Rank (Percentile)
        min_hv = last_year_hv.min()
        max_hv = last_year_hv.max()
        
        if max_hv == min_hv:
            return 50
            
        hv_rank = ((current_hv - min_hv) / (max_hv - min_hv)) * 100
        return hv_rank

    # ─── S3: Connors RSI-2 Mean Reversion ─────────────────────────────────────
    def calculate_rsi2(self, df):
        """S3: Connors RSI-2 Mean Reversion signal.
        
        RSI with period=2 captures extreme short-term oversold/overbought.
        Evidence: Connors (2010) — 84% win rate on SPY backtested 2000-2010,
        confirmed in 2024 re-tests. 18-Persona verdict: 18/18 UNANIMOUS.
        
        Returns:
            dict with rsi2 value, signal, and exit trigger
        """
        if df is None or len(df) < 10:  # Need minimal data for 2-period RSI
            return {'value': None, 'signal': 'neutral', 'exit_trigger': False}
        
        rsi2_indicator = ta.momentum.RSIIndicator(close=df['Close'], window=2)
        rsi2 = rsi2_indicator.rsi()
        current_rsi2 = rsi2.iloc[-1]
        
        # S3-FIX: 200-day SMA trend filter — Connors RSI-2 is explicitly designed
        # to only trigger BUY signals when price is ABOVE the 200-day SMA.
        # Without this filter, extreme_oversold flags stocks in secular downtrends
        # (falling knives). Suppressing oversold signals below SMA200 is essential.
        current_price = df['Close'].iloc[-1]
        above_sma200 = False
        if len(df) >= 200:
            sma200 = df['Close'].rolling(window=200).mean().iloc[-1]
            above_sma200 = current_price > sma200
        # If fewer than 200 bars, we cannot confirm the uptrend — suppress buy signals
        # (conservative default per Risk Manager and Bear Market Survivor personas).

        # Connors thresholds: <5 = extreme oversold (buy), >95 = extreme overbought (sell)
        if current_rsi2 < 5:
            # Only fire buy signal if price is above the 200-day SMA trend filter
            signal = 'extreme_oversold' if above_sma200 else 'neutral'
        elif current_rsi2 < 10:
            signal = 'oversold' if above_sma200 else 'neutral'
        elif current_rsi2 > 95:
            signal = 'extreme_overbought' # Strong mean reversion SELL signal
        elif current_rsi2 > 90:
            signal = 'overbought'         # Moderate sell signal
        else:
            signal = 'neutral'
        
        # Exit trigger: price crosses above 5-day SMA (Connors exit rule)
        sma5 = df['Close'].rolling(window=5).mean()
        exit_trigger = False
        if len(sma5.dropna()) >= 2:
            # Price crossed above SMA5 today (was below yesterday)
            exit_trigger = (
                df['Close'].iloc[-1] > sma5.iloc[-1] and
                df['Close'].iloc[-2] <= sma5.iloc[-2]
            )
        
        return {
            'value': round(current_rsi2, 2) if not pd.isna(current_rsi2) else None,
            'signal': signal,
            'exit_trigger': exit_trigger,
        }

    # ─── S5: Minervini Stage 2 Criteria ─────────────────────────────────────────
    def calculate_minervini_criteria(self, df):
        """S5: Evaluate Mark Minervini's 8 Stage 2 (SEPA) criteria.
        
        Evidence: "Trade Like a Stock Market Wizard" — Minervini's system
        targets stocks in Stage 2 uptrend. 18-Persona verdict: 14/18 APPROVED
        WITH CONDITIONS (zero-results floor required).
        
        The 8 criteria:
          1. Price > SMA150 and SMA200
          2. SMA150 > SMA200
          3. SMA200 trending up for >= 1 month (22 trading days)
          4. SMA50 > SMA150 and SMA200
          5. Price > SMA50
          6. Price >= 25% above 52-week low
          7. Price within 25% of 52-week high
          8. RS rating >= 70 (relative strength vs SPY)
        
        Returns:
            dict with score (0-8), stage, criteria details, and pass/fail
        """
        if df is None or len(df) < 252:  # Need 1 year of data
            return {'score': 0, 'stage': 'UNCLASSIFIED', 'criteria': {},
                    'is_stage2': False, 'reason': 'insufficient_history'}
        
        close = df['Close']
        current_price = close.iloc[-1]
        
        # Calculate SMAs
        sma50 = close.rolling(window=50).mean().iloc[-1]
        sma150 = close.rolling(window=150).mean().iloc[-1]
        sma200 = close.rolling(window=200).mean().iloc[-1]
        
        # SMA200 slope (22 trading days ago)
        sma200_series = close.rolling(window=200).mean()
        sma200_22d_ago = sma200_series.iloc[-23] if len(sma200_series) > 23 else sma200
        sma200_trending_up = sma200 > sma200_22d_ago
        
        # 52-week high/low
        high_52w = df['High'].tail(252).max()
        low_52w = df['Low'].tail(252).min()
        
        # Evaluate 8 criteria
        criteria = {}
        criteria['1_price_above_sma150_200'] = current_price > sma150 and current_price > sma200
        criteria['2_sma150_above_sma200'] = sma150 > sma200
        criteria['3_sma200_trending_up'] = sma200_trending_up
        criteria['4_sma50_above_sma150_200'] = sma50 > sma150 and sma50 > sma200
        criteria['5_price_above_sma50'] = current_price > sma50
        criteria['6_price_25pct_above_52w_low'] = current_price >= low_52w * 1.25
        criteria['7_price_within_25pct_of_52w_high'] = current_price >= high_52w * 0.75
        # Criterion 8 (RS rating) is evaluated externally with SPY data
        criteria['8_rs_rating'] = None  # Filled by caller with calculate_relative_strength()
        
        score = sum(1 for k, v in criteria.items() if v is True)
        
        # S5-FIX: If criterion 8 (RS Rating) is None/deferred, the denominator
        # should be 7 (not 8) so the percentage calculation is accurate.
        # e.g. 7/7 = 100% vs 7/8 = 87.5% — prevents false underscoring.
        max_score = 7 if criteria.get('8_rs_rating') is None else 8
        
        # Stage classification
        if score >= 7:  # 7/8 or 8/8 (criterion 8 may be None)
            stage = 'STAGE_2'
        elif score >= 5:
            stage = 'STAGE_2_EARLY'
        elif criteria.get('3_sma200_trending_up') and criteria.get('2_sma150_above_sma200'):
            stage = 'STAGE_1'  # Building base
        else:
            stage = 'STAGE_3_OR_4'  # Declining or bottoming
        
        return {
            'score': score,
            'max_score': max_score,
            'stage': stage,
            'is_stage2': stage in ('STAGE_2', 'STAGE_2_EARLY'),
            'criteria': criteria,
            'sma50': round(sma50, 2),
            'sma150': round(sma150, 2),
            'sma200': round(sma200, 2),
            'high_52w': round(high_52w, 2),
            'low_52w': round(low_52w, 2),
        }

    # ─── S7A: VWAP Institutional Levels (EOD) ───────────────────────────────────
    def calculate_vwap_levels(self, df):
        """S7A: Calculate weekly and monthly anchored VWAP from daily OHLCV.
        
        Evidence: Brian Shannon's VWAP framework — institutional benchmark.
        18-Persona verdict: 13/18 APPROVED WITH CONDITIONS.
        
        Note: This is Phase A (EOD approximation from daily bars).
        Phase B (intraday VWAP) deferred with S6 ORB.
        
        Returns:
            dict with weekly_vwap, monthly_vwap, distances, and signals
        """
        if df is None or len(df) < 22:  # Need at least ~1 month
            return {'weekly_vwap': None, 'monthly_vwap': None, 'signal': 'neutral'}
        
        current_price = df['Close'].iloc[-1]
        
        # Typical price = (H + L + C) / 3
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        vol = df['Volume']
        
        # Weekly VWAP (last 5 trading days)
        tp_5d = tp.tail(5)
        vol_5d = vol.tail(5)
        weekly_vwap = (tp_5d * vol_5d).sum() / vol_5d.sum() if vol_5d.sum() > 0 else None
        
        # Monthly VWAP (last 22 trading days)
        tp_22d = tp.tail(22)
        vol_22d = vol.tail(22)
        monthly_vwap = (tp_22d * vol_22d).sum() / vol_22d.sum() if vol_22d.sum() > 0 else None
        
        # Distance from VWAP levels (as percentage)
        weekly_dist = ((current_price - weekly_vwap) / weekly_vwap * 100) if weekly_vwap else None
        monthly_dist = ((current_price - monthly_vwap) / monthly_vwap * 100) if monthly_vwap else None
        
        # Signal determination
        # Near VWAP (within 0.5%) = institutional support/resistance zone
        signal = 'neutral'
        score_boost = 0
        
        if weekly_dist is not None and monthly_dist is not None:
            # Price at or near weekly VWAP = strong institutional level
            if abs(weekly_dist) < 0.5:
                signal = 'at_weekly_vwap'  # Price sitting on institutional level
                score_boost = 8   # S7A-FIX: Reduced from +12 to +8; proportionate with other signals
            elif abs(monthly_dist) < 0.5:
                signal = 'at_monthly_vwap'
                score_boost = 8   # +8 for monthly VWAP alignment
            elif weekly_dist > 0 and monthly_dist > 0:
                signal = 'above_vwap'  # Bullish — price above both VWAPs
                score_boost = 5
            elif weekly_dist < 0 and monthly_dist < 0:
                signal = 'below_vwap'  # Bearish — price below both VWAPs
                score_boost = -3
            elif weekly_dist > 0 > monthly_dist:
                signal = 'mixed'  # Pulling up from below monthly
                score_boost = 2
        
        return {
            'weekly_vwap': round(weekly_vwap, 2) if weekly_vwap else None,
            'monthly_vwap': round(monthly_vwap, 2) if monthly_vwap else None,
            'weekly_distance_pct': round(weekly_dist, 2) if weekly_dist is not None else None,
            'monthly_distance_pct': round(monthly_dist, 2) if monthly_dist is not None else None,
            'signal': signal,
            'score_boost': score_boost,
            'current_price': round(current_price, 2),
        }

    def calculate_relative_strength(self, df_stock, df_market, period=5):
        """
        Calculate Relative Strength vs Market (SPY).
        Returns:
            rs_score: > 0 means outperforming, < 0 means underperforming
        """
        if df_stock is None or df_market is None:
            return 0
            
        if len(df_stock) < period or len(df_market) < period:
            return 0
            
        # Get period performance
        stock_perf = (df_stock['Close'].iloc[-1] - df_stock['Close'].iloc[-period-1]) / df_stock['Close'].iloc[-period-1]
        market_perf = (df_market['Close'].iloc[-1] - df_market['Close'].iloc[-period-1]) / df_market['Close'].iloc[-period-1]
        
        return (stock_perf - market_perf) * 100 # Percentage difference
