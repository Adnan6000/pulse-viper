# strategies/crt_tbs.py
import numpy as np
import pandas as pd
import logging
from typing import Dict, Tuple, Optional
from utils.settings_manager import clamp_m1_trade_levels, settings_manager

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
        regime: str = "RANGE",
        symbol: str = "XAUUSDm",
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

            # M1 is mandatory as core data backup
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
            is_range_regime = regime in ["RANGE", "COMPRESSION"]
            is_gold = "XAU" in symbol.upper() or "GOLD" in symbol.upper()
            ofi = volume_cache.get("ofi", 0.0) if volume_cache else 0.0
            # In range/consolidation: htf_bias may be 0 — still allow setups from sweep direction
            if htf_bias == 0 and not is_range_regime:
                cls.logger.debug("CRT+TBS skipped: HTF bias neutral/conflicting")
                return None, "sideway", 0.0, 0.0, {}

            # ── 2. Dynamic Timeframe Cascade Selection ───────────────────────────
            # Assign roles to dataframes based on the active trading mode
            if trading_mode == "scalping":
                crt_ref_df = df_m15 if (df_m15 is not None and len(df_m15) >= 5) else df_m5
                sweep_df = df_m5
                trigger_df = df_m1
                crt_source_label = "M15" if (df_m15 is not None and len(df_m15) >= 5) else "M5"
            elif trading_mode == "swing":
                crt_ref_df = df_h4 if (df_h4 is not None and len(df_h4) >= 5) else df_h1
                sweep_df = df_h1
                trigger_df = df_m15
                crt_source_label = "H4" if (df_h4 is not None and len(df_h4) >= 5) else "H1"
            else: # intraday
                crt_ref_df = df_h1 if (df_h1 is not None and len(df_h1) >= 5) else df_m15
                sweep_df = df_m15
                trigger_df = df_m5
                crt_source_label = "H1" if (df_h1 is not None and len(df_h1) >= 5) else "M15"

            # Fallbacks in case selected timeframes are not loaded
            if crt_ref_df is None or len(crt_ref_df) < 5:
                crt_ref_df = df_h1 if (df_h1 is not None and len(df_h1) >= 5) else df_m15
                crt_source_label = "H1" if (df_h1 is not None and len(df_h1) >= 5) else "M15"
            if crt_ref_df is None or len(crt_ref_df) < 5:
                return None, "sideway", 0.0, 0.0, {}

            if sweep_df is None:
                sweep_df = df_m5 if df_m5 is not None else df_m1
            if trigger_df is None:
                trigger_df = df_m1 if df_m1 is not None else df_m5

            # Find the CRT manipulation zone (widest range candle in the reference window)
            crt_candles = crt_ref_df.iloc[-4:-1]  # last 3 completed candles
            if len(crt_candles) == 0:
                return None, "sideway", 0.0, 0.0, {}

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

            # Double sweep check for Gold in range/compression
            has_double_sweep = False
            if is_gold and is_range_regime and sweep_df is not None and len(sweep_df) >= 15:
                recent_sweep_15 = sweep_df.iloc[-16:-1]
                swept_high_15 = any(float(c['high']) > crt_high for _, c in recent_sweep_15.iterrows())
                swept_low_15  = any(float(c['low']) < crt_low for _, c in recent_sweep_15.iterrows())
                has_double_sweep = swept_high_15 and swept_low_15

            # ── 3. Sweep confirmation on sweep_df ──────────────────────────────
            m5_sweep_confirmed = False
            range_sweep_direction = 0  # 1 = swept low (buy setup), -1 = swept high (sell setup)
            if sweep_df is not None and len(sweep_df) >= 5:
                recent_sweep = sweep_df.iloc[-6:-1]  # last 5 completed candles
                for _, c in recent_sweep.iterrows():
                    if htf_bias == 1 and c['low'] < crt_low:
                        m5_sweep_confirmed = True
                        break
                    elif htf_bias == -1 and c['high'] > crt_high:
                        m5_sweep_confirmed = True
                        break
                    elif is_range_regime and htf_bias == 0:
                        # In range mode: detect any sweep for mean-reversion entry
                        if c['low'] < crt_low:
                            m5_sweep_confirmed = True
                            range_sweep_direction = 1   # swept low → expect bounce up
                            break
                        elif c['high'] > crt_high:
                            m5_sweep_confirmed = True
                            range_sweep_direction = -1  # swept high → expect bounce down
                            break

            # ── 4. Volume Spread Analysis & Breakout Confirmation ──────────────
            from utils.volume_analyzer import VolumeAnalyzer
            active_vsa_patterns = []
            
            # Detect VSA signals on both execution timeframes
            if trigger_df is not None and 'atr' in trigger_df.columns:
                active_vsa_patterns += VolumeAnalyzer.detect_vsa_signals(trigger_df, trigger_df['atr'], lookback=5)
            if sweep_df is not None and 'atr' in sweep_df.columns:
                active_vsa_patterns += VolumeAnalyzer.detect_vsa_signals(sweep_df, sweep_df['atr'], lookback=5)

            vsa_filter_enabled = settings_manager.get("vsa_filter_enabled", False)
            vsa_buy_confirmed = True
            vsa_sell_confirmed = True

            # Extract Relative Volume and candle details for high volume breakout confirmation
            rvol = float(volume_cache.get("rvol", 1.0)) if volume_cache else 1.0
            last_close = float(trigger_df['close'].iloc[-2]) if trigger_df is not None and len(trigger_df) >= 2 else 0.0
            last_open = float(trigger_df['open'].iloc[-2]) if trigger_df is not None and len(trigger_df) >= 2 else 0.0
            is_last_bullish = last_close >= last_open
            
            if vsa_filter_enabled:
                has_bull_vsa = any(s['pattern'] in ['SPRING', 'STOPPING_VOLUME', 'NO_SUPPLY', 'SELLING_CLIMAX', 'TEST_OF_SUPPLY', 'EFFORT_VS_RESULT_BULLISH'] for s in active_vsa_patterns)
                buy_press = volume_cache.get("buy_pressure", 50.0) if volume_cache else 50.0
                has_bull_hvol = (rvol >= 1.5 and is_last_bullish)
                vsa_buy_confirmed = has_bull_vsa or (buy_press >= 60.0 and rvol >= 1.2) or has_bull_hvol
                
                has_bear_vsa = any(s['pattern'] in ['UPTHRUST', 'NO_DEMAND', 'BUYING_CLIMAX', 'TEST_OF_DEMAND', 'EFFORT_VS_RESULT_BEARISH'] for s in active_vsa_patterns)
                sell_press = volume_cache.get("sell_pressure", 50.0) if volume_cache else 50.0
                has_bear_hvol = (rvol >= 1.5 and not is_last_bullish)
                vsa_sell_confirmed = has_bear_vsa or (sell_press >= 60.0 and rvol >= 1.2) or has_bear_hvol
                       
            # ── 5. Multi-Candle TBS Wick Trigger on trigger_df ──────────────────
            # Check the last 3 closed candles for a sweep and close-back-inside
            # In RANGE mode: expand to 5 candles (range sweeps develop slowly)
            #               Also accept current forming candle (iloc[-1]) as close-back signal
            tbs_buy_trigger = False
            tbs_sell_trigger = False
            lowest_sweep_low = np.nan
            highest_sweep_high = np.nan

            # Sweep lookback window: wider in range mode (5 candles vs 3 in trend mode)
            if is_gold and trading_mode == "swing":
                trigger_candles_idx = [-11, -10, -9, -8, -7, -6, -5, -4, -3, -2]
            elif is_range_regime:
                trigger_candles_idx = [-6, -5, -4, -3, -2]   # 5-candle lookback for range
            else:
                trigger_candles_idx = [-4, -3, -2]            # 3-candle lookback for trend
            valid_idxs = [idx for idx in trigger_candles_idx if abs(idx) <= len(trigger_df)]
            
            # Boundary tolerance for range setups: a close within 0.15*ATR of the boundary counts
            # (Handles micro-noise at CRT edges in volatile scalping markets)
            boundary_tol = 0.15 * atr if is_range_regime else 0.0

            if valid_idxs:
                # BUY: any candle swept below crt_low, then any subsequent candle closed back above
                has_swept_buy = any(float(trigger_df.iloc[idx]['low']) < crt_low for idx in valid_idxs)

                # Only last CLOSED candle (iloc[-2]) counts as close-back to prevent repainting
                closed_above_buy = (float(trigger_df.iloc[-2]['close']) > crt_low - boundary_tol)
                if has_swept_buy and closed_above_buy:
                    tbs_buy_trigger = True
                    lowest_sweep_low = min(float(trigger_df.iloc[idx]['low']) for idx in valid_idxs)

                # SELL: any candle swept above crt_high, then closed back below
                has_swept_sell = any(float(trigger_df.iloc[idx]['high']) > crt_high for idx in valid_idxs)
                closed_below_sell = (float(trigger_df.iloc[-2]['close']) < crt_high + boundary_tol)
                if has_swept_sell and closed_below_sell:
                    tbs_sell_trigger = True
                    highest_sweep_high = max(float(trigger_df.iloc[idx]['high']) for idx in valid_idxs)

            # ── 6. BUY Setup Calculation (Structural Gated) ──────────────────────
            # In range mode: allow buy setup from sweep direction even when htf_bias == 0
            effective_buy_bias = (htf_bias == 1) or (is_range_regime and htf_bias == 0 and range_sweep_direction == 1)
            if tbs_buy_trigger and effective_buy_bias:
                has_bull_vsa = any(s['pattern'] in ['SPRING', 'STOPPING_VOLUME', 'NO_SUPPLY', 'SELLING_CLIMAX', 'TEST_OF_SUPPLY', 'EFFORT_VS_RESULT_BULLISH'] for s in active_vsa_patterns)
                
                # Check Gold strict filters when single sweep
                gold_strict_ok = True
                if is_gold and is_range_regime and not has_double_sweep:
                    if not has_bull_vsa:
                        cls.logger.info("🐢 BUY TBS Gold skipped: no bull VSA exhaustion pattern under single sweep")
                        gold_strict_ok = False
                    elif ofi < 0.25:
                        cls.logger.info(f"🐢 BUY TBS Gold skipped: OFI imbalance ({ofi:.2f}) < 0.25 under single sweep")
                        gold_strict_ok = False
                
                # Dealing Range Premium/Discount check
                pd_ok = True
                range_low = np.nan
                range_high = np.nan
                if df_h1 is not None and len(df_h1) > 0:
                    last_row = df_h1.iloc[-1]
                    range_low = float(last_row.get("support", np.nan))
                    range_high = float(last_row.get("resistance", np.nan))
                    if not np.isnan(range_low) and not np.isnan(range_high):
                        rng = range_high - range_low
                        if rng > 0.0:
                            retracement = (current_price - range_low) / rng
                            # Extreme Premium trap check (buying the top 15% of range)
                            if retracement >= 0.85:
                                cls.logger.info(f"🐢 BUY TBS skipped: price is in extreme premium trap ({retracement:.2f})")
                                pd_ok = False
                
                if not vsa_buy_confirmed or not gold_strict_ok or not pd_ok:
                    cls.logger.info("🐢 BUY TBS skipped: VSA / Volume / Gold / Premium-Discount filter confirmation failed")
                else:
                    # Chase guard: current price must not be too far above entry zone
                    # Range mode uses tighter chase to ensure mean-reversion quality
                    if is_gold and is_range_regime and not has_double_sweep:
                        chase_factor = 0.25
                    else:
                        chase_factor = 0.4 if is_range_regime else 0.6
                    chase_limit = crt_low + (chase_factor * atr)
                    if current_price <= chase_limit:
                        # Tight price-action Stop Loss strictly below the sweep wick
                        sl_pad = 0.12 * atr if is_gold else 0.05 * atr
                        sweep_low_val = lowest_sweep_low if not np.isnan(lowest_sweep_low) else crt_low
                        sl_price = min(sweep_low_val, crt_low) - sl_pad
                        sl_distance = current_price - sl_price
                        
                        # Capital Protection: Enforce SL boundaries
                        min_sl = 0.3 * atr
                        # Range mode: tighter SL cap (range = bounded movement)
                        max_sl = 1.5 * atr if is_range_regime else (2.0 * atr if trading_mode == "swing" else 1.5 * atr)
                        
                        if sl_distance < min_sl:
                            sl_price = current_price - min_sl
                            sl_distance = min_sl
                            
                        if sl_distance > max_sl:
                            cls.logger.info(f"🐢 BUY TBS skipped: structural SL distance ({sl_distance:.2f}) exceeds max allowed ({max_sl:.2f})")
                            return None, "sideway", 0.0, 0.0, {}

                        # Structure-targeted Take Profit
                        # Range mode: target is the opposite wall of the range (crt_high)
                        opposing_target = crt_high
                        if not is_range_regime and df_h1 is not None and len(df_h1) >= 10:
                            h1_recent_high = float(df_h1.iloc[-10:]['high'].max())
                            if h1_recent_high > current_price:
                                opposing_target = max(opposing_target, h1_recent_high)

                        structural_rr = (opposing_target - current_price) / sl_distance
                        
                        # Range mode: accept lower min RR (1.0) since confined range has less room
                        min_rr_threshold = 1.0 if is_range_regime else 1.2
                        if structural_rr < min_rr_threshold:
                            cls.logger.info(f"🐢 BUY TBS skipped: structural RR ({structural_rr:.2f}) is under {min_rr_threshold} edge limit")
                            return None, "sideway", 0.0, 0.0, {}
                            
                        # If target is too far, clamp TP to the settings R-ratio
                        if structural_rr > rr_ratio:
                            tp_price = current_price + (rr_ratio * sl_distance)
                        else:
                            tp_price = opposing_target

                        sl_price, tp_price = clamp_m1_trade_levels("BUY", current_price, sl_price, tp_price)

                        setup_label = "RANGE_BOUNCE_BUY" if is_range_regime else "TBS_BUY"
                        metadata = {
                            "strategy": "CRT_TBS",
                            "crt_high": crt_high,
                            "crt_low": crt_low,
                            "lowest_sweep_low": float(lowest_sweep_low) if not np.isnan(lowest_sweep_low) else crt_low,
                            "trigger": setup_label,
                            "m5_sweep_confirmed": m5_sweep_confirmed,
                            "htf_bias": htf_bias,
                            "crt_source": crt_source_label,
                            "range_mode": is_range_regime,
                            "double_sweep": has_double_sweep,
                            "ofi": ofi,
                            "vsa_patterns": [s['pattern'] for s in active_vsa_patterns]
                        }
                        bias_label = "RANGE" if is_range_regime else "BULL"
                        cls.logger.info(
                            f"🐢 BUY TBS | Mode={trading_mode.upper()} | "
                            f"HTF={bias_label} Entry={current_price:.2f} SL={sl_price:.2f} TP={tp_price:.2f} | RR={structural_rr:.2f}"
                        )
                        return "BUY", "bullish", sl_price, tp_price, metadata
                    else:
                        cls.logger.debug(f"🐢 BUY TBS skipped: chase guard (price={current_price:.2f} > limit={chase_limit:.2f})")

            # ── 7. SELL Setup Calculation (Structural Gated) ─────────────────────
            # In range mode: allow sell setup from sweep direction even when htf_bias == 0
            effective_sell_bias = (htf_bias == -1) or (is_range_regime and htf_bias == 0 and range_sweep_direction == -1)
            if tbs_sell_trigger and effective_sell_bias:
                has_bear_vsa = any(s['pattern'] in ['UPTHRUST', 'NO_DEMAND', 'BUYING_CLIMAX', 'TEST_OF_DEMAND', 'EFFORT_VS_RESULT_BEARISH'] for s in active_vsa_patterns)
                
                # Check Gold strict filters when single sweep
                gold_strict_ok = True
                if is_gold and is_range_regime and not has_double_sweep:
                    if not has_bear_vsa:
                        cls.logger.info("🐢 SELL TBS Gold skipped: no bear VSA exhaustion pattern under single sweep")
                        gold_strict_ok = False
                    elif ofi > -0.25:
                        cls.logger.info(f"🐢 SELL TBS Gold skipped: OFI imbalance ({ofi:.2f}) > -0.25 under single sweep")
                        gold_strict_ok = False
                
                # Dealing Range Premium/Discount check
                pd_ok = True
                range_low = np.nan
                range_high = np.nan
                if df_h1 is not None and len(df_h1) > 0:
                    last_row = df_h1.iloc[-1]
                    range_low = float(last_row.get("support", np.nan))
                    range_high = float(last_row.get("resistance", np.nan))
                    if not np.isnan(range_low) and not np.isnan(range_high):
                        rng = range_high - range_low
                        if rng > 0.0:
                            retracement = (current_price - range_low) / rng
                            # Extreme Discount trap check (selling the bottom 15% of range)
                            if retracement <= 0.15:
                                cls.logger.info(f"🐢 SELL TBS skipped: price is in extreme discount trap ({retracement:.2f})")
                                pd_ok = False
                
                if not vsa_sell_confirmed or not gold_strict_ok or not pd_ok:
                    cls.logger.info("🐢 SELL TBS skipped: VSA / Volume / Gold / Premium-Discount filter confirmation failed")
                else:
                    # Chase guard — range mode uses tighter chase
                    if is_gold and is_range_regime and not has_double_sweep:
                        chase_factor = 0.25
                    else:
                        chase_factor = 0.4 if is_range_regime else 0.6
                    chase_limit = crt_high - (chase_factor * atr)
                    if current_price >= chase_limit:
                        # Tight price-action Stop Loss strictly above the sweep wick
                        sl_pad = 0.12 * atr if is_gold else 0.05 * atr
                        sweep_high_val = highest_sweep_high if not np.isnan(highest_sweep_high) else crt_high
                        sl_price = max(sweep_high_val, crt_high) + sl_pad
                        sl_distance = sl_price - current_price
                        
                        min_sl = 0.3 * atr
                        max_sl = 1.5 * atr if is_range_regime else (2.0 * atr if trading_mode == "swing" else 1.5 * atr)
                        
                        if sl_distance < min_sl:
                            sl_price = current_price + min_sl
                            sl_distance = min_sl
                            
                        if sl_distance > max_sl:
                            cls.logger.info(f"🐢 SELL TBS skipped: structural SL distance ({sl_distance:.2f}) exceeds max allowed ({max_sl:.2f})")
                            return None, "sideway", 0.0, 0.0, {}

                        # Structure-targeted Take Profit — range mode targets opposite wall
                        opposing_target = crt_low
                        if not is_range_regime and df_h1 is not None and len(df_h1) >= 10:
                            h1_recent_low = float(df_h1.iloc[-10:]['low'].min())
                            if h1_recent_low < current_price:
                                opposing_target = min(opposing_target, h1_recent_low)

                        structural_rr = (current_price - opposing_target) / sl_distance
                        
                        # Range mode: accept lower min RR (1.0)
                        min_rr_threshold = 1.0 if is_range_regime else 1.2
                        if structural_rr < min_rr_threshold:
                            cls.logger.info(f"🐢 SELL TBS skipped: structural RR ({structural_rr:.2f}) is under {min_rr_threshold} edge limit")
                            return None, "sideway", 0.0, 0.0, {}

                        # If target is too far, clamp TP
                        if structural_rr > rr_ratio:
                            tp_price = current_price - (rr_ratio * sl_distance)
                        else:
                            tp_price = opposing_target

                        sl_price, tp_price = clamp_m1_trade_levels("SELL", current_price, sl_price, tp_price)

                        setup_label = "RANGE_BOUNCE_SELL" if is_range_regime else "TBS_SELL"
                        metadata = {
                            "strategy": "CRT_TBS",
                            "crt_high": crt_high,
                            "crt_low": crt_low,
                            "highest_sweep_high": float(highest_sweep_high) if not np.isnan(highest_sweep_high) else crt_high,
                            "trigger": setup_label,
                            "m5_sweep_confirmed": m5_sweep_confirmed,
                            "htf_bias": htf_bias,
                            "crt_source": crt_source_label,
                            "range_mode": is_range_regime,
                            "double_sweep": has_double_sweep,
                            "ofi": ofi,
                            "vsa_patterns": [s['pattern'] for s in active_vsa_patterns]
                        }
                        bias_label = "RANGE" if is_range_regime else "BEAR"
                        cls.logger.info(
                            f"🐢 SELL TBS | Mode={trading_mode.upper()} | "
                            f"HTF={bias_label} Entry={current_price:.2f} SL={sl_price:.2f} TP={tp_price:.2f} | RR={structural_rr:.2f}"
                        )
                        return "SELL", "bearish", sl_price, tp_price, metadata
                    else:
                        cls.logger.debug(f"🐢 SELL TBS skipped: chase guard (price={current_price:.2f} < limit={chase_limit:.2f})")

            return None, "sideway", 0.0, 0.0, {}

        except Exception as e:
            cls.logger.error(f"Error in evaluate_crt_tbs: {e}")
            import traceback; traceback.print_exc()
            return None, "sideway", 0.0, 0.0, {}
