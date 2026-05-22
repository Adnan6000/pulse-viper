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
        atr = tr.rolling(window=period).mean()
        return atr.bfill()

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
        
        # 2. Identify STH/STL and ITH/ITL Swing Points
        is_sth = np.zeros(n, dtype=bool)
        is_stl = np.zeros(n, dtype=bool)
        is_ith = np.zeros(n, dtype=bool)
        is_itl = np.zeros(n, dtype=bool)
        
        is_swing_high = df['is_swing_high'].values
        is_swing_low = df['is_swing_low'].values
        
        swing_high_indices = np.where(is_swing_high)[0]
        swing_low_indices = np.where(is_swing_low)[0]
        
        # Classify STH
        for idx in swing_high_indices:
            has_bearish_fvg = False
            for forward in range(1, 5):
                if idx + forward < n:
                    if fvg_types[idx + forward] == -1:
                        has_bearish_fvg = True
                        break
            if has_bearish_fvg:
                is_sth[idx] = True
                
        # Classify STL
        for idx in swing_low_indices:
            has_bullish_fvg = False
            for forward in range(1, 5):
                if idx + forward < n:
                    if fvg_types[idx + forward] == 1:
                        has_bullish_fvg = True
                        break
            if has_bullish_fvg:
                is_stl[idx] = True
                
        # Classify ITH
        for k in range(1, len(swing_high_indices) - 1):
            prev_idx = swing_high_indices[k - 1]
            curr_idx = swing_high_indices[k]
            next_idx = swing_high_indices[k + 1]
            if highs[curr_idx] > highs[prev_idx] and highs[curr_idx] > highs[next_idx]:
                is_ith[curr_idx] = True
                
        # Classify ITL
        for k in range(1, len(swing_low_indices) - 1):
            prev_idx = swing_low_indices[k - 1]
            curr_idx = swing_low_indices[k]
            next_idx = swing_low_indices[k + 1]
            if lows[curr_idx] < lows[prev_idx] and lows[curr_idx] < lows[next_idx]:
                is_itl[curr_idx] = True
                
        df['is_sth'] = is_sth
        df['is_stl'] = is_stl
        df['is_ith'] = is_ith
        df['is_itl'] = is_itl
        
        # 3 & 4. Liquidity Sweeps and Market Structure Shifts (MSS)
        liq_sweep_types = np.zeros(n, dtype=int)
        liq_sweep_levels = np.full(n, np.nan)
        mss_signals = np.zeros(n, dtype=int)
        active_biases = np.zeros(n, dtype=int)
        supports = np.full(n, np.nan)
        resistances = np.full(n, np.nan)
        
        current_bias = 0
        
        stls_before_i = []
        itls_before_i = []
        sths_before_i = []
        iths_before_i = []
        
        start_idx = window * 3
        for j in range(start_idx):
            if is_stl[j]:
                stls_before_i.append(lows[j])
            if is_itl[j]:
                itls_before_i.append(lows[j])
            if is_sth[j]:
                sths_before_i.append(highs[j])
            if is_ith[j]:
                iths_before_i.append(highs[j])
                
        for i in range(start_idx, n):
            prev_j = i - 1
            if is_stl[prev_j]:
                stls_before_i.append(lows[prev_j])
            if is_itl[prev_j]:
                itls_before_i.append(lows[prev_j])
            if is_sth[prev_j]:
                sths_before_i.append(highs[prev_j])
            if is_ith[prev_j]:
                iths_before_i.append(highs[prev_j])
                
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
                if closes[i - 1] <= latest_resistance:
                    mss_signals[i] = 1
                    current_bias = 1
            elif not np.isnan(latest_support) and closes[i] < latest_support:
                if closes[i - 1] >= latest_support:
                    mss_signals[i] = -1
                    current_bias = -1
                    
            active_biases[i] = current_bias
            supports[i] = latest_support
            resistances[i] = latest_resistance
            
        df['liq_sweep_type'] = liq_sweep_types
        df['liq_sweep_level'] = liq_sweep_levels
        df['mss_signal'] = mss_signals
        df['active_bias'] = active_biases
        df['support'] = supports
        df['resistance'] = resistances
        
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
        
        df['volatility'] = df['close'].pct_change().rolling(window=20).std().bfill().fillna(0.0)
        df['atr_pct'] = (df['atr'] / df['close']).fillna(0.0)
        
        return df
