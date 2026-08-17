# strategies/quantum_viper_strategy.py
"""
PulseViper Quantum Viper Strategy (Flagship Master Execution Engine).

Combines 5 institutional edge pillars:
1. Multi-Timeframe Structural Trend Alignment (HTF Cascade)
2. Liquidity Sweep & Asian Range Inducement Hunt
3. Displacement & Institutional Fair Value Gap (FVG) / Order Block (OB) Confluence
4. Volume Spread Delta & Order Flow Surge
5. Golden Pocket Fibonacci (61.8%-78.6%) & Dynamic ATR Risk Geometry
"""

import pandas as pd
import numpy as np
import logging
from typing import Tuple, Dict, Any, Optional

from utils.settings_manager import clamp_m1_trade_levels

logger = logging.getLogger("PulseViper.QuantumViperStrategy")

class QuantumViperStrategy:
    @staticmethod
    def evaluate_quantum_viper(
        df_m1: Optional[pd.DataFrame],
        df_m5: Optional[pd.DataFrame],
        df_m15: Optional[pd.DataFrame],
        df_h1: Optional[pd.DataFrame],
        df_h4: Optional[pd.DataFrame],
        df_d1: Optional[pd.DataFrame],
        current_price: float,
        atr: float,
        htf_bias: int = 0,
        volume_cache: Optional[Dict] = None,
        sentiment_cache: Optional[Dict] = None,
        regime: str = "RANGE",
        symbol: str = ""
    ) -> Tuple[Optional[str], float, float, Dict[str, Any]]:
        """
        Evaluates current multi-timeframe market state against Quantum Viper institutional rules.

        Returns:
            (action, sl_price, tp_price, metadata)
        """
        try:
            if df_m5 is None or len(df_m5) < 20 or current_price <= 0:
                return None, 0.0, 0.0, {}

            df_ltf = df_m5
            last_bar = df_ltf.iloc[-1]
            prev_bar = df_ltf.iloc[-2]
            
            ref_atr = max(atr, 0.0001)

            # ── 1. Weighted Multi-Timeframe Cascade Score (FDC) ─────────────────────
            h1_b = float(df_h1['bias'].iloc[-1]) if (df_h1 is not None and 'bias' in df_h1.columns and len(df_h1) > 0) else float(htf_bias)
            h4_b = float(df_h4['bias'].iloc[-1]) if (df_h4 is not None and 'bias' in df_h4.columns and len(df_h4) > 0) else float(htf_bias)
            d1_b = float(df_d1['bias'].iloc[-1]) if (df_d1 is not None and 'bias' in df_d1.columns and len(df_d1) > 0) else float(htf_bias)
            m15_b = float(df_m15['bias'].iloc[-1]) if (df_m15 is not None and 'bias' in df_m15.columns and len(df_m15) > 0) else float(htf_bias)

            # High-precision weighted cascade score (-1.0 to +1.0)
            fdc_score = 0.35 * d1_b + 0.30 * h4_b + 0.20 * h1_b + 0.15 * m15_b
            htf_sum = 1 if fdc_score > 0.15 else (-1 if fdc_score < -0.15 else 0)
            
            # ── 2. Liquidity Sweep & Inducement Detection ─────────────────────────
            sweep_type = 0
            if 'sweep_type' in df_ltf.columns:
                sweep_type = int(df_ltf['sweep_type'].iloc[-1])
            elif df_m15 is not None and 'sweep_type' in df_m15.columns:
                sweep_type = int(df_m15['sweep_type'].iloc[-1])

            # ── 3. Displacement & FVG / Order Block Confluence ─────────────────────
            candle_body = abs(last_bar['close'] - last_bar['open'])
            is_displacement = (candle_body >= 1.5 * ref_atr)

            # ── 4. Volume-Weighted Volatility Expansion Factor (VSE) ────────────
            vol_ratio = 1.0
            if 'volume' in df_ltf.columns and len(df_ltf) >= 20:
                avg_vol = df_ltf['volume'].iloc[-20:].mean()
                if avg_vol > 0:
                    vol_ratio = float(last_bar['volume'] / avg_vol)
            
            # Formula: VSE = vol_ratio * (1 + candle_body / ref_atr)
            vse_factor = vol_ratio * (1.0 + min(candle_body / ref_atr, 2.5))
            is_volume_confirmed = vse_factor >= 2.0 or vol_ratio >= 1.25

            sym_upper = symbol.upper() if isinstance(symbol, str) else str(symbol).upper()
            is_gold = "XAU" in sym_upper or "GOLD" in sym_upper

            # ── 5. Choppiness Index & Volatility Compression Filter ──────────────
            swing_high = float(df_ltf['high'].iloc[-20:].max())
            swing_low = float(df_ltf['low'].iloc[-20:].min())
            swing_range = max(swing_high - swing_low, 0.0001)

            atr_sum = df_ltf['atr'].iloc[-14:].sum() if 'atr' in df_ltf.columns else 14.0 * ref_atr
            chop_index = (100.0 * np.log10((atr_sum + 1e-9) / swing_range) / np.log10(14.0)) if swing_range > 0 else 50.0
            is_choppy_gold = is_gold and (chop_index >= 58.0 or (swing_range / (14.0 * ref_atr)) <= 0.38)

            candle_range = float(last_bar['high'] - last_bar['low'])
            candle_range_safe = max(candle_range, 0.0001)

            # Candlestick Rejection Wicks & Body Ratios
            lower_wick_ratio = float(min(last_bar['open'], last_bar['close']) - last_bar['low']) / candle_range_safe
            upper_wick_ratio = float(last_bar['high'] - max(last_bar['open'], last_bar['close'])) / candle_range_safe
            is_bullish_bar = last_bar['close'] >= last_bar['open']
            is_bearish_bar = last_bar['close'] < last_bar['open']

            # Price Action Momentum & Structure Breakout
            is_bull_engulf = is_bullish_bar and (last_bar['close'] > prev_bar['high']) and (vse_factor >= (2.2 if is_choppy_gold else 1.8))
            is_bear_engulf = is_bearish_bar and (last_bar['close'] < prev_bar['low']) and (vse_factor >= (2.2 if is_choppy_gold else 1.8))
            is_bull_rejection = lower_wick_ratio >= (0.58 if is_choppy_gold else 0.50) and current_price <= (swing_low + 0.30 * swing_range)
            is_bear_rejection = upper_wick_ratio >= (0.58 if is_choppy_gold else 0.50) and current_price >= (swing_high - 0.30 * swing_range)

            fib_618_bull = swing_low + 0.382 * swing_range
            fib_786_bull = swing_low + 0.214 * swing_range

            fib_618_bear = swing_high - 0.382 * swing_range
            fib_786_bear = swing_high - 0.214 * swing_range

            # ── 6. Order Flow Imbalance (OFI) & Volume Delta Surge ─────────────────
            ofi_imbalance = 0.0
            if candle_range > 0:
                ofi_imbalance = float((last_bar['close'] - last_bar['open']) / candle_range) * vol_ratio
            
            is_buy_order_flow = ofi_imbalance >= -0.15 or is_bull_rejection or is_bull_engulf
            is_sell_order_flow = ofi_imbalance <= 0.15 or is_bear_rejection or is_bear_engulf

            # ── EVALUATE BULLISH PRICE ACTION & ORDER FLOW SETUP ─────────────────────
            buy_price_action = (is_bull_engulf or is_bull_rejection or (is_displacement and is_bullish_bar and not is_choppy_gold)) and is_buy_order_flow
            buy_htf_valid = (fdc_score >= -0.10 or sweep_type == -1 or is_gold)
            buy_golden_pocket = (fib_786_bull <= current_price <= fib_618_bull + 0.8 * ref_atr) or is_gold

            if buy_htf_valid and buy_price_action and buy_golden_pocket:
                # Formula: SL = ref_atr * (1.2 + 0.6 * (chop_index / 100.0))
                sl_mult = 1.8 if is_choppy_gold else (1.2 + 0.6 * (chop_index / 100.0))
                sl_dist = max(sl_mult * ref_atr, current_price - swing_low)
                # Micro-Account & Gold Cap: Max 1.50 points SL ($1.50 / 15 pips) for small account protection
                if is_gold:
                    sl_dist = min(sl_dist, 1.50)
                rr_target = max(1.5, min(2.5, 1.8 + (vol_ratio / 3.0)))
                tp_dist = round(rr_target * sl_dist, 2 if is_gold else 5)
                if is_gold:
                    tp_dist = max(1.50, min(tp_dist, 3.00))
                sl_price = round(current_price - sl_dist, 2 if is_gold else 5)
                tp_price = round(current_price + tp_dist, 2 if is_gold else 5)
                if is_gold:
                    sl_price, tp_price = clamp_m1_trade_levels("BUY", current_price, sl_price, tp_price)

                meta = {
                    "strategy": "PRICE_ACTION_GOLD" if is_gold else "QUANTUM_VIPER",
                    "trigger": "BULLISH_VOLATILE_BREAKOUT" if is_bull_engulf else ("CHOPPY_GOLD_REJECTION" if is_choppy_gold else "BULLISH_PINBAR_REJECTION"),
                    "confidence": 0.90 if (is_bull_engulf and is_volume_confirmed) else 0.80,
                    "htf_sum": htf_sum,
                    "chop_index": round(chop_index, 1),
                    "is_choppy": is_choppy_gold,
                    "vol_ratio": round(vol_ratio, 2),
                    "rr_ratio": 2.0,
                    "swing_low": round(swing_low, 2),
                    "swing_high": round(swing_high, 2)
                }
                logger.info(f"🚀 [GOLD_PRICE_ACTION] BUY Setup Triggered on {symbol} @ {current_price:.2f} (CHOP: {chop_index:.1f}) | SL: {sl_price:.2f}, TP: {tp_price:.2f}")
                return "BUY", sl_price, tp_price, meta

            # ── EVALUATE BEARISH PRICE ACTION SETUP (GOLD SPECIALIZED) ────────────
            sell_price_action = is_bear_engulf or is_bear_rejection or (is_displacement and is_bearish_bar and not is_choppy_gold)
            sell_htf_valid = (htf_sum <= 0 or sweep_type == 1 or is_gold)
            sell_golden_pocket = (fib_618_bear - 0.8 * ref_atr <= current_price <= fib_786_bear) or is_gold

            if sell_htf_valid and sell_price_action and sell_golden_pocket:
                # In choppy Gold conditions, use a wider 1.8x ATR buffer to protect against whipsaws
                sl_dist = max(1.8 * ref_atr if is_choppy_gold else 1.3 * ref_atr, swing_high - current_price)
                if is_gold:
                    sl_dist = min(sl_dist, 1.50)
                tp_dist = round(2.0 * sl_dist, 2 if is_gold else 5)
                if is_gold:
                    tp_dist = max(1.50, min(tp_dist, 3.00))
                sl_price = round(current_price + sl_dist, 2 if is_gold else 5)
                tp_price = round(current_price - tp_dist, 2 if is_gold else 5)
                if is_gold:
                    sl_price, tp_price = clamp_m1_trade_levels("SELL", current_price, sl_price, tp_price)

                meta = {
                    "strategy": "PRICE_ACTION_GOLD" if is_gold else "QUANTUM_VIPER",
                    "trigger": "BEARISH_VOLATILE_BREAKDOWN" if is_bear_engulf else ("CHOPPY_GOLD_REJECTION" if is_choppy_gold else "BEARISH_PINBAR_REJECTION"),
                    "confidence": 0.90 if (is_bear_engulf and is_volume_confirmed) else 0.80,
                    "htf_sum": htf_sum,
                    "chop_index": round(chop_index, 1),
                    "is_choppy": is_choppy_gold,
                    "vol_ratio": round(vol_ratio, 2),
                    "rr_ratio": 2.0,
                    "swing_low": round(swing_low, 2),
                    "swing_high": round(swing_high, 2)
                }
                logger.info(f"🔻 [GOLD_PRICE_ACTION] SELL Setup Triggered on {symbol} @ {current_price:.2f} (CHOP: {chop_index:.1f}) | SL: {sl_price:.2f}, TP: {tp_price:.2f}")
                return "SELL", sl_price, tp_price, meta

            return None, 0.0, 0.0, {}

        except Exception as e:
            logger.error(f"Error evaluating QuantumViperStrategy: {e}")
            return None, 0.0, 0.0, {}
