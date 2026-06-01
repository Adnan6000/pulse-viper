# core/market_regime.py
import numpy as np
import pandas as pd
from enum import Enum
import logging

class RegimeType(Enum):
    TRENDING = "TRENDING"
    RANGE = "RANGE"
    COMPRESSION = "COMPRESSION"
    CHAOTIC = "CHAOTIC"

class MarketRegimeDetector:
    logger = logging.getLogger("PulseViper.RegimeDetector")

    @classmethod
    def calculate_chop(cls, df: pd.DataFrame, period: int = 14) -> float:
        """
        Calculate Choppiness Index (CHOP).
        Values > 61.8 indicate extreme range/choppiness (compression).
        Values < 38.2 indicate strong trending expansion.
        """
        if len(df) < period:
            return 50.0
        
        try:
            highs = df['high'].rolling(window=period).max().values
            lows = df['low'].rolling(window=period).min().values
            
            # Sum of true ranges
            tr1 = df['high'] - df['low']
            tr2 = (df['high'] - df['close'].shift(1)).abs()
            tr3 = (df['low'] - df['close'].shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            sum_tr = tr.rolling(window=period).sum().values
            
            # Max high minus min low over the period
            range_diff = highs - lows
            range_diff = np.where(range_diff == 0, 1e-9, range_diff)  # Avoid division by zero
            
            chop = 100.0 * (np.log10(sum_tr) - np.log10(range_diff)) / np.log10(period)
            val = float(chop[-1])
            if np.isnan(val):
                return 50.0
            return val
        except Exception as e:
            cls.logger.error(f"Error calculating Choppiness Index: {e}")
            return 50.0

    @classmethod
    def detect_regime(cls, df: pd.DataFrame, rvol_val: float) -> RegimeType:
        """
        Detect current market regime from candles and relative volume.
        We calculate ADX internally if it exists in the features, or fallback to CHOP and ATR ratios.
        """
        if df is None or len(df) < 30:
            return RegimeType.RANGE
            
        try:
            chop = cls.calculate_chop(df, period=14)
            
            # Calculate ATR Ratio (current ATR relative to rolling 100-period median ATR)
            atr_col = 'atr' if 'atr' in df.columns else None
            if atr_col:
                current_atr = float(df[atr_col].iloc[-1])
                median_atr = float(df[atr_col].rolling(100).median().bfill().iloc[-1])
                atr_ratio = current_atr / (median_atr if median_atr > 0 else 1.0)
            else:
                atr_ratio = 1.0
                
            # Compute a proxy for trend strength from EMA crossover
            closes = df['close'].values
            ema20 = df['close'].ewm(span=20, adjust=False).mean().values
            ema50 = df['close'].ewm(span=50, adjust=False).mean().values
            
            # Check if EMAs are fan aligned (trend indicator)
            is_trending_ema = (closes[-1] > ema20[-1] > ema50[-1]) or (closes[-1] < ema20[-1] < ema50[-1])
            
            # 1. Chaotic regime (extremely high volatility and high volume, typical of news release)
            if atr_ratio > 2.2 or (atr_ratio > 1.8 and rvol_val > 2.0):
                return RegimeType.CHAOTIC
                
            # 2. Volatility Compression regime (high choppiness, low volume, consolidating range)
            if chop > 60.0 and rvol_val < 0.9:
                return RegimeType.COMPRESSION
                
            # 3. Trending Expansion regime (low choppiness, aligned EMAs or volume breakout)
            if chop < 38.2 or (chop < 45.0 and is_trending_ema and rvol_val > 1.2):
                return RegimeType.TRENDING
                
            # 4. Standard Mean Reversion Range (default)
            return RegimeType.RANGE
            
        except Exception as e:
            cls.logger.error(f"Error in detect_regime: {e}")
            return RegimeType.RANGE
