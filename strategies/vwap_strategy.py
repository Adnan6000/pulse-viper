# strategies/vwap_strategy.py
import numpy as np
import pandas as pd
import logging
from typing import Dict, Tuple, Optional
from utils.vwap_analyzer import VwapAnalyzer
from utils.settings_manager import clamp_m1_trade_levels

class VwapStrategy:
    logger = logging.getLogger("PulseViper.VwapStrategy")

    @classmethod
    def evaluate_vwap(
        cls,
        df_m1: Optional[pd.DataFrame] = None,
        df_m5: Optional[pd.DataFrame] = None,
        df_h1: Optional[pd.DataFrame] = None,
        current_price: float = 0.0,
        atr: float = 1.0,
        regime: str = "RANGE",
        htf_bias: int = 0,
    ) -> Tuple[Optional[str], float, float, Dict]:
        """
        VWAP Value Area Strategy (VWAP_VAS):
          - Range/Compression: Mean-reversion when price touches/exceeds outer standard deviation bands (2.0 or 3.0 std dev)
          - Trending: Pullback entry when price retraces back to the VWAP centerline or 1.0 std dev band in the direction of HTF trend
        """
        try:
            # 1. Select the execution timeframe (prefer M5 for cleaner signals, fallback to M1)
            df_exec = df_m5 if df_m5 is not None and len(df_m5) >= 15 else df_m1
            if df_exec is None or len(df_exec) < 10:
                return None, 0.0, 0.0, {}

            # 2. Compute VWAP and bands on execution timeframe
            df_vwap = VwapAnalyzer.calculate_session_vwap(df_exec)
            if 'vwap' not in df_vwap.columns or 'vwap_upper_2' not in df_vwap.columns:
                return None, 0.0, 0.0, {}

            last_row = df_vwap.iloc[-2] if len(df_vwap) >= 2 else df_vwap.iloc[-1]
            prev_row = df_vwap.iloc[-3] if len(df_vwap) >= 3 else last_row

            close = float(last_row['close'])
            low = float(last_row['low'])
            high = float(last_row['high'])
            
            vwap = float(last_row['vwap'])
            upper_1 = float(last_row['vwap_upper_1'])
            lower_1 = float(last_row['vwap_lower_1'])
            upper_2 = float(last_row['vwap_upper_2'])
            lower_2 = float(last_row['vwap_lower_2'])
            upper_3 = float(last_row['vwap_upper_3'])
            lower_3 = float(last_row['vwap_lower_3'])

            is_range_regime = regime in ["RANGE", "COMPRESSION"]

            # --- MEAN REVERSION MODEL (Range/Compression Regimes) ---
            if is_range_regime:
                # BUY setup: Price sweeps below Lower Deviation Band 2 or 3 and closes back above it (rejection check)
                if (prev_row['low'] <= lower_2 or prev_row['low'] <= lower_3) and (close > lower_2):
                    # SL is set below lowest price of last 3 candles or Lower Band 3
                    lowest_recent = float(df_vwap.iloc[-3:]['low'].min()) if len(df_vwap) >= 3 else low
                    sl = min(lowest_recent, lower_3) - 0.5 * atr
                    tp = vwap  # target session mean
                    
                    # Ensure positive risk-reward
                    if current_price > sl:
                        sl, tp = clamp_m1_trade_levels("BUY", current_price, sl, tp)
                        meta = {
                            "strategy": "VWAP_VAS",
                            "trigger": "VWAP_RANGE_BUY_REVERSION",
                            "regime": regime,
                            "vwap_price": vwap,
                            "deviation_band": "lower_2" if prev_row['low'] <= lower_2 else "lower_3"
                        }
                        return "BUY", sl, tp, meta

                # SELL setup: Price sweeps above Upper Deviation Band 2 or 3 and closes back below it
                if (prev_row['high'] >= upper_2 or prev_row['high'] >= upper_3) and (close < upper_2):
                    highest_recent = float(df_vwap.iloc[-3:]['high'].max()) if len(df_vwap) >= 3 else high
                    sl = max(highest_recent, upper_3) + 0.5 * atr
                    tp = vwap
                    
                    if current_price < sl:
                        sl, tp = clamp_m1_trade_levels("SELL", current_price, sl, tp)
                        meta = {
                            "strategy": "VWAP_VAS",
                            "trigger": "VWAP_RANGE_SELL_REVERSION",
                            "regime": regime,
                            "vwap_price": vwap,
                            "deviation_band": "upper_2" if prev_row['high'] >= upper_2 else "upper_3"
                        }
                        return "SELL", sl, tp, meta

            # --- TREND PULLBACK MODEL (Trending Regimes) ---
            else:
                # BULLISH HTF Trend: Pullback to VWAP / Lower Band 1
                if htf_bias == 1:
                    # Look for price trading between lower_1 and VWAP (undervalued zone in uptrend)
                    # and bouncing upwards (closing bullish)
                    if (low <= vwap or low <= lower_1) and (close > vwap or close > lower_1) and (close > last_row['open']):
                        lowest_recent = float(df_vwap.iloc[-4:]['low'].min()) if len(df_vwap) >= 4 else low
                        sl = lowest_recent - 0.5 * atr
                        tp = upper_2  # target outer expansion band
                        
                        if current_price > sl:
                            sl, tp = clamp_m1_trade_levels("BUY", current_price, sl, tp)
                            meta = {
                                "strategy": "VWAP_VAS",
                                "trigger": "VWAP_TREND_BUY_PULLBACK",
                                "regime": regime,
                                "vwap_price": vwap,
                                "deviation_band": "vwap" if low <= vwap else "lower_1"
                            }
                            return "BUY", sl, tp, meta

                # BEARISH HTF Trend: Pullback to VWAP / Upper Band 1
                elif htf_bias == -1:
                    # Look for price trading between upper_1 and VWAP (overvalued zone in downtrend)
                    # and bouncing downwards (closing bearish)
                    if (high >= vwap or high >= upper_1) and (close < vwap or close < upper_1) and (close < last_row['open']):
                        highest_recent = float(df_vwap.iloc[-4:]['high'].max()) if len(df_vwap) >= 4 else high
                        sl = highest_recent + 0.5 * atr
                        tp = lower_2
                        
                        if current_price < sl:
                            sl, tp = clamp_m1_trade_levels("SELL", current_price, sl, tp)
                            meta = {
                                "strategy": "VWAP_VAS",
                                "trigger": "VWAP_TREND_SELL_PULLBACK",
                                "regime": regime,
                                "vwap_price": vwap,
                                "deviation_band": "vwap" if high >= vwap else "upper_1"
                            }
                            return "SELL", sl, tp, meta

            return None, 0.0, 0.0, {}
        except Exception as e:
            cls.logger.error(f"Error in evaluate_vwap: {e}")
            return None, 0.0, 0.0, {}
