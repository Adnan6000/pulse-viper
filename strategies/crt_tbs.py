# strategies/crt_tbs.py
import numpy as np
import pandas as pd
import logging
from typing import Dict, Tuple, Optional

class CrtTbsStrategy:
    logger = logging.getLogger("PulseViper.CrtTbsStrategy")

    @classmethod
    def evaluate_crt_tbs(
        cls, 
        df_context: pd.DataFrame, 
        current_price: float, 
        atr: float,
        volume_cache: Optional[Dict] = None,
        sentiment_cache: Optional[Dict] = None,
        htf_bias: int = 0,
        df_ltf: Optional[pd.DataFrame] = None
    ) -> Tuple[Optional[str], str, float, float, Dict]:
        """
        Evaluate Candle Range Theory (CRT) + Turtle Body Soup (TBS) Setup.
        Uses df_context as HTF Reference Candles (CRT) and df_ltf as LTF Entry timeframes (TBS).
        Returns: Tuple of (Action "BUY"/"SELL"/None, Regime "bullish"/"bearish"/"sideway", SL, TP, Metadata)
        """
        try:
            if df_context is None or df_ltf is None:
                return None, "sideway", 0.0, 0.0, {}
                
            if len(df_context) < 5 or len(df_ltf) < 10:
                return None, "sideway", 0.0, 0.0, {}
                
            # 1. Identify the CRT Reference Candle (last completed HTF candle)
            ref_candle = df_context.iloc[-2]
            crt_high = float(ref_candle['high'])
            crt_low = float(ref_candle['low'])
            
            # 2. Get active risk-reward ratio
            from utils.settings_manager import settings_manager
            trading_mode = settings_manager.get("trading_mode", "intraday").lower()
            if trading_mode == "scalping":
                rr_ratio = 1.5
            elif trading_mode == "swing":
                rr_ratio = 3.0
            else:
                rr_ratio = 2.0
                
            rr_ratio = settings_manager.get("min_rr_ratio", rr_ratio)
            
            # 3. Check for Turtle Body Soup (TBS) Setup on the last 3 completed LTF candles
            tbs_buy_trigger = False
            tbs_sell_trigger = False
            lowest_sweep_low = np.nan
            highest_sweep_high = np.nan
            
            # Check the last 3 closed LTF candles (indexes -4, -3, -2)
            for idx in [-4, -3, -2]:
                if abs(idx) > len(df_ltf):
                    continue
                candle = df_ltf.iloc[idx]
                
                # BUY: Wick went below crt_low, but body closed above crt_low
                if candle['low'] < crt_low and candle['close'] > crt_low:
                    tbs_buy_trigger = True
                    lowest_sweep_low = candle['low'] if np.isnan(lowest_sweep_low) else min(lowest_sweep_low, candle['low'])
                    
                # SELL: Wick went above crt_high, but body closed below crt_high
                if candle['high'] > crt_high and candle['close'] < crt_high:
                    tbs_sell_trigger = True
                    highest_sweep_high = candle['high'] if np.isnan(highest_sweep_high) else max(highest_sweep_high, candle['high'])

            # 4. Evaluate triggers with filters
            # BUY trigger execution
            if tbs_buy_trigger and htf_bias >= 0:
                # Chasing protection: current price must not have moved too far above crt_low
                chase_limit = crt_low + (0.5 * atr)
                if current_price <= chase_limit:
                    sl_price = min(lowest_sweep_low, crt_low) - (0.1 * atr)
                    # Safety buffer: ensure minimum SL distance
                    sl_price = min(sl_price, current_price - (1.5 * atr))
                    tp_price = current_price + (rr_ratio * (current_price - sl_price))
                    
                    # Target upper range liquidity (crt_high) if it gives better RR
                    if crt_high > current_price:
                        tp_price = max(tp_price, crt_high)
                        
                    metadata = {
                        "strategy": "CRT_TBS",
                        "crt_high": crt_high,
                        "crt_low": crt_low,
                        "lowest_sweep_low": lowest_sweep_low if not np.isnan(lowest_sweep_low) else crt_low,
                        "trigger": "TBS_BUY"
                    }
                    cls.logger.info(f"🐢 BUY TBS Confluence | CRT Low: {crt_low:.2f}, Entry: {current_price:.2f}, SL: {sl_price:.2f}, TP: {tp_price:.2f}")
                    return "BUY", "bullish", sl_price, tp_price, metadata
                else:
                    cls.logger.debug(f"🐢 BUY TBS skipped: Chasing protection (price {current_price:.2f} > limit {chase_limit:.2f})")
                    
            # SELL trigger execution
            if tbs_sell_trigger and htf_bias <= 0:
                # Chasing protection: current price must not have moved too far below crt_high
                chase_limit = crt_high - (0.5 * atr)
                if current_price >= chase_limit:
                    sl_price = max(highest_sweep_high, crt_high) + (0.1 * atr)
                    # Safety buffer
                    sl_price = max(sl_price, current_price + (1.5 * atr))
                    tp_price = current_price - (rr_ratio * (sl_price - current_price))
                    
                    # Target lower range liquidity (crt_low) if it gives better RR
                    if crt_low < current_price:
                        tp_price = min(tp_price, crt_low)
                        
                    metadata = {
                        "strategy": "CRT_TBS",
                        "crt_high": crt_high,
                        "crt_low": crt_low,
                        "highest_sweep_high": highest_sweep_high if not np.isnan(highest_sweep_high) else crt_high,
                        "trigger": "TBS_SELL"
                    }
                    cls.logger.info(f"🐢 SELL TBS Confluence | CRT High: {crt_high:.2f}, Entry: {current_price:.2f}, SL: {sl_price:.2f}, TP: {tp_price:.2f}")
                    return "SELL", "bearish", sl_price, tp_price, metadata
                else:
                    cls.logger.debug(f"🐢 SELL TBS skipped: Chasing protection (price {current_price:.2f} < limit {chase_limit:.2f})")
                    
            return None, "sideway", 0.0, 0.0, {}
            
        except Exception as e:
            cls.logger.error(f"Error in evaluate_crt_tbs: {e}")
            return None, "sideway", 0.0, 0.0, {}
