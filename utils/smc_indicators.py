# utils/smc_indicators.py
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional

class SMCIndicators:
    @staticmethod
    def detect_swing_points(df: pd.DataFrame, window: int = 2) -> pd.DataFrame:
        """
        Detect Swing Highs and Swing Lows.
        A candle is a Swing High if its high is higher than the highs of 'window' candles to its left and right.
        A candle is a Swing Low if its low is lower than the lows of 'window' candles to its left and right.
        """
        df = df.copy()
        n = len(df)
        is_swing_high = np.zeros(n, dtype=bool)
        is_swing_low = np.zeros(n, dtype=bool)
        
        highs = df['high'].values
        lows = df['low'].values
        
        for i in range(window, n - window):
            # Check swing high
            is_sh = True
            for w in range(1, window + 1):
                if highs[i] < highs[i - w] or highs[i] < highs[i + w]:
                    is_sh = False
                    break
            is_swing_high[i] = is_sh
            
            # Check swing low
            is_sl = True
            for w in range(1, window + 1):
                if lows[i] > lows[i - w] or lows[i] > lows[i + w]:
                    is_sl = False
                    break
            is_swing_low[i] = is_sl
            
        df['is_swing_high'] = is_swing_high
        df['is_swing_low'] = is_swing_low
        return df

    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range (ATR)"""
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period, min_periods=1).mean()
        return atr.ffill().fillna(0.0)

    @classmethod
    def compute_smc_features(cls, df: pd.DataFrame, window: int = 2, atr_period: int = 14) -> pd.DataFrame:
        """
        Comprehensive SMC/ICT indicator calculation on a historical candle dataset.
        Identifies Swing Points (STH/STL, ITH/ITL), FVGs (PFVG, RFVG, BAG), Sweeps, and MSS.
        Optimized version with O(N) complexity and vector/array-backed loops.
        """
        # Ensure we have swing points and ATR
        df = cls.detect_swing_points(df, window=window)
        atr = cls.calculate_atr(df, period=atr_period)
        df['atr'] = atr
        
        n = len(df)
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        opens = df['open'].values
        atr_vals = df['atr'].values
        
        # 1. Detect and Classify Fair Value Gaps (FVG)
        fvg_types = np.zeros(n, dtype=int)
        fvg_tops = np.full(n, np.nan)
        fvg_bottoms = np.full(n, np.nan)
        fvg_classes = np.array(['none'] * n, dtype=object)
        
        for i in range(2, n):
            atr_val = atr_vals[i]
            # Bullish FVG: Candle i-2 High is below Candle i Low
            if lows[i] > highs[i - 2]:
                fvg_types[i] = 1
                fvg_tops[i] = lows[i]
                fvg_bottoms[i] = highs[i - 2]
                
                range_i = highs[i] - lows[i]
                body_i = abs(closes[i] - opens[i])
                upper_wick = highs[i] - max(opens[i], closes[i])
                
                if range_i < 1.0 * atr_val and body_i < 0.3 * range_i:
                    fvg_classes[i] = 'pfvg'
                elif range_i > 0 and upper_wick / range_i > 0.5:
                    fvg_classes[i] = 'rfvg'
                elif range_i > 1.2 * atr_val:
                    fvg_classes[i] = 'bag'
                else:
                    fvg_classes[i] = 'pfvg'
                    
            # Bearish FVG: Candle i-2 Low is above Candle i High
            elif highs[i] < lows[i - 2]:
                fvg_types[i] = -1
                fvg_tops[i] = lows[i - 2]
                fvg_bottoms[i] = highs[i]
                
                range_i = highs[i] - lows[i]
                body_i = abs(closes[i] - opens[i])
                lower_wick = min(opens[i], closes[i]) - lows[i]
                
                if range_i < 1.0 * atr_val and body_i < 0.3 * range_i:
                    fvg_classes[i] = 'pfvg'
                elif range_i > 0 and lower_wick / range_i > 0.5:
                    fvg_classes[i] = 'rfvg'
                elif range_i > 1.2 * atr_val:
                    fvg_classes[i] = 'bag'
                else:
                    fvg_classes[i] = 'pfvg'
                    
        df['fvg_type'] = fvg_types
        df['fvg_top'] = fvg_tops
        df['fvg_bottom'] = fvg_bottoms
        df['fvg_class'] = fvg_classes
        
        # 2. Identify STH/STL and ITH/ITL Swing Points (Causal)
        is_sth = np.zeros(n, dtype=bool)
        is_stl = np.zeros(n, dtype=bool)
        is_ith = np.zeros(n, dtype=bool)
        is_itl = np.zeros(n, dtype=bool)
        
        is_swing_high = df['is_swing_high'].values
        is_swing_low = df['is_swing_low'].values
        
        # 3 & 4. Liquidity Sweeps and Market Structure Shifts (MSS)
        liq_sweep_types = np.zeros(n, dtype=int)
        liq_sweep_levels = np.full(n, np.nan)
        mss_signals = np.zeros(n, dtype=int)
        active_biases = np.zeros(n, dtype=int)
        supports = np.full(n, np.nan)
        resistances = np.full(n, np.nan)
        
        # Advanced Price Action tracking columns
        ob_reaction_signals = np.zeros(n, dtype=int)
        ob_tops = np.full(n, np.nan)
        ob_bottoms = np.full(n, np.nan)
        ob_directions = np.array(['none'] * n, dtype=object)
        sr_reaction_signals = np.zeros(n, dtype=int)
        retest_pullback_signals = np.zeros(n, dtype=int)
        trend_shift_signals = np.zeros(n, dtype=int)
        
        # Order block tracking lists
        active_bull_obs = []  # list of (top, bottom, creation_idx)
        active_bear_obs = []  # list of (top, bottom, creation_idx)
        
        # Broken levels lists
        broken_resistances = []  # list of (level, break_idx)
        broken_supports = []     # list of (level, break_idx)
        
        current_bias = 0
        
        confirmed_shs = []
        confirmed_sls = []
        
        stls_before_i = []
        itls_before_i = []
        sths_before_i = []
        iths_before_i = []
        
        for i in range(n):
            # 1. Update confirmation of swing points at conf_idx = i - window
            conf_idx = i - window
            if conf_idx >= 0:
                if is_swing_high[conf_idx]:
                    confirmed_shs.append(conf_idx)
                    # Check if the previous confirmed swing high is an ITH
                    if len(confirmed_shs) >= 3:
                        p_idx = confirmed_shs[-3]
                        c_idx = confirmed_shs[-2]
                        n_idx = confirmed_shs[-1]
                        if highs[c_idx] > highs[p_idx] and highs[c_idx] > highs[n_idx]:
                            is_ith[c_idx] = True
                            iths_before_i.append(highs[c_idx])
                            
                if is_swing_low[conf_idx]:
                    confirmed_sls.append(conf_idx)
                    # Check if the previous confirmed swing low is an ITL
                    if len(confirmed_sls) >= 3:
                        p_idx = confirmed_sls[-3]
                        c_idx = confirmed_sls[-2]
                        n_idx = confirmed_sls[-1]
                        if lows[c_idx] < lows[p_idx] and lows[c_idx] < lows[n_idx]:
                            is_itl[c_idx] = True
                            itls_before_i.append(lows[c_idx])
            
            # 2. Check if any past swing point is now confirmed as STH/STL by an FVG closing at index i
            for idx in confirmed_shs:
                if not is_sth[idx] and idx < i <= idx + 4:
                    if fvg_types[i] == -1:
                        is_sth[idx] = True
                        sths_before_i.append(highs[idx])
                        
            for idx in confirmed_sls:
                if not is_stl[idx] and idx < i <= idx + 4:
                    if fvg_types[i] == 1:
                        is_stl[idx] = True
                        stls_before_i.append(lows[idx])
            
            latest_support = itls_before_i[-1] if itls_before_i else (stls_before_i[-1] if stls_before_i else np.nan)
            latest_resistance = iths_before_i[-1] if iths_before_i else (sths_before_i[-1] if sths_before_i else np.nan)
            
            # Liquidity Sweep Check
            if not np.isnan(latest_support):
                if lows[i] < latest_support and closes[i] > latest_support:
                    liq_sweep_types[i] = 1
                    liq_sweep_levels[i] = latest_support
                    
            if not np.isnan(latest_resistance):
                if highs[i] > latest_resistance and closes[i] < latest_resistance:
                    liq_sweep_types[i] = -1
                    liq_sweep_levels[i] = latest_resistance
                    
            # Market Structure Shift (MSS) Check
            if not np.isnan(latest_resistance) and closes[i] > latest_resistance:
                if i > 0 and closes[i - 1] <= latest_resistance:
                    mss_signals[i] = 1
                    current_bias = 1
            elif not np.isnan(latest_support) and closes[i] < latest_support:
                if i > 0 and closes[i - 1] >= latest_support:
                    mss_signals[i] = -1
                    current_bias = -1
                    
            active_biases[i] = current_bias
            supports[i] = latest_support
            resistances[i] = latest_resistance
            
            # --- Support & Resistance reactions (Bounce check) ---
            atr_val = atr_vals[i]
            if not np.isnan(latest_support):
                if lows[i] <= latest_support + 0.15 * atr_val and closes[i] >= latest_support - 0.05 * atr_val:
                    sr_reaction_signals[i] = 1
            if not np.isnan(latest_resistance):
                if highs[i] >= latest_resistance - 0.15 * atr_val and closes[i] <= latest_resistance + 0.05 * atr_val:
                    sr_reaction_signals[i] = -1
                    
            # --- Broken S/R levels & Break-and-Retest pullbacks ---
            if not np.isnan(latest_resistance) and closes[i] > latest_resistance:
                if i > 0 and closes[i - 1] <= latest_resistance:
                    broken_resistances.append((latest_resistance, i))
            if not np.isnan(latest_support) and closes[i] < latest_support:
                if i > 0 and closes[i - 1] >= latest_support:
                    broken_supports.append((latest_support, i))
                    
            # Retest checks for broken resistance (acts as support now)
            active_br = []
            for br, idx in broken_resistances:
                if i - idx <= 20:
                    if lows[i] <= br + 0.15 * atr_val and closes[i] >= br - 0.1 * atr_val:
                        retest_pullback_signals[i] = 1
                    if closes[i] >= br - 0.2 * atr_val:
                        active_br.append((br, idx))
            broken_resistances = active_br
            
            # Retest checks for broken support (acts as resistance now)
            active_bs = []
            for bs, idx in broken_supports:
                if i - idx <= 20:
                    if highs[i] >= bs - 0.15 * atr_val and closes[i] <= bs + 0.1 * atr_val:
                        retest_pullback_signals[i] = -1
                    if closes[i] <= bs + 0.2 * atr_val:
                        active_bs.append((bs, idx))
            broken_supports = active_bs
            
            # --- Order Block Creation on MSS or FVG ---
            # Bullish OB (Demand Zone) creation
            if mss_signals[i] == 1 or fvg_types[i] == 1:
                ob_high = np.nan
                ob_low = np.nan
                # Find the last down candle before the impulsive move
                for k in range(i - 1, max(-1, i - 10), -1):
                    if closes[k] < opens[k]:
                        ob_high = highs[k]
                        ob_low = lows[k]
                        break
                if not np.isnan(ob_high):
                    active_bull_obs.append((ob_high, ob_low, i))
                    
            # Bearish OB (Supply Zone) creation
            if mss_signals[i] == -1 or fvg_types[i] == -1:
                ob_high = np.nan
                ob_low = np.nan
                # Find the last up candle before the impulsive down move
                for k in range(i - 1, max(-1, i - 10), -1):
                    if closes[k] > opens[k]:
                        ob_high = highs[k]
                        ob_low = lows[k]
                        break
                if not np.isnan(ob_high):
                    active_bear_obs.append((ob_high, ob_low, i))
                    
            # --- Order Block reactions & mitigations ---
            next_bull_obs = []
            ob_reacted_bull = False
            latest_ob_bull = (np.nan, np.nan)
            for top, bottom, idx in active_bull_obs:
                if lows[i] <= top and lows[i] >= bottom:
                    ob_reaction_signals[i] = 1
                    ob_reacted_bull = True
                    latest_ob_bull = (top, bottom)
                if closes[i] >= bottom:
                    next_bull_obs.append((top, bottom, idx))
            active_bull_obs = next_bull_obs
            
            # Bearish OBs reaction
            next_bear_obs = []
            ob_reacted_bear = False
            latest_ob_bear = (np.nan, np.nan)
            for top, bottom, idx in active_bear_obs:
                if highs[i] >= bottom and highs[i] <= top:
                    ob_reaction_signals[i] = -1
                    ob_reacted_bear = True
                    latest_ob_bear = (top, bottom)
                if closes[i] <= top:
                    next_bear_obs.append((top, bottom, idx))
            active_bear_obs = next_bear_obs
            
            # Save active OB bounds
            if ob_reacted_bull:
                ob_tops[i] = latest_ob_bull[0]
                ob_bottoms[i] = latest_ob_bull[1]
                ob_directions[i] = 'bullish'
            elif ob_reacted_bear:
                ob_tops[i] = latest_ob_bear[0]
                ob_bottoms[i] = latest_ob_bear[1]
                ob_directions[i] = 'bearish'
            else:
                if active_bull_obs:
                    ob_tops[i] = active_bull_obs[-1][0]
                    ob_bottoms[i] = active_bull_obs[-1][1]
                    ob_directions[i] = 'bullish'
                elif active_bear_obs:
                    ob_tops[i] = active_bear_obs[-1][0]
                    ob_bottoms[i] = active_bear_obs[-1][1]
                    ob_directions[i] = 'bearish'
                    
            # --- CHoCH / Trend Shift Signals ---
            if mss_signals[i] == 1:
                recent_sweep = False
                for k in range(max(0, i - 10), i + 1):
                    if liq_sweep_types[k] == 1:
                        recent_sweep = True
                        break
                if recent_sweep:
                    trend_shift_signals[i] = 1
            elif mss_signals[i] == -1:
                recent_sweep = False
                for k in range(max(0, i - 10), i + 1):
                    if liq_sweep_types[k] == -1:
                        recent_sweep = True
                        break
                if recent_sweep:
                    trend_shift_signals[i] = -1
            
        df['liq_sweep_type'] = liq_sweep_types
        df['liq_sweep_level'] = liq_sweep_levels
        df['mss_signal'] = mss_signals
        df['active_bias'] = active_biases
        df['support'] = supports
        df['resistance'] = resistances
        df['ob_reaction_signal'] = ob_reaction_signals
        df['ob_top'] = ob_tops
        df['ob_bottom'] = ob_bottoms
        df['ob_direction'] = ob_directions
        df['sr_reaction_signal'] = sr_reaction_signals
        df['retest_pullback_signal'] = retest_pullback_signals
        df['trend_shift_signal'] = trend_shift_signals
        
        # 5. Fair Value Area (FVA) breakout tracking
        fva_tops = np.full(n, np.nan)
        fva_bottoms = np.full(n, np.nan)
        
        last_fva = None
        for i in range(1, n):
            mss = mss_signals[i]
            if mss == 1:
                res_val = resistances[i]
                resistance = res_val if not np.isnan(res_val) else highs[i]
                fva_bottom = resistance
                fva_top = max(closes[i], highs[i])
                last_fva = (fva_bottom, fva_top)
            elif mss == -1:
                sup_val = supports[i]
                support = sup_val if not np.isnan(sup_val) else lows[i]
                fva_bottom = min(closes[i], lows[i])
                fva_top = support
                last_fva = (fva_bottom, fva_top)
                
            if last_fva is not None:
                fva_bottoms[i] = last_fva[0]
                fva_tops[i] = last_fva[1]
                
                # Check mitigation using active bias at index i (fixes lookahead bias)
                if active_biases[i] == 1 and closes[i] < last_fva[0]:
                    last_fva = None
                elif active_biases[i] == -1 and closes[i] > last_fva[1]:
                    last_fva = None
                    
        df['fva_top'] = fva_tops
        df['fva_bottom'] = fva_bottoms
        
        df['volatility'] = df['close'].pct_change().rolling(window=20, min_periods=1).std().ffill().fillna(0.0)
        df['atr_pct'] = (df['atr'] / df['close']).fillna(0.0)
        
        return df
