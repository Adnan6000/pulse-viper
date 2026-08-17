# strategies/smc_concepts_strategy.py
import numpy as np
import pandas as pd
import logging
from typing import Dict, Tuple, Optional

from utils.settings_manager import clamp_m1_trade_levels

class SmcConceptsStrategy:
    logger = logging.getLogger("PulseViper.SmcConceptsStrategy")

    @classmethod
    def evaluate_smc(
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
    ) -> Tuple[Optional[str], float, float, Dict]:
        """
        Evaluate advanced SMC Price Action setup triggers:
          1. Order Block (OB) Reactions/Mitigations (SMC_OB_RETEST)
          2. S/R Break-and-Retest level pullbacks (SMC_RETEST_PULLBACK)
          3. Change of Character trend shifts (SMC_TREND_SHIFT)
        
        Returns: (Action, SL, TP, Metadata)
        """
        try:
            if df_m5 is None or len(df_m5) < 20:
                return None, 0.0, 0.0, {}
            if df_m1 is None or len(df_m1) < 10:
                return None, 0.0, 0.0, {}

            from utils.settings_manager import settings_manager
            trading_mode = settings_manager.get("trading_mode", "intraday").lower()
            if trading_mode == "scalping":
                rr_ratio = 1.5
            elif trading_mode == "swing":
                rr_ratio = 3.0
            else:
                rr_ratio = 2.0
            rr_ratio = settings_manager.get("min_rr_ratio", rr_ratio)

            # Assign evaluation priority: Check M5 first for structure, fall back to M1 for fine entry
            # 1. Check Change of Character (CHoCH) Trend Shift
            # Trend shifts are checked in the last 3 candles on M5/M15
            trend_shift = 0
            for idx in [-2, -3, -4]:
                if abs(idx) <= len(df_m5):
                    row = df_m5.iloc[idx]
                    if 'trend_shift_signal' in row and row['trend_shift_signal'] != 0:
                        trend_shift = int(row['trend_shift_signal'])
                        break
            
            if trend_shift != 0:
                # Trigger Trend Shift trade
                if trend_shift == 1: # Bullish trend shift
                    sl = current_price - 1.2 * atr
                    tp = current_price + rr_ratio * (current_price - sl)
                    sl, tp = clamp_m1_trade_levels("BUY", current_price, sl, tp)
                    meta = {
                        "strategy": "SMC_CONCEPTS",
                        "trigger": "SMC_TREND_SHIFT_BUY",
                        "trend_shift": "BULLISH",
                        "regime": regime
                    }
                    cls.logger.info(f"💎 SMC Trend Shift BUY Triggered @ {current_price:.2f} | SL: {sl:.2f}, TP: {tp:.2f}")
                    return "BUY", sl, tp, meta
                elif trend_shift == -1: # Bearish trend shift
                    sl = current_price + 1.2 * atr
                    tp = current_price - rr_ratio * (sl - current_price)
                    sl, tp = clamp_m1_trade_levels("SELL", current_price, sl, tp)
                    meta = {
                        "strategy": "SMC_CONCEPTS",
                        "trigger": "SMC_TREND_SHIFT_SELL",
                        "trend_shift": "BEARISH",
                        "regime": regime
                    }
                    cls.logger.info(f"💎 SMC Trend Shift SELL Triggered @ {current_price:.2f} | SL: {sl:.2f}, TP: {tp:.2f}")
                    return "SELL", sl, tp, meta

            # 2. Check Order Block (OB) Reactions/Mitigations
            # Scan last 3 candles on M5 or M1 for OB touches
            ob_touch = 0
            ob_top = np.nan
            ob_bottom = np.nan
            for df_eval in [df_m5, df_m1]:
                if df_eval is not None and len(df_eval) >= 3:
                    for idx in [-2, -3, -4]:
                        row = df_eval.iloc[idx]
                        if 'ob_reaction_signal' in row and row['ob_reaction_signal'] != 0:
                            ob_touch = int(row['ob_reaction_signal'])
                            ob_top = float(row['ob_top']) if 'ob_top' in row else np.nan
                            ob_bottom = float(row['ob_bottom']) if 'ob_bottom' in row else np.nan
                            break
                    if ob_touch != 0:
                        break

            if ob_touch != 0:
                # Trigger OB Retest trade if aligned with bias or in scalping/range mode
                allow_buy = (htf_bias >= 0) or (trading_mode == "scalping") or (regime in ("RANGE", "COMPRESSION"))
                allow_sell = (htf_bias <= 0) or (trading_mode == "scalping") or (regime in ("RANGE", "COMPRESSION"))

                if ob_touch == 1 and allow_buy: # Bullish OB (Demand zone) touch
                    sl_ref = ob_bottom if not np.isnan(ob_bottom) else current_price - 1.0 * atr
                    sl = sl_ref - 0.1 * atr
                    # Capital protection: clamp SL to avoid excessive range
                    if current_price - sl > 2.0 * atr:
                        sl = current_price - 1.5 * atr
                    tp = current_price + rr_ratio * (current_price - sl)
                    sl, tp = clamp_m1_trade_levels("BUY", current_price, sl, tp)
                    meta = {
                        "strategy": "SMC_CONCEPTS",
                        "trigger": "SMC_OB_RETEST_BUY",
                        "ob_top": ob_top,
                        "ob_bottom": ob_bottom,
                        "regime": regime
                    }
                    cls.logger.info(f"💎 SMC Demand Zone (OB) BUY Triggered @ {current_price:.2f} | SL: {sl:.2f}, TP: {tp:.2f}")
                    return "BUY", sl, tp, meta
                elif ob_touch == -1 and allow_sell: # Bearish OB (Supply zone) touch
                    sl_ref = ob_top if not np.isnan(ob_top) else current_price + 1.0 * atr
                    sl = sl_ref + 0.1 * atr
                    if sl - current_price > 2.0 * atr:
                        sl = current_price + 1.5 * atr
                    tp = current_price - rr_ratio * (sl - current_price)
                    sl, tp = clamp_m1_trade_levels("SELL", current_price, sl, tp)
                    meta = {
                        "strategy": "SMC_CONCEPTS",
                        "trigger": "SMC_OB_RETEST_SELL",
                        "ob_top": ob_top,
                        "ob_bottom": ob_bottom,
                        "regime": regime
                    }
                    cls.logger.info(f"💎 SMC Supply Zone (OB) SELL Triggered @ {current_price:.2f} | SL: {sl:.2f}, TP: {tp:.2f}")
                    return "SELL", sl, tp, meta

            # 3. Check Support/Resistance Break-and-Retest level pullbacks
            retest_pullback = 0
            for df_eval in [df_m5, df_m1]:
                if df_eval is not None and len(df_eval) >= 3:
                    for idx in [-2, -3, -4]:
                        row = df_eval.iloc[idx]
                        if 'retest_pullback_signal' in row and row['retest_pullback_signal'] != 0:
                            retest_pullback = int(row['retest_pullback_signal'])
                            break
                    if retest_pullback != 0:
                        break

            if retest_pullback != 0:
                allow_buy = (htf_bias >= 0) or (trading_mode == "scalping") or (regime in ("RANGE", "COMPRESSION"))
                allow_sell = (htf_bias <= 0) or (trading_mode == "scalping") or (regime in ("RANGE", "COMPRESSION"))

                if retest_pullback == 1 and allow_buy: # Broken resistance retested as support
                    sl = current_price - 1.0 * atr
                    tp = current_price + rr_ratio * (current_price - sl)
                    sl, tp = clamp_m1_trade_levels("BUY", current_price, sl, tp)
                    meta = {
                        "strategy": "SMC_CONCEPTS",
                        "trigger": "SMC_RETEST_PULLBACK_BUY",
                        "regime": regime
                    }
                    cls.logger.info(f"💎 SMC Break-and-Retest BUY Triggered @ {current_price:.2f} | SL: {sl:.2f}, TP: {tp:.2f}")
                    return "BUY", sl, tp, meta
                elif retest_pullback == -1 and allow_sell: # Broken support retested as resistance
                    sl = current_price + 1.0 * atr
                    tp = current_price - rr_ratio * (sl - current_price)
                    sl, tp = clamp_m1_trade_levels("SELL", current_price, sl, tp)
                    meta = {
                        "strategy": "SMC_CONCEPTS",
                        "trigger": "SMC_RETEST_PULLBACK_SELL",
                        "regime": regime
                    }
                    cls.logger.info(f"💎 SMC Break-and-Retest SELL Triggered @ {current_price:.2f} | SL: {sl:.2f}, TP: {tp:.2f}")
                    return "SELL", sl, tp, meta

            return None, 0.0, 0.0, {}
        except Exception as e:
            cls.logger.error(f"Error in evaluate_smc: {e}")
            import traceback; traceback.print_exc()
            return None, 0.0, 0.0, {}
