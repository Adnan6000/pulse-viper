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
    def calculate_volume_profile(df: pd.DataFrame, lookback: int = 100, bins: int = 20) -> Dict[str, Any]:
        """
        Calculate the Volume Profile (Volume at Price histogram) over the last 'lookback' candles.
        Returns the bin edges, volumes, and Point of Control (POC) price level.
        """
        if len(df) == 0:
            return {
                "poc_price": 0.0,
                "bin_edges": [],
                "bin_volumes": [],
                "min_price": 0.0,
                "max_price": 0.0
            }

        sub_df = df.tail(lookback)
        min_price = sub_df['low'].min()
        max_price = sub_df['high'].max()
        
        if max_price == min_price:
            max_price += 0.01  # Avoid division by zero
            
        bin_edges = np.linspace(min_price, max_price, bins + 1)
        bin_volumes = np.zeros(bins)
        
        # Distribute volume proportionally to overlapping bins for accuracy
        for _, row in sub_df.iterrows():
            h = row['high']
            l = row['low']
            v = row['volume']
            
            if h > l:
                overlaps = np.maximum(0, np.minimum(h, bin_edges[1:]) - np.maximum(l, bin_edges[:-1]))
                total_overlap = overlaps.sum()
                if total_overlap > 0:
                    bin_volumes += v * (overlaps / total_overlap)
                else:
                    # Fallback to close price bin
                    bin_idx = np.clip(np.digitize(row['close'], bin_edges) - 1, 0, bins - 1)
                    bin_volumes[bin_idx] += v
            else:
                bin_idx = np.clip(np.digitize(l, bin_edges) - 1, 0, bins - 1)
                bin_volumes[bin_idx] += v
                
        poc_idx = np.argmax(bin_volumes)
        poc_price = (bin_edges[poc_idx] + bin_edges[poc_idx + 1]) / 2.0
        
        return {
            "poc_price": float(poc_price),
            "bin_edges": bin_edges.tolist(),
            "bin_volumes": bin_volumes.tolist(),
            "min_price": float(min_price),
            "max_price": float(max_price)
        }
