# strategies/raja_strategy.py
import numpy as np
import pandas as pd
import logging
from typing import Dict, Tuple, Optional

from utils.settings_manager import clamp_m1_trade_levels

class RajaStrategy:
    logger = logging.getLogger("PulseViper.RajaStrategy")

    @classmethod
    def evaluate_raja(
        cls,
        df_m15: Optional[pd.DataFrame] = None,
        df_m30: Optional[pd.DataFrame] = None,
        df_h1: Optional[pd.DataFrame] = None,
        df_h4: Optional[pd.DataFrame] = None,
        current_price: float = 0.0,
        atr: float = 1.0,
        volume_cache: Optional[Dict] = None,
        regime: str = "RANGE",
    ) -> Tuple[Optional[str], float, float, Dict]:
        """
        Raja Banks (WicksDontLie) Strategy:
          - Zones (Support/Resistance) mapped on Higher Timeframe: H4 and H1.
          - Executed on Lower Timeframe: M30 or M15.
          - Core setups:
            1. Support/Resistance Zone Retest & Candlestick Rejection.
            2. Wick Fill: price fills the wick of a previous candle when breaking highs/lows.
          - Sessions: London (07:00-09:00 UTC) and NY (12:00-14:00 UTC) session focus.
        """
        try:
            # Drop to M30 or M15 for execution
            df_exec = df_m30 if df_m30 is not None and len(df_m30) >= 10 else df_m15
            if df_exec is None or len(df_exec) < 5:
                return None, 0.0, 0.0, {}

            df_htf = df_h4 if df_h4 is not None and len(df_h4) >= 10 else df_h1
            if df_htf is None or len(df_htf) < 5:
                return None, 0.0, 0.0, {}

            # Map key zones on HTF (recent swing points)
            recent_htf = df_htf.iloc[-20:]
            htf_highs = recent_htf['high'].values
            htf_lows = recent_htf['low'].values
            
            # Simple zone search
            sup_zones = []
            res_zones = []
            tol = 0.05 * atr  # Small tolerance to catch zones on flat/ranging price action
            for i in range(2, len(recent_htf) - 2):
                if (htf_lows[i] <= htf_lows[i-1] + tol and htf_lows[i] <= htf_lows[i-2] + tol
                        and htf_lows[i] <= htf_lows[i+1] + tol and htf_lows[i] <= htf_lows[i+2] + tol):
                    sup_zones.append(float(htf_lows[i]))
                if (htf_highs[i] >= htf_highs[i-1] - tol and htf_highs[i] >= htf_highs[i-2] - tol
                        and htf_highs[i] >= htf_highs[i+1] - tol and htf_highs[i] >= htf_highs[i+2] - tol):
                    res_zones.append(float(htf_highs[i]))

            closest_support = max([z for z in sup_zones if z < current_price], default=0.0)
            closest_resistance = min([z for z in res_zones if z > current_price], default=float('inf'))

            # Setup 1: Wick Rejection of Zone (Support/Resistance)
            # Look at the last closed candle on the execution timeframe
            last_candle = df_exec.iloc[-2]
            last_low = float(last_candle['low'])
            last_high = float(last_candle['high'])
            last_close = float(last_candle['close'])
            last_open = float(last_candle['open'])
            last_spread = last_high - last_low

            # Rejection from support
            if closest_support > 0.0 and abs(last_low - closest_support) <= 0.4 * atr:
                # Rejection: long lower wick, closed in upper 50%
                lower_wick = min(last_open, last_close) - last_low
                if lower_wick >= 0.5 * last_spread and last_close > last_open:
                    sl = last_low - 0.1 * atr
                    tp = current_price + 2.0 * (current_price - sl)
                    sl, tp = clamp_m1_trade_levels("BUY", current_price, sl, tp)
                    meta = {
                        "strategy": "RAJA_BANKS",
                        "trigger": "RAJA_SUPPORT_REJECTION",
                        "support_zone": closest_support,
                        "timeframe": "M30" if df_m30 is not None else "M15"
                    }
                    return "BUY", sl, tp, meta

            # Rejection from resistance
            if closest_resistance != float('inf') and abs(last_high - closest_resistance) <= 0.4 * atr:
                # Rejection: long upper wick, closed in lower 50%
                upper_wick = last_high - max(last_open, last_close)
                if upper_wick >= 0.5 * last_spread and last_close < last_open:
                    sl = last_high + 0.1 * atr
                    tp = current_price - 2.0 * (sl - current_price)
                    sl, tp = clamp_m1_trade_levels("SELL", current_price, sl, tp)
                    meta = {
                        "strategy": "RAJA_BANKS",
                        "trigger": "RAJA_RESISTANCE_REJECTION",
                        "resistance_zone": closest_resistance,
                        "timeframe": "M30" if df_m30 is not None else "M15"
                    }
                    return "SELL", sl, tp, meta

            # Setup 2: Wick Fill Setup (clean range candle fill)
            # The previous candle left a large wick, and the current candle is crossing the previous high/low body boundary to fill it.
            prev_candle = df_exec.iloc[-3]  # The candle BEFORE last_candle (wick donor candle)
            prev_high = float(prev_candle['high'])
            prev_low = float(prev_candle['low'])
            prev_close = float(prev_candle['close'])
            prev_open = float(prev_candle['open'])
            prev_spread = prev_high - prev_low
            
            # Bullish wick fill check: previous candle had a long upper wick (>= 40% of spread) and closed bullish
            prev_upper_wick = prev_high - max(prev_open, prev_close)
            if prev_spread > 0 and prev_upper_wick >= 0.4 * prev_spread and prev_close > prev_open:
                # Current price has broken above the previous body close and is moving to fill the wick
                if prev_close < current_price < prev_high:
                    sl = min(prev_open, prev_low)
                    tp = prev_high
                    if (tp - current_price) >= 1.0 * (current_price - sl): # Min RR 1.0
                        sl, tp = clamp_m1_trade_levels("BUY", current_price, sl, tp)
                        meta = {
                            "strategy": "RAJA_BANKS",
                            "trigger": "RAJA_WICK_FILL_BUY",
                            "wick_high": prev_high,
                            "timeframe": "M30" if df_m30 is not None else "M15"
                        }
                        return "BUY", sl, tp, meta

            # Bearish wick fill check: previous candle had a long lower wick (>= 40% of spread) and closed bearish
            prev_lower_wick = min(prev_open, prev_close) - prev_low
            if prev_spread > 0 and prev_lower_wick >= 0.4 * prev_spread and prev_close < prev_open:
                # Current price has broken below the previous body close and is moving to fill the wick
                if prev_high > current_price > prev_close:
                    sl = max(prev_open, prev_high)
                    tp = prev_low
                    if (current_price - tp) >= 1.0 * (sl - current_price): # Min RR 1.0
                        sl, tp = clamp_m1_trade_levels("SELL", current_price, sl, tp)
                        meta = {
                            "strategy": "RAJA_BANKS",
                            "trigger": "RAJA_WICK_FILL_SELL",
                            "wick_low": prev_low,
                            "timeframe": "M30" if df_m30 is not None else "M15"
                        }
                        return "SELL", sl, tp, meta

            return None, 0.0, 0.0, {}
        except Exception as e:
            cls.logger.error(f"Error in evaluate_raja: {e}")
            return None, 0.0, 0.0, {}
