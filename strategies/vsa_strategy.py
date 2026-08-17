# strategies/vsa_strategy.py
import numpy as np
import pandas as pd
import logging
from typing import Dict, Tuple, Optional

from utils.settings_manager import clamp_m1_trade_levels

class VsaStrategy:
    logger = logging.getLogger("PulseViper.VsaStrategy")

    @classmethod
    def evaluate_vsa(
        cls,
        df_m1: Optional[pd.DataFrame] = None,
        df_m5: Optional[pd.DataFrame] = None,
        df_h1: Optional[pd.DataFrame] = None,
        current_price: float = 0.0,
        atr: float = 1.0,
        volume_cache: Optional[Dict] = None,
        regime: str = "RANGE",
    ) -> Tuple[Optional[str], float, float, Dict]:
        """
        Volume Spread Analysis (VSA) Strategy:
          - Background context from H1 (Volume increase/decrease trend).
          - Execution triggers on M5 or M1 using detect_vsa_signals.
        """
        try:
            df_exec = df_m5 if df_m5 is not None and len(df_m5) >= 15 else df_m1
            if df_exec is None or len(df_exec) < 10:
                return None, 0.0, 0.0, {}

            # Detect VSA signals
            from utils.volume_analyzer import VolumeAnalyzer
            vsa_signals = VolumeAnalyzer.detect_vsa_signals(df_exec, df_exec['atr'] if 'atr' in df_exec.columns else pd.Series(atr, index=df_exec.index), lookback=3)
            if not vsa_signals:
                return None, 0.0, 0.0, {}

            # Get the latest detected VSA signal
            latest_signal = vsa_signals[-1]
            pattern = latest_signal["pattern"]
            direction = latest_signal["direction"]
            confidence = latest_signal["confidence"]
            rvol = latest_signal["rvol"]

            # Background check on H1:
            # For a buy, we want to see either:
            # 1. H1 volume increasing on bullish candles (strong demand), or
            # 2. H1 volume declining on bearish candles (selling pressure drying up).
            h1_volume_ok = False  # Must satisfy at least one H1 volume condition
            if df_h1 is not None and len(df_h1) >= 5:
                recent_h1 = df_h1.iloc[-3:]
                h1_closes = recent_h1['close'].values
                h1_opens = recent_h1['open'].values
                h1_vols = recent_h1['volume'].values
                
                # Check if last H1 was bearish but volume was lower than previous
                if h1_closes[-1] < h1_opens[-1] and h1_vols[-1] < h1_vols[-2]:
                    h1_volume_ok = True  # supply drying up
                elif h1_closes[-1] > h1_opens[-1] and h1_vols[-1] > h1_vols[-2]:
                    h1_volume_ok = True  # demand expanding
            else:
                # No H1 data available — allow through (can't check)
                h1_volume_ok = True

            if not h1_volume_ok:
                return None, 0.0, 0.0, {}

            # Execute triggers
            # BUY triggers: SPRING, STOPPING_VOLUME, SELLING_CLIMAX, EFFORT_VS_RESULT_BULLISH, TEST_OF_SUPPLY, NO_SUPPLY
            bull_patterns = ['SPRING', 'STOPPING_VOLUME', 'SELLING_CLIMAX', 'EFFORT_VS_RESULT_BULLISH', 'TEST_OF_SUPPLY', 'NO_SUPPLY']
            if direction == 1 and pattern in bull_patterns:
                # Place stop loss below the low of the signal candle (with minor buffer)
                last_low = float(df_exec.iloc[-2]['low']) if len(df_exec) >= 2 else current_price - atr
                sl = min(last_low, current_price - 1.2 * atr)
                tp = current_price + 1.5 * (current_price - sl)
                sl, tp = clamp_m1_trade_levels("BUY", current_price, sl, tp)
                meta = {
                    "strategy": "VSA",
                    "trigger": f"VSA_{pattern}",
                    "confidence": confidence,
                    "rvol": rvol
                }
                return "BUY", sl, tp, meta

            # SELL triggers: UPTHRUST, BUYING_CLIMAX, EFFORT_VS_RESULT_BEARISH, TEST_OF_DEMAND, NO_DEMAND
            bear_patterns = ['UPTHRUST', 'BUYING_CLIMAX', 'EFFORT_VS_RESULT_BEARISH', 'TEST_OF_DEMAND', 'NO_DEMAND']
            if direction == -1 and pattern in bear_patterns:
                # Place stop loss above the high of the signal candle
                last_high = float(df_exec.iloc[-2]['high']) if len(df_exec) >= 2 else current_price + atr
                sl = max(last_high, current_price + 1.2 * atr)
                tp = current_price - 1.5 * (sl - current_price)
                sl, tp = clamp_m1_trade_levels("SELL", current_price, sl, tp)
                meta = {
                    "strategy": "VSA",
                    "trigger": f"VSA_{pattern}",
                    "confidence": confidence,
                    "rvol": rvol
                }
                return "SELL", sl, tp, meta

            return None, 0.0, 0.0, {}
        except Exception as e:
            cls.logger.error(f"Error in evaluate_vsa: {e}")
            return None, 0.0, 0.0, {}
