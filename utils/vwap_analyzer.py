# utils/vwap_analyzer.py
import pandas as pd
import numpy as np
import logging

class VwapAnalyzer:
    logger = logging.getLogger("PulseViper.VwapAnalyzer")

    @classmethod
    def calculate_session_vwap(cls, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate Session-based VWAP and its 1st, 2nd, and 3rd Standard Deviation Bands.
        Formula:
          Typical Price = (High + Low + Close) / 3
          VWAP = cumsum(Typical Price * Volume) / cumsum(Volume)
          StdDev = sqrt( cumsum(Volume * (Typical Price - VWAP)^2) / cumsum(Volume) )
        Cumulative sums reset at the start of each trading day (session).
        """
        try:
            if df is None or len(df) == 0:
                return df
                
            df = df.copy()
            
            # 1. Calculate Typical Price
            typical_price = (df['high'] + df['low'] + df['close']) / 3.0
            
            # 2. Extract Volume
            volume = df['tick_volume'] if 'tick_volume' in df.columns else (df['volume'] if 'volume' in df.columns else pd.Series(1.0, index=df.index))
            
            # 3. Detect Session Boundaries (group by date)
            if isinstance(df.index, pd.DatetimeIndex):
                dates = df.index.date
            else:
                # Fallback if index is not datetime (e.g. numeric)
                dates = np.zeros(len(df))
                
            pv = typical_price * volume
            
            # Group by dates to perform session cumulative operations
            grouped = pv.groupby(dates)
            cumsum_pv = grouped.cumsum()
            
            grouped_vol = volume.groupby(dates)
            cumsum_vol = grouped_vol.cumsum()
            
            # 4. Calculate VWAP
            vwap = cumsum_pv / (cumsum_vol + 1e-9)
            df['vwap'] = vwap
            
            # 5. Calculate Standard Deviation
            squared_diff_pv = volume * ((typical_price - vwap) ** 2)
            cumsum_var = squared_diff_pv.groupby(dates).cumsum()
            std_dev = np.sqrt(cumsum_var / (cumsum_vol + 1e-9))
            
            # Save bands to DataFrame
            df['vwap_std'] = std_dev
            df['vwap_upper_1'] = vwap + 1.0 * std_dev
            df['vwap_lower_1'] = vwap - 1.0 * std_dev
            df['vwap_upper_2'] = vwap + 2.0 * std_dev
            df['vwap_lower_2'] = vwap - 2.0 * std_dev
            df['vwap_upper_3'] = vwap + 3.0 * std_dev
            df['vwap_lower_3'] = vwap - 3.0 * std_dev
            
            return df
            
        except Exception as e:
            cls.logger.error(f"Error calculating Session VWAP: {e}")
            # Ensure fallback columns so strategy doesn't crash
            if df is not None:
                df['vwap'] = df['close']
                df['vwap_std'] = 0.0
                df['vwap_upper_1'] = df['close']
                df['vwap_lower_1'] = df['close']
                df['vwap_upper_2'] = df['close']
                df['vwap_lower_2'] = df['close']
                df['vwap_upper_3'] = df['close']
                df['vwap_lower_3'] = df['close']
            return df
