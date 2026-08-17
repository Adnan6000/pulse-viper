# strategies/avc_strategy.py
import numpy as np
import pandas as pd
import logging
from typing import Dict, Tuple, Optional

from utils.settings_manager import clamp_m1_trade_levels

class AvcStrategy:
    logger = logging.getLogger("PulseViper.AvcStrategy")

    @classmethod
    def evaluate_avc(
        cls,
        df_m1: Optional[pd.DataFrame] = None,
        df_m5: Optional[pd.DataFrame] = None,
        df_m15: Optional[pd.DataFrame] = None,
        current_price: float = 0.0,
        atr: float = 1.0,
        volume_cache: Optional[Dict] = None,
        regime: str = "RANGE",
    ) -> Tuple[Optional[str], float, float, Dict]:
        """
        Accumulation Volume Confirmation (AVC) Strategy:
          - Accumulation: narrow range consolidation (swing high/low size <= 1.5 * ATR)
            for at least 8 completed candles on M5/M15, with volume drying up (rvol < 1.1).
          - Breakout: A candle breaks out of the range with expanding volume (rvol >= 1.4).
        """
        try:
            df_ref = df_m5 if df_m5 is not None and len(df_m5) >= 15 else df_m15
            if df_ref is None or len(df_ref) < 12:
                return None, 0.0, 0.0, {}

            # Analyze the last 10 candles before the current forming candle
            consolidation_candles = df_ref.iloc[-11:-1]
            highs = consolidation_candles['high'].values
            lows = consolidation_candles['low'].values
            
            range_high = float(highs.max())
            range_low = float(lows.min())
            range_size = range_high - range_low
            
            # Condition 1: Tight range consolidation
            is_accumulating = range_size <= 1.5 * atr
            
            # Condition 2: Volume drying up during consolidation
            from utils.volume_analyzer import VolumeAnalyzer
            recent_rvols = []
            for i in range(len(df_ref) - 11, len(df_ref) - 1):
                recent_rvols.append(VolumeAnalyzer.calculate_rvol_latest(df_ref.iloc[:i]))
            avg_rvol = np.mean(recent_rvols)
            volume_dry = avg_rvol < 1.1
            
            if not (is_accumulating and volume_dry):
                return None, 0.0, 0.0, {}

            # Breakout: current price breaks range, and latest rvol is expanding
            rvol_latest = VolumeAnalyzer.calculate_rvol_latest(df_ref)
            breakout_vol_ok = rvol_latest >= 1.4

            if breakout_vol_ok and current_price > range_high:
                sl = range_low - 0.2 * atr
                tp = current_price + 1.5 * (current_price - sl)
                sl, tp = clamp_m1_trade_levels("BUY", current_price, sl, tp)
                meta = {
                    "strategy": "AVC",
                    "trigger": "AVC_ACCUMULATION_BREAKOUT_BUY",
                    "range_high": range_high,
                    "range_low": range_low,
                    "rvol": rvol_latest,
                }
                return "BUY", sl, tp, meta

            if breakout_vol_ok and current_price < range_low:
                sl = range_high + 0.2 * atr
                tp = current_price - 1.5 * (sl - current_price)
                sl, tp = clamp_m1_trade_levels("SELL", current_price, sl, tp)
                meta = {
                    "strategy": "AVC",
                    "trigger": "AVC_ACCUMULATION_BREAKOUT_SELL",
                    "range_high": range_high,
                    "range_low": range_low,
                    "rvol": rvol_latest,
                }
                return "SELL", sl, tp, meta

            return None, 0.0, 0.0, {}
        except Exception as e:
            cls.logger.error(f"Error in evaluate_avc: {e}")
            return None, 0.0, 0.0, {}
