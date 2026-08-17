# strategies/amd.py
import numpy as np
import pandas as pd
import logging
from datetime import datetime, timezone, time
from typing import Dict, Tuple, Optional

from utils.settings_manager import clamp_m1_trade_levels

class AmdStrategy:
    logger = logging.getLogger("PulseViper.AmdStrategy")

    @classmethod
    def evaluate_amd(
        cls,
        df_m1: Optional[pd.DataFrame] = None,
        df_m5: Optional[pd.DataFrame] = None,
        df_m15: Optional[pd.DataFrame] = None,
        df_h1: Optional[pd.DataFrame] = None,
        df_h4: Optional[pd.DataFrame] = None,
        current_price: float = 0.0,
        atr: float = 1.0,
        htf_bias: int = 0,
        volume_cache: Optional[Dict] = None,
        regime: str = "RANGE",
    ) -> Tuple[Optional[str], str, float, float, Dict]:
        """
        AMD (Accumulation, Manipulation, Distribution) Strategy - ICT Power of 3
        1. Accumulation: Tight range during low volume hours.
        2. Manipulation: Sharp move out of the range to trap retail.
        3. Distribution: True move in the intended direction.
        Returns: (action, regime, sl, tp, metadata)
        """
        try:
            if df_m15 is None or len(df_m15) < 30:
                return None, regime, 0.0, 0.0, {}

            # Detect Accumulation (Last 20 M15 candles ~ 5 hours)
            recent_m15 = df_m15.iloc[-25:-5] 
            acc_high = recent_m15['high'].max()
            acc_low = recent_m15['low'].min()
            acc_range = acc_high - acc_low

            # If accumulation range is too large (> 3 * ATR), it's not accumulation
            if acc_range > atr * 3.0:
                return None, regime, 0.0, 0.0, {}

            # Detect Manipulation in the recent 5 M15 closed candles (excluding forming candle [-1])
            manip_m15 = df_m15.iloc[-6:-1]
            manip_high = manip_m15['high'].max()
            manip_low = manip_m15['low'].min()
            
            sweep_high = manip_high > acc_high + (atr * 0.1)
            sweep_low = manip_low < acc_low - (atr * 0.1)

            action = None
            sl = 0.0
            tp = 0.0
            
            # Distribution Phase
            if sweep_high and current_price < acc_high and htf_bias <= 0:
                action = "SELL"
                sl = manip_high + (atr * 0.5)
                tp = acc_low - (acc_range * 1.5)
            
            elif sweep_low and current_price > acc_low and htf_bias >= 0:
                action = "BUY"
                sl = manip_low - (atr * 0.5)
                tp = acc_high + (acc_range * 1.5)

            if action:
                sl, tp = clamp_m1_trade_levels(action, current_price, sl, tp)
                return action, "TRENDING", sl, tp, {
                    "strategy": "AMD",
                    "acc_high": acc_high,
                    "acc_low": acc_low,
                    "manipulation_swept": "HIGH" if sweep_high else "LOW"
                }

            return None, regime, 0.0, 0.0, {}

        except Exception as e:
            cls.logger.error(f"AMD Strategy Error: {e}")
            return None, regime, 0.0, 0.0, {}
