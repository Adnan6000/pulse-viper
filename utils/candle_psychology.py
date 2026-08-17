# utils/candle_psychology.py
"""
Candlestick Psychology & Rejection Wick Analyzer
=================================================
Analyzes candle formation, momentum, and wick rejections.
Enforces gates to prevent:
  1. Catching a falling knife (buying into strong bearish momentum or selling into strong bullish momentum).
  2. Trading against rejection wicks (buying when resistance rejects price with long upper wicks, or selling when support rejects price with long lower wicks).
"""

import pandas as pd
import numpy as np
import logging

logger = logging.getLogger("PulseViper.CandlePsychology")

class CandlePsychologyAnalyzer:
    @staticmethod
    def analyze_candle(row: pd.Series, prev_row: pd.Series = None) -> dict:
        """
        Analyze a single candle row for body size, wicks, and specific patterns.
        """
        metrics = {
            "is_valid": False,
            "body_size": 0.0,
            "total_range": 0.0,
            "body_ratio": 0.0,
            "upper_wick": 0.0,
            "lower_wick": 0.0,
            "upper_wick_ratio": 0.0,
            "lower_wick_ratio": 0.0,
            "is_bullish": False,
            "is_bearish": False,
            "is_doji": False,
            "is_hammer": False,
            "is_shooting_star": False,
            "is_engulfing": False,
            "is_marubozu": False,
            "has_long_upper_wick": False,
            "has_long_lower_wick": False
        }

        if row is None or any(col not in row for col in ['open', 'high', 'low', 'close']):
            return metrics

        o, h, l, c = float(row['open']), float(row['high']), float(row['low']), float(row['close'])
        total_range = h - l
        if total_range <= 0:
            return metrics

        body_size = abs(c - o)
        body_ratio = body_size / total_range
        is_bullish = c > o
        is_bearish = c < o

        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - l

        upper_wick_ratio = upper_wick / total_range
        lower_wick_ratio = lower_wick / total_range

        metrics.update({
            "is_valid": True,
            "body_size": body_size,
            "total_range": total_range,
            "body_ratio": body_ratio,
            "upper_wick": upper_wick,
            "lower_wick": lower_wick,
            "upper_wick_ratio": upper_wick_ratio,
            "lower_wick_ratio": lower_wick_ratio,
            "is_bullish": is_bullish,
            "is_bearish": is_bearish,
        })

        # 1. Doji / Indecision
        if body_ratio <= 0.12:
            metrics["is_doji"] = True

        # 2. Rejection Wicks (35% - 40% range is significant on 1-minute bars)
        if upper_wick_ratio >= 0.40:
            metrics["has_long_upper_wick"] = True
            if body_ratio <= 0.35:
                metrics["is_shooting_star"] = True
        elif upper_wick_ratio >= 0.35:
            metrics["has_long_upper_wick"] = True

        if lower_wick_ratio >= 0.40:
            metrics["has_long_lower_wick"] = True
            if body_ratio <= 0.35:
                metrics["is_hammer"] = True
        elif lower_wick_ratio >= 0.35:
            metrics["has_long_lower_wick"] = True

        # 3. Marubozu / Strong Momentum
        if body_ratio >= 0.75:
            metrics["is_marubozu"] = True

        # 4. Engulfing pattern
        if prev_row is not None:
            prev_o, prev_c = float(prev_row['open']), float(prev_row['close'])
            prev_body = abs(prev_c - prev_o)
            
            # Current body completely engulfs previous body
            if body_size > prev_body:
                if is_bullish and prev_c < prev_o:
                    metrics["is_engulfing"] = True
                elif is_bearish and prev_c > prev_o:
                    metrics["is_engulfing"] = True

        return metrics

    @classmethod
    def evaluate_psychology_veto(
        cls,
        df_m1: pd.DataFrame,
        df_m5: pd.DataFrame,
        action: str,
        atr_m1: float = 1.0,
        atr_m5: float = 1.0,
        strict_mode: bool = True,
        df_m15: pd.DataFrame = None,
        atr_m15: float = 1.0
    ) -> tuple:
        """
        Evaluate candle wicks, body, and momentum.
        Returns: (allowed: bool, reason: str, score_modifier: float)
        """
        if df_m1 is None or len(df_m1) < 3:
            return True, "Insufficient M1 candles", 0.0
        
        # Determine target candles:
        # iloc[-1] is the forming candle. iloc[-2] is the last completed closed candle.
        # Candle psychology is primarily assessed on the last completed candle (iloc[-2]).
        # If the forming candle is already very large/extreme, we can also check it.
        c_m1_closed = cls.analyze_candle(df_m1.iloc[-2], df_m1.iloc[-3])
        c_m1_prev = cls.analyze_candle(df_m1.iloc[-3])
        c_m1_forming = cls.analyze_candle(df_m1.iloc[-1])
        
        c_m5_closed = None
        if df_m5 is not None and len(df_m5) >= 3:
            c_m5_closed = cls.analyze_candle(df_m5.iloc[-2], df_m5.iloc[-3])
            c_m5_forming = cls.analyze_candle(df_m5.iloc[-1])
            
        c_m15_closed = None
        if df_m15 is not None and len(df_m15) >= 3:
            c_m15_closed = cls.analyze_candle(df_m15.iloc[-2], df_m15.iloc[-3])
            c_m15_forming = cls.analyze_candle(df_m15.iloc[-1])
        
        score_modifier = 0.0

        if action == "BUY":
            # --- BUY GATES (VETO IF BEARISH MOMENTUM / REJECTION) ---
            
            # 1. Bearish Rejection check (Upper Wick Rejection)
            # If the closed candle rejected resistance with a long upper wick, do not buy
            if c_m1_closed["is_shooting_star"] or (c_m1_closed["has_long_upper_wick"] and c_m1_closed["is_bearish"]):
                msg = f"M1 closed candle has long upper rejection wick ({c_m1_closed['upper_wick_ratio']:.2f})"
                if strict_mode:
                    return False, f"VETO: {msg}", -20.0
                score_modifier -= 15.0

            if c_m5_closed and (c_m5_closed["is_shooting_star"] or (c_m5_closed["has_long_upper_wick"] and c_m5_closed["is_bearish"])):
                msg = f"M5 closed candle has long upper rejection wick ({c_m5_closed['upper_wick_ratio']:.2f})"
                if strict_mode:
                    return False, f"VETO: {msg}", -20.0
                score_modifier -= 15.0
                
            if c_m15_closed and (c_m15_closed["is_shooting_star"] or (c_m15_closed["has_long_upper_wick"] and c_m15_closed["is_bearish"])):
                msg = f"M15 closed candle has long upper rejection wick ({c_m15_closed['upper_wick_ratio']:.2f})"
                if strict_mode:
                    return False, f"VETO: {msg}", -20.0
                score_modifier -= 15.0

            # 2. Strong Bearish Momentum Check (Marubozu / Big body)
            # Catching a falling knife: if M1 or M5 has a massive bearish candle
            m1_atr = atr_m1 if atr_m1 > 0 else df_m1['high'].sub(df_m1['low']).rolling(14).mean().iloc[-1]
            if c_m1_closed["is_bearish"] and c_m1_closed["body_ratio"] >= 0.75 and c_m1_closed["total_range"] > 1.2 * m1_atr:
                msg = "M1 closed candle shows strong bearish momentum (falling knife)"
                if strict_mode:
                    return False, f"VETO: {msg}", -20.0
                score_modifier -= 15.0

            if c_m5_closed and c_m5_closed["is_bearish"] and c_m5_closed["body_ratio"] >= 0.75 and c_m5_closed["total_range"] > 1.2 * atr_m5:
                msg = "M5 closed candle shows strong bearish momentum (falling knife)"
                if strict_mode:
                    return False, f"VETO: {msg}", -20.0
                score_modifier -= 15.0
                
            if c_m15_closed and c_m15_closed["is_bearish"] and c_m15_closed["body_ratio"] >= 0.75 and c_m15_closed["total_range"] > 1.2 * atr_m15:
                msg = "M15 closed candle shows strong bearish momentum (falling knife)"
                if strict_mode:
                    return False, f"VETO: {msg}", -20.0
                score_modifier -= 15.0

            # 3. Bearish Engulfing Veto
            if c_m1_closed["is_bearish"] and c_m1_closed["is_engulfing"]:
                msg = "M1 closed candle is a Bearish Engulfing pattern"
                if strict_mode:
                    return False, f"VETO: {msg}", -15.0
                score_modifier -= 10.0

            # --- BUY BOOSTS (FAVORABLE PSYCHOLOGY) ---
            # Favorable lower wick rejection
            if c_m1_closed["has_long_lower_wick"] and c_m1_closed["is_bullish"]:
                score_modifier += 8.0
            elif c_m1_closed["is_bullish"] and c_m1_closed["is_engulfing"]:
                score_modifier += 10.0  # Bullish Engulfing boost

        elif action == "SELL":
            # --- SELL GATES (VETO IF BULLISH MOMENTUM / REJECTION) ---
            
            # 1. Bullish Rejection check (Lower Wick Rejection)
            # If the closed candle rejected support with a long lower wick, do not sell
            if c_m1_closed["is_hammer"] or (c_m1_closed["has_long_lower_wick"] and c_m1_closed["is_bullish"]):
                msg = f"M1 closed candle has long lower rejection wick ({c_m1_closed['lower_wick_ratio']:.2f})"
                if strict_mode:
                    return False, f"VETO: {msg}", -20.0
                score_modifier -= 15.0

            if c_m5_closed and (c_m5_closed["is_hammer"] or (c_m5_closed["has_long_lower_wick"] and c_m5_closed["is_bullish"])):
                msg = f"M5 closed candle has long lower rejection wick ({c_m5_closed['lower_wick_ratio']:.2f})"
                if strict_mode:
                    return False, f"VETO: {msg}", -20.0
                score_modifier -= 15.0
                
            if c_m15_closed and (c_m15_closed["is_hammer"] or (c_m15_closed["has_long_lower_wick"] and c_m15_closed["is_bullish"])):
                msg = f"M15 closed candle has long lower rejection wick ({c_m15_closed['lower_wick_ratio']:.2f})"
                if strict_mode:
                    return False, f"VETO: {msg}", -20.0
                score_modifier -= 15.0

            # 2. Strong Bullish Momentum Check (Marubozu / Big body)
            # Standing in front of a freight train: if M1 or M5 has a massive bullish candle
            m1_atr = atr_m1 if atr_m1 > 0 else df_m1['high'].sub(df_m1['low']).rolling(14).mean().iloc[-1]
            if c_m1_closed["is_bullish"] and c_m1_closed["body_ratio"] >= 0.75 and c_m1_closed["total_range"] > 1.2 * m1_atr:
                msg = "M1 closed candle shows strong bullish momentum (climbing wall)"
                if strict_mode:
                    return False, f"VETO: {msg}", -20.0
                score_modifier -= 15.0

            if c_m5_closed and c_m5_closed["is_bullish"] and c_m5_closed["body_ratio"] >= 0.75 and c_m5_closed["total_range"] > 1.2 * atr_m5:
                msg = "M5 closed candle shows strong bullish momentum (climbing wall)"
                if strict_mode:
                    return False, f"VETO: {msg}", -20.0
                score_modifier -= 15.0
                
            if c_m15_closed and c_m15_closed["is_bullish"] and c_m15_closed["body_ratio"] >= 0.75 and c_m15_closed["total_range"] > 1.2 * atr_m15:
                msg = "M15 closed candle shows strong bullish momentum (climbing wall)"
                if strict_mode:
                    return False, f"VETO: {msg}", -20.0
                score_modifier -= 15.0

            # 3. Bullish Engulfing Veto
            if c_m1_closed["is_bullish"] and c_m1_closed["is_engulfing"]:
                msg = "M1 closed candle is a Bullish Engulfing pattern"
                if strict_mode:
                    return False, f"VETO: {msg}", -15.0
                score_modifier -= 10.0

            # --- SELL BOOSTS (FAVORABLE PSYCHOLOGY) ---
            # Favorable upper wick rejection
            if c_m1_closed["has_long_upper_wick"] and c_m1_closed["is_bearish"]:
                score_modifier += 8.0
            elif c_m1_closed["is_bearish"] and c_m1_closed["is_engulfing"]:
                score_modifier += 10.0  # Bearish Engulfing boost

        return True, "Passed candle psychology checks", score_modifier

    @classmethod
    def check_swing_start_pattern(cls, df_m1: pd.DataFrame, df_m5: pd.DataFrame = None) -> dict:
        """
        Check for a swing start signal on completed M1 or M5 candles (index -2).
        Returns: {
            "bullish_confirmed": bool,
            "bearish_confirmed": bool,
            "pattern_name": str,
            "tf": str
        }
        """
        res = {
            "bullish_confirmed": False,
            "bearish_confirmed": False,
            "pattern_name": "",
            "tf": ""
        }
        
        tfs_to_check = []
        if df_m5 is not None and len(df_m5) >= 3:
            tfs_to_check.append((df_m5, "M5"))
        if df_m1 is not None and len(df_m1) >= 3:
            tfs_to_check.append((df_m1, "M1"))
            
        for df, tf_name in tfs_to_check:
            # Analyze closed candle (index -2) and previous candle (index -3) for engulfing check
            c_closed = cls.analyze_candle(df.iloc[-2], df.iloc[-3])
            
            # Check Bullish patterns
            is_bull = False
            bull_pattern = ""
            
            if c_closed["is_hammer"]:
                is_bull = True
                bull_pattern = "HAMMER"
            elif c_closed["is_engulfing"] and c_closed["is_bullish"]:
                is_bull = True
                bull_pattern = "BULLISH_ENGULFING"
            elif c_closed["is_marubozu"] and c_closed["is_bullish"]:
                is_bull = True
                bull_pattern = "BULLISH_MARUBOZU"
            elif c_closed["has_long_lower_wick"] and c_closed["is_bullish"]:
                is_bull = True
                bull_pattern = f"BULLISH_WICK_REJECTION ({c_closed['lower_wick_ratio']:.2f})"
                
            # Check VSA signals
            if not is_bull:
                from utils.volume_analyzer import VolumeAnalyzer
                if "atr" in df.columns:
                    vsa_signals = VolumeAnalyzer.detect_vsa_signals(df, df["atr"], lookback=2)
                    for sig in vsa_signals:
                        if sig.get("index") == -2 and sig.get("direction") == 1:
                            is_bull = True
                            bull_pattern = f"VSA_{sig['pattern']}"
                            break
                            
            # Check Bearish patterns
            is_bear = False
            bear_pattern = ""
            
            if c_closed["is_shooting_star"]:
                is_bear = True
                bear_pattern = "SHOOTING_STAR"
            elif c_closed["is_engulfing"] and c_closed["is_bearish"]:
                is_bear = True
                bear_pattern = "BEARISH_ENGULFING"
            elif c_closed["is_marubozu"] and c_closed["is_bearish"]:
                is_bear = True
                bear_pattern = "BEARISH_MARUBOZU"
            elif c_closed["has_long_upper_wick"] and c_closed["is_bearish"]:
                is_bear = True
                bear_pattern = f"BEARISH_WICK_REJECTION ({c_closed['upper_wick_ratio']:.2f})"
                
            if not is_bear:
                from utils.volume_analyzer import VolumeAnalyzer
                if "atr" in df.columns:
                    vsa_signals = VolumeAnalyzer.detect_vsa_signals(df, df["atr"], lookback=2)
                    for sig in vsa_signals:
                        if sig.get("index") == -2 and sig.get("direction") == -1:
                            is_bear = True
                            bear_pattern = f"VSA_{sig['pattern']}"
                            break
                            
            if is_bull or is_bear:
                res["bullish_confirmed"] = is_bull
                res["bearish_confirmed"] = is_bear
                res["pattern_name"] = bull_pattern if is_bull else bear_pattern
                res["tf"] = tf_name
                return res
                
        return res

