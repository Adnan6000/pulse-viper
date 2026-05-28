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
        return rvol.bfill()

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
    def calculate_volume_profile(df: pd.DataFrame, lookback: int = 100, bins: int = 20) -> Dict[str, Any]:
        """
        Optimized calculation of the Volume Profile (Volume at Price histogram) using numpy views.
        Avoids duplicate dataframe copies via df.tail().
        """
        n = len(df)
        if n == 0:
            return {
                "poc_price": 0.0,
                "bin_edges": [],
                "bin_volumes": [],
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
        
        poc_idx = np.argmax(bin_volumes)
        poc_price = (bin_edges[poc_idx] + bin_edges[poc_idx + 1]) / 2.0
        
        return {
            "poc_price": float(poc_price),
            "bin_edges": bin_edges.tolist(),
            "bin_volumes": bin_volumes.tolist(),
            "min_price": float(min_price),
            "max_price": float(max_price)
        }
