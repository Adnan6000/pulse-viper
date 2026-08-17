# strategies/fib_retest.py
import numpy as np
import pandas as pd
import logging
from typing import Dict, Tuple, Optional, List
from utils.settings_manager import clamp_m1_trade_levels

class FibRetestStrategy:
    logger = logging.getLogger("PulseViper.FibRetestStrategy")

    @staticmethod
    def calculate_ema(series: pd.Series, period: int) -> pd.Series:
        """Legacy helper for backward compatibility."""
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def calculate_adx(df: pd.DataFrame, period: int = 14) -> float:
        """Legacy helper for backward compatibility."""
        try:
            high = df['high']
            low = df['low']
            close = df['close']
            
            tr1 = high - low
            tr2 = (high - close.shift()).abs()
            tr3 = (low - close.shift()).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            
            upmove = high - high.shift()
            downmove = low.shift() - low
            
            plus_dm = np.where((upmove > downmove) & (upmove > 0), upmove, 0.0)
            minus_dm = np.where((downmove > upmove) & (downmove > 0), downmove, 0.0)
            
            plus_dm = pd.Series(plus_dm, index=df.index)
            minus_dm = pd.Series(minus_dm, index=df.index)
            
            tr_smooth = tr.rolling(window=period).mean()
            plus_di = 100 * (plus_dm.rolling(window=period).mean() / (tr_smooth + 1e-9))
            minus_di = 100 * (minus_dm.rolling(window=period).mean() / (tr_smooth + 1e-9))
            
            dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
            adx = dx.rolling(window=period).mean()
            return float(adx.iloc[-1])
        except Exception:
            return 0.0

    @staticmethod
    def detect_swing_points_pure(df: pd.DataFrame, window: int = 3) -> Tuple[List[float], List[float]]:
        """
        Detect Swing Highs and Swing Lows from candle history.
        A peak/trough must be higher/lower than w candles on either side.
        """
        highs = df['high'].values
        lows = df['low'].values
        n = len(df)
        swing_highs = []
        swing_lows = []
        
        for i in range(window, n - window):
            is_sh = True
            for w in range(1, window + 1):
                if highs[i] < highs[i - w] or highs[i] < highs[i + w]:
                    is_sh = False
                    break
            if is_sh:
                swing_highs.append(float(highs[i]))
                
            is_sl = True
            for w in range(1, window + 1):
                if lows[i] > lows[i - w] or lows[i] > lows[i + w]:
                    is_sl = False
                    break
            if is_sl:
                swing_lows.append(float(lows[i]))
                
        return swing_highs, swing_lows

    @classmethod
    def find_sr_zones(cls, swing_highs: List[float], swing_lows: List[float], atr: float) -> Tuple[List[float], List[float]]:
        """
        Group nearby swing points to identify Horizontal Support & Resistance Zones.
        """
        threshold = max(0.20 * atr, 1e-5)
        
        def cluster_points(points: List[float]) -> List[float]:
            if not points:
                return []
            
            # Count density
            density = []
            for p in points:
                count = sum(1 for x in points if abs(x - p) <= threshold)
                density.append((p, count))
                
            # Sort by density (highest first)
            density.sort(key=lambda x: x[1], reverse=True)
            
            # Filter unique levels
            zones = []
            for p, count in density:
                if not any(abs(x - p) <= threshold for x in zones):
                    zones.append(p)
            return sorted(zones)
            
        supports = cluster_points(swing_lows)
        resistances = cluster_points(swing_highs)
        return supports, resistances

    @classmethod
    def find_order_blocks(cls, df: pd.DataFrame, atr: float) -> Tuple[List[Dict], List[Dict]]:
        """
        Find recent unmitigated Bullish and Bearish Order Blocks (OB).
        A Bullish OB is the last bearish candle body before a strong upward expansion.
        A Bearish OB is the last bullish candle body before a strong downward expansion.
        """
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        opens = df['open'].values
        times = df.index
        n = len(df)
        
        bullish_obs = []
        bearish_obs = []
        
        # Check for impulse expansions (move >= 1.5 * ATR over last 2 candles)
        for i in range(2, n - 2):
            atr_val = atr
            # Bullish expansion
            move_up = closes[i] - opens[i-1]
            if move_up > 1.5 * atr_val and closes[i-2] < opens[i-2]:
                ob_top = max(opens[i-2], closes[i-2])
                ob_bottom = lows[i-2]
                
                # Check mitigation: Has price closed below ob_bottom since?
                mitigated = False
                for j in range(i, n):
                    if closes[j] < ob_bottom:
                        mitigated = True
                        break
                if not mitigated:
                    bullish_obs.append({
                        'top': float(ob_top),
                        'bottom': float(ob_bottom),
                        'time': str(times[i-2])
                    })
                    
            # Bearish expansion
            move_down = opens[i-1] - closes[i]
            if move_down > 1.5 * atr_val and closes[i-2] > opens[i-2]:
                ob_top = highs[i-2]
                ob_bottom = min(opens[i-2], closes[i-2])
                
                # Check mitigation: Has price closed above ob_top since?
                mitigated = False
                for j in range(i, n):
                    if closes[j] > ob_top:
                        mitigated = True
                        break
                if not mitigated:
                    bearish_obs.append({
                        'top': float(ob_top),
                        'bottom': float(ob_bottom),
                        'time': str(times[i-2])
                    })
                    
        return bullish_obs[-3:], bearish_obs[-3:]

    @staticmethod
    def detect_candlestick_reversal(df: pd.DataFrame) -> Tuple[Optional[str], float]:
        """
        Scan recent candles for:
        - Engulfing candles
        - 3-candle Morning/Evening Stars
        - Rejection wicks (Pin bars / Hammers / Shooting stars)
        """
        if len(df) < 3:
            return None, 0.0
            
        c1 = df.iloc[-3]
        c2 = df.iloc[-2]
        c3 = df.iloc[-1]
        
        c1_body = abs(c1['close'] - c1['open'])
        c2_body = abs(c2['close'] - c2['open'])
        c3_body = abs(c3['close'] - c3['open'])
        
        c1_dir = c1['close'] - c1['open']
        c3_dir = c3['close'] - c3['open']
        
        # 1. 3-Candle Morning/Evening Star Check
        # Morning Star (Bullish Reversal): Bearish candle -> Small body candle -> Bullish candle closing > 50% of first candle body
        if c1_dir < 0 and c3_dir > 0:
            if c2_body < 0.35 * c1_body and c3['close'] >= c1['close'] + 0.5 * c1_body:
                return "BULLISH_REVERSAL", 0.95
                
        # Evening Star (Bearish Reversal): Bullish candle -> Small body candle -> Bearish candle closing < 50% of first candle body
        if c1_dir > 0 and c3_dir < 0:
            if c2_body < 0.35 * c1_body and c3['close'] <= c1['close'] - 0.5 * c1_body:
                return "BEARISH_REVERSAL", 0.95
                
        # 2. Engulfing Check
        prev_body_dir = c2['close'] - c2['open']
        last_body_dir = c3['close'] - c3['open']
        
        if prev_body_dir < 0 and last_body_dir > 0:
            if c3['close'] >= c2['open'] and c3['open'] <= c2['close']:
                return "BULLISH_REVERSAL", 0.85
                
        if prev_body_dir > 0 and last_body_dir < 0:
            if c3['close'] <= c2['open'] and c3['open'] >= c2['close']:
                return "BEARISH_REVERSAL", 0.85
                
        # 3. Pin Bar / Rejection Wick Check on the last candle
        last_range = c3['high'] - c3['low']
        if last_range > 0:
            upper_wick = c3['high'] - max(c3['open'], c3['close'])
            lower_wick = min(c3['open'], c3['close']) - c3['low']
            
            # Bullish Rejection Pinbar (long lower wick >= 50% of candle range, body is small)
            if lower_wick / last_range >= 0.50 and c3_body / last_range <= 0.35:
                return "BULLISH_REVERSAL", float(lower_wick / last_range)
                
            # Bearish Rejection Pinbar (long upper wick >= 50% of candle range, body is small)
            if upper_wick / last_range >= 0.50 and c3_body / last_range <= 0.35:
                return "BEARISH_REVERSAL", float(upper_wick / last_range)
                
        return None, 0.0

    @staticmethod
    def detect_market_structure_trend(swing_highs: List[float], swing_lows: List[float]) -> str:
        """
        Dow Theory swing point analysis (HH/HL or LH/LL) to classify trend.
        """
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return "sideway"
            
        recent_highs = swing_highs[-3:]
        recent_lows = swing_lows[-3:]
        
        # Check Bullish (rising highs and lows)
        is_rising_highs = all(recent_highs[i] > recent_highs[i-1] for i in range(1, len(recent_highs)))
        is_rising_lows = all(recent_lows[i] > recent_lows[i-1] for i in range(1, len(recent_lows)))
        
        # Check Bearish (falling highs and lows)
        is_falling_highs = all(recent_highs[i] < recent_highs[i-1] for i in range(1, len(recent_highs)))
        is_falling_lows = all(recent_lows[i] < recent_lows[i-1] for i in range(1, len(recent_lows)))
        
        if is_rising_highs or is_rising_lows:
            return "bullish"
        elif is_falling_highs or is_falling_lows:
            return "bearish"
        return "sideway"

    @classmethod
    def evaluate_retest(
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
        Evaluate Price Action Levels Confluence setup on the 1-minute timeframe (df_ltf).
        Returns: Tuple of (Action "BUY"/"SELL"/None, Regime "bullish"/"bearish"/"sideway", SL, TP, Metadata)
        """
        try:
            # Shift core calculations to the 1-minute timeframe (df_ltf) if available
            calc_df = df_ltf if df_ltf is not None else df_context
            
            if len(calc_df) < 30:
                return None, "sideway", 0.0, 0.0, {}

            # 1. Swing points and trend detection on 1-minute timeframe
            from utils.settings_manager import settings_manager
            swing_window = settings_manager.get("smc_swing_window", 3)
            swing_highs, swing_lows = cls.detect_swing_points_pure(calc_df, window=swing_window)
            regime = cls.detect_market_structure_trend(swing_highs, swing_lows)
            
            # 2. Key Level Detection on 1-minute timeframe
            supports, resistances = cls.find_sr_zones(swing_highs, swing_lows, atr)
            bullish_obs, bearish_obs = cls.find_order_blocks(calc_df, atr)
            
            # Calculate Fibonacci Levels from latest major swings
            recent_high = max(swing_highs[-5:]) if swing_highs else float(calc_df['high'].max())
            recent_low = min(swing_lows[-5:]) if swing_lows else float(calc_df['low'].min())
            fib_range = recent_high - recent_low
            fib_50 = recent_high - 0.50 * fib_range if fib_range > 0 else current_price
            fib_618 = recent_high - 0.618 * fib_range if fib_range > 0 else current_price
            fib_786 = recent_high - 0.786 * fib_range if fib_range > 0 else current_price
            
            # Volume Profile info
            poc = 0.0
            val = 0.0
            vah = 0.0
            if volume_cache and 'profile' in volume_cache:
                prof = volume_cache['profile']
                poc = prof.get('poc_price', 0.0)
                min_p = prof.get('min_price', 0.0)
                max_p = prof.get('max_price', 0.0)
                val = min_p + 0.3 * (max_p - min_p)  # Approximation of VAL
                vah = min_p + 0.7 * (max_p - min_p)  # Approximation of VAH
                
            # Retrieve cached daily levels (PDH/PDL) and weekly levels (PWH/PWL)
            pdh = sentiment_cache.get('pdh', np.nan) if sentiment_cache else np.nan
            pdl = sentiment_cache.get('pdl', np.nan) if sentiment_cache else np.nan
            pwh = sentiment_cache.get('pwh', np.nan) if sentiment_cache else np.nan
            pwl = sentiment_cache.get('pwl', np.nan) if sentiment_cache else np.nan
            
            # Previous candle high/low (PCH/PCL)
            prev_row = calc_df.iloc[-2]
            pch = float(prev_row['high'])
            pcl = float(prev_row['low'])
            
            last_row = calc_df.iloc[-1]
            last_high = float(last_row['high'])
            last_low = float(last_row['low'])
            last_close = float(last_row['close'])
            
            # Liquidity Sweep Detections (ISL / OSL)
            bullish_sweep = False
            bearish_sweep = False
            sweep_reasons = []
            
            # OSL sweeps
            if not np.isnan(pdl) and last_low < pdl and last_close > pdl:
                bullish_sweep = True
                sweep_reasons.append(f"OSL Sweep: Swept PDL ({pdl:.2f})")
            if not np.isnan(pdh) and last_high > pdh and last_close < pdh:
                bearish_sweep = True
                sweep_reasons.append(f"OSL Sweep: Swept PDH ({pdh:.2f})")
            if not np.isnan(pwl) and last_low < pwl and last_close > pwl:
                bullish_sweep = True
                sweep_reasons.append(f"OSL Sweep: Swept PWL ({pwl:.2f})")
            if not np.isnan(pwh) and last_high > pwh and last_close < pwh:
                bearish_sweep = True
                sweep_reasons.append(f"OSL Sweep: Swept PWH ({pwh:.2f})")
                
            # ISL sweeps (shorter term)
            if last_low < pcl and last_close > pcl:
                bullish_sweep = True
                sweep_reasons.append(f"ISL Sweep: Swept PCL ({pcl:.2f})")
            if last_high > pch and last_close < pch:
                bearish_sweep = True
                sweep_reasons.append(f"ISL Sweep: Swept PCH ({pch:.2f})")
                
            if swing_lows:
                recent_sl = swing_lows[-1]
                if last_low < recent_sl and last_close > recent_sl:
                    bullish_sweep = True
                    sweep_reasons.append(f"Swing Low Sweep ({recent_sl:.2f})")
            if swing_highs:
                recent_sh = swing_highs[-1]
                if last_high > recent_sh and last_close < recent_sh:
                    bearish_sweep = True
                    sweep_reasons.append(f"Swing High Sweep ({recent_sh:.2f})")

            # Candlestick Confirmation
            pa_pattern, pa_strength = cls.detect_candlestick_reversal(calc_df)
            
            # 3. Confluence Scoring
            buy_score = 0
            sell_score = 0
            buy_reasons = []
            sell_reasons = []
            
            # --- BULLISH CONFLUENCE ---
            # 1. Sweep trigger (Max 35 points)
            if bullish_sweep:
                points = 35
                buy_score += points
                buy_reasons.append(f"Bullish Liquidity Sweep ({', '.join(sweep_reasons)}): +{points}pts")
                
            # 2. Reversal Candlestick trigger (Max 25 points)
            if pa_pattern == "BULLISH_REVERSAL":
                points = int(25 * pa_strength)
                buy_score += points
                buy_reasons.append(f"Candlestick Confirmation ({pa_pattern}): +{points}pts")
                
            # 3. Level Touch (Max 15 points)
            nearest_support = None
            for s in reversed(supports):
                if s <= current_price:
                    nearest_support = s
                    break
            if nearest_support:
                dist = abs(current_price - nearest_support)
                if dist <= 0.25 * atr:
                    points = int(max(0, 15 * (1.0 - dist / (0.25 * atr))))
                    buy_score += points
                    buy_reasons.append(f"Near Support Level ({nearest_support:.2f}): +{points}pts")
                    
            # 4. Bullish OB / FVG Mitigation (Max 15 points)
            active_bull_ob = None
            for ob in bullish_obs:
                if ob['bottom'] - 0.1*atr <= current_price <= ob['top'] + 0.1*atr:
                    active_bull_ob = ob
                    buy_score += 15
                    buy_reasons.append(f"Bullish Order Block ({ob['bottom']:.2f}-{ob['top']:.2f}): +15pts")
                    break
            
            # Check last 3 candles for bullish FVG touch
            for idx in range(-1, -4, -1):
                if idx >= -len(calc_df):
                    row = calc_df.iloc[idx]
                    if row.get('fvg_type') == 1 and last_low <= row.get('fvg_top'):
                        buy_score += 10
                        buy_reasons.append("Bullish FVG Mitigation (First Line of Defense): +10pts")
                        break
                        
            # 5. Fib Pullback (Max 15 points)
            if fib_786 <= current_price <= fib_50:
                buy_score += 15
                buy_reasons.append("Fib Golden Zone (50%-78.6%): +15pts")
                
            # 6. Volume Profile VAL/POC (Max 10 points)
            if val > 0 and abs(current_price - val) <= 0.2 * atr:
                buy_score += 10
                buy_reasons.append(f"Near Vol Profile VAL ({val:.2f}): +10pts")
            elif poc > 0 and abs(current_price - poc) <= 0.15 * atr:
                buy_score += 8
                buy_reasons.append(f"Near Vol Profile POC ({poc:.2f}): +8pts")
                
            # 7. Structure / MSS / Bias (Max 15 points)
            recent_mss_signal = 0
            for idx in range(-1, -6, -1):
                if idx >= -len(calc_df):
                    if calc_df.iloc[idx].get('mss_signal') == 1:
                        recent_mss_signal = 1
                        break
            if recent_mss_signal == 1:
                buy_score += 15
                buy_reasons.append("Bullish Market Structure Shift (MSS/CHoCH): +15pts")
            elif htf_bias == 1:
                buy_score += 10
                buy_reasons.append("Bullish HTF Bias aligned: +10pts")
            elif htf_bias == -1:
                buy_score -= 25
                buy_reasons.append("Bearish HTF Bias conflict: -25pts")
                
            # 8. Volume Pressure & Expansion (Max 15 points)
            if volume_cache:
                buy_press = volume_cache.get('buy_pressure', 50.0)
                rvol = volume_cache.get('rvol', 1.0)
                if buy_press > 53.0:
                    points = int((buy_press - 50.0) * 1.5)
                    buy_score += points
                    buy_reasons.append(f"Dominant Buy Volume ({buy_press:.1f}%): +{points}pts")
                if rvol > 1.2:
                    buy_score += 5
                    buy_reasons.append(f"Volume Expansion (RVOL={rvol:.2f}): +5pts")
                    
            # 9. Sentiment (Max 15 points)
            if sentiment_cache:
                trading_mode = settings_manager.get("trading_mode", "intraday").lower()
                if trading_mode == "scalping":
                    sent_tf1 = sentiment_cache.get('m1', 0.0)
                    sent_tf2 = sentiment_cache.get('m5', 0.0)
                    sent_tf3 = sentiment_cache.get('h1', 0.0)
                    tf1_name, tf2_name, tf3_name = 'M1', 'M5', 'H1'
                elif trading_mode == "swing":
                    sent_tf1 = sentiment_cache.get('m15', 0.0)
                    sent_tf2 = sentiment_cache.get('h1', 0.0)
                    sent_tf3 = sentiment_cache.get('d1', 0.0)
                    tf1_name, tf2_name, tf3_name = 'M15', 'H1', 'D1'
                else:
                    sent_tf1 = sentiment_cache.get('m5', 0.0)
                    sent_tf2 = sentiment_cache.get('m15', 0.0)
                    sent_tf3 = sentiment_cache.get('h1', 0.0)
                    tf1_name, tf2_name, tf3_name = 'M5', 'M15', 'H1'
                
                avg_sent = (sent_tf1 + sent_tf2 + sent_tf3) / 3.0
                if avg_sent > 0.15:
                    buy_score += 15
                    buy_reasons.append(f"Bullish Multitimeframe Sentiment ({tf1_name}/{tf2_name}/{tf3_name} avg: {avg_sent:.2f}): +15pts")
                elif avg_sent < -0.15:
                    buy_score -= 15
                    buy_reasons.append(f"Bearish Sentiment conflict: -15pts")
            
            # --- BEARISH CONFLUENCE ---
            # 1. Sweep trigger (Max 35 points)
            if bearish_sweep:
                points = 35
                sell_score += points
                sell_reasons.append(f"Bearish Liquidity Sweep ({', '.join(sweep_reasons)}): +{points}pts")
                
            # 2. Reversal Candlestick trigger (Max 25 points)
            if pa_pattern == "BEARISH_REVERSAL":
                points = int(25 * pa_strength)
                sell_score += points
                sell_reasons.append(f"Candlestick Confirmation ({pa_pattern}): +{points}pts")
                
            # 3. Level Touch (Max 15 points)
            nearest_resistance = None
            for r in resistances:
                if r >= current_price:
                    nearest_resistance = r
                    break
            if nearest_resistance:
                dist = abs(current_price - nearest_resistance)
                if dist <= 0.25 * atr:
                    points = int(max(0, 15 * (1.0 - dist / (0.25 * atr))))
                    sell_score += points
                    sell_reasons.append(f"Near Resistance Level ({nearest_resistance:.2f}): +{points}pts")
                    
            # 4. Bearish OB / FVG Mitigation (Max 15 points)
            active_bear_ob = None
            for ob in bearish_obs:
                if ob['bottom'] - 0.1*atr <= current_price <= ob['top'] + 0.1*atr:
                    active_bear_ob = ob
                    sell_score += 15
                    sell_reasons.append(f"Bearish Order Block ({ob['bottom']:.2f}-{ob['top']:.2f}): +15pts")
                    break
            
            # Check last 3 candles for bearish FVG touch
            for idx in range(-1, -4, -1):
                if idx >= -len(calc_df):
                    row = calc_df.iloc[idx]
                    if row.get('fvg_type') == -1 and last_high >= row.get('fvg_bottom'):
                        sell_score += 10
                        sell_reasons.append("Bearish FVG Mitigation (First Line of Defense): +10pts")
                        break
                        
            # 5. Fib Pullback (Max 15 points)
            if fib_50 <= current_price <= fib_786:
                sell_score += 15
                sell_reasons.append("Fib Golden Zone (50%-78.6%): +15pts")
                
            # 6. Volume Profile VAH/POC (Max 10 points)
            if vah > 0 and abs(current_price - vah) <= 0.2 * atr:
                sell_score += 10
                sell_reasons.append(f"Near Vol Profile VAH ({vah:.2f}): +10pts")
            elif poc > 0 and abs(current_price - poc) <= 0.15 * atr:
                sell_score += 8
                sell_reasons.append(f"Near Vol Profile POC ({poc:.2f}): +8pts")
                
            # 7. Structure / MSS / Bias (Max 15 points)
            recent_bear_mss = 0
            for idx in range(-1, -6, -1):
                if idx >= -len(calc_df):
                    if calc_df.iloc[idx].get('mss_signal') == -1:
                        recent_bear_mss = 1
                        break
            if recent_bear_mss == 1:
                sell_score += 15
                sell_reasons.append("Bearish Market Structure Shift (MSS/CHoCH): +15pts")
            elif htf_bias == -1:
                sell_score += 10
                sell_reasons.append("Bearish HTF Bias aligned: +10pts")
            elif htf_bias == 1:
                sell_score -= 25
                sell_reasons.append("Bullish HTF Bias conflict: -25pts")
                
            # 8. Volume Pressure & Expansion (Max 15 points)
            if volume_cache:
                sell_press = volume_cache.get('sell_pressure', 50.0)
                rvol = volume_cache.get('rvol', 1.0)
                if sell_press > 53.0:
                    points = int((sell_press - 50.0) * 1.5)
                    sell_score += points
                    sell_reasons.append(f"Dominant Sell Volume ({sell_press:.1f}%): +{points}pts")
                if rvol > 1.2:
                    sell_score += 5
                    sell_reasons.append(f"Volume Expansion (RVOL={rvol:.2f}): +5pts")
                    
            # 9. Sentiment (Max 15 points)
            if sentiment_cache:
                trading_mode = settings_manager.get("trading_mode", "intraday").lower()
                if trading_mode == "scalping":
                    sent_tf1 = sentiment_cache.get('m1', 0.0)
                    sent_tf2 = sentiment_cache.get('m5', 0.0)
                    sent_tf3 = sentiment_cache.get('h1', 0.0)
                    tf1_name, tf2_name, tf3_name = 'M1', 'M5', 'H1'
                elif trading_mode == "swing":
                    sent_tf1 = sentiment_cache.get('m15', 0.0)
                    sent_tf2 = sentiment_cache.get('h1', 0.0)
                    sent_tf3 = sentiment_cache.get('d1', 0.0)
                    tf1_name, tf2_name, tf3_name = 'M15', 'H1', 'D1'
                else:
                    sent_tf1 = sentiment_cache.get('m5', 0.0)
                    sent_tf2 = sentiment_cache.get('m15', 0.0)
                    sent_tf3 = sentiment_cache.get('h1', 0.0)
                    tf1_name, tf2_name, tf3_name = 'M5', 'M15', 'H1'
                
                avg_sent = (sent_tf1 + sent_tf2 + sent_tf3) / 3.0
                if avg_sent < -0.15:
                    sell_score += 15
                    sell_reasons.append(f"Bearish Multitimeframe Sentiment ({tf1_name}/{tf2_name}/{tf3_name} avg: {avg_sent:.2f}): +15pts")
                elif avg_sent > 0.15:
                    sell_score -= 15
                    sell_reasons.append(f"Bullish Sentiment conflict: -15pts")

            # 4. Action and Invalidation Levels Determination
            action = None
            sl_price = 0.0
            tp_price = 0.0
            
            # Entry Threshold: 55 points
            entry_threshold = 55
            
            # Calculate swing size
            swing_range = recent_high - recent_low
            large_swing = swing_range >= 2.5 * atr
            
            metadata = {
                "regime": regime,
                "buy_score": buy_score,
                "sell_score": sell_score,
                "buy_reasons": buy_reasons,
                "sell_reasons": sell_reasons,
                "supports": supports[-3:],
                "resistances": resistances[-3:],
                "order_blocks": {
                    "bullish": bullish_obs,
                    "bearish": bearish_obs
                },
                "fib_50": fib_50,
                "fib_618": fib_618,
                "fib_786": fib_786,
                "poc": poc,
                "val": val,
                "vah": vah,
                "swing_range": swing_range,
                "large_swing": large_swing
            }
            
            if buy_score >= entry_threshold and buy_score > sell_score:
                action = "BUY"
                support_level = last_low if bullish_sweep else (nearest_support if nearest_support else (active_bull_ob['bottom'] if active_bull_ob else recent_low))
                sl_price = support_level - (0.2 * atr)
                sl_price = min(sl_price, current_price - (1.5 * atr))
                
                tp_price = recent_high
                risk = current_price - sl_price
                reward = tp_price - current_price
                if risk > 0 and reward / risk < 1.5:
                    tp_price = current_price + 1.5 * risk
                    
            elif sell_score >= entry_threshold and sell_score > buy_score:
                action = "SELL"
                resistance_level = last_high if bearish_sweep else (nearest_resistance if nearest_resistance else (active_bear_ob['top'] if active_bear_ob else recent_high))
                sl_price = resistance_level + (0.2 * atr)
                sl_price = max(sl_price, current_price + (1.5 * atr))
                
                tp_price = recent_low
                risk = sl_price - current_price
                reward = current_price - tp_price
                if risk > 0 and reward / risk < 1.5:
                    tp_price = current_price - 1.5 * risk
                    
            # Premium / Discount Location Filter
            if action == "BUY" and current_price > fib_50:
                cls.logger.info(f"🚫 BUY trade blocked: price ({current_price:.2f}) is in Premium zone (above 50% Fib: {fib_50:.2f})")
                action = None
            elif action == "SELL" and current_price < fib_50:
                cls.logger.info(f"🚫 SELL trade blocked: price ({current_price:.2f}) is in Discount zone (below 50% Fib: {fib_50:.2f})")
                action = None

            if action:
                sl_price, tp_price = clamp_m1_trade_levels(action, current_price, sl_price, tp_price)
                cls.logger.info(f"📊 M1 Price Action Confluence triggered {action} | Score: {max(buy_score, sell_score)}/100")
                cls.logger.info(f"   Reasons: {buy_reasons if action == 'BUY' else sell_reasons}")
                cls.logger.info(f"   Levels: SL={sl_price:.2f}, TP={tp_price:.2f} (Price={current_price:.2f})")

            return action, regime, sl_price, tp_price, metadata

        except Exception as e:
            cls.logger.error(f"Error evaluating Price Action strategy: {e}")
            import traceback
            traceback.print_exc()
            return None, "sideway", 0.0, 0.0, {}
