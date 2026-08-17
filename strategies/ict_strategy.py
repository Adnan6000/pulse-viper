# strategies/ict_strategy.py
import numpy as np
import pandas as pd
import logging
from datetime import datetime, timezone, time
from typing import Dict, Tuple, Optional

from utils.settings_manager import clamp_m1_trade_levels, settings_manager

class IctStrategy:
    logger = logging.getLogger("PulseViper.IctStrategy")

    @classmethod
    def evaluate_ict(
        cls,
        df_m1: Optional[pd.DataFrame] = None,
        df_m5: Optional[pd.DataFrame] = None,
        df_m15: Optional[pd.DataFrame] = None,
        df_h1: Optional[pd.DataFrame] = None,
        df_h4: Optional[pd.DataFrame] = None,
        current_price: float = 0.0,
        atr: float = 1.0,
        htf_bias: int = 0,
        volume_cache: Optional[Dict] = None,
        regime: str = "RANGE",
        sim_time: Optional[datetime] = None, # Added for simulation routing
    ) -> Tuple[Optional[str], float, float, Dict]:
        """
        ICT (Inner Circle Trader) Strategy:
          - Bias from Daily / H4 / H1.
          - Asian Range defined between 22:00 and 06:00 UTC.
          - London Killzone (07:00 - 09:00 UTC) or NY Killzone (12:00 - 14:00 UTC).
          - Setup: Sweep of Asian high/low during London/NY Killzone.
          - Trigger: Displacement on M5/M1 followed by pullback into OTE (62%-79%) or FVG.
        """
        try:
            if df_m15 is None or len(df_m15) < 30:
                return None, 0.0, 0.0, {}
            if df_m5 is None or len(df_m5) < 15:
                return None, 0.0, 0.0, {}
            if df_m1 is None or len(df_m1) < 15:
                return None, 0.0, 0.0, {}

            # Time Checks (UTC)
            if sim_time is not None:
                current_time_utc = sim_time.time() if not isinstance(sim_time, time) else sim_time
            else:
                now_utc = datetime.now(timezone.utc)
                current_time_utc = now_utc.time()

            # 1. Killzone Gate: London (07:00-09:00 UTC) or NY (12:00-14:00 UTC)
            in_london = time(7, 0) <= current_time_utc <= time(9, 0)
            in_ny = time(12, 0) <= current_time_utc <= time(14, 0)
            
            killzone_active = in_london or in_ny
            trading_mode = settings_manager.get("trading_mode", "scalping").lower()
            min_ai_conf = settings_manager.get("min_ai_confidence", 0.75)
            
            if not killzone_active:
                extended_hours = time(6, 0) <= current_time_utc <= time(20, 0)
                if not (trading_mode == "scalping" and extended_hours and min_ai_conf >= 0.75):
                    return None, 0.0, 0.0, {}

            # 2. Map Asian Range (22:00 to 06:00 UTC) using M15
            # Scan M15 candles from the current day or previous day to find the Asian high/low range
            asian_high = 0.0
            asian_low = float('inf')
            
            # Find the most recent Asian session boundaries
            # Asian session is from 22:00 of previous day to 06:00 of current day (or current day if we're past 22:00)
            # Let's filter df_m15 by time
            # We look at the last 100 candles on M15
            for idx, row in df_m15.iloc[-100:].iterrows():
                # Get the hour/minute in UTC
                row_time = idx.time() if hasattr(idx, 'time') else None
                if row_time is None:
                    continue
                # If row_time is between 22:00 and 06:00 UTC
                is_asian = row_time >= time(22, 0) or row_time <= time(6, 0)
                if is_asian:
                    asian_high = max(asian_high, float(row['high']))
                    asian_low = min(asian_low, float(row['low']))

            if asian_high == 0.0 or asian_low == float('inf'):
                # Cannot reliably determine Asian session range — skip rather than guess.
                # Using recent candles as a fallback produces false sweeps and pollutes signals.
                cls.logger.debug("ICT: Could not parse Asian session range from M15 timestamps — skipping")
                return None, 0.0, 0.0, {}

            # 3. Sweep check
            # Verify if any of the last 10 M15 candles swept the Asian High/Low
            swept_high = False
            swept_low = False
            recent_exec = df_m15.iloc[-11:-1]
            for _, r in recent_exec.iterrows():
                if float(r['high']) > asian_high and float(r['close']) < asian_high:
                    swept_high = True
                if float(r['low']) < asian_low and float(r['close']) > asian_low:
                    swept_low = True

            # 4. Displacement & OTE Retracement (M5 timeframe)
            recent_m5 = df_m5.iloc[-16:-1]
            swing_high = float(recent_m5['high'].max())
            swing_low = float(recent_m5['low'].min())
            swing_range = swing_high - swing_low
            
            # Ensure significant displacement leg (at least 1.5 * ATR)
            if swing_range < 1.5 * atr:
                return None, 0.0, 0.0, {}

            high_idx = recent_m5['high'].idxmax()
            low_idx = recent_m5['low'].idxmin()
            is_bullish_displacement = high_idx > low_idx

            # OTE zone (62% - 79% retracement of displacement leg)
            # BUY: Swept Asian Low (or general low), bullish displacement, price pull back to OTE zone
            if is_bullish_displacement and (swept_low or htf_bias >= 0):
                fib_62 = swing_high - 0.62 * swing_range
                fib_79 = swing_high - 0.79 * swing_range
                if fib_79 <= current_price <= fib_62:
                    # Look for fresh FVG on M1 in last 5 candles
                    has_fvg = False
                    for i in range(-5, 0):
                        if i < -len(df_m1): continue
                        c_prev2 = df_m1.iloc[i-2]
                        c_curr = df_m1.iloc[i]
                        if float(c_curr['low']) > float(c_prev2['high']):
                            has_fvg = True
                            break
                    
                    if has_fvg or regime == "RANGE":
                        sl = swing_low - 0.1 * atr
                        tp = swing_high
                        sl, tp = clamp_m1_trade_levels("BUY", current_price, sl, tp)
                        meta = {
                            "strategy": "ICT",
                            "trigger": "ICT_OTE_BUY",
                            "ote_zone": f"{fib_79:.2f} - {fib_62:.2f}",
                            "asian_low": asian_low,
                            "swept_low": swept_low
                        }
                        return "BUY", sl, tp, meta

            # SELL: Swept Asian High (or general high), bearish displacement, price pull back to OTE zone
            if not is_bullish_displacement and (swept_high or htf_bias <= 0):
                fib_62 = swing_low + 0.62 * swing_range
                fib_79 = swing_low + 0.79 * swing_range
                if fib_62 <= current_price <= fib_79:
                    # Look for bearish FVG on M1
                    has_fvg = False
                    for i in range(-5, 0):
                        if i < -len(df_m1): continue
                        c_prev2 = df_m1.iloc[i-2]
                        c_curr = df_m1.iloc[i]
                        if float(c_curr['high']) < float(c_prev2['low']):
                            has_fvg = True
                            break
                    
                    if has_fvg or regime == "RANGE":
                        sl = swing_high + 0.1 * atr
                        tp = swing_low
                        sl, tp = clamp_m1_trade_levels("SELL", current_price, sl, tp)
                        meta = {
                            "strategy": "ICT",
                            "trigger": "ICT_OTE_SELL",
                            "ote_zone": f"{fib_62:.2f} - {fib_79:.2f}",
                            "asian_high": asian_high,
                            "swept_high": swept_high
                        }
                        return "SELL", sl, tp, meta

            return None, 0.0, 0.0, {}
        except Exception as e:
            cls.logger.error(f"Error in evaluate_ict: {e}")
            return None, 0.0, 0.0, {}
