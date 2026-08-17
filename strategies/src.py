# strategies/src.py
import numpy as np
import pandas as pd
import logging
from datetime import datetime, timezone, time
from typing import Dict, Tuple, Optional

from utils.settings_manager import clamp_m1_trade_levels

class SrcStrategy:
    logger = logging.getLogger("PulseViper.SrcStrategy")

    @classmethod
    def evaluate_src(
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
        SRC (Support and Resistance Channels)
        Detects ascending/descending parallel channels.
        Buys at the bottom of an ascending channel, Sells at the top of descending.
        Also trades breakouts.
        Returns: (action, regime, sl, tp, metadata)
        """
        try:
            if df_m15 is None or len(df_m15) < 50:
                return None, regime, 0.0, 0.0, {}

            # Very simplified channel detection using rolling mins/maxs
            rolling_high = df_m15['high'].rolling(10).max()
            rolling_low = df_m15['low'].rolling(10).min()
            
            # Get latest 3 swing points, using closed candles only to prevent repainting
            h1, h2, h3 = rolling_high.iloc[-30], rolling_high.iloc[-15], rolling_high.iloc[-2]
            l1, l2, l3 = rolling_low.iloc[-30], rolling_low.iloc[-15], rolling_low.iloc[-2]
            
            # Check for ascending channel (Higher Highs, Higher Lows)
            ascending = (h3 > h2 > h1) and (l3 > l2 > l1)
            # Check for descending channel (Lower Highs, Lower Lows)
            descending = (h3 < h2 < h1) and (l3 < l2 < l1)

            action = None
            sl = 0.0
            tp = 0.0
            
            # Current channel boundaries
            channel_top = h3
            channel_bottom = l3

            # Trading the Bounce
            if ascending and current_price <= channel_bottom + (atr * 0.5):
                action = "BUY"
                sl = channel_bottom - atr
                tp = channel_top
            
            elif descending and current_price >= channel_top - (atr * 0.5):
                action = "SELL"
                sl = channel_top + atr
                tp = channel_bottom

            if action:
                sl, tp = clamp_m1_trade_levels(action, current_price, sl, tp)
                return action, "TRENDING", sl, tp, {
                    "strategy": "SRC",
                    "channel_top": channel_top,
                    "channel_bottom": channel_bottom,
                    "channel_type": "ASCENDING" if ascending else "DESCENDING"
                }

            return None, regime, 0.0, 0.0, {}

        except Exception as e:
            cls.logger.error(f"SRC Strategy Error: {e}")
            return None, regime, 0.0, 0.0, {}
