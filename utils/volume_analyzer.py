# utils/volume_analyzer.py
import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple

class VolumeAnalyzer:
    @staticmethod
    def calculate_rvol(df: pd.DataFrame, period: int = 20) -> pd.Series:
        """
        Calculate Relative Volume (RVOL) which compares the volume of the current candle
        to a rolling SMA of volume.
        RVOL > 1.5 indicates significant volume expansion.
        """
        if 'volume' not in df.columns:
            return pd.Series(1.0, index=df.index)
        
        volume_sma = df['volume'].rolling(window=period).mean()
        # Avoid division by zero
        volume_sma_safe = np.where(volume_sma == 0, 1e-9, volume_sma)
        rvol = df['volume'] / volume_sma_safe
        return rvol.ffill().fillna(1.0)

    @staticmethod
    def calculate_rvol_latest(df: pd.DataFrame, period: int = 20) -> float:
        """
        Ultra-optimized version of RVOL calculation returning only the latest value.
        Bypasses rolling series allocations and computes directly using numpy slices.
        """
        if 'volume' not in df.columns or len(df) == 0:
            return 1.0
        v = df['volume'].values
        if len(v) < period:
            return 1.0
        mean_vol = np.mean(v[-period:])
        if mean_vol == 0:
            return 1.0
        return float(v[-1] / mean_vol)

    @staticmethod
    def calculate_buying_selling_pressure(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """
        Decompose candle volume into Buying and Selling pressure based on the candle close position relative to its range.
        Formula:
          BuyingVolume = Volume * (Close - Low) / (High - Low)
          SellingVolume = Volume * (High - Close) / (High - Low)
        """
        if 'volume' not in df.columns or len(df) == 0:
            empty = pd.Series(0.0, index=df.index)
            return empty, empty

        high = df['high'].values
        low = df['low'].values
        close = df['close'].values
        volume = df['volume'].values
        
        denom = high - low
        # Avoid division by zero
        denom_safe = np.where(denom == 0, 1e-9, denom)
        
        buying_ratio = (close - low) / denom_safe
        selling_ratio = (high - close) / denom_safe
        
        # If High == Low, split the volume 50/50
        buying_ratio = np.where(denom == 0, 0.5, buying_ratio)
        selling_ratio = np.where(denom == 0, 0.5, selling_ratio)
        
        buying_volume = volume * buying_ratio
        selling_volume = volume * selling_ratio
        
        return pd.Series(buying_volume, index=df.index), pd.Series(selling_volume, index=df.index)

    @staticmethod
    def calculate_buying_selling_pressure_latest(df: pd.DataFrame) -> Tuple[float, float]:
        """
        Ultra-optimized version of buying/selling pressure returning only the latest value.
        Bypasses pandas series allocations and computes directly on scalar values.
        """
        if 'volume' not in df.columns or len(df) == 0:
            return 0.0, 0.0
        high = float(df['high'].values[-1])
        low = float(df['low'].values[-1])
        close = float(df['close'].values[-1])
        volume = float(df['volume'].values[-1])
        denom = high - low
        if denom == 0:
            return volume * 0.5, volume * 0.5
        return volume * (close - low) / denom, volume * (high - close) / denom

    @staticmethod
    def calculate_volume_profile(df: pd.DataFrame, lookback: int = 300, bins: int = 30) -> Dict[str, Any]:
        """
        Optimized calculation of the Volume Profile (Volume at Price histogram) using numpy views.
        Avoids duplicate dataframe copies via df.tail().
        """
        n = len(df)
        if n == 0:
            return {
                "poc_price": 0.0,
                "val_price": 0.0,
                "vah_price": 0.0,
                "bin_edges": [],
                "bin_volumes": [],
                "buy_volumes": [],
                "sell_volumes": [],
                "overall_buy_pct": 50.0,
                "poc_buy_pct": 50.0,
                "market_control": "NEUTRAL",
                "min_price": 0.0,
                "max_price": 0.0
            }

        start_idx = max(0, n - lookback)
        highs = df['high'].values[start_idx:]
        lows = df['low'].values[start_idx:]
        closes = df['close'].values[start_idx:]
        volumes = df['volume'].values[start_idx:]
        
        min_price = lows.min()
        max_price = highs.max()
        
        if max_price == min_price:
            max_price += 0.01  # Avoid division by zero
            
        bin_edges = np.linspace(min_price, max_price, bins + 1)
        
        # Vectorized calculation of volume distribution using numpy arrays directly
        h_arr = highs[:, np.newaxis]
        l_arr = lows[:, np.newaxis]
        v_arr = volumes[:, np.newaxis]
        c_arr = closes[:, np.newaxis]
        
        be_low = bin_edges[:-1][np.newaxis, :]
        be_high = bin_edges[1:][np.newaxis, :]
        
        # Calculate overlaps for all rows and bins
        overlaps = np.maximum(0, np.minimum(h_arr, be_high) - np.maximum(l_arr, be_low))
        
        # Sum overlaps per row
        total_overlap = overlaps.sum(axis=1, keepdims=True)
        total_overlap_safe = np.where(total_overlap == 0, 1e-9, total_overlap)
        
        # Distribute volume where high > low and total_overlap > 0
        valid_overlap = (h_arr > l_arr) & (total_overlap > 0)
        distributed_vol = np.where(valid_overlap, v_arr * overlaps / total_overlap_safe, 0.0)
        
        # Fallback logic for rows that don't overlap properly
        fallback_val = np.where(h_arr > l_arr, c_arr, l_arr)
        fallback_bins = np.clip(np.digitize(fallback_val, bin_edges) - 1, 0, bins - 1)
        
        # Mask fallback bins for rows that were not distributed via overlap
        fallback_mask = (np.arange(bins)[np.newaxis, :] == fallback_bins) & (~valid_overlap)
        
        # Sum the distributed and fallback volumes
        bin_volumes_matrix = distributed_vol + np.where(fallback_mask, v_arr, 0.0)
        bin_volumes = bin_volumes_matrix.sum(axis=0)
        
        # Calculate Buying and Selling Volume decomposition per bin
        denom = highs - lows
        denom_safe = np.where(denom == 0, 1e-9, denom)
        buy_ratio_row = np.clip((closes - lows) / denom_safe, 0.0, 1.0)[:, np.newaxis]
        sell_ratio_row = 1.0 - buy_ratio_row
        
        buy_volumes_matrix = bin_volumes_matrix * buy_ratio_row
        sell_volumes_matrix = bin_volumes_matrix * sell_ratio_row
        
        buy_volumes = buy_volumes_matrix.sum(axis=0)
        sell_volumes = sell_volumes_matrix.sum(axis=0)
        
        poc_idx = np.argmax(bin_volumes)
        poc_price = (bin_edges[poc_idx] + bin_edges[poc_idx + 1]) / 2.0
        
        # Calculate 70% Value Area Low (VAL) and Value Area High (VAH)
        total_vol = bin_volumes.sum()
        target_vol = total_vol * 0.70
        low_idx = poc_idx
        high_idx = poc_idx
        accumulated_vol = float(bin_volumes[poc_idx]) if len(bin_volumes) > 0 else 0.0
        
        while accumulated_vol < target_vol and (low_idx > 0 or high_idx < len(bin_volumes) - 1):
            next_low_vol = float(bin_volumes[low_idx - 1]) if low_idx > 0 else -1.0
            next_high_vol = float(bin_volumes[high_idx + 1]) if high_idx < len(bin_volumes) - 1 else -1.0
            
            if next_high_vol >= next_low_vol and high_idx < len(bin_volumes) - 1:
                high_idx += 1
                accumulated_vol += next_high_vol
            elif low_idx > 0:
                low_idx -= 1
                accumulated_vol += next_low_vol
            else:
                break
                
        val_price = (bin_edges[low_idx] + bin_edges[low_idx + 1]) / 2.0
        vah_price = (bin_edges[high_idx] + bin_edges[high_idx + 1]) / 2.0

        total_buy_vol = buy_volumes.sum()
        overall_buy_pct = float(total_buy_vol / (total_vol + 1e-9) * 100.0)
        
        # More aggressive exponential weighting for recent candles to measure active market control accurately.
        # The previous `linspace` was too slow; this new `np.logspace` focuses heavily on the last few bars.
        n_bars = len(closes)
        if n_bars > 1:
            weights = np.logspace(start=-2, stop=0, num=n_bars, base=10.0)
        else:
            weights = np.array([1.0])
        weighted_buy = (buy_ratio_row.squeeze() * volumes * weights).sum()
        weighted_total = (volumes * weights).sum()
        recent_buy_pct = float(weighted_buy / (weighted_total + 1e-9) * 100.0)
        
        # Recent momentum direction check (last 15 bars)
        momentum_up = (closes[-1] > closes[max(0, n_bars - 15)])
        
        # Combine recent buy ratio & price momentum for accurate market control
        if recent_buy_pct >= 50.0 or (momentum_up and recent_buy_pct >= 45.0):
            market_control = "BUYERS"
        else:
            market_control = "SELLERS"

        poc_buy_vol = float(buy_volumes[poc_idx]) if len(buy_volumes) > poc_idx else 0.0
        poc_sell_vol = float(sell_volumes[poc_idx]) if len(sell_volumes) > poc_idx else 0.0
        poc_tot = poc_buy_vol + poc_sell_vol
        poc_buy_pct = poc_buy_vol / (poc_tot + 1e-9) * 100.0

        return {
            "poc_price": float(poc_price),
            "val_price": float(val_price),
            "vah_price": float(vah_price),
            "bin_edges": bin_edges.tolist(),
            "bin_volumes": bin_volumes.tolist(),
            "buy_volumes": buy_volumes.tolist(),
            "sell_volumes": sell_volumes.tolist(),
            "overall_buy_pct": round(recent_buy_pct, 1),
            "poc_buy_pct": round(poc_buy_pct, 1),
            "market_control": market_control,
            "min_price": float(min_price),
            "max_price": float(max_price)
        }

    @staticmethod
    def detect_vsa_signals(df: pd.DataFrame, atr_series: pd.Series, lookback: int = 5) -> list:
        """
        Detect key VSA patterns on the recent candles.
        Returns a list of dicts with detected signals, e.g. [{"pattern": "SPRING", "index": -2, "direction": 1, "confidence": 0.85}, ...]
        """
        signals = []
        n = len(df)
        if n < lookback + 20:
            return signals

        # We look at the last 'lookback' candles, INCLUDING the current forming candle at -1
        # so that VSA signals are detected in real-time before the candle closes.
        for idx in range(-lookback - 1, 0):
            if idx >= 0 or idx < -n:
                continue
            
            try:
                # Current candle (at index)
                c = df.iloc[idx]
                high = float(c['high'])
                low = float(c['low'])
                close = float(c['close'])
                open_p = float(c['open'])
                raw_v = c['volume'] if 'volume' in c and pd.notna(c['volume']) else (c['tick_volume'] if 'tick_volume' in c else 1.0)
                vol = float(raw_v)
                
                # Candle spread (range)
                spread = high - low
                if spread == 0:
                    spread = 1e-9
                    
                # ATR for scale
                atr = float(atr_series.iloc[idx]) if idx < len(atr_series) else 1.0
                if np.isnan(atr) or atr == 0:
                    atr = 1.0
                
                # Average volume of the last 20 candles before this index
                start_vol_idx = max(0, n + idx - 20)
                end_vol_idx = n + idx
                vol_col = 'volume' if 'volume' in df.columns else 'tick_volume'
                prev_vols = df[vol_col].values[start_vol_idx:end_vol_idx]
                avg_vol = float(np.mean(prev_vols)) if len(prev_vols) > 0 else 1.0
                if avg_vol == 0:
                    avg_vol = 1e-9
                rvol = vol / avg_vol
                
                # Close position in percent (0 = low, 1 = high)
                close_pos = (close - low) / spread
                
                # Bullish or Bearish candle
                is_bullish = close >= open_p
                
                # 1. SPRING (Bullish reversal)
                # Close in top 35%, sweeps low, volume either high or low
                if close_pos >= 0.65 and (rvol > 1.3 or rvol < 0.8):
                    prev_lows = df['low'].values[max(0, n + idx - 5):n + idx]
                    if len(prev_lows) > 0 and low < np.min(prev_lows):
                        signals.append({
                            "pattern": "SPRING",
                            "index": idx,
                            "direction": 1,
                            "confidence": 0.85 if rvol > 1.3 else 0.75,
                            "rvol": rvol,
                            "price": close
                        })
                        continue

                # 2. UPTHRUST (Bearish reversal)
                # Close in bottom 35%, sweeps high, volume high or low
                if close_pos <= 0.35 and (rvol > 1.3 or rvol < 0.8):
                    prev_highs = df['high'].values[max(0, n + idx - 5):n + idx]
                    if len(prev_highs) > 0 and high > np.max(prev_highs):
                        signals.append({
                            "pattern": "UPTHRUST",
                            "index": idx,
                            "direction": -1,
                            "confidence": 0.85 if rvol > 1.3 else 0.75,
                            "rvol": rvol,
                            "price": close
                        })
                        continue

                # 3. STOPPING VOLUME (Bullish reversal)
                # Wide spread down candle, closes off low (top 50%), very high volume
                if not is_bullish and spread > 1.2 * atr and close_pos >= 0.45 and rvol > 1.5:
                    signals.append({
                        "pattern": "STOPPING_VOLUME",
                        "index": idx,
                        "direction": 1,
                        "confidence": 0.80,
                        "rvol": rvol,
                        "price": close
                    })
                    continue

                # 4. NO SUPPLY (Bullish test)
                # Narrow spread down candle, closes in lower half, below average volume
                if not is_bullish and spread < 0.8 * atr and close_pos <= 0.50 and rvol < 0.8:
                    signals.append({
                        "pattern": "NO_SUPPLY",
                        "index": idx,
                        "direction": 1,
                        "confidence": 0.75,
                        "rvol": rvol,
                        "price": close
                    })
                    continue

                # 5. NO DEMAND (Bearish test)
                # Narrow spread up candle, closes in upper half, below average volume
                if is_bullish and spread < 0.8 * atr and close_pos >= 0.50 and rvol < 0.8:
                    signals.append({
                        "pattern": "NO_DEMAND",
                        "index": idx,
                        "direction": -1,
                        "confidence": 0.75,
                        "rvol": rvol,
                        "price": close
                    })
                    continue

                # 6. BUYING CLIMAX (Bearish exhaustion)
                # Wide spread up candle, closes off high (lower 50%), extremely high volume
                if is_bullish and spread > 1.5 * atr and close_pos <= 0.50 and rvol > 2.0:
                    signals.append({
                        "pattern": "BUYING_CLIMAX",
                        "index": idx,
                        "direction": -1,
                        "confidence": 0.80,
                        "rvol": rvol,
                        "price": close
                    })
                    continue

                # 7. SELLING CLIMAX (Bullish exhaustion)
                # Wide spread down candle, closes off low (upper 50%), extremely high volume
                if not is_bullish and spread > 1.5 * atr and close_pos >= 0.50 and rvol > 2.0:
                    signals.append({
                        "pattern": "SELLING_CLIMAX",
                        "index": idx,
                        "direction": 1,
                        "confidence": 0.80,
                        "rvol": rvol,
                        "price": close
                    })
                    continue

                # 8. EFFORT VS RESULT BULLISH (Buying effort met with absorption/demand)
                if rvol >= 1.7 and spread < 0.7 * atr and close_pos >= 0.5:
                    signals.append({
                        "pattern": "EFFORT_VS_RESULT_BULLISH",
                        "index": idx,
                        "direction": 1,
                        "confidence": 0.85,
                        "rvol": rvol,
                        "price": close
                    })
                    continue

                # 9. EFFORT VS RESULT BEARISH (Selling effort met with absorption/supply)
                if rvol >= 1.7 and spread < 0.7 * atr and close_pos <= 0.5:
                    signals.append({
                        "pattern": "EFFORT_VS_RESULT_BEARISH",
                        "index": idx,
                        "direction": -1,
                        "confidence": 0.85,
                        "rvol": rvol,
                        "price": close
                    })
                    continue

                # 10. TEST OF SUPPLY (Sweep low on low volume, closes high)
                if close_pos >= 0.6 and rvol < 0.8:
                    prev_lows = df['low'].values[max(0, n + idx - 5):n + idx]
                    if len(prev_lows) > 0 and low < np.min(prev_lows):
                        signals.append({
                            "pattern": "TEST_OF_SUPPLY",
                            "index": idx,
                            "direction": 1,
                            "confidence": 0.80,
                            "rvol": rvol,
                            "price": close
                        })
                        continue

                # 11. TEST OF DEMAND (Sweep high on low volume, closes low)
                if close_pos <= 0.4 and rvol < 0.8:
                    prev_highs = df['high'].values[max(0, n + idx - 5):n + idx]
                    if len(prev_highs) > 0 and high > np.max(prev_highs):
                        signals.append({
                            "pattern": "TEST_OF_DEMAND",
                            "index": idx,
                            "direction": -1,
                            "confidence": 0.80,
                            "rvol": rvol,
                            "price": close
                        })
                        continue
            except Exception:
                pass
                
        return signals
