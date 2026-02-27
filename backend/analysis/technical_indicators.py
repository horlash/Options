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
        Calculate all technical indicators
        
        Args:
            price_history: Price history data from TD Ameritrade
        
        Returns:
            Dictionary with all indicators and signals
        """
        df = self.prepare_dataframe(price_history)
        
        if df is None:
            return None
        
        # Calculate all indicators
        rsi_value, rsi_signal = self.calculate_rsi(df)
        macd_values, macd_signal = self.calculate_macd(df)
        bb_values, bb_signal = self.calculate_bollinger_bands(df)
        ma_values, ma_signal = self.calculate_moving_averages(df)
        volume_values, volume_signal = self.analyze_volume(df)  # QW-6: removed duplicate call
        sr_levels = self.calculate_support_resistance(df)
        atr = self.calculate_atr(df)
        hv_rank = self.calculate_hv_rank(df)
        
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
                    'iv_rank': hv_rank # Map HV Rank to IV Rank slot for now as proxy
                },
                'signal': 'neutral'
            },
            'support_resistance': sr_levels
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
