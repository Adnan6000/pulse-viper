# strategies/fib_retest.py
import numpy as np
import pandas as pd
import logging
from typing import Dict, Tuple, Optional

class FibRetestStrategy:
    logger = logging.getLogger("PulseViper.FibRetestStrategy")

    @staticmethod
    def calculate_ema(series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def calculate_adx(df: pd.DataFrame, period: int = 14) -> float:
        """Calculate ADX for the latest bar"""
        try:
            high = df['high']
            low = df['low']
            close = df['close']
            
            tr1 = high - low
            tr2 = (high - close.shift()).abs()
            tr3 = (low - close.shift()).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            
            upmove = high - high.shift()
            downmove = low.shift() - low
            
            plus_dm = np.where((upmove > downmove) & (upmove > 0), upmove, 0.0)
            minus_dm = np.where((downmove > upmove) & (downmove > 0), downmove, 0.0)
            
            plus_dm = pd.Series(plus_dm, index=df.index)
            minus_dm = pd.Series(minus_dm, index=df.index)
            
            # Simple rolling average smoothing
            tr_smooth = tr.rolling(window=period).mean()
            plus_di = 100 * (plus_dm.rolling(window=period).mean() / (tr_smooth + 1e-9))
            minus_di = 100 * (minus_dm.rolling(window=period).mean() / (tr_smooth + 1e-9))
            
            dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
            adx = dx.rolling(window=period).mean()
            return float(adx.iloc[-1])
        except Exception:
            return 0.0

    @classmethod
    def evaluate_retest(cls, df_context: pd.DataFrame, current_price: float, atr: float) -> Tuple[Optional[str], str, float, float, Dict]:
        """
        Evaluate Fibonacci retest entries based on market regime.
        Returns: Tuple of (Action "BUY"/"SELL"/None, Regime "bullish"/"bearish"/"sideway", SL, TP, Metadata)
        """
        try:
            if len(df_context) < 100:
                return None, "sideway", 0.0, 0.0, {}

            # 1. Determine Market Regime using EMA 20/50 and ADX 14
            close_series = df_context['close']
            ema20_series = cls.calculate_ema(close_series, 20)
            ema50_series = cls.calculate_ema(close_series, 50)
            
            ema20 = ema20_series.iloc[-1]
            ema50 = ema50_series.iloc[-1]
            adx = cls.calculate_adx(df_context, 14)
            
            if adx >= 22:
                if ema20 > ema50:
                    regime = "bullish"
                else:
                    regime = "bearish"
            else:
                regime = "sideway"

            # 2. Find Swing High/Low in the last 100 bars
            recent_df = df_context.tail(100)
            swing_high = float(recent_df['high'].max())
            swing_low = float(recent_df['low'].min())
            price_range = swing_high - swing_low
            
            if price_range <= 0:
                return None, regime, 0.0, 0.0, {}

            # Calculate Fib Levels
            fib_50 = swing_high - 0.50 * price_range
            fib_618 = swing_high - 0.618 * price_range
            fib_786 = swing_high - 0.786 * price_range

            action = None
            sl_price = 0.0
            tp_price = 0.0
            metadata = {
                "regime": regime,
                "swing_high": swing_high,
                "swing_low": swing_low,
                "fib_50": fib_50,
                "fib_618": fib_618,
                "fib_786": fib_786,
                "adx": adx,
                "ema20": ema20,
                "ema50": ema50
            }

            if regime == "bullish":
                # BUY pullback when price is in the Golden Zone (between 50% and 78.6% retracement)
                if fib_786 <= current_price <= fib_50:
                    action = "BUY"
                    sl_price = swing_low - (0.2 * atr)
                    # Minimum SL distance to avoid tight stops
                    sl_price = min(sl_price, current_price - (1.5 * atr))
                    tp_price = swing_high
            
            elif regime == "bearish":
                # SELL pullback when price is in the Golden Zone (between 50% and 78.6% retracement)
                if fib_50 <= current_price <= fib_786:
                    action = "SELL"
                    sl_price = swing_high + (0.2 * atr)
                    # Minimum SL distance
                    sl_price = max(sl_price, current_price + (1.5 * atr))
                    tp_price = swing_low
            
            else: # sideway
                # Buy boundary retest when price is within 15% distance of swing_low
                buy_boundary = swing_low + 0.15 * price_range
                sell_boundary = swing_high - 0.15 * price_range
                
                if current_price <= buy_boundary:
                    action = "BUY"
                    sl_price = swing_low - (0.2 * atr)
                    sl_price = min(sl_price, current_price - (1.5 * atr))
                    tp_price = swing_high
                # Sell boundary retest when price is within 15% distance of swing_high
                elif current_price >= sell_boundary:
                    action = "SELL"
                    sl_price = swing_high + (0.2 * atr)
                    sl_price = max(sl_price, current_price + (1.5 * atr))
                    tp_price = swing_low

            return action, regime, sl_price, tp_price, metadata

        except Exception as e:
            cls.logger.error(f"Error evaluating Fibonacci retest: {e}")
            return None, "sideway", 0.0, 0.0, {}
