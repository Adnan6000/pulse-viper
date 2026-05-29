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
        # 6-TF dataframes (all optional except M1)
        df_m1: Optional[pd.DataFrame] = None,
        df_m5: Optional[pd.DataFrame] = None,
        df_m15: Optional[pd.DataFrame] = None,
        df_h1: Optional[pd.DataFrame] = None,
        df_h4: Optional[pd.DataFrame] = None,
        df_d1: Optional[pd.DataFrame] = None,
        # Legacy params kept for backward compat
        df_context: Optional[pd.DataFrame] = None,
        df_ltf: Optional[pd.DataFrame] = None,
        # Required scalars
        current_price: float = 0.0,
        atr: float = 1.0,
        volume_cache: Optional[Dict] = None,
        sentiment_cache: Optional[Dict] = None,
        htf_bias: int = 0,
    ) -> Tuple[Optional[str], str, float, float, Dict]:
        """
        Full 6-Timeframe CRT + TBS Setup Evaluation.

        Cascade:
          D1 + H4  → Master bias gate (trade direction must match)
          H1 + M15 → CRT reference zone (the 'manipulation range')
          M5       → Liquidity sweep confirmation
          M1       → TBS wick trigger (exact entry candle)

        Returns: (Action, Regime, SL, TP, Metadata)
        """
        try:
            # Resolve dataframes (backward compatibility with old single df_context/df_ltf API)
            if df_m1 is None and df_ltf is not None:
                df_m1 = df_ltf
            if df_m15 is None and df_context is not None:
                df_m15 = df_context

            # M1 is mandatory
            if df_m1 is None or len(df_m1) < 10:
                return None, "sideway", 0.0, 0.0, {}

            from utils.settings_manager import settings_manager
            trading_mode = settings_manager.get("trading_mode", "intraday").lower()
            if trading_mode == "scalping":
                rr_ratio = 1.5
            elif trading_mode == "swing":
                rr_ratio = 3.0
            else:
                rr_ratio = 2.0
            rr_ratio = settings_manager.get("min_rr_ratio", rr_ratio)

            # ── 1. Master bias gate (D1 + H4) ─────────────────────────────────────
            # htf_bias is computed by the engine's 6-TF cascade:
            #   +1 = bullish (D1+H4 agree bullish or best available)
            #   -1 = bearish (D1+H4 agree bearish or best available)
            #    0 = neutral/conflicting → skip trade
            if htf_bias == 0:
                cls.logger.debug("CRT+TBS skipped: HTF bias neutral/conflicting")
                return None, "sideway", 0.0, 0.0, {}

            # ── 2. CRT reference zone from H1 or M15 ─────────────────────────────
            # Use H1 if available (more reliable CRT range), fallback to M15
            crt_ref_df = df_h1 if (df_h1 is not None and len(df_h1) >= 5) else df_m15
            if crt_ref_df is None or len(crt_ref_df) < 5:
                cls.logger.debug("CRT+TBS skipped: No H1/M15 reference data")
                return None, "sideway", 0.0, 0.0, {}

            # Find the key H1 CRT zone: look at the last 3 completed H1 candles
            # CRT range = the high and low of the reference candle that formed manipulation
            # Use the candle with the largest range as the CRT manipulation candle
            crt_candles = crt_ref_df.iloc[-4:-1]  # last 3 completed candles
            if len(crt_candles) == 0:
                return None, "sideway", 0.0, 0.0, {}

            # Pick the candle with widest range as the CRT reference (manipulation candle)
            crt_candles = crt_candles.copy()
            crt_candles['range'] = crt_candles['high'] - crt_candles['low']
            ref_candle = crt_candles.loc[crt_candles['range'].idxmax()]
            crt_high = float(ref_candle['high'])
            crt_low = float(ref_candle['low'])
            crt_range = crt_high - crt_low

            # Minimum meaningful CRT range: at least 0.3x ATR
            if crt_range < 0.3 * atr:
                cls.logger.debug(f"CRT+TBS skipped: CRT range {crt_range:.2f} too small vs ATR {atr:.2f}")
                return None, "sideway", 0.0, 0.0, {}

            # ── 3. M5 sweep confirmation ──────────────────────────────────────────
            # Check if M5 has recently swept either the CRT high or low
            m5_sweep_confirmed = False
            if df_m5 is not None and len(df_m5) >= 5:
                recent_m5 = df_m5.iloc[-6:-1]  # last 5 M5 candles
                for _, c in recent_m5.iterrows():
                    if htf_bias == 1 and c['low'] < crt_low:
                        m5_sweep_confirmed = True
                        break
                    elif htf_bias == -1 and c['high'] > crt_high:
                        m5_sweep_confirmed = True
                        break

            # ── 4. TBS wick trigger on M1 ─────────────────────────────────────────
            # Check the last 3 closed M1 candles for a TBS wick
            tbs_buy_trigger = False
            tbs_sell_trigger = False
            lowest_sweep_low = np.nan
            highest_sweep_high = np.nan
            tbs_trigger_candle = None

            for idx in [-4, -3, -2]:
                if abs(idx) > len(df_m1):
                    continue
                candle = df_m1.iloc[idx]

                # BUY: wick swept below crt_low (fake-out) but closed back above crt_low
                if (candle['low'] < crt_low and candle['close'] > crt_low):
                    tbs_buy_trigger = True
                    if np.isnan(lowest_sweep_low):
                        lowest_sweep_low = candle['low']
                        tbs_trigger_candle = candle
                    else:
                        lowest_sweep_low = min(lowest_sweep_low, candle['low'])

                # SELL: wick swept above crt_high but closed back below crt_high
                if (candle['high'] > crt_high and candle['close'] < crt_high):
                    tbs_sell_trigger = True
                    if np.isnan(highest_sweep_high):
                        highest_sweep_high = candle['high']
                        tbs_trigger_candle = candle
                    else:
                        highest_sweep_high = max(highest_sweep_high, candle['high'])

            # ── 5. BUY setup ─────────────────────────────────────────────────────
            if tbs_buy_trigger and htf_bias == 1:
                # Chase guard: current price must not be too far above entry zone
                chase_limit = crt_low + (0.6 * atr)
                if current_price <= chase_limit:
                    # SL: below the lowest M1 sweep wick with buffer
                    sl_price = min(lowest_sweep_low, crt_low) - (0.15 * atr)
                    sl_price = min(sl_price, current_price - (1.5 * atr))

                    # TP: target opposite H1 liquidity (crt_high) or RR-based
                    tp_rr = current_price + (rr_ratio * (current_price - sl_price))
                    tp_price = max(tp_rr, crt_high) if crt_high > current_price else tp_rr

                    # If H1 structure provides a better target, use it
                    if df_h1 is not None and len(df_h1) >= 10:
                        h1_recent_high = float(df_h1.iloc[-10:]['high'].max())
                        if h1_recent_high > current_price:
                            tp_price = max(tp_price, h1_recent_high)

                    metadata = {
                        "strategy": "CRT_TBS",
                        "crt_high": crt_high,
                        "crt_low": crt_low,
                        "lowest_sweep_low": float(lowest_sweep_low) if not np.isnan(lowest_sweep_low) else crt_low,
                        "trigger": "TBS_BUY",
                        "m5_sweep_confirmed": m5_sweep_confirmed,
                        "htf_bias": htf_bias,
                        "crt_source": "H1" if (df_h1 is not None and len(df_h1) >= 5) else "M15"
                    }
                    cls.logger.info(
                        f"🐢 BUY TBS ({'✅M5' if m5_sweep_confirmed else '⚠️noM5'}) | "
                        f"HTF={'BULL'} CRT_Low={crt_low:.2f} Entry={current_price:.2f} "
                        f"SL={sl_price:.2f} TP={tp_price:.2f}"
                    )
                    return "BUY", "bullish", sl_price, tp_price, metadata
                else:
                    cls.logger.debug(f"🐢 BUY TBS skipped: chase guard (price={current_price:.2f} > limit={chase_limit:.2f})")

            # ── 6. SELL setup ────────────────────────────────────────────────────
            if tbs_sell_trigger and htf_bias == -1:
                # Chase guard
                chase_limit = crt_high - (0.6 * atr)
                if current_price >= chase_limit:
                    # SL: above the highest M1 sweep wick
                    sl_price = max(highest_sweep_high, crt_high) + (0.15 * atr)
                    sl_price = max(sl_price, current_price + (1.5 * atr))

                    # TP: target crt_low or RR-based
                    tp_rr = current_price - (rr_ratio * (sl_price - current_price))
                    tp_price = min(tp_rr, crt_low) if crt_low < current_price else tp_rr

                    # If H1 structure provides a better target, use it
                    if df_h1 is not None and len(df_h1) >= 10:
                        h1_recent_low = float(df_h1.iloc[-10:]['low'].min())
                        if h1_recent_low < current_price:
                            tp_price = min(tp_price, h1_recent_low)

                    metadata = {
                        "strategy": "CRT_TBS",
                        "crt_high": crt_high,
                        "crt_low": crt_low,
                        "highest_sweep_high": float(highest_sweep_high) if not np.isnan(highest_sweep_high) else crt_high,
                        "trigger": "TBS_SELL",
                        "m5_sweep_confirmed": m5_sweep_confirmed,
                        "htf_bias": htf_bias,
                        "crt_source": "H1" if (df_h1 is not None and len(df_h1) >= 5) else "M15"
                    }
                    cls.logger.info(
                        f"🐢 SELL TBS ({'✅M5' if m5_sweep_confirmed else '⚠️noM5'}) | "
                        f"HTF={'BEAR'} CRT_High={crt_high:.2f} Entry={current_price:.2f} "
                        f"SL={sl_price:.2f} TP={tp_price:.2f}"
                    )
                    return "SELL", "bearish", sl_price, tp_price, metadata
                else:
                    cls.logger.debug(f"🐢 SELL TBS skipped: chase guard (price={current_price:.2f} < limit={chase_limit:.2f})")

            return None, "sideway", 0.0, 0.0, {}

        except Exception as e:
            cls.logger.error(f"Error in evaluate_crt_tbs: {e}")
            import traceback; traceback.print_exc()
            return None, "sideway", 0.0, 0.0, {}
