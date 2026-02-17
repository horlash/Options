import pandas as pd
import ta
import numpy as np
from backend.config import Config

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
        
        # Determine signal
        if current_rsi < self.rsi_oversold:
            signal = 'bullish'  # Oversold - potential buy
        elif current_rsi > self.rsi_overbought:
            signal = 'bearish'  # Overbought - potential sell
        else:
            signal = 'neutral'
        
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
        
        # Determine signal based on crossover
        if macd_line > signal_line and histogram > 0:
            signal_type = 'bullish'
        elif macd_line < signal_line and histogram < 0:
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
        
        # Determine signal
        if current_price <= lower_band:
            signal = 'bullish'  # Price at lower band - potential buy
        elif current_price >= upper_band:
            signal = 'bearish'  # Price at upper band - potential sell
        else:
            signal = 'neutral'
        
        return {
            'upper': upper_band,
            'middle': middle_band,
            'lower': lower_band,
            'current_price': current_price
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
        
        print(f"DEBUG: Calculated SMA5={sma_5}, SMA50={sma_50}")
        
        # Golden cross / Death cross
        if sma_50 > sma_200 and current_price > sma_50:
            signal = 'bullish'
        elif sma_50 < sma_200 and current_price < sma_50:
            signal = 'bearish'
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
        
        # High volume can confirm trends
        if volume_ratio > Config.MIN_VOLUME_MULTIPLIER:
            signal = 'strong'  # High volume confirms movement
        else:
            signal = 'weak'  # Low volume - weak signal
        
        return {
            'current_volume': current_volume,
            'avg_volume': avg_volume,
            'volume_ratio': volume_ratio
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
        volume_values, volume_signal = self.analyze_volume(df)
        volume_values, volume_signal = self.analyze_volume(df)
        sr_levels = self.calculate_support_resistance(df)
        atr = self.calculate_atr(df)
        hv_rank = self.calculate_hv_rank(df)
        
        print(f"DEBUG TI RETURN MA_VALUES: {ma_values}")
        
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
        Calculate overall technical score from all indicators
        
        Args:
            indicators: Dictionary of all indicators
        
        Returns:
            Technical score (0-100)
        """
        if not indicators:
            return 0
        
        score = 0
        weights = {
            'rsi': 20,
            'macd': 25,
            'bollinger_bands': 20,
            'moving_averages': 25,
            'volume': 10
        }
        
        # RSI score
        if indicators['rsi']['signal'] == 'bullish':
            score += weights['rsi']
        elif indicators['rsi']['signal'] == 'bearish':
            score -= weights['rsi']
        
        # MACD score
        if indicators['macd']['signal'] == 'bullish':
            score += weights['macd']
        elif indicators['macd']['signal'] == 'bearish':
            score -= weights['macd']
        
        # Bollinger Bands score
        if indicators['bollinger_bands']['signal'] == 'bullish':
            score += weights['bollinger_bands']
        elif indicators['bollinger_bands']['signal'] == 'bearish':
            score -= weights['bollinger_bands']
        
        # Moving Averages score
        if indicators['moving_averages']['signal'] == 'bullish':
            score += weights['moving_averages']
        elif indicators['moving_averages']['signal'] == 'bearish':
            score -= weights['moving_averages']
        
        # Volume confirmation
        if indicators['volume']['signal'] == 'strong':
            score *= 1.1  # Boost score by 10% for strong volume
        
        # Normalize to 0-100 scale
        normalized_score = ((score + 100) / 200) * 100
        
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
