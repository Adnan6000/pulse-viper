# utils/features.py
import numpy as np
import pandas as pd
from scipy import stats

class AdvancedFeatureEngine:
    def __init__(self):
        self.feature_cache = {}
    
    def compute_rsi(self, prices, period=14):
        """Standard Welles Wilder smoothed RSI matching MT5"""
        delta = prices.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        
        # Wilder's smoothing uses alpha = 1 / period
        avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        
        rs = avg_gain / (avg_loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        return rsi.fillna(50)
    
    def compute_ema_ribbon(self, prices, periods=[8, 13, 21, 34, 55]):
        """Multiple EMA ribbon for trend strength"""
        emas = {}
        for period in periods:
            emas[f'ema_{period}'] = prices.ewm(span=period, adjust=False).mean()
        return pd.DataFrame(emas)
    
    def compute_atr(
        self,
        df: pd.DataFrame,
        period: int = 14,
    ) -> tuple[pd.Series, pd.Series]:
        """Advanced ATR with normalization"""
        high, low, close = df['high'], df['low'], df['close']
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        # Use Wilder's smoothing for ATR to match MT5
        atr = tr.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        # Normalize ATR by price
        atr_pct = atr / close
        return atr, atr_pct
    
    def compute_macd(self, prices, fast=12, slow=26, signal=9):
        """MACD with histogram"""
        ema_fast = prices.ewm(span=fast, adjust=False).mean()
        ema_slow = prices.ewm(span=slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=signal, adjust=False).mean()
        macd_histogram = macd - macd_signal
        return macd, macd_signal, macd_histogram
    
    def compute_bollinger_bands(self, prices, period=20, std=2):
        """Bollinger Bands with squeeze detection"""
        sma = prices.rolling(period).mean()
        rolling_std = prices.rolling(period).std()
        upper = sma + (rolling_std * std)
        lower = sma - (rolling_std * std)
        bandwidth = (upper - lower) / sma
        return upper, sma, lower, bandwidth
    
    def compute_market_regime(self, df, lookback=50):
        """Detect trending vs ranging markets"""
        returns = df['close'].pct_change()
        volatility = returns.rolling(lookback).std()
        adx = self.compute_adx(df, period=14)
        
        # Regime classification
        regime = 'ranging'
        if adx.iloc[-1] > 25:
            regime = 'trending'
        if volatility.iloc[-1] > volatility.quantile(0.8):
            regime = 'volatile'
        
        return regime
    
    def compute_adx(self, df, period=14):
        """Welles Wilder's Standard ADX matching MT5"""
        high, low, close = df['high'], df['low'], df['close']
        
        # Up move and down move
        up_move = high - high.shift(1)
        down_move = low.shift(1) - low
        
        # +DM and -DM calculations
        plus_dm = pd.Series(0.0, index=df.index)
        minus_dm = pd.Series(0.0, index=df.index)
        
        # Conditions
        cond_plus = (up_move > down_move) & (up_move > 0)
        cond_minus = (down_move > up_move) & (down_move > 0)
        
        plus_dm[cond_plus] = up_move[cond_plus]
        minus_dm[cond_minus] = down_move[cond_minus]
        
        # ATR / TR calculation
        tr = self.compute_true_range(df)
        # Welles Wilder smoothing (exponential moving average with alpha = 1 / period)
        atr_wilder = tr.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        
        smoothed_plus_dm = plus_dm.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        smoothed_minus_dm = minus_dm.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        
        plus_di = 100 * (smoothed_plus_dm / (atr_wilder + 1e-10))
        minus_di = 100 * (smoothed_minus_dm / (atr_wilder + 1e-10))
        
        dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10))
        adx = dx.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        return adx
    
    def compute_true_range(self, df):
        high, low, close = df['high'], df['low'], df['close']
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    def compute_volume_profile(self, df, period=20):
        """Volume-based features"""
        volume_sma = df['volume'].rolling(period).mean()
        volume_ratio = df['volume'] / volume_sma
        obv = (np.sign(df['close'].diff()) * df['volume']).cumsum()
        return volume_ratio, obv
    
    def compute_advanced_features(self, df):
        """Comprehensive feature engineering"""
        df = df.copy()
        
        # Price-based features
        df['returns'] = df['close'].pct_change()
        df['log_returns'] = np.log(df['close'] / df['close'].shift())
        df['price_position'] = (df['close'] - df['low'].rolling(20).min()) / \
                              (df['high'].rolling(20).max() - df['low'].rolling(20).min())
        
        # Momentum indicators
        df['rsi'] = self.compute_rsi(df['close'])
        df['rsi_slope'] = df['rsi'].diff(3)  # 3-period slope
        
        # Trend indicators
        ema_ribbon = self.compute_ema_ribbon(df['close'])
        df = pd.concat([df, ema_ribbon], axis=1)
        df['ema_trend'] = (df['ema_8'] > df['ema_21']).astype(int)
        
        # Volatility features
        df['atr'], df['atr_pct'] = self.compute_atr(df)
        df['volatility'] = df['returns'].rolling(20).std()
        
        # MACD
        macd, macd_signal, macd_hist = self.compute_macd(df['close'])
        df['macd'] = macd
        df['macd_signal'] = macd_signal
        df['macd_hist'] = macd_hist
        
        # Bollinger Bands
        bb_upper, bb_middle, bb_lower, bb_bandwidth = self.compute_bollinger_bands(df['close'])
        df['bb_upper'] = bb_upper
        df['bb_lower'] = bb_lower
        df['bb_position'] = (df['close'] - bb_lower) / (bb_upper - bb_lower)
        df['bb_squeeze'] = (bb_bandwidth < bb_bandwidth.quantile(0.1)).astype(int)
        
        # Volume features
        df['volume_ratio'], df['obv'] = self.compute_volume_profile(df)
        
        # Market regime
        df['market_regime'] = self.compute_market_regime(df)
        
        # Support/Resistance levels
        df['resistance'] = df['high'].rolling(20).max()
        df['support'] = df['low'].rolling(20).min()
        df['distance_to_resistance'] = (df['resistance'] - df['close']) / df['close']
        df['distance_to_support'] = (df['close'] - df['support']) / df['close']
        
        # Clean up
        df = df.dropna()
        
        return df

# Global instance
feature_engine = AdvancedFeatureEngine()