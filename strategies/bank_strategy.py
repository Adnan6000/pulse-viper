# strategies/bank_strategy.py
import numpy as np
import pandas as pd
import logging
from typing import Dict, Tuple, Optional

from utils.settings_manager import clamp_m1_trade_levels

class BankStrategy:
    logger = logging.getLogger("PulseViper.BankStrategy")

    @classmethod
    def evaluate_bank(
        cls,
        df_m1: Optional[pd.DataFrame] = None,
        df_m5: Optional[pd.DataFrame] = None,
        df_m15: Optional[pd.DataFrame] = None,
        df_h1: Optional[pd.DataFrame] = None,
        df_h4: Optional[pd.DataFrame] = None,
        current_price: float = 0.0,
        atr: float = 1.0,
        volume_cache: Optional[Dict] = None,
        regime: str = "RANGE",
    ) -> Tuple[Optional[str], float, float, Dict]:
        """
        Bank-to-Bank Trading Strategy:
          - High Timeframe: H4 / H1 to compute Volume Profile POC / High Volume Nodes.
          - Low Timeframe: M15 / M5 for retest execution.
          - Trigger: Price retests the POC/HVN level on lower timeframe on declining volume (rvol < 1.0)
            and wicks reject the level.
        """
        try:
            if not volume_cache or "profile" not in volume_cache:
                return None, 0.0, 0.0, {}

            df_exec = df_m15 if df_m15 is not None and len(df_m15) >= 10 else df_m5
            if df_exec is None or len(df_exec) < 5:
                return None, 0.0, 0.0, {}

            profile = volume_cache["profile"]
            poc_price = profile.get("poc_price", 0.0)
            if poc_price == 0.0:
                return None, 0.0, 0.0, {}

            # Check closeness to POC (within 0.5 * ATR)
            dist = abs(current_price - poc_price)
            if dist > 0.5 * atr:
                return None, 0.0, 0.0, {}

            # Verify low volume retest on execution timeframe
            # Calculate rolling relative volume of the last 3 closed candles
            from utils.volume_analyzer import VolumeAnalyzer
            recent_rvols = []
            for i in range(len(df_exec) - 3, len(df_exec)):
                recent_rvols.append(VolumeAnalyzer.calculate_rvol_latest(df_exec.iloc[:i]))
            
            avg_rvol = np.mean(recent_rvols)
            volume_dried = avg_rvol < 1.0  # volume dried up on retest (institutional absorption)
            
            if not volume_dried:
                return None, 0.0, 0.0, {}

            # Wick Rejection Trigger: last closed candle low or high wicks through POC, body closes back
            last_candle = df_exec.iloc[-2]
            last_low = float(last_candle['low'])
            last_high = float(last_candle['high'])
            last_close = float(last_candle['close'])
            last_open = float(last_candle['open'])
            
            # Rejection from below (BUY)
            if last_low <= poc_price < last_close and current_price > poc_price:
                sl = min(last_low, poc_price - 0.2 * atr)
                tp = current_price + 2.0 * (current_price - sl)
                sl, tp = clamp_m1_trade_levels("BUY", current_price, sl, tp)
                meta = {
                    "strategy": "BANK_TO_BANK",
                    "trigger": "BANK_POC_RETEST_BUY",
                    "poc_price": poc_price,
                    "retest_rvol": avg_rvol,
                }
                return "BUY", sl, tp, meta

            # Rejection from above (SELL)
            if last_high >= poc_price > last_close and current_price < poc_price:
                sl = max(last_high, poc_price + 0.2 * atr)
                tp = current_price - 2.0 * (sl - current_price)
                sl, tp = clamp_m1_trade_levels("SELL", current_price, sl, tp)
                meta = {
                    "strategy": "BANK_TO_BANK",
                    "trigger": "BANK_POC_RETEST_SELL",
                    "poc_price": poc_price,
                    "retest_rvol": avg_rvol,
                }
                return "SELL", sl, tp, meta

            return None, 0.0, 0.0, {}
        except Exception as e:
            cls.logger.error(f"Error in evaluate_bank: {e}")
            return None, 0.0, 0.0, {}
