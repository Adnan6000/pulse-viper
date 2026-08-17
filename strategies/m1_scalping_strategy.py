# strategies/m1_scalping_strategy.py
import numpy as np
import pandas as pd
import logging
from typing import Dict, Tuple, Optional
from utils.settings_manager import clamp_m1_trade_levels

class M1ScalpingStrategy:
    logger = logging.getLogger("PulseViper.M1ScalpingStrategy")

    @staticmethod
    def calculate_ema(series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def calculate_stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> Tuple[pd.Series, pd.Series]:
        low_min = df['low'].rolling(window=k_period).min()
        high_max = df['high'].rolling(window=k_period).max()
        denom = high_max - low_min
        k_line = np.where(denom == 0, 50.0, 100 * (df['close'] - low_min) / np.where(denom == 0, 1.0, denom))
        k_series = pd.Series(k_line, index=df.index)
        d_series = k_series.rolling(window=d_period).mean()
        return k_series.fillna(50.0), d_series.fillna(50.0)

    @classmethod
    def evaluate_m1_scalping(
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
        M1 Gold Scalping Strategies:
          1. 4-EMA Pullback Setup (8, 13, 21, 34 EMAs)
          2. Stochastic Hook Entry (50, 100 EMAs + Stochastic < 20 / > 80 hook)
          3. 9-SMA Volume Rejection (9 SMA + Volume spike + rejection candle)
        """
        try:
            if df_m1 is None or len(df_m1) < 110:
                return None, 0.0, 0.0, {}

            # Timeframe filters: verify we are trading in direction of trend using M5/M15
            trend_dir = 0
            if df_m5 is not None and len(df_m5) >= 20:
                # Check simple slope or EMA alignment on M5
                m5_ema50 = cls.calculate_ema(df_m5['close'], 50)
                if float(df_m5['close'].iloc[-2]) > float(m5_ema50.iloc[-2]):
                    trend_dir = 1
                else:
                    trend_dir = -1

            # ── STRATEGY 1: 4-EMA Pullback Setup ──────────────────────────────
            closes = df_m1['close']
            opens = df_m1['open']
            highs = df_m1['high']
            lows = df_m1['low']

            ema8 = cls.calculate_ema(closes, 8)
            ema13 = cls.calculate_ema(closes, 13)
            ema21 = cls.calculate_ema(closes, 21)
            ema34 = cls.calculate_ema(closes, 34)

            # Stack checks
            stacked_bull = (ema8.iloc[-2] > ema13.iloc[-2] > ema21.iloc[-2] > ema34.iloc[-2])
            stacked_bear = (ema8.iloc[-2] < ema13.iloc[-2] < ema21.iloc[-2] < ema34.iloc[-2])

            # BUY conditions
            if stacked_bull and (trend_dir >= 0 or regime == "RANGE"):
                # Pullback: low of one of recent 3 candles touched or dipped below 13 EMA
                pulled_back = any(float(lows.iloc[idx]) <= float(ema13.iloc[idx]) for idx in [-4, -3, -2])
                # Close back: last closed candle was bullish and closed back above 8 EMA or 13 EMA
                close_back = float(closes.iloc[-2]) > float(ema13.iloc[-2]) and float(closes.iloc[-2]) > float(opens.iloc[-2])
                
                if pulled_back and close_back:
                    sl = float(ema34.iloc[-2]) - 0.2 * atr
                    tp = current_price + 1.5 * (current_price - sl)
                    sl, tp = clamp_m1_trade_levels("BUY", current_price, sl, tp)
                    meta = {
                        "strategy": "M1_SCALPING",
                        "trigger": "M1_4EMA_PULLBACK_BUY",
                        "ema8": float(ema8.iloc[-2]),
                        "ema34": float(ema34.iloc[-2])
                    }
                    return "BUY", sl, tp, meta

            # SELL conditions
            if stacked_bear and (trend_dir <= 0 or regime == "RANGE"):
                # Pullback: high of recent candles touched/exceeded 13 EMA
                pulled_back = any(float(highs.iloc[idx]) >= float(ema13.iloc[idx]) for idx in [-4, -3, -2])
                # Close back: closed bearish and closed below 13 EMA
                close_back = float(closes.iloc[-2]) < float(ema13.iloc[-2]) and float(closes.iloc[-2]) < float(opens.iloc[-2])
                
                if pulled_back and close_back:
                    sl = float(ema34.iloc[-2]) + 0.2 * atr
                    tp = current_price - 1.5 * (sl - current_price)
                    sl, tp = clamp_m1_trade_levels("SELL", current_price, sl, tp)
                    meta = {
                        "strategy": "M1_SCALPING",
                        "trigger": "M1_4EMA_PULLBACK_SELL",
                        "ema8": float(ema8.iloc[-2]),
                        "ema34": float(ema34.iloc[-2])
                    }
                    return "SELL", sl, tp, meta

            # ── STRATEGY 2: Stochastic Hook Entry ─────────────────────────────
            ema50 = cls.calculate_ema(closes, 50)
            ema100 = cls.calculate_ema(closes, 100)
            stoch_k, stoch_d = cls.calculate_stochastic(df_m1, 14, 3)

            # BUY Hook: price above 50 and 100 EMAs, stoch k crosses above d below 20, close to 50 EMA (within 3 pips)
            is_bull_trend = float(closes.iloc[-2]) > float(ema50.iloc[-2]) > float(ema100.iloc[-2])
            if is_bull_trend and (trend_dir >= 0 or regime == "RANGE"):
                stoch_oversold = any(stoch_k.iloc[idx] <= 20.0 for idx in [-3, -2])
                stoch_hook = stoch_k.iloc[-2] > stoch_d.iloc[-2] and stoch_k.iloc[-3] <= stoch_d.iloc[-3]
                near_ema50 = abs(float(closes.iloc[-2]) - float(ema50.iloc[-2])) <= 3.0 # within 30 pips for Gold
                
                if stoch_oversold and stoch_hook and near_ema50:
                    sl = float(ema50.iloc[-2]) - 0.3 * atr
                    tp = current_price + 1.5 * (current_price - sl)
                    sl, tp = clamp_m1_trade_levels("BUY", current_price, sl, tp)
                    meta = {
                        "strategy": "M1_SCALPING",
                        "trigger": "M1_STOCH_HOOK_BUY",
                        "stoch_k": float(stoch_k.iloc[-2]),
                        "stoch_d": float(stoch_d.iloc[-2])
                    }
                    return "BUY", sl, tp, meta

            # SELL Hook: price below 50 and 100 EMAs, stoch k crosses below d above 80, close to 50 EMA
            is_bear_trend = float(closes.iloc[-2]) < float(ema50.iloc[-2]) < float(ema100.iloc[-2])
            if is_bear_trend and (trend_dir <= 0 or regime == "RANGE"):
                stoch_overbought = any(stoch_k.iloc[idx] >= 80.0 for idx in [-3, -2])
                stoch_hook = stoch_k.iloc[-2] < stoch_d.iloc[-2] and stoch_k.iloc[-3] >= stoch_d.iloc[-3]
                near_ema50 = abs(float(closes.iloc[-2]) - float(ema50.iloc[-2])) <= 3.0
                
                if stoch_overbought and stoch_hook and near_ema50:
                    sl = float(ema50.iloc[-2]) + 0.3 * atr
                    tp = current_price - 1.5 * (sl - current_price)
                    sl, tp = clamp_m1_trade_levels("SELL", current_price, sl, tp)
                    meta = {
                        "strategy": "M1_SCALPING",
                        "trigger": "M1_STOCH_HOOK_SELL",
                        "stoch_k": float(stoch_k.iloc[-2]),
                        "stoch_d": float(stoch_d.iloc[-2])
                    }
                    return "SELL", sl, tp, meta

            # ── STRATEGY 3: 9-SMA Volume Rejection ────────────────────────────
            sma9 = closes.rolling(window=9).mean()
            vols = df_m1['volume']
            avg_vol = vols.rolling(window=20).mean()

            # Hammer rejection pattern check (BUY)
            # Candle touched 9 SMA (low <= 9 SMA <= high), long lower wick, closed bullish, high volume
            last_low = float(lows.iloc[-2])
            last_high = float(highs.iloc[-2])
            last_close = float(closes.iloc[-2])
            last_open = float(opens.iloc[-2])
            last_sma9 = float(sma9.iloc[-2])
            last_vol = float(vols.iloc[-2])
            last_avg_vol = float(avg_vol.iloc[-2])

            touched_sma9 = last_low <= last_sma9 <= last_high
            volume_spiked = last_vol > 1.3 * last_avg_vol
            
            if touched_sma9 and volume_spiked:
                # Hammer: open/close in upper 40%, lower wick >= 2.0 * body
                body_size = abs(last_close - last_open)
                lower_wick = min(last_open, last_close) - last_low
                upper_wick = last_high - max(last_open, last_close)
                
                is_hammer = (lower_wick >= 1.5 * body_size) and (upper_wick <= 0.4 * body_size or upper_wick < lower_wick * 0.3)
                
                if is_hammer and last_close > last_open and (trend_dir >= 0 or regime == "RANGE"):
                    sl = last_low - 0.1 * atr
                    tp = current_price + 1.5 * (current_price - sl)
                    sl, tp = clamp_m1_trade_levels("BUY", current_price, sl, tp)
                    meta = {
                        "strategy": "M1_SCALPING",
                        "trigger": "M1_9SMA_HAMMER_REJECTION_BUY",
                        "vol_ratio": last_vol / (last_avg_vol + 1e-9)
                    }
                    return "BUY", sl, tp, meta

            # Shooting Star rejection pattern check (SELL)
            if touched_sma9 and volume_spiked:
                # Shooting Star: open/close in lower 40%, upper wick >= 1.5 * body
                body_size = abs(last_close - last_open)
                lower_wick = min(last_open, last_close) - last_low
                upper_wick = last_high - max(last_open, last_close)
                
                is_shooting_star = (upper_wick >= 1.5 * body_size) and (lower_wick <= 0.4 * body_size or lower_wick < upper_wick * 0.3)
                
                if is_shooting_star and last_close < last_open and (trend_dir <= 0 or regime == "RANGE"):
                    sl = last_high + 0.1 * atr
                    tp = current_price - 1.5 * (sl - current_price)
                    sl, tp = clamp_m1_trade_levels("SELL", current_price, sl, tp)
                    meta = {
                        "strategy": "M1_SCALPING",
                        "trigger": "M1_9SMA_STAR_REJECTION_SELL",
                        "vol_ratio": last_vol / (last_avg_vol + 1e-9)
                    }
                    return "SELL", sl, tp, meta

            # ── STRATEGY 4: Liquidity Sweep + Strong Displacement ────────────
            # Detect low sweep followed by bullish displacement bar (or high sweep + bearish bar)
            if len(df_m1) >= 5:
                recent_5_low = float(df_m1['low'].iloc[-6:-1].min())
                recent_5_high = float(df_m1['high'].iloc[-6:-1].max())

                # Bullish sweep + displacement: last candle swept below 5-bar low and closed strong above open with high volume
                if last_low < recent_5_low and last_close > last_open:
                    body = last_close - last_open
                    if body >= 0.4 * (last_high - last_low) and last_vol > 1.2 * last_avg_vol:
                        sl = last_low - 0.1 * atr
                        tp = current_price + 1.5 * (current_price - sl)
                        sl, tp = clamp_m1_trade_levels("BUY", current_price, sl, tp)
                        meta = {
                            "strategy": "M1_SCALPING",
                            "trigger": "M1_SWEEP_DISPLACEMENT_BUY",
                            "swept_low": recent_5_low
                        }
                        return "BUY", sl, tp, meta

                # Bearish sweep + displacement
                if last_high > recent_5_high and last_close < last_open:
                    body = last_open - last_close
                    if body >= 0.4 * (last_high - last_low) and last_vol > 1.2 * last_avg_vol:
                        sl = last_high + 0.1 * atr
                        tp = current_price - 1.5 * (sl - current_price)
                        sl, tp = clamp_m1_trade_levels("SELL", current_price, sl, tp)
                        meta = {
                            "strategy": "M1_SCALPING",
                            "trigger": "M1_SWEEP_DISPLACEMENT_SELL",
                            "swept_high": recent_5_high
                        }
                        return "SELL", sl, tp, meta

            # ── STRATEGY 5: Micro Fair Value Gap (FVG) Retracement ────────────
            if len(df_m1) >= 4:
                # Check 3-candle FVG gap: candle[-4].high < candle[-2].low for bullish FVG
                c4_high = float(df_m1['high'].iloc[-4])
                c2_low = float(df_m1['low'].iloc[-2])
                c4_low = float(df_m1['low'].iloc[-4])
                c2_high = float(df_m1['high'].iloc[-2])

                # Bullish micro-FVG: gap between c4 high and c2 low, and current price in gap
                if c2_low > c4_high:
                    fvg_bottom = c4_high
                    fvg_top = c2_low
                    if fvg_bottom <= current_price <= fvg_top + 0.2 * atr:
                        sl = fvg_bottom - 0.1 * atr
                        tp = current_price + 1.5 * (current_price - sl)
                        sl, tp = clamp_m1_trade_levels("BUY", current_price, sl, tp)
                        meta = {
                            "strategy": "M1_SCALPING",
                            "trigger": "M1_MICRO_FVG_RETRACEMENT_BUY",
                            "fvg_top": fvg_top,
                            "fvg_bottom": fvg_bottom
                        }
                        return "BUY", sl, tp, meta

                # Bearish micro-FVG: gap between c2 high and c4 low
                if c2_high < c4_low:
                    fvg_top = c4_low
                    fvg_bottom = c2_high
                    if fvg_bottom - 0.2 * atr <= current_price <= fvg_top:
                        sl = fvg_top + 0.1 * atr
                        tp = current_price - 1.5 * (sl - current_price)
                        sl, tp = clamp_m1_trade_levels("SELL", current_price, sl, tp)
                        meta = {
                            "strategy": "M1_SCALPING",
                            "trigger": "M1_MICRO_FVG_RETRACEMENT_SELL",
                            "fvg_top": fvg_top,
                            "fvg_bottom": fvg_bottom
                        }
                        return "SELL", sl, tp, meta

            return None, 0.0, 0.0, {}
        except Exception as e:
            cls.logger.error(f"Error in evaluate_m1_scalping: {e}")
            return None, 0.0, 0.0, {}
